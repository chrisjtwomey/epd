// mbedtls/base64.h stub for native host builds: the encoder and the decoder
// the firmware calls, with mbedTLS's contract. The encoder writes the
// terminator, and refuses a buffer without room for it.
#ifndef __STUB_MBEDTLS_BASE64_H__
#define __STUB_MBEDTLS_BASE64_H__

#include <stddef.h>

#define MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL -0x002A

static inline int mbedtls_base64_encode(unsigned char* dst, size_t dlen, size_t* olen,
                                        const unsigned char* src, size_t slen) {
    static const char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const size_t need = 4 * ((slen + 2) / 3);
    *olen = need + 1;
    if (dlen < need + 1) return MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL;
    size_t o = 0;
    for (size_t i = 0; i < slen; i += 3) {
        const unsigned v = (unsigned)src[i] << 16 | (i + 1 < slen ? (unsigned)src[i + 1] << 8 : 0) |
                           (i + 2 < slen ? src[i + 2] : 0);
        dst[o++] = alphabet[(v >> 18) & 63];
        dst[o++] = alphabet[(v >> 12) & 63];
        dst[o++] = i + 1 < slen ? alphabet[(v >> 6) & 63] : '=';
        dst[o++] = i + 2 < slen ? alphabet[v & 63] : '=';
    }
    dst[o] = '\0';
    *olen = o;
    return 0;
}

#define MBEDTLS_ERR_BASE64_INVALID_CHARACTER -0x002C

static inline int stub_base64_value(unsigned char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

// The decoder, with mbedTLS's contract: padded input only, and *olen says
// what the output needs when the buffer is too small.
static inline int mbedtls_base64_decode(unsigned char* dst, size_t dlen, size_t* olen,
                                        const unsigned char* src, size_t slen) {
    if (slen % 4) return MBEDTLS_ERR_BASE64_INVALID_CHARACTER;
    size_t pad = 0;
    while (pad < 2 && slen > pad && src[slen - 1 - pad] == '=') ++pad;
    const size_t need = slen / 4 * 3 - pad;
    *olen = need;
    for (size_t i = 0; i < slen - pad; ++i)
        if (stub_base64_value(src[i]) < 0) return MBEDTLS_ERR_BASE64_INVALID_CHARACTER;
    if (dlen < need) return MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL;
    size_t o = 0;
    for (size_t i = 0; i < slen; i += 4) {
        unsigned v = 0;
        for (size_t k = 0; k < 4; ++k) {
            const int d = src[i + k] == '=' ? 0 : stub_base64_value(src[i + k]);
            v = v << 6 | (unsigned)d;
        }
        for (int k = 2; k >= 0; --k)
            if (o < need) dst[o++] = (unsigned char)(v >> (8 * k));
    }
    return 0;
}

#endif  // __STUB_MBEDTLS_BASE64_H__
