// mbedtls/bignum.h for the native_io tests: a 32-byte number as its bytes.
#ifndef EPD_FAKE_MBEDTLS_BIGNUM_H
#define EPD_FAKE_MBEDTLS_BIGNUM_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define MBEDTLS_ERR_MPI_BUFFER_TOO_SMALL -0x0008

typedef struct {
    uint8_t bytes[32];
} mbedtls_mpi;

static inline void mbedtls_mpi_init(mbedtls_mpi* x) { memset(x, 0, sizeof(*x)); }
static inline void mbedtls_mpi_free(mbedtls_mpi* x) { memset(x, 0, sizeof(*x)); }
static inline int mbedtls_mpi_write_binary(const mbedtls_mpi* x, unsigned char* buf, size_t len) {
    if (len < sizeof(x->bytes)) return MBEDTLS_ERR_MPI_BUFFER_TOO_SMALL;
    memcpy(buf, x->bytes, sizeof(x->bytes));
    return 0;
}

#endif  // EPD_FAKE_MBEDTLS_BIGNUM_H
