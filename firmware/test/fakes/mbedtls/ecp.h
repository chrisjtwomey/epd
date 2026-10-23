// mbedtls/ecp.h for the native_io tests: points as plain bytes, not P-256.
// Pairing's maths is mbedTLS's; these tests check what the board does with
// it. Our half is 0x04 then the random bytes; the shared secret is the x of
// the server's half alone, so a test can derive the key the board keeps,
// and cannot tell which private key the board used.
#ifndef EPD_FAKE_MBEDTLS_ECP_H
#define EPD_FAKE_MBEDTLS_ECP_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "bignum.h"

#define MBEDTLS_ECP_DP_SECP256R1 3
#define MBEDTLS_ECP_PF_UNCOMPRESSED 0
#define MBEDTLS_ERR_ECP_BAD_INPUT_DATA -0x4F80
#define MBEDTLS_ERR_ECP_INVALID_KEY -0x4C80
#define FAKE_P256_POINT_BYTES 65

typedef int mbedtls_ecp_group_id;
typedef struct {
    int id;
} mbedtls_ecp_group;
typedef struct {
    uint8_t bytes[FAKE_P256_POINT_BYTES];
} mbedtls_ecp_point;

static inline void mbedtls_ecp_group_init(mbedtls_ecp_group* g) { g->id = 0; }
static inline void mbedtls_ecp_group_free(mbedtls_ecp_group*) {}
static inline int mbedtls_ecp_group_load(mbedtls_ecp_group* g, mbedtls_ecp_group_id id) {
    g->id = id;
    return 0;
}
static inline void mbedtls_ecp_point_init(mbedtls_ecp_point* p) { memset(p, 0, sizeof(*p)); }
static inline void mbedtls_ecp_point_free(mbedtls_ecp_point*) {}

static inline int mbedtls_ecp_gen_keypair(mbedtls_ecp_group*, mbedtls_mpi* d, mbedtls_ecp_point* q,
                                          int (*f_rng)(void*, unsigned char*, size_t), void* p_rng) {
    q->bytes[0] = 0x04;
    f_rng(p_rng, q->bytes + 1, FAKE_P256_POINT_BYTES - 1);
    memcpy(d->bytes, q->bytes + 1, sizeof(d->bytes));
    return 0;
}
static inline int mbedtls_ecp_point_write_binary(const mbedtls_ecp_group*, const mbedtls_ecp_point* p,
                                                 int, size_t* olen, unsigned char* buf, size_t len) {
    if (len < FAKE_P256_POINT_BYTES) return MBEDTLS_ERR_ECP_BAD_INPUT_DATA;
    memcpy(buf, p->bytes, FAKE_P256_POINT_BYTES);
    *olen = FAKE_P256_POINT_BYTES;
    return 0;
}
static inline int mbedtls_ecp_point_read_binary(const mbedtls_ecp_group*, mbedtls_ecp_point* p,
                                                const unsigned char* buf, size_t len) {
    if (len != FAKE_P256_POINT_BYTES || buf[0] != 0x04) return MBEDTLS_ERR_ECP_BAD_INPUT_DATA;
    memcpy(p->bytes, buf, len);
    return 0;
}
// A point whose x is all zero bytes stands for one off the curve.
static inline int mbedtls_ecp_check_pubkey(const mbedtls_ecp_group*, const mbedtls_ecp_point* p) {
    for (int i = 1; i <= 32; ++i)
        if (p->bytes[i]) return 0;
    return MBEDTLS_ERR_ECP_INVALID_KEY;
}

#endif  // EPD_FAKE_MBEDTLS_ECP_H
