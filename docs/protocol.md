# The HTTP contract

Everything between a panel and its server is plain HTTP. Two headers on a
page response carry the whole schedule; two more offer a firmware update.
There is no state on either side beyond that, except a key each board may
share with its server ([Board keys](#board-keys)). A server may serve the same
routes over HTTPS on a second port, for a browser; the panels never use it.

Read this if you are debugging with `curl`, writing a client for hardware
epd does not cover, or serving epd panels from something other than
`epd_server`.

## The names

Every header starts with the product's own name, because the responses are
the product's interface and a reader of the traffic should not have to know
what library built it. The examples below use `EPD-`, which is the default.

A project sets its own on both sides, and the two must agree:

```python
DisplayServer(..., header_prefix="Canary")
```

```ini
build_flags = -DEPD_HEADER_PREFIX='"Canary"'
```

A mismatch is silent. The client simply never sees the headers and falls
back to its compiled-in interval, so set both from one place.

## Value lengths

The board keeps each text header in a field of fixed size. It drops a longer
value with a warning and acts as if the header was not sent, because a URL or
a version cut short is wrong. A dropped `EPD-Next-URL` leaves the board on the
address it has; a dropped firmware URL or version means no update is offered.

| Header | Most characters |
|---|---|
| `EPD-Next-URL` | 255 |
| `EPD-Server-Firmware-URL` | 255 |
| `EPD-Server-Firmware-Version` | 31 |
| `EPD-Server-Version` | 31 |
| `EPD-Server-Timezone` | 63 |

## Fetching a page

```
GET /<page>.png
  EPD-Device: my-display                     ← who is asking
  EPD-Device-Version: v1.2.0                 ← and what it runs

  200 image/png
  EPD-Next-Display-Refresh-Seconds: 7200     ← sleep this many seconds
  EPD-Next-URL: http://host/hourly.png       ← fetch this next time
  EPD-Server-Version: 0.1.0                  ← which server answered
  EPD-Server-Epoch-Seconds: 1758234000       ← and what time it thinks it is
```

The server is the only thing that knows when to wake and what to show. The
client does no timezone arithmetic and holds no schedule. A server may also
answer the address with another page, chosen from the data just before the
wake ([Choosing a page from the data](../server/README.md#choosing-a-page-from-the-data)).

Both headers are optional. A client that receives neither keeps the value it
last had, or its compiled default on a cold boot, and asks for the same URL
again. That is what makes a server restart harmless.

The board reads a page, and any other answer it fetches with `downloadFile`
or `downloadSigned`, into one buffer of the `Content-Length`. With no length,
a server sends the body in chunks (`Transfer-Encoding: chunked`) or closes
the connection to end it, and the buffer is the size the project allows. A
firmware image is not read this way: it streams to flash
([ota.md](ota.md)). The download fails when:

- the `Content-Length` is over the size the project allows. This fails
  before any buffer is allocated, so a server cannot make the board reserve
  more memory than the project chose;
- the server sends no byte for 5 s;
- it closes before the `Content-Length` it sent, or before the last chunk;
- with no `Content-Length`, the body is longer than the size the project
  allows;
- a chunk size cannot be read;
- the body is empty, with or without a length. Every answer a board fetches
  carries a body, so an empty one is a fault, and a caller never gets a
  buffer it would have to check for size 0.

The headers are read before the body, so a download that fails still hands
back what the server said about the next wake, its clock and firmware.

## Identifying the client

Every request carries the panel's identity in two headers, from the
`CLIENT_NAME` and `CLIENT_VERSION` build flags:

```
EPD-Device: my-display
EPD-Device-Version: v1.2.0
```

The server uses the name to decide which firmware image, if any, is for this
panel, and which board key signs its answers to it; and the version to decide
whether it already has the image. A board with a key also sends that key's id
as `EPD-Key-Id` on the requests whose answers must be signed
([Board keys](#board-keys)). It logs both, so
you can see which board asked for what.

A request also carries a conventional User-Agent, built from the same two
values plus the board's `deviceName()`:

```
User-Agent: my-display/v1.2.0 (Inkplate10)
```

That one is for your access log and for anything else that reads a
User-Agent. It decides nothing. Identity has a single source, so there is no
rule to write for what should happen when the two disagree.

None of this is needed to serve a page: a client that sends no headers at
all still gets its images. An update is offered only when both headers are
present and well formed — a name matching `[A-Za-z0-9][A-Za-z0-9._-]*`, and
a version that could be a filename, since the filename is where the server
keeps it.

## Which server answered, and when

Every response carries the server's version, its clock and its time zone:

```
EPD-Server-Version: 0.1.0
EPD-Server-Epoch-Seconds: 1758234000
EPD-Server-Timezone: IST-1GMT0,M10.5.0,M3.5.0/1
```

The version is whatever the project passes as `server_version`, and defaults
to the version of the `epd_server` package. The version and the clock are
unconditional, so `curl -I` against any route tells you what a deployment is
running.

The clock is UTC seconds at the moment the server answered. A board without
a clock of its own can keep time from it, which is one fewer service to
reach than NTP and, more to the point, guarantees the two agree about when a
schedule falls due. EpdClient sets the board's clock, time zone and RTC from
every page it fetches (`keepServerTime()`). A board that stamps readings with
the clock does better to hold it as an offset from its own uptime, so a
correction can never send a stamp backwards.

The time zone is `server.timezone` as a POSIX TZ string, the form a C
library's `TZ` takes, so a board shows local time with no lookup of its own.
It is the footer of the zone's file in the server's zone database, sent as
written. Two databases can write one zone two ways: Debian writes
Europe/Dublin as above, with winter as a negative daylight shift, and macOS
as `GMT0IST,M3.5.0/1,M10.5.0`. Both give the same local time to a reader of
the full POSIX form. A server whose zone has no IANA name, such as a fixed
offset, sends no time zone.

## When a board posts or syncs next

A board that posts readings, or syncs its state, on a schedule can take the
schedule from the server too. The project passes a function of the time now
and the name the board states in `EPD-Device`, None when it states none:

```python
DisplayServer(..., sensor_poll=lambda now, name: seconds_until_next_sync(name, now))
```

and every response to that board then carries its answer:

```
EPD-Next-Sensor-Poll-Seconds: 240
```

A board the function answers None for gets no header. It goes on every
response, not only the one to a readings post, so a board learns it from
whatever it last asked, and it is independent of
`EPD-Next-Display-Refresh-Seconds`: the panel and the sync keep their own
schedules. The client reads it into `ServerResponse::nextSensorPollSeconds`,
which stays 0 when the server sends none.

## When a board and a server cannot work together

A project whose boards and server take their versions from the same tags can
ask the server to refuse readings from a board that speaks a different
contract:

```python
DisplayServer(..., server_version="v0.2.2", version_gate=True)
```

Two versions match when their major numbers match, or, while the major is 0,
their major and minor. That is semantic versioning's own rule: before 1.0.0 a
minor release may break the contract, and after it only a major one may.
`epd_server.compat` and the firmware's `version_compat.h` apply the same
rule, so both ends reach the same answer about each other.

A post from a board that does not match is refused before its handler runs:

```
POST /readings
  EPD-Device-Version: v0.3.0

  409 application/json
  {"error": "version", "device": "v0.3.0", "server": "v0.2.2"}
```

409 is the one refusal a sender should hold on to rather than drop. The
document is sound; only the pairing is wrong. The same response offers the
image the server's version calls for, when it holds one, so taking it makes
the document acceptable again. A project that passes `on_refused` hears of
each refusal, with the board's name and version, and can say so on its
pages.

Three things the gate never does:

- **Refuse a board whose version cannot be read.** `dev`, a bare commit hash
  and a missing header all pass. Refusing them would silently stop the
  readings of every development build.
- **Refuse a page.** A board the server will not take readings from still
  fetches its pages, because the page response is where an update is
  offered. Refusing the page would leave it no way back.
- **Apply without being asked.** A server whose version comes from a
  different stream than its boards', such as the `epd-server` package's own
  default, would refuse everything.

## Offering a firmware update

When the server holds an image for this client's product, and that image is
a different version, it adds two headers to any response to that client: a
page, a readings post, a query, even a refusal.

```
GET /<page>.png
  EPD-Server-Firmware-Version: v1.6.0
  EPD-Server-Firmware-URL: http://host/firmware.bin
```

Which image depends on `version_gate`. Without it the server offers the
newest file. With it, it offers the highest version that can work with its
own, by the rule above (a build past a tag counts as higher the more commits
it is past it), whether that is newer than the board's or older: the
server's version is the one the boards follow. A gated server whose own
version cannot be read offers nothing, and it logs a warning each time it
offers a board an older image than the one it runs.

A server that holds several products (`client.firmware.products`) names the
image in the URL, `/firmware.bin?product=my-sensor&version=v1.6.0`, since the
one route serves them all.

The version travels beside the URL because the panel checks it before it
downloads anything: against the version it is running, and against the one
it last rolled back from. A URL on its own would let a bad release loop.

The image itself is a separate route:

```
GET /firmware.bin[?product=<name>&version=<version>]
  200 application/octet-stream, with Content-Length, x-MD5 and Content-Digest,
      and a signature for a board with a key (Board keys, below)
  304 when the request's x-ESP32-version equals the version held
  404 when the server holds no such image
```

Without the query it serves the image it would offer the default product.

`x-MD5` is what the ESP32's `Update` checks the download against, so it must
be the md5 of the exact bytes served. `Content-Digest` is their SHA-256, which
the signature covers.

The client fetches the image only after it has drawn its page. A failed
update therefore costs nothing on the panel: the wake ends the way it would
have ended anyway, and the next one tries again.

See [Updates over the air](ota.md) for what the panel does with the image.

## A USB flash

Two more routes serve what a first flash over USB writes. Nothing on the
panel asks for them; a person, the install page or the install script
does. The server serves that script at `GET /install-firmware.sh`
(text/plain, no-store), with its own address filled in.

```
GET /firmware.merged.bin[?product=<name>]
  200 application/octet-stream, with Content-Length, x-MD5 and Content-Digest
  404 text/plain when the server has no such product, or no merged image of
      the version it offers
```

The merged image is the bootloader, the partition table and the app in one
file, written from address 0. It is of the version the server offers that
product over the air, so a panel flashed with it is not updated straight
after.

```
GET /network.bin[?product=<name>]
  200 application/octet-stream, with Cache-Control: no-store
  404 text/plain when the server has no such product
  409 text/plain when a key it needs is not set; the body names them
```

The network settings are the panel's whole settings store, written at
0x9000 after the merged image. They hold the server URL, the Wi-Fi network
and its password, and the MQTT block when MQTT is on, with the product's
name as the client ID. They replace the whole store, the board's key
included, so a paired board pairs again after the flash. The server makes the file from its config at each
download. epd puts no sign-in in front of it, so anyone who can reach the
server can download it, password included, unless the project adds one
([the server reference](../server/README.md#from-a-terminal)).

Both routes take the default product without the query, as `/firmware.bin`
does. `/network.bin` exists when a project passes the server its network
settings and its firmware settings, which name the products; see
[Configuration](configuration.md#server-configyaml).

## Sending data back

A board can post to the server:

```
POST /<name>
  Content-Type: application/json
  {"temperature": 19.4, "humidity": 58}
  204, or 200 with the handler's JSON
  401 when the server requires signatures and this post has no good one
      (Board keys, below)
```

The body is one JSON object or an array of them, so a board that held
documents while the server was down can send them in one request.

The client call is `postJson(url, userAgent, body, rsp)`, which returns the
HTTP status. A POST response carries the server's version and clock like any
other, so `rsp` is how a board that never fetches a page gets them; pass
`nullptr` to ignore it. The server side declares which names it accepts:

```python
DisplayServer(..., ingest={"readings": handler})
```

`POST /readings` then parses the body and calls `handler(docs)` once, with
the list: a single object arrives as a list of one. What the handler returns
goes back as JSON with a 200, and None is a 204. A `ValueError` raised by
the handler becomes a 400.

To keep what arrives, the handler can be `ReadingsStore.add_many`: the store
writes the batch in one transaction, keeps each document by its `device`
and `ts` keys, ignores a second copy of the same pair, and answers with
which documents were new. That makes the route safe to retry. A sender that loses
the reply to a POST can send the same document again and change nothing, so
it never has to choose between a duplicate and a gap. See
[server/README.md](../server/README.md).

## Asking the server

A panel can also ask the server something:

```
GET /<name>?device=my-sensor&before=1757443200
  200 application/json
  404 when the server has no answer
```

The server side declares the names it answers, beside the ones it accepts:

```python
DisplayServer(..., queries={"calibration": handler})
```

`handler(args)` gets the query string as a dict, and what it returns is the
JSON answer. None becomes a 404 and a `ValueError` a 400. One name can have
both routes: a POST that sends something and a GET that asks for it back.

## Board keys

A server can take a board's posts only when the board signs them, and sign
its own answers to the board, with a key the two share. Each board has its
own key, agreed over the air and approved by a person. On the server this is
`epd_server.board_keys`; on the board, `board_key.h` and `postJson`.

### Pairing

```
POST /pair
  {"device": "my-sensor", "key": "<base64: the board's P-256 point, uncompressed>"}
  200 {"key": "<base64: the server's P-256 point, uncompressed>"}
  400 when the body is not that object, the server names no board of that name,
      or the key is not base64 of a point on the curve
```

Each side combines its own private half with the other's point (ECDH), and
derives the key from the shared secret with HKDF-SHA256: no salt, and
`epd board key <device>` as the info. The key never travels. The server
keeps it as pending until a person approves it (`BoardKeys.approve`), so a
device that pairs in a board's name gains nothing on its own. A new request
for a board replaces its pending key and leaves its approved one working
until the new one is approved.

A board with no key pairs when a refusal says `pair`. **A board that holds a
key pairs again only when that refusal is signed with its key** (A signed
refusal, below), because only its own server holds the key. Otherwise a
device that answered in the server's place could make the board take a key
of the device's own, and then sign its own images.

The board pairs on a FreeRTOS task of its own, with a 16 KB stack: mbedTLS's
P-256 maths needs more than a board's loop has to spare. The signature
buffers sit on the heap for the same reason.

The route exists only while the server requires signatures.

### A signed post

The signature follows RFC 9421 with hmac-sha256, under the label `sig1`,
and the body's SHA-256 as its Content-Digest (RFC 9530):

```
POST /readings
  Content-Digest: sha-256=:<base64 SHA-256 of the body>:
  Signature-Input: sig1=("@method" "@path" "@query" "content-digest");created=<epoch>;keyid="<16 hex>"
  Signature: sig1=:<base64 HMAC-SHA256 of the signature base>:
```

The key id is the first 16 hex digits of the key's SHA-256. The signature
carries no `alg` parameter: the key decides it, as RFC 9421 advises. The
server takes a signature made within 300 s of its own clock, and takes each
one once.

A post the server refuses gets a 401 that says why:

```
401 application/json {"problem": "<words for the log>"}
  EPD-Key: pair | pending | clock | refused
```

| `EPD-Key` | Why | What the board does |
|---|---|---|
| `pair` | No signature, a key the server does not hold, or one it no longer takes posts under | Pairs, then posts once more. A board with a key does so only when the refusal is signed with that key; otherwise it keeps its key, and logs that a USB install clears it |
| `pending` | The key waits for a person's approval | Keeps the document for later |
| `clock` | Signed more than 300 s from the server's clock | Takes `EPD-Server-Epoch-Seconds`, signs again, posts once more. Without that header, keeps the document for later |
| `refused` | The body, path or query changed, a signature used before, or another board's key | Keeps the document for later |

`postJson` does all of that, so a project only keeps the body when the
answer is a 401.

### A signed refusal

A refusal of a post that is shown to be signed with a key the server holds
is itself signed with that key, as an answer is (below), and also over the
post's `"content-digest";req`, so it answers that post alone:

```
401
  Content-Digest: sha-256=:<base64 SHA-256 of the refusal's body>:
  Signature-Input: sig1=("@status" "content-digest" "@method";req "@path";req "@query";req "content-digest";req);created=<epoch>;keyid="<16 hex>"
  Signature: sig1=:<base64 HMAC-SHA256>:
```

The keys it holds for this are a board's approved one, its pending one, and
the last four it stopped using: rejected, forgotten, or replaced by an
approval. The server takes no post under a key it stopped using. It keeps
them so that a board still on one can be told, in a way it can trust, to pair
again, and gets its answers signed with it until it does.

### A signed answer

For a board whose key the server holds, the server signs the image and its
answer to each query a project names (`signed_queries`):

```
200
  Content-Digest: sha-256=:<base64 SHA-256 of the body>:
  Signature-Input: sig1=("@status" "content-digest" "@method";req "@path";req "@query";req);created=<epoch>;keyid="<16 hex>"
  Signature: sig1=:<base64 HMAC-SHA256>:
```

The `;req` components are the request's, so no answer can stand in for
another: the settings of one board for another's, or the image of one
version for another's. The server picks the key by the `EPD-Device` header
and the `EPD-Key-Id` the board sends with its key's id: any key it holds for
that board, so a board that waits for approval keeps its settings and its
updates. Without `EPD-Key-Id` it signs with the approved key. A board with a
key takes such an answer only with a good signature made within 300 s of its
clock, or of any time while its clock is not set: `downloadSigned`, and the
update download ([Updates over the air](ota.md#signed-images)).

### While the server does not require signatures

It takes every post, signed or not, offers no pairing, and goes on signing
its answers for each board whose key it holds. A board keeps its key, so the
check can be turned off and on again without a new pairing.

A USB install writes the board's settings store anew, so the board loses
its key and pairs again at its first refused post. **A server that loses its
keys file leaves each board with a key unable to take the server's settings
and images, and, with signatures required, its posts:** the server can no
longer sign a `pair` the board would trust. A USB install clears the board's
key, and it pairs again.

## Status

```
GET /
  200 application/json
```

Lists the pages served, the schedule, the seconds until the next wake, the
page that wake will ask for, and the firmware image held, if any. Useful for
checking a deployment without waiting for a panel.
