# Contributing to epd

This guide explains the layout, how to run the tests, and how to make and submit changes.

For what the kit is and how a project uses it, start with [README.md](README.md) and [server/README.md](server/README.md).

## Layout

```
firmware/                 EpdClient — PlatformIO library (hardware-agnostic client)
  include/  src/          IBoard, the steps of a wake, network / sleep / display helpers
  boards/inkplate/        EpdBoardInkplate — the Inkplate IBoard, a separate library
  test/                   host-only tests, two environments
  test_support/           stub headers a consumer needs to test its own sequence
  platformio.ini          test project only; excluded from the published library
server/                   epd-server — pip package
  epd_server/             config, registry, cache, page, render, quantise,
                          source, pipeline, scheduling, mqtt, app, firmware,
                          network, certificate, install
    static/install/       the install page, install-firmware.sh, and
                          esptool-js kept at a fixed version with its licences
  tests/
docs/                     configuration, ota, protocol, testing, custom-board
examples/                 minimal, the README's quickstart as a project; ota, the
                          same with updates on; live-data, a server with a
                          data source, a cache and two pages. The first two
                          are the only ESP32 builds
```

Two libraries, not one, so that a project on other hardware never pulls in
InkplateLibrary. Nothing in `firmware/src` may name an Inkplate type: if a
change needs one, it goes in `boards/inkplate/`, or behind a new method on
`IBoard`.

A project that uses epd takes both libraries from the PlatformIO registry
and `epd-server` from PyPI, at a release ([Publishing](#publishing)). To
change epd and try the change in a project, check this repo out beside the
project and build the project's `dev` environment, which uses
`symlink://../epd/firmware` ([Consumers](#consumers)). A `lib_deps` git URL
cannot do this, because it can only address a repository root, and these two
libraries sit in one tree.

## Tests

No device, network, or browser is needed for any test.

### Firmware

```sh
cd firmware
pio test -e native              # pure helpers: back-off, battery, refresh header parsing
pio test -e native_mock         # display + sleep against MockBoard
pio test -e native_settings     # loadConfig against a Preferences stub
cd ../examples/minimal
pio run -e dev                  # an ESP32 build of this checkout; the host tests never see the framework
```

`examples/minimal` is the README's quickstart, file for file, and
`server/tests/test_examples.py` fails when they differ. Change one and copy
it to the other.

The order of a wake belongs to the project that decides it, so its test does
too. A consumer runs one from its own repository, against `MockBoard.h` and
the stub headers this kit ships in `test_support/`. Setting that up is
[docs/testing.md](docs/testing.md); keep the two in step.

### Server

```sh
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

`Page.save()` is tested with a fake `Renderer`, `DisplayServer` with Flask's
test client, and `GreyscaleQuantiser(levels=4)` byte-for-byte against the
algorithm it replaced. Keep it that way: a test that needs Chromium or a
network belongs in a consumer, not here.

## Consumers

A project builds against this repo two ways, and a change here can break
either:

- Firmware: the project's default environment takes `chrisjtwomey/EpdClient`
  and `chrisjtwomey/EpdBoardInkplate` from the PlatformIO registry, pinned to
  a release. A second environment extends it and swaps only `lib_deps`, so
  nobody edits the tracked file to work on epd:

  ```ini
  [env:release]
  lib_deps =
  	chrisjtwomey/EpdClient @ ^x.y.z
  	chrisjtwomey/EpdBoardInkplate @ ^x.y.z

  [env:dev]
  extends = env:release
  lib_deps =
  	symlink://../epd/firmware
  	symlink://../epd/firmware/boards/inkplate
  ```

  `pio run -e dev` needs this repo checked out beside the project.
  `PLATFORMIO_DEFAULT_ENVS=dev` makes a plain `pio run` build it. PlatformIO
  still downloads the registry's EpdClient there, because EpdBoardInkplate
  depends on it, but the build compiles the checkout's. A project that has
  not moved to the registry yet builds only through the symlink.
- Server: `epd-server==x.y.z` from PyPI in `requirements.txt`.

Before opening a pull request, build a consumer against your branch: its
`dev` environments in its root, and `pytest` in its `server/` with this
checkout installed editable after the consumer's requirements. Installed
before them, it loses: `pip install -r` puts the pinned release back whenever
the checkout declares another version.

### Publishing

One version covers all three, declared in both `library.json` files,
`server/pyproject.toml` and `server/epd_server/_version.py`. The README, the
docs and the examples pin the published packages at it. Set all of them at
once, and never by hand:

```sh
python3 scripts/version.py          # what is declared now
python3 scripts/version.py 0.3.0    # set every declaration
```

`server/tests/test_version.py` fails if they ever disagree. That matters more
than tidiness: the server sends its own version to every client in the
`EPD-Server-Version` header.

The registry ships what `library.json`'s `export` rules allow, not the
directory, so build a consumer against the exact tarball before publishing
anything:

```sh
pio pkg pack firmware/ -o /tmp/EpdClient.tar.gz
pio pkg pack firmware/boards/inkplate/ -o /tmp/EpdBoardInkplate.tar.gz
```

Point a scratch project's `lib_deps` at `file:///tmp/EpdClient.tar.gz` and
build it. What resolves is what the registry will serve.

Then tag, and publish each library from its own directory:

```sh
pio pkg publish firmware/
pio pkg publish firmware/boards/inkplate/
```

Both are public: the repository already is, so a private package would hide
nothing while costing a subscription and a CI token. The registry lists a
version some minutes after it accepts it, and a machine that asked before
keeps the old list for a while.

Build the server package from the tag, not from the working tree, try the
wheel in a clean venv, and upload it to PyPI:

```sh
git archive v<version> server | tar -x -C /tmp/epd-release
cd /tmp/epd-release/server && python3 -m build
twine check dist/* && twine upload dist/*
```

`twine` takes a PyPI API token as the password of the user `__token__`. A
version on PyPI cannot be uploaded a second time.

Consumers then move their pins: `chrisjtwomey/EpdClient` and
`chrisjtwomey/EpdBoardInkplate` in `platformio.ini`, and `epd-server` in
`requirements.txt`.

## Making Changes

- Tests live with the code they cover. Code that moves here brings its
  tests. Add a test for every behaviour you add or change.
- Keep the wire contract stable. [docs/protocol.md](docs/protocol.md) lists
  every header a board reads and sends; renaming or removing one is a breaking
  change for every deployed device. Before 1.0 that is a minor release, with
  no old names kept beside the new ones: a board on older firmware is
  reflashed.
- Comments describe the present, not the change. Git holds the history.
- Fork the repository, and make a new branch for your changes.
- Follow the policy in the [AI-Assisted Code](#ai-assisted-code) section when AI tools are used.

## AI-Assisted Code

If your change was written by an AI tool (such as GitHub Copilot, Claude, or similar), add a `Co-Authored-By` trailer to the commit message naming the tool.

Example commit message:

```
Add new feature X

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Submitting Pull Requests

- Ensure your changes build and pass tests, here and in the consumers.
- Open a pull request with a clear description of your changes.
- Reference any related issues.
