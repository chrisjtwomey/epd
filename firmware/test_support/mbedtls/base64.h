// mbedtls/base64.h stub for native host builds: the encoder board_key.cpp
// calls, with mbedTLS's contract: it writes the terminator, and refuses a
// buffer without room for it.
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

#endif  // __STUB_MBEDTLS_BASE64_H__
