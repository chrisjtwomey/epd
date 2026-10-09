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
| `test_support/` | Stub headers for `Arduino.h`, `WiFi.h`, `SPIFFS.h` and the ESP-IDF pieces, so your code compiles for the host. |

## Setting it up

Add a native environment to your `platformio.ini` that compiles your own
`setup()` together with the epd sources it calls:

```ini
[env:native_integration]
platform = native
test_framework = unity
test_build_src = yes
test_filter = test_integration
lib_deps = chrisjtwomey/EpdClient @ ^0.10.3
lib_ignore = EpdClient
epd = ${platformio.libdeps_dir}/${this.__env__}/EpdClient
build_flags =
	-std=c++14
	-Iinclude
	-I${this.epd}/include
	-I${this.epd}/test_support
	-Itest/test_integration
	-DLOG_LEVEL=0
	-DNATIVE
build_src_filter =
	+<app.cpp>
	+<${this.epd}/src/wake.cpp>
	+<${this.epd}/src/ota_offer.cpp>
	+<${this.epd}/src/backoff.cpp>
	+<${this.epd}/src/user_agent.cpp>

[env:native_integration-dev]
extends = env:native_integration
lib_deps =
epd = ${PROJECT_DIR}/../epd/firmware
```

List whichever epd sources your `app.cpp` actually calls; anything you leave
out fails to link and tells you so.

`lib_deps` downloads EpdClient from the registry: pin it at the same version
as your board environment. The package holds epd's sources and the stub
headers, and `epd` names its folder, so the paths compile only the sources
you list. `lib_ignore` keeps PlatformIO from building the whole library for
the host.

The `-dev` twin compiles the same sources from an epd checkout beside your
project, to try a change to epd before it is released
([CONTRIBUTING.md](../CONTRIBUTING.md#consumers)).

Then run it:

```sh
pio test -e native_integration
pio test -e native_integration-dev    # against the checkout
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
