// Signed downloads and posts from a board that holds a key, against the
// server's vectors (the same as test_board_key's). The board's clock starts
// unset, so a vector's age is not judged until a test sets the clock.
#include <unity.h>

#include <stdlib.h>
#include <string>

#include <Preferences.h>

#include "board_key.h"
#include "epd_headers.h"
#include "fake_globals.h"
#include "io_test.h"
#include "network_utils.h"
#include "ota.h"
#include "settings_store.h"

// The server's vectors, made with the key 00 01 .. 1f.
static const char kAnswerURL[] = "http://192.168.1.20:8080/board-settings?device=my-dock";
static const char kAnswerBody[] = "{\"led\": 1}";
static const char kAnswerInput[] =
    "sig1=(\"@status\" \"content-digest\" \"@method\";req \"@path\";req \"@query\";req)"
    ";created=1760000000;keyid=\"630dcd2966c43366\"";
static const char kAnswerDigest[] = "sha-256=:ljoQw9lxGK38HgIQvkE1LzzMtN7u8NH2gyZY+C/rHQ8=:";
static const char kAnswerSignature[] = "sig1=:ep4RQgi2eOuyIYpYNL+rAmgBORfQAVjiTxXGEe3RMj4=:";

static const char kPostURL[] = "http://192.168.1.20:8080/sensor-readings";
static const char kPostBody[] = "{\"device\": \"my-dock\", \"ts\": 1}";
static const char kPostDigest[] = "sha-256=:2NQ1bwkVtGU1JEHr9Gie5wOYMIWti2B1/0NqC+N2pU0=:";
static const char kRefusalBody[] = "{\"problem\": \"x\"}";
static const char kRefusalInput[] =
    "sig1=(\"@status\" \"content-digest\" \"@method\";req \"@path\";req \"@query\";req "
    "\"content-digest\";req);created=1760000000;keyid=\"630dcd2966c43366\"";
static const char kRefusalDigest[] = "sha-256=:57zVMV0DszyRQXTXyYu5dvuOdTMkMxHo2+fohJF4KkA=:";
static const char kRefusalSignature[] = "sig1=:Qwl6BPdt0iZvKLGamU/ATpuwOJKwzi/vFxjVkAzTIXs=:";

void setUp() {
    fake::http().reset();
    fake::lines().clear();
    Update = UpdateClass();
    ESP = FakeEsp();
}
void tearDown() {}

static fake::HttpAnswer& signedAnswer(const char* signature = kAnswerSignature) {
    fake::HttpAnswer& a = answer(200, kAnswerBody);
    a.headers = {{CONTENT_DIGEST_HEADER, kAnswerDigest},
                 {SIGNATURE_INPUT_HEADER, kAnswerInput},
                 {SIGNATURE_HEADER, signature}};
    return a;
}

void test_a_signed_download_names_the_key_and_holds() {
    signedAnswer();
    int32_t size = 100;
    uint8_t* body = downloadSigned(kAnswerURL, "ua", &size, nullptr);
    TEST_ASSERT_NOT_NULL(body);
    TEST_ASSERT_EQUAL_MEMORY(kAnswerBody, body, size);
    TEST_ASSERT_EQUAL_STRING("630dcd2966c43366", lastRequest().header(EPD_H_KEY_ID).c_str());
    TEST_ASSERT_TRUE(logged("signing with board key 630dcd2966c43366"));
    free(body);
}

void test_a_signed_download_whose_signature_does_not_hold_is_refused() {
    signedAnswer("sig1=:ep4RQgi2eOuyIYpYNL+rAmgBORfQAVjiTxXGEe3RMj5=:");
    int32_t size = 100;
    TEST_ASSERT_NULL(downloadSigned(kAnswerURL, "ua", &size, nullptr));
    TEST_ASSERT_TRUE(logged("refused the answer from"));
}

void test_a_plain_download_is_not_checked() {
    answer(200, "PNG");
    int32_t size = 100;
    uint8_t* page = downloadFile(kAnswerURL, "ua", &size, nullptr);
    TEST_ASSERT_NOT_NULL(page);
    TEST_ASSERT_TRUE(lastRequest().header(EPD_H_KEY_ID).empty());
    free(page);
}

void test_a_post_is_signed_over_its_body() {
    answer(204);
    TEST_ASSERT_EQUAL(204, postJson(kPostURL, "ua", kPostBody, nullptr));
    TEST_ASSERT_EQUAL_STRING(kPostDigest, lastRequest().header(CONTENT_DIGEST_HEADER).c_str());
    TEST_ASSERT_FALSE(lastRequest().header(SIGNATURE_INPUT_HEADER).empty());
    TEST_ASSERT_FALSE(lastRequest().header(SIGNATURE_HEADER).empty());
}

void test_a_request_to_pair_that_is_not_signed_keeps_the_key() {
    answer(401).headers = {{EPD_H_KEY, "pair"}};
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", kPostBody, nullptr));
    TEST_ASSERT_EQUAL(1, (int)fake::http().requests.size());
    TEST_ASSERT_TRUE(logged("does not prove it holds key 630dcd2966c43366"));
    TEST_ASSERT_TRUE(logged("not trusted"));
}

void test_a_key_that_waits_for_approval_says_so() {
    answer(401).headers = {{EPD_H_KEY, "pending"}};
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", kPostBody, nullptr));
    TEST_ASSERT_TRUE(logged("board key 630dcd2966c43366 waits for approval"));
}

void test_any_other_refusal_is_reported() {
    answer(401).headers = {{EPD_H_KEY, "no"}};
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", kPostBody, nullptr));
    TEST_ASSERT_TRUE(logged("the server refused this board's post"));
}

// An image signed for this board is written; one that is not is thrown away.
void test_a_signed_image_is_flashed() {
    signedAnswer();
    TEST_ASSERT_EQUAL(ESP_OK, applyFirmwareUpdate(kAnswerURL, "v1.3.0", "ua", nullptr));
    TEST_ASSERT_EQUAL_STRING(kAnswerBody, Update.written.c_str());
    TEST_ASSERT_TRUE(Update.ended);
    TEST_ASSERT_EQUAL(1, ESP.restarts);
}

void test_an_image_whose_signature_does_not_hold_is_thrown_away() {
    signedAnswer("sig1=:ep4RQgi2eOuyIYpYNL+rAmgBORfQAVjiTxXGEe3RMj5=:");
    TEST_ASSERT_EQUAL(ESP_FAIL, applyFirmwareUpdate(kAnswerURL, "v1.3.0", "ua", nullptr));
    TEST_ASSERT_TRUE(Update.aborted);
    TEST_ASSERT_FALSE(Update.ended);
    TEST_ASSERT_TRUE(logged("firmware v1.3.0 refused"));
}

// From here on the clock is set.
void test_a_post_signed_at_the_wrong_time_takes_the_servers_and_posts_again() {
    answer(401).headers = {{EPD_H_KEY, "clock"}, {EPD_H_SERVER_EPOCH, "1760000000"}};
    answer(204);
    TEST_ASSERT_EQUAL(204, postJson(kPostURL, "ua", kPostBody, nullptr));
    TEST_ASSERT_EQUAL(1760000000, fake::clockSetTo());
    TEST_ASSERT_EQUAL(2, (int)fake::http().requests.size());
}

// Last: the board pairs anew, and its key changes.
void test_a_signed_request_to_pair_is_trusted() {
    fake::HttpAnswer& refusal = answer(401, kRefusalBody);
    refusal.headers = {{EPD_H_KEY, "pair"},
                       {CONTENT_DIGEST_HEADER, kRefusalDigest},
                       {SIGNATURE_INPUT_HEADER, kRefusalInput},
                       {SIGNATURE_HEADER, kRefusalSignature}};
    answer(500);  // the pair itself fails here: the trust is what this checks
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", kPostBody, nullptr));
    TEST_ASSERT_EQUAL(2, (int)fake::http().requests.size());
    TEST_ASSERT_EQUAL_STRING("http://192.168.1.20:8080/pair", lastRequest().url.c_str());
    TEST_ASSERT_TRUE(logged("the server asks this board to pair"));
}

int main() {
    Preferences().clear();
    uint8_t key[BOARD_KEY_LEN];
    for (int i = 0; i < BOARD_KEY_LEN; ++i) key[i] = (uint8_t)i;
    storeBoardKey(key);
    UNITY_BEGIN();
    RUN_TEST(test_a_signed_download_names_the_key_and_holds);
    RUN_TEST(test_a_signed_download_whose_signature_does_not_hold_is_refused);
    RUN_TEST(test_a_plain_download_is_not_checked);
    RUN_TEST(test_a_post_is_signed_over_its_body);
    RUN_TEST(test_a_request_to_pair_that_is_not_signed_keeps_the_key);
    RUN_TEST(test_a_key_that_waits_for_approval_says_so);
    RUN_TEST(test_any_other_refusal_is_reported);
    RUN_TEST(test_a_signed_image_is_flashed);
    RUN_TEST(test_an_image_whose_signature_does_not_hold_is_thrown_away);
    RUN_TEST(test_a_post_signed_at_the_wrong_time_takes_the_servers_and_posts_again);
    RUN_TEST(test_a_signed_request_to_pair_is_trusted);
    return UNITY_END();
}
