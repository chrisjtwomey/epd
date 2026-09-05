#include "EpdBoardInkplate.h"
#include "EpdClient.h"

static InkplateBoard inkplateBoard;

ClientConfig builtInSettings();     // from src/defaults.cpp

// Below this an offered update waits for a charge.
#define BATTERY_FOR_UPDATE_PERCENT 20

// No page reached the panel. On a trial boot the new image is to blame until
// proven otherwise, so the previous one is booted instead.
static void endFailedWake(const char* why, bool trialBoot, uint32_t sleepSeconds) {
    if (trialBoot) otaRollback(why);    // does not return
    sleep_for(sleepSeconds);
}

void setup() {
    epdBegin(inkplateBoard);
    startBoard(1);

    // The first boot of a freshly written image. The bootloader takes it
    // back unless this wake calls otaConfirm().
    const bool trialBoot = otaTrialPending();
    if (trialBoot) logf(LOG_NOTICE, "trial boot of %s", CLIENT_VERSION);

    ClientConfig cfg = loadConfig(builtInSettings());
    const char* userAgent = clientUserAgent(epdBoard().deviceName());

    if (connectNetwork(cfg) != ESP_OK) {
        endFailedWake("wifi connect timeout", trialBoot, cfg.defaultRefreshSeconds);
        return;
    }

    PageFetch page = {};
    page.length = epdBoard().getWidth() * epdBoard().getHeight() * 8 + 100;
    const char* errMsg = nullptr;
    if (!fetchPage(cfg.serverURL, userAgent, cfg.serverRetries, &page, &errMsg) ||
        !drawPage(page, nullptr, cfg.serverRetries, nullptr, &errMsg)) {
        endFailedWake(errMsg, trialBoot, cfg.defaultRefreshSeconds);
        return;
    }

    // A page is on the panel, so this image works. Say so before taking the
    // next offer: a write to the idle slot is refused while one is pending.
    if (trialBoot) otaConfirm();

    // Returns only when nothing was flashed. A flashed image restarts the board.
    takeOfferedUpdate(page.response, userAgent, readBatteryPercent(), BATTERY_FOR_UPDATE_PERCENT);

    sleep_for(page.response.nextRefreshSeconds ? page.response.nextRefreshSeconds
                                               : cfg.defaultRefreshSeconds);
}

void loop() {}
