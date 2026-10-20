#include "network_utils.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <esp_random.h>
#include <mbedtls/base64.h>
#include <mbedtls/bignum.h>
#include <mbedtls/ecdh.h>
#include <mbedtls/ecp.h>
#include <mbedtls/md.h>

#include "body_read.h"
#include "current_board_key.h"
#include "epd_headers.h"
#include "log_utils.h"
#include "mem_utils.h"
#include "refresh_header.h"
#include "settings.h"
#include "time_utils.h"
#include "version.h"

// Logs the first answer from an epd server since boot, the line the install
// page waits for. Any web server answers HTTP; only ours sends its version.
static void noteServerReached(HTTPClient& http, const char* url) {
    static bool reached = false;
    if (reached || http.header(EPD_H_SERVER_VERSION).isEmpty()) return;
    reached = true;
    logf(LOG_INFO, "reached the server at %s", url);
}

// Copy a header value into a fixed field, logging what arrived.
static void copyHeader(HTTPClient& http, const char* name, char* out, size_t size) {
    if (!out || !size || !http.hasHeader(name)) return;
    const String value = http.header(name);
    if (!copyWholeValue(value.c_str(), out, size)) {
        logf(LOG_WARNING, "%s value is longer than %u characters, ignoring", name,
             (unsigned)(size - 1));
        return;
    }
    logf(LOG_INFO, "received header %s: %s", name, out);
}

// Read a whole-number header into *out, leaving it alone when the header is
// absent or malformed.
static void numberHeader(HTTPClient& http, const char* name, uint32_t* out) {
    if (!out || !http.hasHeader(name)) return;
    String value = http.header(name);
    uint32_t parsed = 0;
    if (parseRefreshTime(value.c_str(), &parsed)) {
        *out = parsed;
        logf(LOG_INFO, "received header %s: %lu", name, (unsigned long)parsed);
    } else {
        logf(LOG_WARNING, "%s value '%s' is malformed, ignoring", name, value.c_str());
    }
}

// What the server says about itself and the firmware on offer, on any
// response.
static void readServerHeaders(HTTPClient& http, ServerResponse* rsp) {
    if (!rsp) return;
    copyHeader(http, EPD_H_SERVER_VERSION, rsp->serverVersion, sizeof(rsp->serverVersion));
    copyHeader(http, EPD_H_FIRMWARE_VERSION, rsp->firmwareVersion, sizeof(rsp->firmwareVersion));
    copyHeader(http, EPD_H_FIRMWARE_URL, rsp->firmwareURL, sizeof(rsp->firmwareURL));
    numberHeader(http, EPD_H_SERVER_EPOCH, &rsp->serverEpoch);
    copyHeader(http, EPD_H_SERVER_TIMEZONE, rsp->serverTimezone, sizeof(rsp->serverTimezone));
    numberHeader(http, EPD_H_NEXT_SENSOR_POLL, &rsp->nextSensorPollSeconds);
}

// The headers every request carries: the board decides these, not the
// User-Agent, so neither end has to parse an identity back out of a
// formatted string.
static void addDeviceHeaders(HTTPClient& http) {
    http.addHeader(EPD_H_DEVICE, CLIENT_NAME);
    http.addHeader(EPD_H_DEVICE_VERSION, CLIENT_VERSION);
}

// The stack of the task that pairs: mbedTLS's P-256 maths takes several KB.
#define PAIR_STACK_BYTES 16384

// The key, read from the settings store by the first request that needs it.
static BoardKey boardKey = {};
static bool boardKeyRead = false;

const BoardKey& currentBoardKey() {
    if (!boardKeyRead) {
        boardKey = loadBoardKey();
        boardKeyRead = true;
        if (boardKey.present) logf(LOG_INFO, "signing with board key %s", boardKey.id);
    }
    return boardKey;
}

// Sign a post with the board's key, and keep the post's digest in ``digest``
// for the check of a signed refusal; ``digest`` stays empty without a key.
static void addSignature(HTTPClient& http, const char* url, const char* body,
                         char digest[CONTENT_DIGEST_SIZE]) {
    digest[0] = '\0';
    const BoardKey& key = currentBoardKey();
    if (!key.present) return;
    SignedRequest sig;
    if (!signRequest(key, "POST", url, (const uint8_t*)body, strlen(body),
                     (uint32_t)time(nullptr), &sig)) {
        logf(LOG_WARNING, "cannot sign a post to %s", url);
        return;
    }
    http.addHeader(CONTENT_DIGEST_HEADER, sig.contentDigest);
    http.addHeader(SIGNATURE_INPUT_HEADER, sig.signatureInput);
    http.addHeader(SIGNATURE_HEADER, sig.signature);
    strlcpy(digest, sig.contentDigest, CONTENT_DIGEST_SIZE);
}

// Whether a refusal answers this post with the board's own key: only the
// server that holds the key can sign it, so only it can make the board pair
// again.
static bool refusalHolds(HTTPClient& http, const char* url, const char* postDigest) {
    if (!postDigest[0]) return false;
    const String answer = http.getString();
    uint8_t sha[32];
    mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), (const unsigned char*)answer.c_str(),
               answer.length(), sha);
    char why[ANSWER_WHY_SIZE];
    if (answerHolds(currentBoardKey(), 401, sha, "POST", url,
                    http.header(CONTENT_DIGEST_HEADER).c_str(),
                    http.header(SIGNATURE_INPUT_HEADER).c_str(),
                    http.header(SIGNATURE_HEADER).c_str(), (uint32_t)time(nullptr), why,
                    sizeof(why), postDigest)) {
        return true;
    }
    logf(LOG_ERROR, "refusal from %s not trusted: %s", url, why);
    return false;
}

// The wait for the next byte of a body: the wait HTTPClient gives the
// connection and the headers.
static const uint32_t kBodyStallMs = HTTPCLIENT_DEFAULT_TCP_TIMEOUT;

// A response body as HTTPClient receives it.
class HttpBody : public IBodySource {
public:
    explicit HttpBody(HTTPClient& http) : http_(http), stream_(*http.getStreamPtr()) {}
    size_t available() override { return stream_.available(); }
    size_t read(uint8_t* out, size_t len) override {
        const int n = stream_.read(out, len);
        return n > 0 ? (size_t)n : 0;
    }
    bool connected() override { return http_.connected(); }
    uint32_t nowMs() override { return millis(); }
    void wait() override { delay(1); }

private:
    HTTPClient& http_;
    WiFiClient& stream_;
};

static uint8_t* fetch(const char* url, const char* userAgent, int32_t* defaultLen,
                      ServerResponse* rsp, bool signedAnswer) {
    logf(LOG_INFO, "downloading file at URL %s", url);
    const bool check = signedAnswer && currentBoardKey().present;

    bool sleep = WiFi.getSleep();
    WiFi.setSleep(false);

    HTTPClient http;

    const char* headersToCollect[] = {
        EPD_H_NEXT_REFRESH,     EPD_H_NEXT_URL,         EPD_H_SERVER_VERSION,
        EPD_H_SERVER_EPOCH,     EPD_H_SERVER_TIMEZONE,  EPD_H_NEXT_SENSOR_POLL,
        EPD_H_FIRMWARE_VERSION, EPD_H_FIRMWARE_URL,     CONTENT_DIGEST_HEADER,
        SIGNATURE_INPUT_HEADER, SIGNATURE_HEADER,       "Transfer-Encoding",
    };
    http.collectHeaders(headersToCollect,
                        sizeof(headersToCollect) / sizeof(headersToCollect[0]));

    if (userAgent && userAgent[0])
        http.setUserAgent(userAgent);

    http.begin(url);
    addDeviceHeaders(http);
    if (check) http.addHeader(EPD_H_KEY_ID, currentBoardKey().id);

    int httpCode = http.GET();
    noteServerReached(http, url);
    if (httpCode != HTTP_CODE_OK) {
        if (httpCode < 0)
            logf(LOG_ERROR, "GET %s failed: %s", url, HTTPClient::errorToString(httpCode).c_str());
        else
            logf(LOG_ERROR, "Non-200 response from URL %s: %d", url, httpCode);
        http.end();
        WiFi.setSleep(sleep);
        return nullptr;
    }

    if (rsp) {
        // The server is authoritative for when to refresh next; the board just
        // counts down. No timezone arithmetic on the client.
        numberHeader(http, EPD_H_NEXT_REFRESH, &rsp->nextRefreshSeconds);

        copyHeader(http, EPD_H_NEXT_URL, rsp->nextURL, sizeof(rsp->nextURL));
        readServerHeaders(http, rsp);
    }

    const int32_t reported = http.getSize();
    if (reported == 0) {
        logf(LOG_ERROR, "empty answer from %s", url);
        http.end();
        WiFi.setSleep(sleep);
        return nullptr;
    }
    const size_t limit = *defaultLen > 0 ? (size_t)*defaultLen : 0;
    if (reported > 0 && (size_t)reported > limit) {
        logf(LOG_ERROR, "answer from %s is %ld bytes, more than the %u allowed", url,
             (long)reported, (unsigned)limit);
        http.end();
        WiFi.setSleep(sleep);
        return nullptr;
    }
    const size_t capacity = reported >= 0 ? (size_t)reported : limit;

    uint8_t* buffer = (uint8_t *)boardMalloc(capacity);
    if (!buffer) {
        logf(LOG_ERROR, "failed to allocate %u bytes for download buffer", (unsigned)capacity);
        http.end();
        WiFi.setSleep(sleep);
        return nullptr;
    }

    // The socket exists only after GET() has connected.
    http.getStream().setNoDelay(true);

    HttpBody body(http);
    size_t got = 0;
    const bool chunked = http.header("Transfer-Encoding").equalsIgnoreCase("chunked");
    const BodyRead read =
        chunked ? readChunkedBody(body, buffer, capacity, kBodyStallMs, &got)
                : readBody(body, reported, buffer, capacity, kBodyStallMs, &got);
    if (read != BodyRead::Complete) {
        logf(LOG_ERROR, "download from %s failed after %u bytes: %s", url, (unsigned)got,
             bodyReadName(read));
        free(buffer);
        buffer = nullptr;
    } else if (got == 0) {
        logf(LOG_ERROR, "empty answer from %s", url);
        free(buffer);
        buffer = nullptr;
    } else {
        *defaultLen = (int32_t)got;
    }

    if (buffer && check) {
        uint8_t digest[32];
        mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), buffer, got, digest);
        char why[ANSWER_WHY_SIZE];
        if (!answerHolds(currentBoardKey(), httpCode, digest, "GET", url,
                         http.header(CONTENT_DIGEST_HEADER).c_str(),
                         http.header(SIGNATURE_INPUT_HEADER).c_str(),
                         http.header(SIGNATURE_HEADER).c_str(), (uint32_t)time(nullptr), why,
                         sizeof(why))) {
            logf(LOG_ERROR, "refused the answer from %s: %s", url, why);
            free(buffer);
            buffer = nullptr;
        }
    }

    http.end();
    WiFi.setSleep(sleep);

    return buffer;
}

uint8_t* downloadFile(const char* url, const char* userAgent, int32_t* defaultLen,
                      ServerResponse* rsp) {
    return fetch(url, userAgent, defaultLen, rsp, false);
}

uint8_t* downloadSigned(const char* url, const char* userAgent, int32_t* defaultLen,
                        ServerResponse* rsp) {
    return fetch(url, userAgent, defaultLen, rsp, true);
}

static int fillRandom(void*, unsigned char* out, size_t len) {
    esp_fill_random(out, len);
    return 0;
}

// Agree a key with the server by ECDH on P-256, and keep it. The server
// holds it as pending until a person approves it.
static esp_err_t pairNow(const char* url, const char* userAgent) {
    char root[192], pairURL[200];
    if (!serverRoot(url, root, sizeof(root))) return ESP_FAIL;
    snprintf(pairURL, sizeof(pairURL), "%s/pair", root);

    mbedtls_ecp_group grp;
    mbedtls_mpi d, z;
    mbedtls_ecp_point ours, theirs;
    mbedtls_ecp_group_init(&grp);
    mbedtls_mpi_init(&d);
    mbedtls_mpi_init(&z);
    mbedtls_ecp_point_init(&ours);
    mbedtls_ecp_point_init(&theirs);

    esp_err_t result = ESP_FAIL;
    uint8_t half[65], theirHalf[65], shared[32], key[BOARD_KEY_LEN];
    size_t halfLen = 0, theirLen = 0, written = 0;
    char half64[96], answer64[96], body[192];
    const char* failed = nullptr;
    do {
        if (mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1) != 0 ||
            mbedtls_ecp_gen_keypair(&grp, &d, &ours, fillRandom, nullptr) != 0 ||
            mbedtls_ecp_point_write_binary(&grp, &ours, MBEDTLS_ECP_PF_UNCOMPRESSED, &halfLen,
                                           half, sizeof(half)) != 0 ||
            mbedtls_base64_encode((unsigned char*)half64, sizeof(half64), &written, half,
                                  halfLen) != 0) {
            failed = "cannot make this board's half of the key";
            break;
        }
        snprintf(body, sizeof(body), "{\"device\":\"%s\",\"key\":\"%s\"}", CLIENT_NAME, half64);

        HTTPClient http;
        if (userAgent && userAgent[0]) http.setUserAgent(userAgent);
        http.begin(pairURL);
        http.addHeader("Content-Type", "application/json");
        addDeviceHeaders(http);
        const int code = http.POST((uint8_t*)body, strlen(body));
        const String answer = code == HTTP_CODE_OK ? http.getString() : String();
        http.end();
        if (code != HTTP_CODE_OK) {
            logf(LOG_ERROR, "pairing with %s failed: %d", pairURL, code);
            break;
        }
        if (!keyInPairAnswer(answer.c_str(), answer64, sizeof(answer64)) ||
            mbedtls_base64_decode(theirHalf, sizeof(theirHalf), &theirLen,
                                  (const unsigned char*)answer64, strlen(answer64)) != 0 ||
            mbedtls_ecp_point_read_binary(&grp, &theirs, theirHalf, theirLen) != 0 ||
            mbedtls_ecp_check_pubkey(&grp, &theirs) != 0) {
            failed = "the server's half of the key cannot be read";
            break;
        }
        if (mbedtls_ecdh_compute_shared(&grp, &z, &theirs, &d, fillRandom, nullptr) != 0 ||
            mbedtls_mpi_write_binary(&z, shared, sizeof(shared)) != 0) {
            failed = "cannot work out the key";
            break;
        }
        deriveBoardKey(shared, sizeof(shared), CLIENT_NAME, key);
        if (!storeBoardKey(key)) {
            failed = "cannot keep the key in the settings store";
            break;
        }
        boardKey = boardKeyFrom(key);
        boardKeyRead = true;
        logf(LOG_NOTICE, "paired with %s: key %s waits for approval in the server's Settings",
             root, boardKey.id);
        result = ESP_OK;
    } while (false);

    if (failed) logf(LOG_ERROR, "pairing with %s failed: %s", pairURL, failed);
    memset(shared, 0, sizeof(shared));
    memset(key, 0, sizeof(key));
    mbedtls_ecp_point_free(&theirs);
    mbedtls_ecp_point_free(&ours);
    mbedtls_mpi_free(&z);
    mbedtls_mpi_free(&d);
    mbedtls_ecp_group_free(&grp);
    return result;
}

struct PairJob {
    const char* url;
    const char* userAgent;
    esp_err_t result;
    SemaphoreHandle_t done;
};

static void pairTask(void* arg) {
    PairJob* job = (PairJob*)arg;
    job->result = pairNow(job->url, job->userAgent);
    xSemaphoreGive(job->done);
    vTaskDelete(nullptr);
}

// pairNow on a task of its own: mbedTLS's elliptic-curve maths needs more
// stack than a board's loop has to spare. The wait is on a semaphore of its
// own, not the caller's task notification, which the caller's code may use.
static esp_err_t pairWithServer(const char* url, const char* userAgent) {
    PairJob job = {url, userAgent, ESP_FAIL, xSemaphoreCreateBinary()};
    if (!job.done || xTaskCreate(pairTask, "epd-pair", PAIR_STACK_BYTES, &job,
                                 uxTaskPriorityGet(nullptr), nullptr) != pdPASS) {
        log(LOG_ERROR, "pairing failed: no memory for its task");
        if (job.done) vSemaphoreDelete(job.done);
        return ESP_FAIL;
    }
    xSemaphoreTake(job.done, portMAX_DELAY);
    vSemaphoreDelete(job.done);
    return job.result;
}

// One post. On a 401 its <prefix>-Key goes to ``keyState``, and ``trusted``
// says whether the refusal is signed for this post with the board's key.
static int postOnce(const char* url, const char* userAgent, const char* body,
                    ServerResponse* rsp, char* keyState, size_t stateSize, bool* trusted) {
    HTTPClient http;
    const char* headersToCollect[] = {EPD_H_SERVER_VERSION,   EPD_H_SERVER_EPOCH,
                                      EPD_H_SERVER_TIMEZONE,  EPD_H_NEXT_SENSOR_POLL,
                                      EPD_H_FIRMWARE_VERSION, EPD_H_FIRMWARE_URL,
                                      EPD_H_KEY,              CONTENT_DIGEST_HEADER,
                                      SIGNATURE_INPUT_HEADER, SIGNATURE_HEADER};
    http.collectHeaders(headersToCollect, sizeof(headersToCollect) / sizeof(headersToCollect[0]));
    if (userAgent && userAgent[0])
        http.setUserAgent(userAgent);
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    addDeviceHeaders(http);
    char postDigest[CONTENT_DIGEST_SIZE];
    addSignature(http, url, body, postDigest);
    int code = http.POST((uint8_t*)body, strlen(body));
    noteServerReached(http, url);
    readServerHeaders(http, rsp);
    strlcpy(keyState, http.header(EPD_H_KEY).c_str(), stateSize);
    *trusted = code == 401 && refusalHolds(http, url, postDigest);
    http.end();
    if (code < 0)
        logf(LOG_ERROR, "POST %s failed: %s", url, HTTPClient::errorToString(code).c_str());
    return code;
}

static int postSigned(const char* url, const char* userAgent, const char* body,
                      ServerResponse* into);

int postJson(const char* url, const char* userAgent, const char* body, ServerResponse* rsp) {
    // The caller's own, else one on the heap: the stack is short already.
    ServerResponse* heard = rsp ? nullptr : (ServerResponse*)calloc(1, sizeof(ServerResponse));
    ServerResponse* into = rsp ? rsp : heard;
    if (!into) return HTTPC_ERROR_TOO_LESS_RAM;
    const int code = postSigned(url, userAgent, body, into);
    free(heard);
    return code;
}

static RefusalStep stepAfter(const char* state, const ServerResponse* into, bool trusted) {
    const Refusal refusal = {state, into->serverEpoch != 0, currentBoardKey().present, trusted};
    return afterRefusal(refusal);
}

static int postSigned(const char* url, const char* userAgent, const char* body,
                      ServerResponse* into) {
    char state[12] = "";
    bool trusted = false;
    int code = postOnce(url, userAgent, body, into, state, sizeof(state), &trusted);
    if (code != 401) return code;
    if (stepAfter(state, into, trusted) == RefusalStep::TakeClock) {
        logf(LOG_WARNING, "signed with the wrong time; taking the server's, %lu",
             (unsigned long)into->serverEpoch);
        setClock((time_t)into->serverEpoch);
        code = postOnce(url, userAgent, body, into, state, sizeof(state), &trusted);
    }
    if (code == 401) {
        const RefusalStep step = stepAfter(state, into, trusted);
        if (step == RefusalStep::KeepKey) {
            logf(LOG_ERROR, "the server asks this board to pair, but does not prove it holds "
                            "key %s; keeping it. A USB install clears it",
                 currentBoardKey().id);
        } else if (step == RefusalStep::Pair) {
            log(LOG_WARNING, "the server asks this board to pair");
            if (pairWithServer(url, userAgent) == ESP_OK)
                code = postOnce(url, userAgent, body, into, state, sizeof(state), &trusted);
        }
    }
    if (code == 401 && stepAfter(state, into, trusted) == RefusalStep::Wait)
        logf(LOG_WARNING, "board key %s waits for approval in the server's Settings",
             currentBoardKey().id);
    else if (code == 401)
        logf(LOG_ERROR, "the server refused this board's post to %s (%s)", url, state);
    return code;
}
