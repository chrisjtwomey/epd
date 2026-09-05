# The HTTP contract

Everything between a panel and its server is plain HTTP. Two headers on a
page response carry the whole schedule; two more offer a firmware update.
There is no state on either side beyond that.

Read this if you are debugging with `curl`, writing a client for hardware
epd does not cover, or serving epd panels from something other than
`epd_server`.

## Fetching a page

```
GET /<page>.png
  X-Client-Name: my-display            ← who is asking
  X-Client-Version: v1.2.0             ← and what it runs

  200 image/png
  X-Next-Refresh-Seconds: 7200         ← sleep this many seconds
  X-Next-URL: http://host/hourly.png   ← fetch this next time
  X-Server-Version: 0.1.0              ← which epd_server answered
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
X-Client-Name: my-display
X-Client-Version: v1.2.0
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

## Which server answered

Every response carries the version of the `epd_server` package serving it:

```
X-Server-Version: 0.1.0
```

It is unconditional, so `curl -I` against any route tells you what a
deployment is running.

## Offering a firmware update

When the server holds an image for this client's product, and that image is
a different version, it adds two headers to the page response:

```
GET /<page>.png
  X-Server-Firmware-Version: v1.6.0
  X-Server-Firmware-URL: http://host/firmware.bin
```

The version travels beside the URL because the panel checks it before it
downloads anything: against the version it is running, and against the one
it last rolled back from. A URL on its own would let a bad release loop.

### Panels flashed before these header names

A panel built before `X-Client-Name` existed states itself only in its
User-Agent, and reads the offer as `X-Firmware-Version` and
`X-Firmware-URL`. A server that spoke only the current names could never
reach it, and it would need a cable.

So when the two client headers are absent, the server falls back to parsing
the User-Agent, and sends the old header pair beside the new one. Such a
panel takes the one update that teaches it the current contract, and never
needs the fallback again.

This is temporary. The server logs a line naming any panel that arrives this
way, so you can see when none do; the fallback and the `X-Firmware-*`
headers go together at that point.

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
```

The client call is `postJson(url, userAgent, body)`, which returns the HTTP
status. The server side declares which names it accepts:

```python
DisplayServer(..., ingest={"readings": handler})
```

`POST /readings` then parses the body as a JSON object and calls
`handler(doc)`. A `ValueError` raised by the handler becomes a 400.

## Status

```
GET /
  200 application/json
```

Lists the pages served, the schedule, the seconds until the next wake, the
page that wake will ask for, and the firmware image held, if any. Useful for
checking a deployment without waiting for a panel.
