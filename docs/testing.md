# Testing your own project

The order of a wake is where the decisions live: how low the battery has to
be before you skip the fetch, how long to wait after a failure, whether to
take a firmware update. epd deliberately leaves those to you, which means
they are yours to test.

You can run all of it on your laptop. No board, no cable, no network.

## What epd ships for this

| | |
|---|---|
| `include/MockBoard.h` | An `IBoard` that records what it was asked to do instead of driving a panel. Assert on the calls. |
| `test_support/` | Stub headers for `Arduino.h`, `WiFi.h`, `SPIFFS.h`, `ezTime.h` and the ESP-IDF pieces, so your code compiles for the host. |

## Setting it up

Add a native environment to your `platformio.ini` that compiles your own
`setup()` together with the epd sources it calls:

```ini
[env:native_integration]
platform = native
test_framework = unity
test_build_src = yes
test_filter = test_integration
build_flags =
	-std=c++14
	-Iinclude
	-I../epd/firmware/include
	-I../epd/firmware/test_support
	-Itest/test_integration
	-DLOG_LEVEL=0
	-DNATIVE
build_src_filter =
	+<app.cpp>
	+<../../epd/firmware/src/wake.cpp>
	+<../../epd/firmware/src/ota_offer.cpp>
	+<../../epd/firmware/src/backoff.cpp>
	+<../../epd/firmware/src/user_agent.cpp>
```

List whichever epd sources your `app.cpp` actually calls; anything you leave
out fails to link and tells you so.

Then run it:

```sh
pio test -e native_integration
```

Two things make this work. First, keep the order of a wake in its own file —
`src/app.cpp` with a `run_app()` in it — and let `src/main.cpp` do nothing
but name the board and call it. `main.cpp` cannot be compiled for the host,
because it names the Inkplate driver, which only builds for the ESP32.
`app.cpp` can.

Second, stub the few calls that reach hardware. Give your test directory a
`stubs.cpp` defining the network and sleep functions, so the test can say
"the fetch fails twice then succeeds" and watch what your code does.

Give the board environments `test_ignore = *`, or `pio test` with no
environment will try to upload a test to a panel.

Running epd's own tests is a different job, and it belongs to whoever is
changing epd. It is in [CONTRIBUTING.md](../CONTRIBUTING.md#tests).
