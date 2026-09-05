#include "EpdBoardInkplate.h"
#include "EpdClient.h"

static InkplateBoard inkplateBoard;

ClientConfig builtInSettings();     // from src/defaults.cpp

void setup() {
    epdBegin(inkplateBoard);        // the panel epd draws on
    startBoard(1);                  // 1 = portrait

    // Your settings, with the ones the panel keeps for itself resolved.
    ClientConfig cfg = loadConfig(builtInSettings());

    uint32_t sleepSeconds = cfg.defaultRefreshSeconds;
    if (connectNetwork(cfg) == ESP_OK) {
        PageFetch page = {};
        page.length = epdBoard().getWidth() * epdBoard().getHeight() * 8 + 100;
        const char* errMsg = nullptr;
        if (fetchPage(cfg.serverURL, clientUserAgent(epdBoard().deviceName()),
                      cfg.serverRetries, &page, &errMsg)) {
            drawPage(page, nullptr, cfg.serverRetries, nullptr, &errMsg);
            if (page.response.nextRefreshSeconds)
                sleepSeconds = page.response.nextRefreshSeconds;   // the server decides
        }
    }
    sleep_for(sleepSeconds);
}

void loop() {}
