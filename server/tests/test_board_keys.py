"""Board keys: pairing, the signatures both ways, and DisplayServer's use of them."""
import base64
import hashlib
import hmac
import json
import os
import re
import stat

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from epd_server import board_keys as bk
from epd_server.board_keys import BoardKeys
from epd_server.config import FirmwareSettings

from .test_app import BIN, PNG, make

DOCK = "my-dock"
BODY = b'{"device": "my-dock", "ts": 1}'
T0 = 1_760_000_000.0


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def keys(tmp_path, clock):
    return BoardKeys(str(tmp_path / "board-keys.json"), [DOCK, "my-display"], now=clock)


def hkdf_by_hand(shared: bytes, info: bytes) -> bytes:
    """HKDF-SHA256 with no salt and one block, as a board computes it with HMAC alone."""
    prk = hmac.new(b"\x00" * 32, shared, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


def board_half() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    ours = ec.generate_private_key(ec.SECP256R1())
    return ours, ours.public_key().public_bytes(serialization.Encoding.X962,
                                                serialization.PublicFormat.UncompressedPoint)


def board_key(ours: ec.EllipticCurvePrivateKey, server_half: bytes, device: str = DOCK) -> bytes:
    theirs = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_half)
    return hkdf_by_hand(ours.exchange(ec.ECDH(), theirs), b"epd board key " + device.encode())


def paired(keys: BoardKeys, device: str = DOCK, approve: bool = True) -> bytes:
    """A board's key, made as the board makes it, and approved."""
    ours, half = board_half()
    key = board_key(ours, keys.pair(device, half), device)
    if approve:
        keys.approve(device)
    return key


def signed(key: bytes, body: bytes = BODY, path: str = "/sensor-readings", query: str = "",
           created: float = T0) -> dict[str, str]:
    return bk.request_signature(key, "POST", path, query, bk.content_digest(body), int(created))


def check(keys, headers, body=BODY, path="/sensor-readings", query=""):
    return keys.check_request("POST", path, query, headers, body)


# ── The standards' own examples ─────────────────────────────────────

RFC_SECRET = base64.b64decode("uzvJfB4u3N0Jy4T7NZ75MDVcr8zSTInedJtkgcu46YW4XByzNJjxBdtjUkdJPBt"
                              "bmHhIDi6pcl8jsasjlTMtDQ==")


def test_the_rfc_9421_hmac_example_signs_as_the_rfc_says():
    """RFC 9421, B.2.5: the signature base and the signature over it."""
    params = bk.signature_params(('"date"', '"@authority"', '"content-type"'), 1618884473,
                                 "test-shared-secret")
    base = bk.signature_base([('"date"', "Tue, 20 Apr 2021 02:07:55 GMT"),
                              ('"@authority"', "example.com"),
                              ('"content-type"', "application/json")], params)
    assert base == ('"date": Tue, 20 Apr 2021 02:07:55 GMT\n'
                    '"@authority": example.com\n'
                    '"content-type": application/json\n'
                    '"@signature-params": ("date" "@authority" "content-type")'
                    ';created=1618884473;keyid="test-shared-secret"')
    assert bk.hmac_sha256(RFC_SECRET, base) == "pxcQw6G3AjtMBQjwo8XzkZf/bws5LelbaMk5rGIGtE8="


@pytest.mark.parametrize("body, field", [
    (b'{"hello": "world"}\n', "sha-256=:RK/0qy18MlBSVnWgjwz6lZEWjP/lF5HF9bvEF8FabDg=:"),
    (b"", "sha-256=:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=:"),
])
def test_content_digest_is_rfc_9530s(body, field):
    """RFC 9530, B.1 and B.2."""
    assert bk.content_digest(body) == field


def test_a_request_with_no_query_signs_a_lone_question_mark():
    assert bk.query_value("") == "?"
    assert bk.query_value("device=my-dock") == "?device=my-dock"


# ── Pairing ─────────────────────────────────────────────────────────

def test_a_board_and_the_server_derive_the_same_key(keys):
    ours, half = board_half()
    key = board_key(ours, keys.pair(DOCK, half))
    assert keys.board(DOCK).pending.key == key
    assert keys.board(DOCK).approved is None


def test_a_pending_key_waits_for_approval_and_then_signs(keys):
    key = paired(keys, approve=False)
    assert check(keys, signed(key)).state == bk.PENDING
    keys.approve(DOCK)
    verdict = check(keys, signed(key, created=T0 + 1))
    assert (verdict.state, verdict.device) == ("", DOCK)


def test_a_new_request_leaves_the_approved_key_working_until_it_is_approved(keys):
    old = paired(keys)
    new = paired(keys, approve=False)
    assert check(keys, signed(old)).state == ""
    assert check(keys, signed(new)).state == bk.PENDING
    keys.approve(DOCK)
    assert check(keys, signed(old, created=T0 + 1)).state == bk.PAIR
    assert check(keys, signed(new, created=T0 + 1)).state == ""


def test_reject_drops_only_the_pending_key(keys):
    old = paired(keys)
    new = paired(keys, approve=False)
    keys.reject(DOCK)
    assert check(keys, signed(new)).state == bk.PAIR
    assert check(keys, signed(old)).state == ""


def test_forget_makes_the_board_pair_again(keys):
    key = paired(keys)
    keys.forget(DOCK)
    assert check(keys, signed(key)).state == bk.PAIR


@pytest.mark.parametrize("device, half", [("nobody", None), (DOCK, b"\x04" + b"\x01" * 64)])
def test_pairing_needs_a_known_board_and_a_point_on_the_curve(keys, device, half):
    with pytest.raises(ValueError):
        keys.pair(device, half if half is not None else board_half()[1])


def test_the_keys_survive_a_restart_in_a_file_only_the_server_reads(keys, tmp_path):
    key = paired(keys)
    again = BoardKeys(keys.path, [DOCK, "my-display"], now=keys.now)
    assert again.board(DOCK).approved.key == key
    assert stat.S_IMODE(os.stat(keys.path).st_mode) == 0o600


def test_a_board_no_longer_named_is_dropped_from_the_file(keys):
    paired(keys)
    again = BoardKeys(keys.path, ["my-display"])
    assert again.board(DOCK) is None and [b.device for b in again.boards()] == ["my-display"]


# ── The server's check of a board's post ────────────────────────────

def test_a_post_without_a_signature_is_told_to_pair(keys):
    verdict = check(keys, {})
    assert verdict.state == bk.PAIR and "Pair" in verdict.words


def test_a_key_the_server_has_not_got_is_told_to_pair(keys):
    assert check(keys, signed(b"\x01" * 32)).state == bk.PAIR


@pytest.mark.parametrize("skew", [-bk.WINDOW_S - 1, bk.WINDOW_S + 1])
def test_a_signature_outside_the_window_is_told_to_take_the_servers_clock(keys, skew):
    key = paired(keys)
    assert check(keys, signed(key, created=T0 + skew)).state == bk.CLOCK


@pytest.mark.parametrize("skew", [-bk.WINDOW_S, bk.WINDOW_S])
def test_a_signature_at_the_edge_of_the_window_is_taken(keys, skew):
    key = paired(keys)
    assert check(keys, signed(key, created=T0 + skew)).state == ""


def test_a_signature_is_taken_once(keys):
    key = paired(keys)
    headers = signed(key)
    assert check(keys, headers).state == ""
    assert check(keys, headers).state == bk.REFUSED


def test_a_signature_is_forgotten_once_it_is_out_of_the_window(keys, clock):
    key = paired(keys)
    assert check(keys, signed(key)).state == ""
    clock.t += bk.WINDOW_S + 1
    assert check(keys, signed(key, created=clock.t)).state == ""
    assert len(keys._seen) == 1


@pytest.mark.parametrize("change", [
    lambda h, b: (h, b + b" "),                                              # another body
    lambda h, b: ({**h, "Content-Digest": bk.content_digest(b + b" ")}, b + b" "),
    lambda h, b: ({**h, "Signature": "sig1=:" + "A" * 43 + "=:"}, b),          # another signature
    lambda h, b: ({**h, "Signature": "sig1=:x:"}, b),                         # not a signature
])
def test_a_post_changed_after_its_signing_is_refused(keys, change):
    key = paired(keys)
    headers, body = change(signed(key), BODY)
    assert check(keys, headers, body).state == bk.REFUSED


@pytest.mark.parametrize("path, query", [("/calibration", ""), ("/sensor-readings", "a=1")])
def test_a_signature_covers_the_path_and_the_query(keys, path, query):
    key = paired(keys)
    assert check(keys, signed(key), path=path, query=query).state == bk.REFUSED


def test_signature_input_must_cover_exactly_these_components(keys):
    key = paired(keys)
    headers = signed(key)
    headers["Signature-Input"] = headers["Signature-Input"].replace(' "@query"', "")
    assert check(keys, headers).state == bk.PAIR


# ── The server's signature on its answers ───────────────────────────

def answer_good(key: bytes, headers, body: bytes, status: int, method: str, path: str,
                query: str) -> bool:
    """Whether an answer's signature holds, as a board checks it."""
    found = re.fullmatch(r'sig1=\("@status" "content-digest" "@method";req "@path";req '
                         r'"@query";req\);created=(\d+);keyid="([0-9a-f]{16})"',
                         headers["Signature-Input"])
    if not found or found.group(2) != bk.key_id(key):
        return False
    if headers["Content-Digest"] != bk.content_digest(body):
        return False
    expected = bk.answer_signature(key, status, headers["Content-Digest"], method, path, query,
                                   int(found.group(1)))
    return hmac.compare_digest(expected["Signature"], headers["Signature"])


def test_an_answer_is_signed_with_the_boards_approved_key(keys):
    key = paired(keys)
    body = b'{"led": 1}'
    headers = keys.sign_answer(DOCK, 200, bk.content_digest(body), "GET", "/board-settings",
                               "device=my-dock")
    assert answer_good(key, headers, body, 200, "GET", "/board-settings", "device=my-dock")
    assert not answer_good(key, headers, body, 200, "GET", "/calibration", "device=my-dock")


@pytest.mark.parametrize("approve", [False, None])
def test_a_board_without_an_approved_key_gets_no_signature(keys, approve):
    if approve is not None:
        paired(keys, approve=approve)
    assert keys.sign_answer(DOCK, 200, bk.content_digest(b""), "GET", "/x", "") == {}


# ── In DisplayServer ────────────────────────────────────────────────

def keyed_server(tmp_path, keys, require=True, **kw):
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    taken = []
    server = make(tmp_path, ingest={"sensor-readings": taken.extend},
                  queries={"board-settings": lambda args: {"led": 1},
                           "status": lambda args: {"ok": True}},
                  header_prefix="Acme", board_keys=keys, require_signatures=require,
                  signed_queries=("board-settings",), **kw)
    server.app.config["TESTING"] = True
    return server.app.test_client(), taken


AS_DOCK = {"Acme-Device": DOCK, "Content-Type": "application/json"}


def test_an_unsigned_post_is_refused_and_told_to_pair(tmp_path, keys):
    client, taken = keyed_server(tmp_path, keys)
    rsp = client.post("/sensor-readings", data=BODY, headers=AS_DOCK)
    assert rsp.status_code == 401 and rsp.headers["Acme-Key"] == bk.PAIR
    assert "Pair" in rsp.get_json()["problem"] and taken == []


def test_a_board_pairs_waits_for_approval_and_then_posts(tmp_path, keys, clock):
    client, taken = keyed_server(tmp_path, keys)
    ours, half = board_half()
    rsp = client.post("/pair", json={"device": DOCK, "key": base64.b64encode(half).decode()})
    key = board_key(ours, base64.b64decode(rsp.get_json()["key"]))
    rsp = client.post("/sensor-readings", data=BODY, headers={**AS_DOCK, **signed(key)})
    assert rsp.status_code == 401 and rsp.headers["Acme-Key"] == bk.PENDING
    keys.approve(DOCK)
    rsp = client.post("/sensor-readings", data=BODY, headers={**AS_DOCK, **signed(key, created=T0 + 1)})
    assert rsp.status_code == 204 and taken == [json.loads(BODY)]


@pytest.mark.parametrize("body", [{"device": "nobody", "key": "BAAA"}, {"device": DOCK, "key": "%%"},
                                  ["not", "an", "object"]])
def test_a_pairing_request_that_cannot_work_is_a_400(tmp_path, keys, body):
    client, _ = keyed_server(tmp_path, keys)
    assert client.post("/pair", json=body).status_code == 400


def test_a_post_signed_by_one_board_cannot_claim_to_be_another(tmp_path, keys):
    client, taken = keyed_server(tmp_path, keys)
    key = paired(keys)
    rsp = client.post("/sensor-readings", data=BODY,
                      headers={**AS_DOCK, "Acme-Device": "my-display", **signed(key)})
    assert rsp.status_code == 401 and rsp.headers["Acme-Key"] == bk.REFUSED and taken == []


def test_a_wrong_clock_is_told_to_take_the_servers_time(tmp_path, keys):
    client, _ = keyed_server(tmp_path, keys)
    key = paired(keys)
    rsp = client.post("/sensor-readings", data=BODY,
                      headers={**AS_DOCK, **signed(key, created=T0 - 3600)})
    assert rsp.headers["Acme-Key"] == bk.CLOCK and "Acme-Server-Epoch-Seconds" in rsp.headers


def test_a_named_query_is_signed_and_another_is_not(tmp_path, keys):
    client, _ = keyed_server(tmp_path, keys)
    key = paired(keys)
    rsp = client.get("/board-settings?device=my-dock", headers={"Acme-Device": DOCK})
    assert answer_good(key, rsp.headers, rsp.data, 200, "GET", "/board-settings", "device=my-dock")
    rsp = client.get("/status", headers={"Acme-Device": DOCK})
    assert "Signature" not in rsp.headers


def test_the_image_is_signed_over_its_digest(tmp_path, keys):
    fw = tmp_path / "fw"
    fw.mkdir()
    (fw / "v1.6.0.bin").write_bytes(BIN)
    firmware = FirmwareSettings(enabled=True, dir=str(fw), product=DOCK, offer_dev_builds=False)
    client, _ = keyed_server(tmp_path, keys, firmware=firmware)
    key = paired(keys)
    rsp = client.get("/firmware.bin", headers={"Acme-Device": DOCK})
    assert rsp.headers["Content-Digest"] == bk.content_digest(BIN)
    assert answer_good(key, rsp.headers, rsp.data, 200, "GET", "/firmware.bin", "")


def test_without_required_signatures_posts_are_taken_and_no_board_pairs(tmp_path, keys):
    client, taken = keyed_server(tmp_path, keys, require=False)
    key = paired(keys)
    assert client.post("/sensor-readings", data=BODY, headers=AS_DOCK).status_code == 204
    assert client.post("/pair", json={"device": DOCK, "key": "x"}).status_code == 404
    rsp = client.get("/board-settings", headers={"Acme-Device": DOCK})
    assert answer_good(key, rsp.headers, rsp.data, 200, "GET", "/board-settings", "")


@pytest.mark.parametrize("kw, words", [
    ({"require_signatures": True}, "require_signatures needs board_keys"),
    ({"signed_queries": ("nothing",), "queries": {}}, r"signed_queries \['nothing'\]"),
    ({"queries": {"pair": dict}}, "a route named pair"),
])
def test_signatures_need_keys_and_name_real_queries(tmp_path, kw, words):
    with pytest.raises(ValueError, match=words):
        make(tmp_path, **({"board_keys": BoardKeys(str(tmp_path / "k.json"), [DOCK])}
                          if "require_signatures" not in kw else {}), **kw)


# ── The vectors firmware/test/test_board_key checks too ─────────────

VECTOR_KEY = bytes(range(32))


def test_the_vectors_the_board_tests_too():
    """The same numbers the board's host test checks, so both ends sign alike."""
    assert bk.key_id(VECTOR_KEY) == "630dcd2966c43366"
    assert bk.derive_key(bytes(range(32)), "my-dock").hex() == (
        "e47ed665f16bc6dc1675534103c15039bd8588690c021f2eea011e50b3e7c907")
    assert bk.content_digest(BODY) == "sha-256=:2NQ1bwkVtGU1JEHr9Gie5wOYMIWti2B1/0NqC+N2pU0=:"
    request = bk.request_signature(VECTOR_KEY, "POST", "/sensor-readings", "",
                                   bk.content_digest(BODY), 1760000000)
    assert request["Signature"] == "sig1=:s51U7fDl4udYdVlsgV+YWz0DHLYwIrKMtnt7I4a18+M=:"
    answer = bk.answer_signature(VECTOR_KEY, 200, bk.content_digest(b'{"led": 1}'), "GET",
                                 "/board-settings", "device=my-dock", 1760000000)
    assert answer["Signature"] == "sig1=:ep4RQgi2eOuyIYpYNL+rAmgBORfQAVjiTxXGEe3RMj4=:"


def test_the_refusal_vector_the_board_tests_too():
    refusal = bk.answer_signature(VECTOR_KEY, 401, bk.content_digest(b'{"problem": "x"}'), "POST",
                                  "/sensor-readings", "", 1760000000, bk.content_digest(BODY))
    assert refusal["Signature"] == "sig1=:Qwl6BPdt0iZvKLGamU/ATpuwOJKwzi/vFxjVkAzTIXs=:"


# ── Keys out of use, and a pair the board can trust ─────────────────

def refusal_good(key: bytes, headers, body: bytes, request_body: bytes = BODY,
                 path: str = "/sensor-readings") -> bool:
    """Whether a refusal's signature holds for a post of ``request_body``, as a board checks it."""
    found = re.fullmatch(r'sig1=\("@status" "content-digest" "@method";req "@path";req '
                         r'"@query";req "content-digest";req\);created=(\d+);keyid="([0-9a-f]{16})"',
                         headers.get("Signature-Input", ""))
    if not found or found.group(2) != bk.key_id(key):
        return False
    expected = bk.answer_signature(key, 401, bk.content_digest(body), "POST", path, "",
                                   int(found.group(1)), bk.content_digest(request_body))
    return hmac.compare_digest(expected["Signature"], headers.get("Signature", ""))


@pytest.mark.parametrize("retire", ["forget", "reject", "approve"])
def test_a_post_under_a_key_out_of_use_is_told_to_pair_under_that_key(keys, retire):
    old = paired(keys, approve=retire != "reject")
    if retire == "approve":
        paired(keys, approve=False)
    getattr(keys, retire)(DOCK)
    verdict = check(keys, signed(old))
    assert (verdict.state, verdict.key) == (bk.PAIR, old)


def test_a_post_that_only_names_a_key_out_of_use_is_refused_without_its_key(keys):
    old = paired(keys)
    keys.forget(DOCK)
    headers = signed(b"\x02" * 32)
    headers["Signature-Input"] = headers["Signature-Input"].replace(bk.key_id(b"\x02" * 32),
                                                                    bk.key_id(old))
    verdict = check(keys, headers)
    assert (verdict.state, verdict.key) == (bk.REFUSED, None)


def test_a_post_under_a_pending_key_is_refused_under_that_key(keys):
    key = paired(keys, approve=False)
    assert check(keys, signed(key)).key == key


def test_the_keys_out_of_use_are_kept_the_newest_few(keys):
    first = paired(keys)
    for _ in range(bk.RETIRED_KEPT + 1):
        paired(keys)
    retired = keys.board(DOCK).retired
    assert len(retired) == bk.RETIRED_KEPT and first not in [k.key for k in retired]
    again = BoardKeys(keys.path, [DOCK])
    assert again.board(DOCK).retired == retired


def test_an_answer_is_signed_with_the_key_the_board_names(keys):
    approved = paired(keys)
    pending = paired(keys, approve=False)
    body = b'{"led": 1}'
    for key in (approved, pending):
        headers = keys.sign_answer(DOCK, 200, bk.content_digest(body), "GET", "/board-settings",
                                   "", bk.key_id(key))
        assert answer_good(key, headers, body, 200, "GET", "/board-settings", "")
    assert keys.sign_answer(DOCK, 200, bk.content_digest(body), "GET", "/x", "",
                            bk.key_id(b"\x03" * 32)) == {}


def test_a_refusal_under_a_key_out_of_use_is_signed_for_that_post_alone(tmp_path, keys):
    client, _ = keyed_server(tmp_path, keys)
    old = paired(keys)
    keys.forget(DOCK)
    rsp = client.post("/sensor-readings", data=BODY, headers={**AS_DOCK, **signed(old)})
    assert rsp.status_code == 401 and rsp.headers["Acme-Key"] == bk.PAIR
    assert refusal_good(old, rsp.headers, rsp.data)
    assert not refusal_good(old, rsp.headers, rsp.data, request_body=BODY + b" ")


def test_a_refusal_of_a_post_not_shown_to_be_signed_carries_no_signature(tmp_path, keys):
    client, _ = keyed_server(tmp_path, keys)
    rsp = client.post("/sensor-readings", data=BODY, headers=AS_DOCK)
    assert rsp.headers["Acme-Key"] == bk.PAIR and "Signature" not in rsp.headers


def test_a_board_waiting_for_approval_still_gets_signed_answers(tmp_path, keys):
    client, _ = keyed_server(tmp_path, keys)
    key = paired(keys, approve=False)
    rsp = client.get("/board-settings", headers={"Acme-Device": DOCK, "Acme-Key-Id": bk.key_id(key)})
    assert answer_good(key, rsp.headers, rsp.data, 200, "GET", "/board-settings", "")
