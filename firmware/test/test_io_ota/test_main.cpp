// Updates over the air, for a board without a key: the download into the
// idle slot, the trial of a new image, and the way back from a bad one.
#include <unity.h>

#include <string>
#include <vector>

#include <Preferences.h>
#include <esp_ota_ops.h>

#include "fake_globals.h"
#include "io_test.h"
#include "ota.h"

static const char kURL[] = "http://server:8080/firmware.bin";
static const std::string kImage(5000, 'i');

static std::vector<int> progress;
static void onProgress(int done, int total) {
    progress.push_back(done);
    TEST_ASSERT_EQUAL((int)kImage.size(), total);
}

void setUp() {
    fake::http().reset();
    fake::lines().clear();
    fake::ota() = fake::Ota();
    Update = UpdateClass();
    ESP = FakeEsp();
    Preferences().clear();
    progress.clear();
}
void tearDown() {}

static esp_err_t update() { return applyFirmwareUpdate(kURL, "v1.3.0", "ua", onProgress); }

void test_a_whole_image_is_written_checked_and_restarted_into() {
    answer(200, kImage).headers = {{"x-MD5", "0123456789abcdef0123456789abcdef"}};
    TEST_ASSERT_EQUAL(ESP_OK, update());
    TEST_ASSERT_EQUAL(kImage.size(), Update.size);
    TEST_ASSERT_TRUE(Update.written == kImage);
    TEST_ASSERT_EQUAL_STRING("0123456789abcdef0123456789abcdef", Update.md5.c_str());
    TEST_ASSERT_TRUE(Update.ended);
    TEST_ASSERT_EQUAL(1, ESP.restarts);
    TEST_ASSERT_EQUAL((int)kImage.size(), progress.back());
    TEST_ASSERT_TRUE(logged("firmware update 100% (5000/5000 bytes)"));
    TEST_ASSERT_EQUAL_STRING("v1.2.0", lastRequest().header("x-ESP32-version").c_str());
}

void test_nothing_newer_after_all_keeps_this_image() {
    answer(304);
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    TEST_ASSERT_EQUAL(0u, Update.size);
    TEST_ASSERT_TRUE(logged("nothing newer after all"));
}

void test_an_answer_that_is_not_an_image_is_refused() {
    answer(404);
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    answer(200, "abc").contentLength = false;  // no length to size the slot with
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    TEST_ASSERT_EQUAL(0u, Update.size);
}

void test_a_url_that_is_not_one_is_refused() {
    TEST_ASSERT_EQUAL(ESP_FAIL, applyFirmwareUpdate("ftp://server/x.bin", "v1.3.0", "ua", nullptr));
    TEST_ASSERT_TRUE(fake::http().requests.empty());
}

void test_a_slot_that_will_not_open_stops_the_update() {
    answer(200, kImage);
    Update.beginOk = false;
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    TEST_ASSERT_TRUE(Update.written.empty());
}

void test_an_image_that_stops_arriving_is_thrown_away() {
    answer(200, kImage).stallAt = 3000;
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    TEST_ASSERT_TRUE(Update.aborted);
    TEST_ASSERT_EQUAL(0, ESP.restarts);
    TEST_ASSERT_TRUE(logged("failed after 3000 of 5000 bytes"));
}

void test_a_flash_write_that_falls_short_is_thrown_away() {
    answer(200, kImage);
    Update.writeLimit = 1000;
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    TEST_ASSERT_TRUE(Update.aborted);
}

void test_an_image_that_fails_its_check_is_not_booted() {
    answer(200, kImage);
    Update.endOk = false;
    TEST_ASSERT_EQUAL(ESP_FAIL, update());
    TEST_ASSERT_EQUAL(0, ESP.restarts);
}

void test_only_an_image_on_trial_is_confirmed() {
    otaConfirm();
    TEST_ASSERT_EQUAL(0, fake::ota().markedValid);
    fake::ota().stateReadable = false;
    TEST_ASSERT_FALSE(otaTrialPending());

    fake::ota() = fake::Ota();
    fake::ota().state = ESP_OTA_IMG_PENDING_VERIFY;
    TEST_ASSERT_TRUE(otaTrialPending());
    otaConfirm();
    TEST_ASSERT_EQUAL(1, fake::ota().markedValid);
    TEST_ASSERT_TRUE(logged("firmware v1.2.0 confirmed"));
}

void test_a_confirmation_that_fails_says_so() {
    fake::ota().state = ESP_OTA_IMG_PENDING_VERIFY;
    fake::ota().markValidResult = ESP_FAIL;
    otaConfirm();
    TEST_ASSERT_TRUE(logged("failed to confirm the running firmware"));
}

// The image that failed is remembered before the reboot, so it is refused
// when the server offers it again.
void test_a_rollback_remembers_the_image_that_failed() {
    TEST_ASSERT_EQUAL_STRING("", otaRejectedVersion());
    otaRollback("no page drawn");
    TEST_ASSERT_EQUAL_STRING("v1.2.0", otaRejectedVersion());
    TEST_ASSERT_EQUAL(1, fake::ota().markedInvalid);
    TEST_ASSERT_TRUE(logged("failed its first cycle (no page drawn)"));
    // The fake's bootloader has nothing to roll back to.
    TEST_ASSERT_TRUE(Update.rolledBack);
    TEST_ASSERT_EQUAL(1, ESP.restarts);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_a_whole_image_is_written_checked_and_restarted_into);
    RUN_TEST(test_nothing_newer_after_all_keeps_this_image);
    RUN_TEST(test_an_answer_that_is_not_an_image_is_refused);
    RUN_TEST(test_a_url_that_is_not_one_is_refused);
    RUN_TEST(test_a_slot_that_will_not_open_stops_the_update);
    RUN_TEST(test_an_image_that_stops_arriving_is_thrown_away);
    RUN_TEST(test_a_flash_write_that_falls_short_is_thrown_away);
    RUN_TEST(test_an_image_that_fails_its_check_is_not_booted);
    RUN_TEST(test_only_an_image_on_trial_is_confirmed);
    RUN_TEST(test_a_confirmation_that_fails_says_so);
    RUN_TEST(test_a_rollback_remembers_the_image_that_failed);
    return UNITY_END();
}
