// mbedtls/md.h stub for native host builds: SHA-256 and HMAC-SHA256, whole
// and streamed, the part board_key.cpp calls. The board uses the ESP32 framework's own.
// test_board_key checks this one against FIPS 180-4's and RFC 4231's
// examples before it checks anything built on it.
#ifndef __STUB_MBEDTLS_MD_H__
#define __STUB_MBEDTLS_MD_H__

#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef enum { MBEDTLS_MD_NONE = 0, MBEDTLS_MD_SHA256 = 9 } mbedtls_md_type_t;

typedef struct {
    mbedtls_md_type_t type;
} mbedtls_md_info_t;

typedef struct {
    uint32_t h[8];
    uint64_t bytes;
    uint8_t block[64];
    size_t used;
} stub_sha256_t;

typedef struct {
    const mbedtls_md_info_t* info;
    stub_sha256_t sha;
    uint8_t hmacKey[64];
} mbedtls_md_context_t;

static inline uint32_t stub_ror(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

static inline void stub_sha256_block(stub_sha256_t* s, const uint8_t* p) {
    static const uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
        w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 |
               (uint32_t)p[4 * i + 2] << 8 | (uint32_t)p[4 * i + 3];
    for (int i = 16; i < 64; ++i) {
        const uint32_t s0 = stub_ror(w[i - 15], 7) ^ stub_ror(w[i - 15], 18) ^ (w[i - 15] >> 3);
        const uint32_t s1 = stub_ror(w[i - 2], 17) ^ stub_ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = s->h[0], b = s->h[1], c = s->h[2], d = s->h[3];
    uint32_t e = s->h[4], f = s->h[5], g = s->h[6], h = s->h[7];
    for (int i = 0; i < 64; ++i) {
        const uint32_t t1 = h + (stub_ror(e, 6) ^ stub_ror(e, 11) ^ stub_ror(e, 25)) +
                            ((e & f) ^ (~e & g)) + k[i] + w[i];
        const uint32_t t2 = (stub_ror(a, 2) ^ stub_ror(a, 13) ^ stub_ror(a, 22)) +
                            ((a & b) ^ (a & c) ^ (b & c));
        h = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    s->h[0] += a; s->h[1] += b; s->h[2] += c; s->h[3] += d;
    s->h[4] += e; s->h[5] += f; s->h[6] += g; s->h[7] += h;
}

static inline void stub_sha256_start(stub_sha256_t* s) {
    static const uint32_t iv[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                   0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(s->h, iv, sizeof(iv));
    s->bytes = 0;
    s->used = 0;
}

static inline void stub_sha256_update(stub_sha256_t* s, const uint8_t* p, size_t len) {
    s->bytes += len;
    while (len) {
        const size_t take = len < 64 - s->used ? len : 64 - s->used;
        memcpy(s->block + s->used, p, take);
        s->used += take;
        p += take;
        len -= take;
        if (s->used == 64) {
            stub_sha256_block(s, s->block);
            s->used = 0;
        }
    }
}

static inline void stub_sha256_finish(stub_sha256_t* s, uint8_t out[32]) {
    const uint64_t bits = s->bytes * 8;
    const uint8_t one = 0x80, zero = 0x00;
    stub_sha256_update(s, &one, 1);
    while (s->used != 56) stub_sha256_update(s, &zero, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; ++i) len[i] = (uint8_t)(bits >> (56 - 8 * i));
    stub_sha256_update(s, len, 8);
    for (int i = 0; i < 8; ++i) {
        out[4 * i] = (uint8_t)(s->h[i] >> 24);
        out[4 * i + 1] = (uint8_t)(s->h[i] >> 16);
        out[4 * i + 2] = (uint8_t)(s->h[i] >> 8);
        out[4 * i + 3] = (uint8_t)s->h[i];
    }
}

static inline const mbedtls_md_info_t* mbedtls_md_info_from_type(mbedtls_md_type_t type) {
    static const mbedtls_md_info_t sha256 = {MBEDTLS_MD_SHA256};
    return type == MBEDTLS_MD_SHA256 ? &sha256 : NULL;
}

static inline void mbedtls_md_init(mbedtls_md_context_t* ctx) { memset(ctx, 0, sizeof(*ctx)); }
static inline void mbedtls_md_free(mbedtls_md_context_t* ctx) { memset(ctx, 0, sizeof(*ctx)); }

static inline int mbedtls_md_setup(mbedtls_md_context_t* ctx, const mbedtls_md_info_t* info,
                                   int hmac) {
    (void)hmac;
    ctx->info = info;
    return info ? 0 : -1;
}

static inline int mbedtls_md_starts(mbedtls_md_context_t* ctx) {
    stub_sha256_start(&ctx->sha);
    return 0;
}

static inline int mbedtls_md_update(mbedtls_md_context_t* ctx, const unsigned char* input,
                                    size_t len) {
    stub_sha256_update(&ctx->sha, input, len);
    return 0;
}

static inline int mbedtls_md_finish(mbedtls_md_context_t* ctx, unsigned char* output) {
    stub_sha256_finish(&ctx->sha, output);
    return 0;
}

static inline int mbedtls_md(const mbedtls_md_info_t* info, const unsigned char* input,
                             size_t len, unsigned char* output) {
    if (!info) return -1;
    stub_sha256_t s;
    stub_sha256_start(&s);
    stub_sha256_update(&s, input, len);
    stub_sha256_finish(&s, output);
    return 0;
}

static inline int mbedtls_md_hmac(const mbedtls_md_info_t* info, const unsigned char* key,
                                  size_t keylen, const unsigned char* input, size_t ilen,
                                  unsigned char* output) {
    if (!info) return -1;
    uint8_t k[64] = {0};
    if (keylen > 64) {
        mbedtls_md(info, key, keylen, k);
    } else {
        memcpy(k, key, keylen);
    }
    uint8_t pad[64];
    uint8_t inner[32];
    stub_sha256_t s;
    for (int i = 0; i < 64; ++i) pad[i] = k[i] ^ 0x36;
    stub_sha256_start(&s);
    stub_sha256_update(&s, pad, 64);
    stub_sha256_update(&s, input, ilen);
    stub_sha256_finish(&s, inner);
    for (int i = 0; i < 64; ++i) pad[i] = k[i] ^ 0x5c;
    stub_sha256_start(&s);
    stub_sha256_update(&s, pad, 64);
    stub_sha256_update(&s, inner, 32);
    stub_sha256_finish(&s, output);
    return 0;
}

static inline int mbedtls_md_hmac_starts(mbedtls_md_context_t* ctx, const unsigned char* key,
                                         size_t keylen) {
    if (!ctx->info) return -1;
    memset(ctx->hmacKey, 0, sizeof(ctx->hmacKey));
    if (keylen > 64) {
        mbedtls_md(ctx->info, key, keylen, ctx->hmacKey);
    } else {
        memcpy(ctx->hmacKey, key, keylen);
    }
    uint8_t pad[64];
    for (int i = 0; i < 64; ++i) pad[i] = ctx->hmacKey[i] ^ 0x36;
    stub_sha256_start(&ctx->sha);
    stub_sha256_update(&ctx->sha, pad, 64);
    return 0;
}

static inline int mbedtls_md_hmac_update(mbedtls_md_context_t* ctx, const unsigned char* input,
                                         size_t ilen) {
    stub_sha256_update(&ctx->sha, input, ilen);
    return 0;
}

static inline int mbedtls_md_hmac_finish(mbedtls_md_context_t* ctx, unsigned char* output) {
    uint8_t inner[32], pad[64];
    stub_sha256_finish(&ctx->sha, inner);
    for (int i = 0; i < 64; ++i) pad[i] = ctx->hmacKey[i] ^ 0x5c;
    stub_sha256_start(&ctx->sha);
    stub_sha256_update(&ctx->sha, pad, 64);
    stub_sha256_update(&ctx->sha, inner, 32);
    stub_sha256_finish(&ctx->sha, output);
    return 0;
}

#endif  // __STUB_MBEDTLS_MD_H__
