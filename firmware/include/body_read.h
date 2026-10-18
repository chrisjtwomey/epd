#ifndef EPD_BODY_READ_H
#define EPD_BODY_READ_H

#include <stddef.h>
#include <stdint.h>

/** The connection a response body arrives on, and the clock that times it. */
class IBodySource {
public:
    virtual ~IBodySource() {}
    /** Bytes that can be read now without waiting. */
    virtual size_t available() = 0;
    /** Read up to len bytes that are available; returns how many. */
    virtual size_t read(uint8_t* out, size_t len) = 0;
    /** False once the server has closed and every byte has been read. */
    virtual bool connected() = 0;
    virtual uint32_t nowMs() = 0;
    /** Let other tasks run while no byte is waiting. */
    virtual void wait() = 0;
};

enum class BodyRead { Complete, TooLong, CutShort, Stalled, Malformed };

/**
  Read a response body into buf.

  expectedLen is the length the server sent, or -1 when it sent none: then
  the body ends when the server closes the connection. Fails with TooLong
  when the body does not fit in capacity, CutShort when the connection closes
  before expectedLen bytes, and Stalled when no byte arrives for stallMs.
  Never writes past capacity.

  Pure: no hardware, no globals. Tested in test/test_body_read/.

  @returns the result; *got is the number of bytes read, whatever the result.
*/
BodyRead readBody(IBodySource& src, int32_t expectedLen, uint8_t* buf, size_t capacity,
                  uint32_t stallMs, size_t* got);

/**
  Read a body sent with Transfer-Encoding: chunked into buf, without the
  chunk sizes. Fails as readBody does, and with Malformed when a chunk size
  or the line after a chunk cannot be read. Trailer fields are skipped.

  @returns the result; *got is the number of body bytes read, whatever the
  result.
*/
BodyRead readChunkedBody(IBodySource& src, uint8_t* buf, size_t capacity, uint32_t stallMs,
                         size_t* got);

/** A short name for a result, for a log line. */
const char* bodyReadName(BodyRead result);

#endif
