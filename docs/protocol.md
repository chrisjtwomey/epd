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
  200 image/png
  X-Next-Refresh-Seconds: 7200         ← sleep this many seconds
  X-Next-URL: http://host/hourly.png   ← fetch this next time
```

The server is the only thing that knows when to wake and what to show. The
client does no timezone arithmetic and holds no schedule.

Both headers are optional. A client that receives neither keeps the value it
last had, or its compiled default on a cold boot, and asks for the same URL
again. That is what makes a server restart harmless.

## Identifying the client

Every request carries the panel's identity:

```
User-Agent: my-display/v1.2.0 (Inkplate10)
```

The grammar is `name/version (device)`. The name comes from `CLIENT_NAME`,
the version from `CLIENT_VERSION`, and the device from the board's
`deviceName()`. The comment is omitted when there is no device name.

The server uses the name to decide which firmware image, if any, is for this
panel, and the version to decide whether it already has it. Nothing else
depends on it, so a client that sends no User-Agent still gets its pages.

## Offering a firmware update

When the server holds an image for this client's product, and that image is
a different version, it adds two headers to the page response:

```
GET /<page>.png
  X-Firmware-Version: v1.6.0
  X-Firmware-URL: http://host/firmware.bin
```

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
