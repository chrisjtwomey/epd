# Contributing to epd

Thank you for your interest in contributing! This document explains the layout, how to run the tests, and how to make and submit changes.

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
                          source, pipeline, scheduling, mqtt, app
  tests/
docs/                     custom-board.md and other guides
```

Two libraries, not one, so that a project on other hardware never pulls in
InkplateLibrary. Nothing in `firmware/src` may name an Inkplate type: if a
change needs one, it goes in `boards/inkplate/`, or behind a new method on
`IBoard`.

## Tests

No device, network, or browser is needed for any test.

### Firmware

```sh
cd firmware
pio test -e native              # pure helpers: back-off, battery, refresh header parsing
pio test -e native_mock         # display + sleep against MockBoard
```

The order of a wake belongs to the project that decides it, so its test does
too. `inkplate10-weather-cal` runs one with `pio test -e native_integration`,
against `MockBoard.h` and the stub headers this kit ships in `test_support/`.

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

[inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal)
and [inkplate5-env-monitor](https://github.com/chrisjtwomey/inkplate5-env-monitor)
build against this repo:

- Firmware: `lib_deps = symlink://../epd/firmware` and
  `symlink://../epd/firmware/boards/inkplate`, so they need this repo checked
  out beside them. Their CI checks out both.
- Server: `epd-server @ git+https://github.com/chrisjtwomey/epd.git@main#subdirectory=server`
  in `requirements.txt`. pip honours `#subdirectory=` for VCS URLs only, so a
  git binary is needed where that is installed.

A change here can break them. Before opening a pull request, build at least
the weather calendar: `pio run` in its root and `pytest` in its `server/`.

### Publishing

The two firmware libraries publish to the PlatformIO registry separately,
from their own directories: `pio pkg publish` in `firmware/` and in
`firmware/boards/inkplate/`. Consumers then pin `chrisjtwomey/EpdClient@^x.y`
instead of the symlink. Tag the repo and point consumers' `requirements.txt`
at the tag instead of `@main` in the same release.

## Making Changes

- Tests live with the code they cover. Code that moves here brings its
  tests. Add a test for every behaviour you add or change.
- Keep the wire contract stable. The client reads exactly two headers,
  `X-Next-Refresh-Seconds` and `X-Next-URL`; anything else is a breaking
  change for every deployed device.
- Comments describe the present, not the change. Git holds the history.
- Please fork the repository and create a new branch for your changes.
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

Thank you for helping improve this project!
