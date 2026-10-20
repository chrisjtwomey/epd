#ifndef EPD_BOARD_KEY_H
#define EPD_BOARD_KEY_H

#include <stddef.h>
#include <stdint.h>

/**
  The key this board shares with its server, and the signatures made with
  it: RFC 9421 with hmac-sha256, under the label sig1, as the server's
  epd_server.board_keys makes and checks them.

  The board signs each POST over its method, path, query and Content-Digest
  (RFC 9530). The server signs its answer to the image and to the routes a
  project names; once the board has a key, it takes those answers only with
  a good signature. When the board pairs, the server's half of the key comes
  in its answer to /pair.

  Nothing here touches the network or the settings store, so the host tests
  check it against the RFC's own example and against the server's vectors.
*/

#define BOARD_KEY_LEN 32
#define BOARD_KEY_ID_LEN 16
// How far a signature's time may be from the reader's clock, either way.
#define SIGNATURE_WINDOW_S 300
// Room for "sha-256=:" + 44 base64 characters + ":".
#define CONTENT_DIGEST_SIZE 56
// Room for "sig1=:" + 44 base64 characters + ":".
#define SIGNATURE_SIZE 56
#define SIGNATURE_INPUT_SIZE 160

struct BoardKey {
    bool present;
    uint8_t key[BOARD_KEY_LEN];
    char id[BOARD_KEY_ID_LEN + 1];   // the start of the key's SHA-256, in hex
};

/** The headers that sign one request. */
struct SignedRequest {
    char contentDigest[CONTENT_DIGEST_SIZE];
    char signatureInput[SIGNATURE_INPUT_SIZE];
    char signature[SIGNATURE_SIZE];
};

/** ``key`` as a BoardKey, with its id. */
BoardKey boardKeyFrom(const uint8_t key[BOARD_KEY_LEN]);

/** The Content-Digest field of a body whose SHA-256 is ``sha256``. */
void contentDigest(const uint8_t sha256[32], char out[CONTENT_DIGEST_SIZE]);

/** The Content-Digest field of ``body``. */
void contentDigestOf(const uint8_t* body, size_t len, char out[CONTENT_DIGEST_SIZE]);

/**
  The path and the query of an http(s) URL: "/" when it has no path, and ""
  when it has no query. The query comes without its "?".

  @returns false when the URL is not http(s), or a part does not fit.
*/
bool splitTarget(const char* url, char* path, size_t pathSize, char* query, size_t querySize);

/** The scheme, host and port of an http(s) URL, without a path. */
bool serverRoot(const char* url, char* out, size_t size);

/**
  RFC 9421's signature base: each of ``n`` components as ``name: value`` on
  a line of its own, then the signature's parameters.

  @returns the length written, or 0 when it does not fit in ``size``.
*/
size_t signatureBase(const char* const* names, const char* const* values, size_t n,
                     const char* params, char* out, size_t size);

/** HMAC-SHA256 of ``base`` under ``key``, in base64. */
void hmacBase64(const uint8_t* key, size_t keyLen, const char* base, char out[48]);

/**
  The headers that sign a request to ``url`` with ``body``, made at
  ``created``.

  @returns false when the URL cannot be split.
*/
bool signRequest(const BoardKey& key, const char* method, const char* url, const uint8_t* body,
                 size_t len, uint32_t created, SignedRequest* out);

/**
  Whether the server's answer to ``method url`` holds for ``key``: its
  Content-Digest is that of the body read (``sha256``), and its signature
  covers that digest, ``status`` and the request, under this key, made
  within SIGNATURE_WINDOW_S of ``now``. An answer to a post passes the
  post's Content-Digest as ``requestDigest``, which the answer must cover too.

  A clock not set yet (``now`` before 2023) takes a signature of any time,
  since the board learns the time from the server it checks.

  @param why where to say what failed, for the log.
*/
bool answerHolds(const BoardKey& key, int status, const uint8_t sha256[32], const char* method,
                 const char* url, const char* contentDigestField, const char* signatureInput,
                 const char* signature, uint32_t now, char* why, size_t whySize,
                 const char* requestDigest = nullptr);

/**
  The board key from an ECDH shared secret: HKDF-SHA256 with no salt, and
  "epd board key <device>" as the info.
*/
void deriveBoardKey(const uint8_t* shared, size_t sharedLen, const char* device,
                    uint8_t out[BOARD_KEY_LEN]);

/**
  The server's half of the key from its answer to /pair, {"key": "<base64>"},
  copied into out. False when the answer holds no "key" string, or the value
  does not fit in size with its terminator.
*/
bool keyInPairAnswer(const char* json, char* out, size_t size);

#endif  // EPD_BOARD_KEY_H
