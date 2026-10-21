// Reading a response body: its length, its chunks, its end, and a server
// that stops.
#include <unity.h>
#include <cstdint>
#include <cstring>

#include "body_read.h"

void setUp() {}
void tearDown() {}

// A server that sends each piece at its time, then closes at closeAtMs.
// wait() moves the clock on by one millisecond.
class FakeSource : public IBodySource {
public:
    struct Piece {
        uint32_t atMs;
        const char* bytes;
    };

    FakeSource(const Piece* pieces, size_t count, uint32_t closeAtMs)
        : pieces_(pieces), count_(count), closeAtMs_(closeAtMs) {}

    size_t available() override {
        size_t n = 0;
        for (size_t i = next_; i < count_ && pieces_[i].atMs <= now_; ++i)
            n += strlen(pieces_[i].bytes) - (i == next_ ? offset_ : 0);
        return n;
    }

    size_t read(uint8_t* out, size_t len) override {
        size_t n = 0;
        while (n < len && next_ < count_ && pieces_[next_].atMs <= now_) {
            const char* piece = pieces_[next_].bytes;
            out[n++] = (uint8_t)piece[offset_++];
            if (offset_ == strlen(piece)) {
                ++next_;
                offset_ = 0;
            }
        }
        return n;
    }

    bool connected() override { return available() > 0 || now_ < closeAtMs_; }
    uint32_t nowMs() override { return now_; }
    void wait() override { ++now_; }

private:
    const Piece* pieces_;
    size_t count_;
    uint32_t closeAtMs_;
    uint32_t now_ = 0;
    size_t next_ = 0;
    size_t offset_ = 0;
};

// A connection that says bytes are ready, but whose read gives none.
class ReadFailsSource : public IBodySource {
public:
    size_t available() override { return 3; }
    size_t read(uint8_t*, size_t) override { return 0; }
    bool connected() override { return true; }
    uint32_t nowMs() override { return now_; }
    void wait() override { ++now_; }

private:
    uint32_t now_ = 0;
};

// Keeps what it is given, and refuses every write after the first ``okWrites``.
class FakeSink : public IBodySink {
public:
    explicit FakeSink(int okWrites = 1000) : okWrites_(okWrites) {}
    bool write(const uint8_t* data, size_t len) override {
        if (writes_++ >= okWrites_) return false;
        memcpy(kept + size, data, len);
        size += len;
        return true;
    }
    uint8_t kept[64] = {};
    size_t size = 0;

private:
    int okWrites_;
    int writes_ = 0;
};

static const uint32_t kStallMs = 5000;
static const uint32_t kNeverCloses = UINT32_MAX;

void test_a_known_length_arrives_in_pieces() {
    const FakeSource::Piece pieces[] = {{0, "hel"}, {10, "lo"}};
    FakeSource src(pieces, 2, kNeverCloses);
    uint8_t buf[5];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, got);
    TEST_ASSERT_EQUAL_MEMORY("hello", buf, 5);
}

void test_a_known_length_cut_short_fails() {
    const FakeSource::Piece pieces[] = {{0, "hel"}};
    FakeSource src(pieces, 1, 20);
    uint8_t buf[5];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::CutShort, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(3, got);
}

void test_a_known_length_past_the_buffer_fails_before_reading() {
    const FakeSource::Piece pieces[] = {{0, "hello"}};
    FakeSource src(pieces, 1, kNeverCloses);
    uint8_t buf[4];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::TooLong, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(0, got);
}

void test_bytes_past_a_known_length_are_left_unread() {
    const FakeSource::Piece pieces[] = {{0, "hello, and more"}};
    FakeSource src(pieces, 1, kNeverCloses);
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, got);
}

void test_an_unknown_length_ends_when_the_server_closes() {
    const FakeSource::Piece pieces[] = {{0, "hel"}, {100, "lo"}};
    FakeSource src(pieces, 2, 200);
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readBody(src, -1, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL_MESSAGE(5, got, "a pause between pieces is not the end");
    TEST_ASSERT_EQUAL_MEMORY("hello", buf, 5);
}

void test_an_unknown_length_that_fills_the_buffer_exactly_completes() {
    const FakeSource::Piece pieces[] = {{0, "hello"}};
    FakeSource src(pieces, 1, 10);
    uint8_t buf[5];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readBody(src, -1, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, got);
}

void test_an_unknown_length_past_the_buffer_fails_without_writing_past_it() {
    const FakeSource::Piece pieces[] = {{0, "hello"}, {10, "world"}};
    FakeSource src(pieces, 2, kNeverCloses);
    uint8_t buf[8];
    memset(buf, 0xAA, sizeof(buf));
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::TooLong, readBody(src, -1, buf, 6, kStallMs, &got));
    TEST_ASSERT_EQUAL(6, got);
    TEST_ASSERT_EQUAL_HEX8(0xAA, buf[6]);
    TEST_ASSERT_EQUAL_HEX8(0xAA, buf[7]);
}

void test_a_server_that_stops_sending_stalls() {
    const FakeSource::Piece pieces[] = {{0, "hel"}};
    FakeSource src(pieces, 1, kNeverCloses);
    uint8_t buf[5];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Stalled, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(3, got);
    TEST_ASSERT_EQUAL_UINT32(kStallMs, src.nowMs());
}

void test_a_read_that_gives_nothing_stalls() {
    ReadFailsSource src;
    uint8_t buf[5];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Stalled, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(0, got);
    TEST_ASSERT_EQUAL_UINT32(kStallMs, src.nowMs());
}

void test_the_stall_counts_from_the_last_byte() {
    const FakeSource::Piece pieces[] = {{4000, "hel"}, {8000, "lo"}};
    FakeSource src(pieces, 2, kNeverCloses);
    uint8_t buf[5];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readBody(src, 5, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, got);
}

void test_an_empty_body_completes() {
    FakeSource src(nullptr, 0, kNeverCloses);
    uint8_t buf[1];
    size_t got = 1;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readBody(src, 0, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(0, got);
}

static BodyRead readChunked(const FakeSource::Piece* pieces, size_t count, uint8_t* buf,
                            size_t capacity, size_t* got) {
    FakeSource src(pieces, count, kNeverCloses);
    return readChunkedBody(src, buf, capacity, kStallMs, got);
}

void test_chunks_are_joined_without_their_sizes() {
    const FakeSource::Piece pieces[] = {{0, "3\r\nhel\r\n"}, {10, "2\r\nlo\r\n0\r\n\r\n"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readChunked(pieces, 2, buf, sizeof(buf), &got));
    TEST_ASSERT_EQUAL(5, got);
    TEST_ASSERT_EQUAL_MEMORY("hello", buf, 5);
}

void test_a_chunk_split_across_reads_is_whole() {
    const FakeSource::Piece pieces[] = {{0, "1"}, {10, "0\r"}, {20, "\n0123456"},
                                        {30, "789abcdef\r\n0\r\n\r\n"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readChunked(pieces, 4, buf, sizeof(buf), &got));
    TEST_ASSERT_EQUAL(16, got);
    TEST_ASSERT_EQUAL_MEMORY("0123456789abcdef", buf, 16);
}

void test_extensions_upper_case_sizes_and_trailers_are_accepted() {
    const FakeSource::Piece pieces[] = {
        {0, "A;name=value\r\n0123456789\r\n0\r\nExpires: never\r\n\r\n"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readChunked(pieces, 1, buf, sizeof(buf), &got));
    TEST_ASSERT_EQUAL(10, got);
}

void test_an_empty_chunked_body_completes() {
    const FakeSource::Piece pieces[] = {{0, "0\r\n\r\n"}};
    uint8_t buf[1];
    size_t got = 1;
    TEST_ASSERT_EQUAL(BodyRead::Complete, readChunked(pieces, 1, buf, sizeof(buf), &got));
    TEST_ASSERT_EQUAL(0, got);
}

void test_chunks_past_the_buffer_fail_without_writing_past_it() {
    const FakeSource::Piece pieces[] = {{0, "4\r\nabcd\r\n4\r\nefgh\r\n0\r\n\r\n"}};
    uint8_t buf[8];
    memset(buf, 0xAA, sizeof(buf));
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::TooLong, readChunked(pieces, 1, buf, 6, &got));
    TEST_ASSERT_EQUAL(4, got);
    TEST_ASSERT_EQUAL_HEX8(0xAA, buf[4]);
}

void test_a_size_that_is_not_hex_is_malformed() {
    const FakeSource::Piece pieces[] = {{0, "x\r\nhello\r\n0\r\n\r\n"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Malformed, readChunked(pieces, 1, buf, sizeof(buf), &got));
}

void test_a_size_too_large_for_size_t_is_malformed() {
    const FakeSource::Piece pieces[] = {{0, "1000000000000000000000000\r\n"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Malformed, readChunked(pieces, 1, buf, sizeof(buf), &got));
}

void test_data_longer_than_its_size_is_malformed() {
    const FakeSource::Piece pieces[] = {{0, "3\r\nhello\r\n0\r\n\r\n"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Malformed, readChunked(pieces, 1, buf, sizeof(buf), &got));
}

void test_an_endless_size_line_is_malformed() {
    static char endless[2000];
    memset(endless, '0', sizeof(endless) - 1);
    const FakeSource::Piece pieces[] = {{0, endless}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Malformed, readChunked(pieces, 1, buf, sizeof(buf), &got));
}

void test_a_chunked_body_closed_mid_chunk_is_cut_short() {
    const FakeSource::Piece pieces[] = {{0, "5\r\nhel"}};
    FakeSource src(pieces, 1, 20);
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::CutShort, readChunkedBody(src, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(3, got);
}

void test_a_chunked_body_with_no_last_chunk_is_cut_short() {
    const FakeSource::Piece pieces[] = {{0, "5\r\nhello\r\n"}};
    FakeSource src(pieces, 1, 20);
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::CutShort, readChunkedBody(src, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, got);
}

void test_a_chunked_body_that_stops_stalls() {
    const FakeSource::Piece pieces[] = {{0, "5\r\nhel"}};
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Stalled, readChunked(pieces, 1, buf, sizeof(buf), &got));
}

void test_a_streamed_body_reaches_the_sink_in_buffer_sized_pieces() {
    const FakeSource::Piece pieces[] = {{0, "hello"}, {10, " world"}};
    FakeSource src(pieces, 2, kNeverCloses);
    FakeSink sink;
    uint8_t buf[4];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete,
                      streamBody(src, 11, sink, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(11, got);
    TEST_ASSERT_EQUAL(11, sink.size);
    TEST_ASSERT_EQUAL_MEMORY("hello world", sink.kept, 11);
}

void test_a_streamed_body_leaves_bytes_past_its_length_unread() {
    const FakeSource::Piece pieces[] = {{0, "hello, and more"}};
    FakeSource src(pieces, 1, kNeverCloses);
    FakeSink sink;
    uint8_t buf[16];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Complete,
                      streamBody(src, 5, sink, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, sink.size);
}

void test_a_streamed_body_cut_short_or_stalled_fails() {
    const FakeSource::Piece pieces[] = {{0, "hel"}};
    uint8_t buf[16];
    size_t got = 0;
    FakeSource closes(pieces, 1, 20);
    FakeSink first;
    TEST_ASSERT_EQUAL(BodyRead::CutShort,
                      streamBody(closes, 5, first, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(3, got);
    FakeSource stops(pieces, 1, kNeverCloses);
    FakeSink second;
    TEST_ASSERT_EQUAL(BodyRead::Stalled,
                      streamBody(stops, 5, second, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(3, got);
}

void test_a_sink_that_refuses_a_write_stops_the_body() {
    const FakeSource::Piece pieces[] = {{0, "hello"}, {10, "world"}};
    FakeSource src(pieces, 2, kNeverCloses);
    FakeSink sink(1);
    uint8_t buf[8];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::WriteFailed,
                      streamBody(src, 10, sink, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(5, got);
}

void test_a_streamed_read_that_gives_nothing_stalls() {
    ReadFailsSource src;
    FakeSink sink;
    uint8_t buf[8];
    size_t got = 0;
    TEST_ASSERT_EQUAL(BodyRead::Stalled,
                      streamBody(src, 5, sink, buf, sizeof(buf), kStallMs, &got));
    TEST_ASSERT_EQUAL(0, got);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_a_known_length_arrives_in_pieces);
    RUN_TEST(test_a_known_length_cut_short_fails);
    RUN_TEST(test_a_known_length_past_the_buffer_fails_before_reading);
    RUN_TEST(test_bytes_past_a_known_length_are_left_unread);
    RUN_TEST(test_an_unknown_length_ends_when_the_server_closes);
    RUN_TEST(test_an_unknown_length_that_fills_the_buffer_exactly_completes);
    RUN_TEST(test_an_unknown_length_past_the_buffer_fails_without_writing_past_it);
    RUN_TEST(test_a_server_that_stops_sending_stalls);
    RUN_TEST(test_a_read_that_gives_nothing_stalls);
    RUN_TEST(test_the_stall_counts_from_the_last_byte);
    RUN_TEST(test_an_empty_body_completes);
    RUN_TEST(test_chunks_are_joined_without_their_sizes);
    RUN_TEST(test_a_chunk_split_across_reads_is_whole);
    RUN_TEST(test_extensions_upper_case_sizes_and_trailers_are_accepted);
    RUN_TEST(test_an_empty_chunked_body_completes);
    RUN_TEST(test_chunks_past_the_buffer_fail_without_writing_past_it);
    RUN_TEST(test_a_size_that_is_not_hex_is_malformed);
    RUN_TEST(test_a_size_too_large_for_size_t_is_malformed);
    RUN_TEST(test_data_longer_than_its_size_is_malformed);
    RUN_TEST(test_an_endless_size_line_is_malformed);
    RUN_TEST(test_a_chunked_body_closed_mid_chunk_is_cut_short);
    RUN_TEST(test_a_chunked_body_with_no_last_chunk_is_cut_short);
    RUN_TEST(test_a_chunked_body_that_stops_stalls);
    RUN_TEST(test_a_streamed_body_reaches_the_sink_in_buffer_sized_pieces);
    RUN_TEST(test_a_streamed_body_leaves_bytes_past_its_length_unread);
    RUN_TEST(test_a_streamed_body_cut_short_or_stalled_fails);
    RUN_TEST(test_a_sink_that_refuses_a_write_stops_the_body);
    RUN_TEST(test_a_streamed_read_that_gives_nothing_stalls);
    return UNITY_END();
}
