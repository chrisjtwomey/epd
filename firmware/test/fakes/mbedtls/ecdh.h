// mbedtls/ecdh.h for the native_io tests: the shared secret is the x of the
// server's half (see ecp.h).
#ifndef EPD_FAKE_MBEDTLS_ECDH_H
#define EPD_FAKE_MBEDTLS_ECDH_H

#include "bignum.h"
#include "ecp.h"

static inline int mbedtls_ecdh_compute_shared(mbedtls_ecp_group*, mbedtls_mpi* z,
                                              const mbedtls_ecp_point* theirs, const mbedtls_mpi*,
                                              int (*)(void*, unsigned char*, size_t), void*) {
    memcpy(z->bytes, theirs->bytes + 1, sizeof(z->bytes));
    return 0;
}

#endif  // EPD_FAKE_MBEDTLS_ECDH_H
