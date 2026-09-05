# Updates over the air

A panel on a wall is hard to reach. It may be in a frame, or screwed to a
mount, and getting a USB cable to it means taking it down. So the panel
updates itself: it asks its server for a page as usual, and the server
answers with the page plus, when there is one, a newer version of the
panel's own software.

You flash the panel over USB once. After that, publishing a release is
enough.

## What happens at a wake

1. The panel fetches its page and draws it, exactly as it always does.
2. If the response offered a newer version, the panel downloads it.
3. It writes the image, restarts, and comes up running the new software.

The update is last on purpose. A download that fails, a server that has gone
away, a flat battery — none of it stops the picture reaching the screen. The
wake ends as it would have ended anyway and the next one tries again.

## Trial boots, and how a bad release undoes itself

The ESP32 has two program slots. The new image is written to the idle one,
and the panel restarts into it **on trial**. The bootloader will take the
new image back and boot the old one unless the software says it is working.

Your `setup()` decides what "working" means:

- Call `otaConfirm()` once the wake has done the thing the display exists to
  do — normally a page on the screen. Until then, nothing is committed.
- Call `otaRollback()` on any failure before that. The panel boots the
  previous image again, which is known to work.

Confirm before you take the next offer. A write to the idle slot is refused
while an image is still pending, so an unconfirmed image blocks the next
update.

A panel that rolled back remembers the version it rejected and will not take
that version again. Without that memory it would roll back, be offered the
same image, take it again, and loop. Publish the fix under a new version
number; the panel will take that one.

## Credentials, and the one USB flash

An image built by a release pipeline cannot contain your WiFi password. So
the panel keeps its own copy of the three settings that cannot be compiled
in — the server URL, the network name and its password — in the ESP32's own
storage (`Preferences`, namespace `epd`).

The rule is simple:

- If the running image carries a **real** value, it wins, and it is written
  to the panel's storage on the way past.
- If it carries only a **placeholder** — empty, `XXXX`, or anything
  containing `YOUR_` — the stored value wins.

So the build you flash over USB, with your real `src/defaults.cpp`,
provisions the panel. Every later image comes from CI with placeholders,
finds the stored values, and connects. One USB flash, and only one.

Nothing else from `defaults.cpp` is stored. The rest is code and comes from
the image, which means a change to, say, the MQTT settings needs a new
release rather than a new flash.

## The first update onto a new contract

The panel's headers changed once already, and could again. A panel is always
reachable by the server that speaks the names it was built to read, so the
rule is: the server learns a new name **before** the panel does, and keeps
answering the old one until no panel uses it. See [the HTTP
contract](protocol.md) for the fallback in force today.

## Forcing an update now

Press RST. The panel boots from the top — WiFi, fetch, draw, then the update
check — so an offered image is applied within a minute rather than at the
next scheduled wake.

Pressing reset during the write is safe. The pointer that says which slot to
boot is moved only after the whole image is written, so a reset before that
boots the old image and a reset after boots the new one. There is no
half-written state.

## Publishing an update

The server holds a directory of images named for their versions:

```sh
cp firmware.bin server/firmware/v1.6.0.bin
```

The filename **is** the version. Nothing else has to be written down, and
the newest file is the one offered.

To have the server fetch releases itself, give it a `source` block:

```yaml
client:
  firmware:
    enabled: true
    source:
      github: owner/repo
      asset: firmware.bin
      poll_seconds: 3600
```

It asks GitHub for the latest release on a background thread and takes the
named asset whenever the tag differs from the version it holds. An `ETag`
makes an unchanged answer cheap. For a private repository, set the token in
`CLIENT_FIRMWARE_SOURCE_TOKEN` rather than writing it into the file.

See [Configuration](configuration.md) for the rest of the block.

## Who gets offered what

An image is offered only when all of these hold:

- The block is enabled and the server holds an image.
- The panel sent `X-Client-Name` and `X-Client-Version`, and the name equals
  `client.firmware.product`. Offering one product's image to another
  product's panel would brick it.
- The panel's version is a clean tag — `v1.5.1`, not `v1.5.1-3-gab12cd4`,
  `-dirty` or `dev`. A panel on your bench built from a working tree is left
  alone, so you are not flashed back to the last release mid-experiment. Set
  `offer_dev_builds: true` to override that, on a bench server only.
- The version differs from the one the panel reports.

Battery is the panel's own decision, not the server's. A typical `setup()`
skips the update below about 20% and takes it at the next wake instead.
