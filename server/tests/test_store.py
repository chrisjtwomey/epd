"""ReadingsStore: documents kept by device and ts, read back by time."""
import threading

import pytest

from epd_server.store import ReadingsStore


@pytest.fixture
def store(tmp_path):
    s = ReadingsStore(tmp_path / "readings.db")
    yield s
    s.close()


def test_add_then_read_back_the_newest_and_a_range(store):
    for ts in (100, 300, 200):
        assert store.add({"ts": ts, "device": "a", "co2_ppm": ts})
    assert store.latest() == {"ts": 300, "device": "a", "co2_ppm": 300}
    assert [d["ts"] for d in store.between(150)] == [200, 300]
    assert [d["ts"] for d in store.between(100, 200)] == [100, 200]
    assert store.count() == 3


def test_a_document_that_arrives_late_lands_in_ts_order(store):
    store.add({"ts": 500, "device": "a"})
    store.add({"ts": 100, "device": "a"})   # held by the board while the server was down
    assert [d["ts"] for d in store.between(0)] == [100, 500]


def test_a_second_copy_of_the_same_device_and_ts_is_ignored(store):
    assert store.add({"ts": 1, "device": "a", "v": 1})
    assert not store.add({"ts": 1, "device": "a", "v": 2})
    assert store.latest() == {"ts": 1, "device": "a", "v": 1}
    assert store.add({"ts": 1, "device": "b", "v": 3})   # another board, the same second


def test_device_limits_every_read(store):
    store.add({"ts": 1, "device": "a"})
    store.add({"ts": 2, "device": "b"})
    assert store.latest("a")["ts"] == 1
    assert [d["device"] for d in store.between(0, device="b")] == ["b"]
    assert store.count("a") == 1 and store.count() == 2


def test_an_empty_store(store):
    assert store.latest() is None
    assert store.between(0) == []
    assert store.count() == 0


@pytest.mark.parametrize("doc", [{}, {"ts": "1"}, {"ts": True}, {"ts": 1.5},
                                 {"ts": 1, "device": 7}])
def test_add_rejects_a_missing_or_wrong_ts_or_device(store, doc):
    with pytest.raises(ValueError):
        store.add(doc)
    assert store.count() == 0


def test_a_document_without_a_device_is_kept_under_an_empty_one(store):
    assert store.add({"ts": 1})
    assert store.latest("") == {"ts": 1}


def test_prune_drops_what_is_older_than_the_cut(store):
    for ts in (1, 2, 3):
        store.add({"ts": ts})
    assert store.prune(3) == 2
    assert [d["ts"] for d in store.between(0)] == [3]


def test_the_file_outlives_the_object(tmp_path):
    path = tmp_path / "readings.db"
    first = ReadingsStore(path)
    first.add({"ts": 7, "device": "a"})
    first.close()
    again = ReadingsStore(path)
    assert again.latest() == {"ts": 7, "device": "a"}
    again.close()


def test_adds_from_several_threads_all_land(store):
    def post(base):
        for i in range(50):
            store.add({"ts": base + i, "device": "a"})
    threads = [threading.Thread(target=post, args=(n * 1000,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert store.count() == 200


def test_a_memory_store_needs_no_file():
    s = ReadingsStore(":memory:")
    s.add({"ts": 1})
    assert s.count() == 1
    s.close()
