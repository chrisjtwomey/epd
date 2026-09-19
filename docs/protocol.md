# The HTTP contract

Everything between a panel and its server is plain HTTP. Two headers on a
page response carry the whole schedule; two more offer a firmware update.
There is no state on either side beyond that.

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
client does no timezone arithmetic and holds no schedule.

Both headers are optional. A client that receives neither keeps the value it
last had, or its compiled default on a cold boot, and asks for the same URL
again. That is what makes a server restart harmless.

## Identifying the client

Every request carries the panel's identity in two headers, from the
`CLIENT_NAME` and `CLIENT_VERSION` build flags:

```
EPD-Device: my-display
EPD-Device-Version: v1.2.0
```

The server uses the name to decide which firmware image, if any, is for this
panel, and the version to decide whether it already has it. It logs both, so
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

Every response carries the server's version and its clock:

```
EPD-Server-Version: 0.1.0
EPD-Server-Epoch-Seconds: 1758234000
```

The version is whatever the project passes as `server_version`, and defaults
to the version of the `epd_server` package. Both headers are unconditional,
so `curl -I` against any route tells you what a deployment is running.

The clock is UTC seconds at the moment the server answered. A board without
a clock of its own can keep time from it, which is one fewer service to
reach than NTP and, more to the point, guarantees the two agree about when a
schedule falls due. Hold it as an offset from the board's own uptime rather
than setting a clock from it, so a correction can never send timestamps
backwards.

## When a sensor board posts next

A board that posts readings on a schedule can take the schedule from the
server too. The project passes a function of the time now:

```python
DisplayServer(..., sensor_poll=lambda now: seconds_until_next_post(now))
```

and every response then carries its answer:

```
EPD-Next-Sensor-Poll-Seconds: 240
```

It goes on every response, not only the one to a readings post, so a board
learns it from whatever it last asked, and it is independent of
`EPD-Next-Display-Refresh-Seconds`: the panel and the sensors keep their own
schedules. The client reads it into `PageResponse::nextSensorPollSeconds`,
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
document is sound; only the pairing is wrong, and fixing whichever end is
older makes it acceptable again.

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
a different version, it adds two headers to the page response:

```
GET /<page>.png
  EPD-Server-Firmware-Version: v1.6.0
  EPD-Server-Firmware-URL: http://host/firmware.bin
```

The version travels beside the URL because the panel checks it before it
downloads anything: against the version it is running, and against the one
it last rolled back from. A URL on its own would let a bad release loop.

### Panels flashed before these header names

The names have changed twice, and the server still speaks both older sets so
that no deployed panel needs a cable to catch up.

Before the prefix, every name began with `X-` and the identity headers were
called `X-Client-Name` and `X-Client-Version`. The server reads those from a
request when the current ones are absent, and sends `X-Next-Refresh-Seconds`,
`X-Next-URL`, `X-Server-Version`, `X-Server-Firmware-Version` and
`X-Server-Firmware-URL` beside the current names on every response.

Before that, a panel stated itself only in its User-Agent and read the offer
as `X-Firmware-Version` and `X-Firmware-URL`. When no identity header of
either generation is present, the server falls back to parsing the
User-Agent and sends that pair too. Such a panel takes the one update that
teaches it the current contract and never needs the fallback again.

Both fallbacks are temporary. The server logs a line naming any panel that
arrives by the User-Agent route, so you can see when none do.

The image itself is a separate route:

```
GET /firmware.bin
  200 application/octet-stream, with Content-Length and x-MD5
  304 when the request's x-ESP32-version equals the version held
  404 when the server holds no image
```

`x-MD5` is what the ESP32 update library checks the download against, so it
must be the md5 of the exact bytes served.

The client fetches the image only after it has drawn its page. A failed
update therefore costs nothing on the panel: the wake ends the way it would
have ended anyway, and the next one tries again.

See [Updates over the air](ota.md) for what the panel does with the image.

## Sending data back

A panel that is awake can post to the server:

```
POST /<name>
  Content-Type: application/json
  {"temperature": 19.4, "humidity": 58}
  204, or 200 with the handler's JSON
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
GET /<name>?device=inkplate5-env-monitor&before=1757443200
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

## Status

```
GET /
  200 application/json
```

Lists the pages served, the schedule, the seconds until the next wake, the
page that wake will ask for, and the firmware image held, if any. Useful for
checking a deployment without waiting for a panel.
