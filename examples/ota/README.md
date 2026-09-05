# ota

[`minimal`](../minimal), plus a panel that updates itself. Same page, same
settings; the server is given a directory of images, and the panel's
`setup()` takes an offered image, confirms it once a page is on the screen,
and boots the previous image when it is not.

What is different from `minimal`:

- `server.py` passes `firmware=FirmwareSettings(...)`. The server offers
  the newest `firmware/<version>.bin` to any panel that calls itself
  `my-display` and runs a different version.
- `src/main.cpp` reads the trial flag first, rolls back on any failure
  before a page is drawn, confirms after one, and then takes the offer.
  Every path out of a trial boot ends in one of the two.

[docs/ota.md](../../docs/ota.md) says why it is built this way.

## Seeing an update on the bench

Run the server as for `minimal`, from this directory, so `firmware/` is
beside `server.py`. Then:

1. Put your real values in `src/defaults.cpp`, and flash the panel over
   USB with `pio run -t upload`. This build is `v1.0.0`, and it provisions
   the panel with your settings. No later image needs them.
2. Change `CLIENT_VERSION` in `platformio.ini` to `v1.0.1`, build, and hand
   the image to the server:

   ```sh
   pio run
   cp .pio/build/release/firmware.bin firmware/v1.0.1.bin
   ```

   The filename is the version. Nothing else is needed.
3. Press RST on the panel and watch `pio device monitor -b 115200`. It
   fetches its page, draws it, sees the offer, downloads the image and
   restarts. The next lines are `trial boot of v1.0.1`, a page, and the
   confirmation. The server's log shows the same panel asking for the page
   as `v1.0.1`.

## Seeing a rollback

Make a release that cannot work: set `cfg.serverURL` in `src/defaults.cpp`
to an address nothing answers, such as `http://192.0.2.1:8080/clock.png`,
set `CLIENT_VERSION` to `v1.0.2`, build, and copy the image in as before.

Press RST. The panel takes `v1.0.2`, boots it on trial, cannot fetch a page,
and rolls back; the next boot is `v1.0.1` again, and the page is back. The
panel remembers that it rejected `v1.0.2` and will not take it a second
time, so fix the address, build `v1.0.3`, and copy that in.
