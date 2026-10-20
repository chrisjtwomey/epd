#include "board_key.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mbedtls/base64.h>
#include <mbedtls/md.h>

static const char* const REQUEST_COMPONENTS[] = {"\"@method\"", "\"@path\"", "\"@query\"",
                                                 "\"content-digest\""};
static const char* const ANSWER_COMPONENTS[] = {"\"@status\"", "\"content-digest\"",
                                                "\"@method\";req", "\"@path\";req",
                                                "\"@query\";req"};
static const char REQUEST_LIST[] = "(\"@method\" \"@path\" \"@query\" \"content-digest\")";
static const char ANSWER_LIST[] =
    "(\"@status\" \"content-digest\" \"@method\";req \"@path\";req \"@query\";req)";
static const char* const POST_ANSWER_COMPONENTS[] = {"\"@status\"", "\"content-digest\"",
                                                     "\"@method\";req", "\"@path\";req",
                                                     "\"@query\";req", "\"content-digest\";req"};
static const char POST_ANSWER_LIST[] =
    "(\"@status\" \"content-digest\" \"@method\";req \"@path\";req \"@query\";req "
    "\"content-digest\";req)";
// Long enough for any query a board sends, with the rest of a base.
#define BASE_SIZE 1024
#define TARGET_SIZE 320
// 2023-01-01: a clock before it has not been set.
#define CLOCK_SET_EPOCH 1672531200u

static const mbedtls_md_info_t* sha256Info() {
    return mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
}

static void base64(const uint8_t* in, size_t len, char* out, size_t size) {
    size_t written = 0;
    if (mbedtls_base64_encode((unsigned char*)out, size, &written, in, len) != 0) written = 0;
    out[written] = '\0';
}

BoardKey boardKeyFrom(const uint8_t key[BOARD_KEY_LEN]) {
    BoardKey out = {};
    out.present = true;
    memcpy(out.key, key, BOARD_KEY_LEN);
    uint8_t sha[32];
    mbedtls_md(sha256Info(), key, BOARD_KEY_LEN, sha);
    for (int i = 0; i < BOARD_KEY_ID_LEN / 2; ++i) snprintf(out.id + 2 * i, 3, "%02x", sha[i]);
    return out;
}

void contentDigest(const uint8_t sha256[32], char out[CONTENT_DIGEST_SIZE]) {
    char b64[48];
    base64(sha256, 32, b64, sizeof(b64));
    snprintf(out, CONTENT_DIGEST_SIZE, "sha-256=:%s:", b64);
}

void contentDigestOf(const uint8_t* body, size_t len, char out[CONTENT_DIGEST_SIZE]) {
    uint8_t sha[32];
    mbedtls_md(sha256Info(), body, len, sha);
    contentDigest(sha, out);
}

bool splitTarget(const char* url, char* path, size_t pathSize, char* query, size_t querySize) {
    const char* at = strstr(url, "://");
    if (!at || (strncmp(url, "http", 4) != 0)) return false;
    const char* slash = strchr(at + 3, '/');
    const char* mark = strchr(at + 3, '?');
    const char* end = strchr(at + 3, '#');
    if (!end) end = url + strlen(url);
    if (mark && mark > end) mark = nullptr;
    if (slash && ((mark && slash > mark) || slash > end)) slash = nullptr;
    const char* pathEnd = mark ? mark : end;
    const size_t pathLen = slash ? (size_t)(pathEnd - slash) : 1;
    const size_t queryLen = mark ? (size_t)(end - mark - 1) : 0;
    if (pathLen >= pathSize || queryLen >= querySize) return false;
    if (slash) {
        memcpy(path, slash, pathLen);
    } else {
        path[0] = '/';
    }
    path[pathLen] = '\0';
    if (mark) memcpy(query, mark + 1, queryLen);
    query[queryLen] = '\0';
    return true;
}

bool serverRoot(const char* url, char* out, size_t size) {
    const char* at = strstr(url, "://");
    if (!at || strncmp(url, "http", 4) != 0) return false;
    const char* host = at + 3;
    const size_t len = (size_t)(host - url) + strcspn(host, "/?#");
    if (len >= size) return false;
    memcpy(out, url, len);
    out[len] = '\0';
    return true;
}

size_t signatureBase(const char* const* names, const char* const* values, size_t n,
                     const char* params, char* out, size_t size) {
    size_t used = 0;
    for (size_t i = 0; i < n; ++i) {
        const int w = snprintf(out + used, size - used, "%s: %s\n", names[i], values[i]);
        if (w < 0 || (size_t)w >= size - used) return 0;
        used += (size_t)w;
    }
    const int w = snprintf(out + used, size - used, "\"@signature-params\": %s", params);
    if (w < 0 || (size_t)w >= size - used) return 0;
    return used + (size_t)w;
}

void hmacBase64(const uint8_t* key, size_t keyLen, const char* base, char out[48]) {
    uint8_t mac[32];
    mbedtls_md_hmac(sha256Info(), key, keyLen, (const unsigned char*)base, strlen(base), mac);
    base64(mac, sizeof(mac), out, 48);
}

static void params(const char* list, uint32_t created, const char* keyid, char* out, size_t size) {
    snprintf(out, size, "%s;created=%lu;keyid=\"%s\"", list, (unsigned long)created, keyid);
}

// What a signature covers, on the heap: a board signs from deep in its loop,
// whose stack these 2 KB would overflow.
struct Workspace {
    char path[TARGET_SIZE];
    char query[TARGET_SIZE];
    char queryField[TARGET_SIZE + 1];
    char params[SIGNATURE_INPUT_SIZE - 5];
    char base[BASE_SIZE];
};

// The workspace with the URL's path and query in it; nullptr when there is
// no memory, or the URL cannot be split.
static Workspace* workspaceFor(const char* url) {
    Workspace* w = (Workspace*)malloc(sizeof(Workspace));
    if (w && !splitTarget(url, w->path, sizeof(w->path), w->query, sizeof(w->query))) {
        free(w);
        return nullptr;
    }
    if (w) snprintf(w->queryField, sizeof(w->queryField), "?%s", w->query);
    return w;
}

bool signRequest(const BoardKey& key, const char* method, const char* url, const uint8_t* body,
                 size_t len, uint32_t created, SignedRequest* out) {
    Workspace* w = workspaceFor(url);
    if (!w) return false;
    contentDigestOf(body, len, out->contentDigest);
    params(REQUEST_LIST, created, key.id, w->params, sizeof(w->params));
    const char* values[] = {method, w->path, w->queryField, out->contentDigest};
    const bool fits = signatureBase(REQUEST_COMPONENTS, values, 4, w->params, w->base,
                                    sizeof(w->base)) > 0;
    if (fits) {
        char mac[48];
        hmacBase64(key.key, BOARD_KEY_LEN, w->base, mac);
        snprintf(out->signatureInput, SIGNATURE_INPUT_SIZE, "sig1=%s", w->params);
        snprintf(out->signature, SIGNATURE_SIZE, "sig1=:%s:", mac);
    }
    free(w);
    return fits;
}

// Constant time, so that a wrong guess says nothing of where it went wrong.
static bool sameText(const char* a, const char* b) {
    const size_t len = strlen(a);
    if (strlen(b) != len) return false;
    unsigned char diff = 0;
    for (size_t i = 0; i < len; ++i) diff |= (unsigned char)(a[i] ^ b[i]);
    return diff == 0;
}

// The time in an answer's Signature-Input, when it covers ``list`` under
// ``keyid``; 0 when it does not.
static uint32_t signedAt(const char* input, const char* list, const char* keyid) {
    char head[sizeof(POST_ANSWER_LIST) + 16];
    snprintf(head, sizeof(head), "sig1=%s;created=", list);
    const size_t headLen = strlen(head);
    if (strncmp(input, head, headLen) != 0) return 0;
    const char* digits = input + headLen;
    char* after = nullptr;
    const unsigned long created = strtoul(digits, &after, 10);
    if (after == digits || created == 0) return 0;
    char tail[BOARD_KEY_ID_LEN + 12];
    snprintf(tail, sizeof(tail), ";keyid=\"%s\"", keyid);
    return strcmp(after, tail) == 0 ? (uint32_t)created : 0;
}

bool answerHolds(const BoardKey& key, int status, const uint8_t sha256[32], const char* method,
                 const char* url, const char* contentDigestField, const char* signatureInput,
                 const char* signature, uint32_t now, char* why, size_t whySize,
                 const char* requestDigest) {
    const char* list = requestDigest ? POST_ANSWER_LIST : ANSWER_LIST;
    if (!signatureInput[0] || !signature[0]) {
        snprintf(why, whySize, "it carries no signature");
        return false;
    }
    char digest[CONTENT_DIGEST_SIZE];
    contentDigest(sha256, digest);
    if (strcmp(contentDigestField, digest) != 0) {
        snprintf(why, whySize, "its body does not match its Content-Digest");
        return false;
    }
    const uint32_t created = signedAt(signatureInput, list, key.id);
    if (!created) {
        snprintf(why, whySize, "it is not signed with this board's key %s", key.id);
        return false;
    }
    if (now >= CLOCK_SET_EPOCH) {
        const uint32_t apart = now > created ? now - created : created - now;
        if (apart > SIGNATURE_WINDOW_S) {
            snprintf(why, whySize, "it was signed at %lu, %lu s from this board's clock",
                     (unsigned long)created, (unsigned long)apart);
            return false;
        }
    }
    Workspace* w = workspaceFor(url);
    if (!w) {
        snprintf(why, whySize, "its URL cannot be read, or there is no memory to check it");
        return false;
    }
    char code[8];
    snprintf(code, sizeof(code), "%d", status);
    params(list, created, key.id, w->params, sizeof(w->params));
    const char* values[] = {code, digest, method, w->path, w->queryField, requestDigest};
    const bool fits = signatureBase(requestDigest ? POST_ANSWER_COMPONENTS : ANSWER_COMPONENTS,
                                    values, requestDigest ? 6 : 5, w->params, w->base,
                                    sizeof(w->base)) > 0;
    char mac[48] = "", expected[SIGNATURE_SIZE];
    if (fits) hmacBase64(key.key, BOARD_KEY_LEN, w->base, mac);
    free(w);
    if (!fits) {
        snprintf(why, whySize, "its URL is too long to check");
        return false;
    }
    snprintf(expected, sizeof(expected), "sig1=:%s:", mac);
    if (!sameText(expected, signature)) {
        snprintf(why, whySize, "its signature does not hold");
        return false;
    }
    return true;
}

void deriveBoardKey(const uint8_t* shared, size_t sharedLen, const char* device,
                    uint8_t out[BOARD_KEY_LEN]) {
    static const uint8_t noSalt[32] = {0};
    uint8_t prk[32];
    mbedtls_md_hmac(sha256Info(), noSalt, sizeof(noSalt), shared, sharedLen, prk);
    char info[96];
    const int n = snprintf(info, sizeof(info), "epd board key %s", device);
    uint8_t message[97];
    memcpy(message, info, (size_t)n);
    message[n] = 0x01;
    mbedtls_md_hmac(sha256Info(), prk, sizeof(prk), message, (size_t)n + 1, out);
    memset(prk, 0, sizeof(prk));
}

bool keyInPairAnswer(const char* json, char* out, size_t size) {
    const char* at = strstr(json, "\"key\"");
    if (!at) return false;
    at += 5;
    while (*at == ' ' || *at == ':') ++at;
    if (*at++ != '"') return false;
    const char* end = strchr(at, '"');
    if (!end || (size_t)(end - at) >= size) return false;
    memcpy(out, at, (size_t)(end - at));
    out[end - at] = '\0';
    return true;
}

RefusalStep afterRefusal(const Refusal& refusal) {
    const char* state = refusal.keyState ? refusal.keyState : "";
    if (strcmp(state, "clock") == 0)
        return refusal.serverSentClock ? RefusalStep::TakeClock : RefusalStep::Refused;
    if (strcmp(state, "pair") == 0)
        return refusal.boardHasKey && !refusal.signedWithBoardKey ? RefusalStep::KeepKey
                                                                  : RefusalStep::Pair;
    if (strcmp(state, "pending") == 0) return RefusalStep::Wait;
    return RefusalStep::Refused;
}
