// Native tests for the board key's signatures: first the stand-in hashes
// against their standards, then RFC 9421's own example, then the vectors
// server/tests/test_board_keys.py checks, so both ends sign alike.

#include <unity.h>

#include <stdio.h>
#include <string.h>

#include <mbedtls/md.h>

#include "board_key.h"

static const char BODY[] = "{\"device\": \"my-dock\", \"ts\": 1}";
static const uint32_t CREATED = 1760000000;

static void hex(const uint8_t* bytes, size_t len, char* out) {
    for (size_t i = 0; i < len; ++i) snprintf(out + 2 * i, 3, "%02x", bytes[i]);
}

static BoardKey vectorKey() {
    uint8_t key[BOARD_KEY_LEN];
    for (int i = 0; i < BOARD_KEY_LEN; ++i) key[i] = (uint8_t)i;
    return boardKeyFrom(key);
}

static void sha256(const char* text, uint8_t out[32]) {
    mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), (const unsigned char*)text,
               strlen(text), out);
}

// ── The stand-ins, against their standards ──────────────────────────

void test_the_stand_in_sha256_matches_fips_180_4(void) {
    uint8_t out[32];
    char text[65];
    sha256("abc", out);
    hex(out, 32, text);
    TEST_ASSERT_EQUAL_STRING("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                             text);
    sha256("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", out);
    hex(out, 32, text);
    TEST_ASSERT_EQUAL_STRING("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
                             text);
}

void test_the_stand_in_hmac_matches_rfc_4231(void) {
    const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    uint8_t key[131], out[32];
    char text[65];
    memset(key, 0x0b, 20);
    mbedtls_md_hmac(info, key, 20, (const unsigned char*)"Hi There", 8, out);
    hex(out, 32, text);
    TEST_ASSERT_EQUAL_STRING("b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",
                             text);
    const char* data = "Test Using Larger Than Block-Size Key - Hash Key First";
    memset(key, 0xaa, sizeof(key));
    mbedtls_md_hmac(info, key, sizeof(key), (const unsigned char*)data, strlen(data), out);
    hex(out, 32, text);
    TEST_ASSERT_EQUAL_STRING("60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54",
                             text);
}

// ── The standards' own examples ─────────────────────────────────────

void test_the_rfc_9421_hmac_example_signs_as_the_rfc_says(void) {
    // RFC 9421, B.1.5's test-shared-secret, and B.2.5.
    static const uint8_t secret[64] = {
        0xbb, 0x3b, 0xc9, 0x7c, 0x1e, 0x2e, 0xdc, 0xdd, 0x09, 0xcb, 0x84, 0xfb, 0x35, 0x9e, 0xf9,
        0x30, 0x35, 0x5c, 0xaf, 0xcc, 0xd2, 0x4c, 0x89, 0xde, 0x74, 0x9b, 0x64, 0x81, 0xcb, 0xb8,
        0xe9, 0x85, 0xb8, 0x5c, 0x1c, 0xb3, 0x34, 0x98, 0xf1, 0x05, 0xdb, 0x63, 0x52, 0x47, 0x49,
        0x3c, 0x1b, 0x5b, 0x98, 0x78, 0x48, 0x0e, 0x2e, 0xa9, 0x72, 0x5f, 0x23, 0xb1, 0xab, 0x23,
        0x95, 0x33, 0x2d, 0x0d};
    const char* names[] = {"\"date\"", "\"@authority\"", "\"content-type\""};
    const char* values[] = {"Tue, 20 Apr 2021 02:07:55 GMT", "example.com", "application/json"};
    char base[512], mac[48];
    TEST_ASSERT_TRUE(signatureBase(names, values, 3,
                                   "(\"date\" \"@authority\" \"content-type\")"
                                   ";created=1618884473;keyid=\"test-shared-secret\"",
                                   base, sizeof(base)) > 0);
    TEST_ASSERT_EQUAL_STRING(
        "\"date\": Tue, 20 Apr 2021 02:07:55 GMT\n"
        "\"@authority\": example.com\n"
        "\"content-type\": application/json\n"
        "\"@signature-params\": (\"date\" \"@authority\" \"content-type\")"
        ";created=1618884473;keyid=\"test-shared-secret\"",
        base);
    hmacBase64(secret, sizeof(secret), base, mac);
    TEST_ASSERT_EQUAL_STRING("pxcQw6G3AjtMBQjwo8XzkZf/bws5LelbaMk5rGIGtE8=", mac);
}

void test_content_digest_is_rfc_9530s(void) {
    // RFC 9530, B.1 and B.2.
    char field[CONTENT_DIGEST_SIZE];
    contentDigestOf((const uint8_t*)"{\"hello\": \"world\"}\n", 19, field);
    TEST_ASSERT_EQUAL_STRING("sha-256=:RK/0qy18MlBSVnWgjwz6lZEWjP/lF5HF9bvEF8FabDg=:", field);
    contentDigestOf((const uint8_t*)"", 0, field);
    TEST_ASSERT_EQUAL_STRING("sha-256=:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=:", field);
}

// ── The server's vectors ────────────────────────────────────────────

void test_the_key_id_and_the_derived_key_are_the_servers(void) {
    TEST_ASSERT_EQUAL_STRING("630dcd2966c43366", vectorKey().id);
    uint8_t shared[32], key[BOARD_KEY_LEN];
    char text[65];
    for (int i = 0; i < 32; ++i) shared[i] = (uint8_t)i;
    deriveBoardKey(shared, sizeof(shared), "my-dock", key);
    hex(key, sizeof(key), text);
    TEST_ASSERT_EQUAL_STRING("e47ed665f16bc6dc1675534103c15039bd8588690c021f2eea011e50b3e7c907",
                             text);
}

void test_a_post_is_signed_as_the_server_checks_it(void) {
    SignedRequest out;
    TEST_ASSERT_TRUE(signRequest(vectorKey(), "POST", "http://192.168.1.20:8080/sensor-readings",
                                 (const uint8_t*)BODY, strlen(BODY), CREATED, &out));
    TEST_ASSERT_EQUAL_STRING("sha-256=:2NQ1bwkVtGU1JEHr9Gie5wOYMIWti2B1/0NqC+N2pU0=:",
                             out.contentDigest);
    TEST_ASSERT_EQUAL_STRING("sig1=(\"@method\" \"@path\" \"@query\" \"content-digest\")"
                             ";created=1760000000;keyid=\"630dcd2966c43366\"",
                             out.signatureInput);
    TEST_ASSERT_EQUAL_STRING("sig1=:s51U7fDl4udYdVlsgV+YWz0DHLYwIrKMtnt7I4a18+M=:", out.signature);
}

// ── The board's check of an answer ──────────────────────────────────

static const char ANSWER_URL[] = "http://192.168.1.20:8080/board-settings?device=my-dock";
static const char ANSWER_INPUT[] =
    "sig1=(\"@status\" \"content-digest\" \"@method\";req \"@path\";req \"@query\";req)"
    ";created=1760000000;keyid=\"630dcd2966c43366\"";
static const char ANSWER_DIGEST[] = "sha-256=:ljoQw9lxGK38HgIQvkE1LzzMtN7u8NH2gyZY+C/rHQ8=:";
static const char ANSWER_SIGNATURE[] = "sig1=:ep4RQgi2eOuyIYpYNL+rAmgBORfQAVjiTxXGEe3RMj4=:";

static bool answer(const char* url, const char* body, const char* input, const char* signature,
                   uint32_t now, int status = 200) {
    uint8_t sha[32];
    char why[96] = "";
    sha256(body, sha);
    return answerHolds(vectorKey(), status, sha, "GET", url, ANSWER_DIGEST, input, signature, now,
                       why, sizeof(why));
}

void test_an_answer_signed_by_the_server_holds(void) {
    TEST_ASSERT_TRUE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE, CREATED));
    TEST_ASSERT_TRUE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE,
                            CREATED + SIGNATURE_WINDOW_S));
}

void test_an_answer_changed_on_the_way_does_not_hold(void) {
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 2}", ANSWER_INPUT, ANSWER_SIGNATURE, CREATED));
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE, CREATED,
                             304));
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT,
                             "sig1=:ep4RQgi2eOuyIYpYNL+rAmgBORfQAVjiTxXGEe3RMj5=:", CREATED));
}

void test_an_unsigned_answer_says_so(void) {
    uint8_t sha[32];
    char why[96] = "";
    sha256("{\"led\": 1}", sha);
    TEST_ASSERT_FALSE(answerHolds(vectorKey(), 200, sha, "GET", ANSWER_URL, "", "", "", CREATED,
                                  why, sizeof(why)));
    TEST_ASSERT_EQUAL_STRING("it carries no signature", why);
}

void test_an_answer_to_another_request_does_not_hold(void) {
    TEST_ASSERT_FALSE(answer("http://192.168.1.20:8080/calibration?device=my-dock", "{\"led\": 1}",
                             ANSWER_INPUT, ANSWER_SIGNATURE, CREATED));
    TEST_ASSERT_FALSE(answer("http://192.168.1.20:8080/board-settings?device=my-display",
                             "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE, CREATED));
}

void test_an_answer_under_another_key_or_list_does_not_hold(void) {
    char other[sizeof(ANSWER_INPUT)];
    strcpy(other, ANSWER_INPUT);
    memcpy(strstr(other, "630dcd"), "730dcd", 6);
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 1}", other, ANSWER_SIGNATURE, CREATED));
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 1}",
                             "sig1=(\"@status\" \"content-digest\");created=1760000000"
                             ";keyid=\"630dcd2966c43366\"",
                             ANSWER_SIGNATURE, CREATED));
}

void test_an_old_answer_does_not_hold_once_the_clock_is_set(void) {
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE,
                             CREATED + SIGNATURE_WINDOW_S + 1));
    TEST_ASSERT_FALSE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE,
                             CREATED - SIGNATURE_WINDOW_S - 1));
    TEST_ASSERT_TRUE(answer(ANSWER_URL, "{\"led\": 1}", ANSWER_INPUT, ANSWER_SIGNATURE, 30));
}

// A refusal of a post, signed with the post's key: the server's vector.
static const char POST_URL[] = "http://192.168.1.20:8080/sensor-readings";
static const char REFUSAL_INPUT[] =
    "sig1=(\"@status\" \"content-digest\" \"@method\";req \"@path\";req \"@query\";req "
    "\"content-digest\";req);created=1760000000;keyid=\"630dcd2966c43366\"";
static const char REFUSAL_DIGEST[] = "sha-256=:57zVMV0DszyRQXTXyYu5dvuOdTMkMxHo2+fohJF4KkA=:";
static const char REFUSAL_SIGNATURE[] = "sig1=:Qwl6BPdt0iZvKLGamU/ATpuwOJKwzi/vFxjVkAzTIXs=:";
static const char POST_DIGEST[] = "sha-256=:2NQ1bwkVtGU1JEHr9Gie5wOYMIWti2B1/0NqC+N2pU0=:";

static bool refusal(const char* requestDigest, const char* input = REFUSAL_INPUT) {
    uint8_t sha[32];
    char why[96] = "";
    sha256("{\"problem\": \"x\"}", sha);
    return answerHolds(vectorKey(), 401, sha, "POST", POST_URL, REFUSAL_DIGEST, input,
                       REFUSAL_SIGNATURE, CREATED, why, sizeof(why), requestDigest);
}

void test_a_refusal_signed_for_this_post_holds(void) {
    TEST_ASSERT_TRUE(refusal(POST_DIGEST));
}

void test_a_refusal_for_another_post_or_as_a_plain_answer_does_not_hold(void) {
    TEST_ASSERT_FALSE(refusal("sha-256=:47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=:"));
    TEST_ASSERT_FALSE(refusal(nullptr));
    TEST_ASSERT_FALSE(refusal(POST_DIGEST, ANSWER_INPUT));
}

// ── URLs ────────────────────────────────────────────────────────────

static void target(const char* url, const char* path, const char* query) {
    char p[64], q[64];
    TEST_ASSERT_TRUE_MESSAGE(splitTarget(url, p, sizeof(p), q, sizeof(q)), url);
    TEST_ASSERT_EQUAL_STRING_MESSAGE(path, p, url);
    TEST_ASSERT_EQUAL_STRING_MESSAGE(query, q, url);
}

void test_a_url_splits_into_its_path_and_query(void) {
    target("http://host:8080/sensor-readings", "/sensor-readings", "");
    target("http://host:8080/calibration?device=d&before=1", "/calibration", "device=d&before=1");
    target("https://host", "/", "");
    target("http://host?x=1", "/", "x=1");
    target("http://host/a?b=1#frag", "/a", "b=1");
}

void test_a_url_that_is_not_http_or_does_not_fit_is_refused(void) {
    char p[8], q[8];
    TEST_ASSERT_FALSE(splitTarget("ftp://host/a", p, sizeof(p), q, sizeof(q)));
    TEST_ASSERT_FALSE(splitTarget("host/a", p, sizeof(p), q, sizeof(q)));
    TEST_ASSERT_FALSE(splitTarget("http://host/far-too-long", p, sizeof(p), q, sizeof(q)));
}

void test_the_pair_answer_gives_the_servers_half(void) {
    char out[16];
    TEST_ASSERT_TRUE(keyInPairAnswer("{\"key\": \"QUJD\"}", out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("QUJD", out);
    TEST_ASSERT_TRUE(keyInPairAnswer("{\"id\":\"ab\",\"key\":\"QUJD\"}", out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("QUJD", out);
}

void test_a_pair_answer_without_a_whole_key_is_refused(void) {
    char out[5];
    TEST_ASSERT_FALSE(keyInPairAnswer("{\"id\": \"ab\"}", out, sizeof(out)));
    TEST_ASSERT_FALSE(keyInPairAnswer("{\"key\": 5}", out, sizeof(out)));
    TEST_ASSERT_FALSE(keyInPairAnswer("{\"key\": \"QUJD", out, sizeof(out)));
    TEST_ASSERT_FALSE(keyInPairAnswer("{\"key\": \"QUJDRA\"}", out, sizeof(out)));
    TEST_ASSERT_TRUE(keyInPairAnswer("{\"key\": \"QUJD\"}", out, sizeof(out)));
}

void test_the_server_root_is_the_url_before_its_path(void) {
    char root[64];
    TEST_ASSERT_TRUE(serverRoot("http://192.168.1.20:8080/sensor-readings?x=1", root, sizeof(root)));
    TEST_ASSERT_EQUAL_STRING("http://192.168.1.20:8080", root);
    TEST_ASSERT_TRUE(serverRoot("https://canary.local", root, sizeof(root)));
    TEST_ASSERT_EQUAL_STRING("https://canary.local", root);
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_the_stand_in_sha256_matches_fips_180_4);
    RUN_TEST(test_the_stand_in_hmac_matches_rfc_4231);
    RUN_TEST(test_the_rfc_9421_hmac_example_signs_as_the_rfc_says);
    RUN_TEST(test_content_digest_is_rfc_9530s);
    RUN_TEST(test_the_key_id_and_the_derived_key_are_the_servers);
    RUN_TEST(test_a_post_is_signed_as_the_server_checks_it);
    RUN_TEST(test_an_answer_signed_by_the_server_holds);
    RUN_TEST(test_an_answer_changed_on_the_way_does_not_hold);
    RUN_TEST(test_an_unsigned_answer_says_so);
    RUN_TEST(test_an_answer_to_another_request_does_not_hold);
    RUN_TEST(test_an_answer_under_another_key_or_list_does_not_hold);
    RUN_TEST(test_an_old_answer_does_not_hold_once_the_clock_is_set);
    RUN_TEST(test_a_refusal_signed_for_this_post_holds);
    RUN_TEST(test_a_refusal_for_another_post_or_as_a_plain_answer_does_not_hold);
    RUN_TEST(test_a_url_splits_into_its_path_and_query);
    RUN_TEST(test_a_url_that_is_not_http_or_does_not_fit_is_refused);
    RUN_TEST(test_the_server_root_is_the_url_before_its_path);
    RUN_TEST(test_the_pair_answer_gives_the_servers_half);
    RUN_TEST(test_a_pair_answer_without_a_whole_key_is_refused);
    return UNITY_END();
}
