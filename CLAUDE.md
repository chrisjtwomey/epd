# epd

## This repo

- Two PlatformIO libraries in `firmware/` (`EpdClient`, `EpdBoardInkplate`) and one pip package in `server/` (`epd_server`). They share one wire contract — the `EPD-Next-*` headers, whose prefix each product sets to its own name — and version together.
- Consumers (`inkplate10-weather-cal`, `canary`) sit beside this repo. canary takes the libraries from the PlatformIO registry and `epd-server` from PyPI, at one pinned release; its `-dev` environments use `symlink://../epd/firmware`. weather-cal still builds only through the symlink, and pins `epd-server` to a release tag on GitHub. A change here can break them: run their builds against this checkout too. If weather-cal breaks, say so in one line. Do not edit weather-cal to keep up.
- Before 1.0, a breaking change also gets no transition release and no data migration ([CONTRIBUTING.md](CONTRIBUTING.md#making-changes)). State its consequence in one line, for example that a board needs a USB flash. Then make the change.
- Tests live with the code they cover. Code that moves here brings its tests.
- Nothing under `server/tests` may need a network or a browser. `Page.save()` is tested with a fake `Renderer`; `DisplayServer` with Flask's test client.
- Nothing hardware-specific outside `firmware/boards/`. `EpdClient` depends on `IBoard` only; if a change needs an Inkplate type, it belongs in `EpdBoardInkplate` or behind a new `IBoard` method.
- Set the version only with `scripts/version.py`, never by hand: it sets every declaration, and the pins in the README, the docs and the examples.
- To try a change in a consumer's server, install this checkout editable after the consumer's requirements. Installed before them, it can lose to the pinned release.

## Docs

Read a doc only when the task needs it.

| When the task | Read |
|---|---|
| Needs the layout, or runs the tests | [CONTRIBUTING.md](CONTRIBUTING.md), "Layout" and "Tests" |
| Builds a consumer against a change, or publishes a release | [CONTRIBUTING.md](CONTRIBUTING.md), "Consumers" and "Publishing" |
| Changes what a product or a user sees of the kit | [README.md](README.md) |
| Changes the server package's API | [server/README.md](server/README.md) |
| Changes a config key, on the board or on the server | [docs/configuration.md](docs/configuration.md) |
| Changes `IBoard`, or adds a board | [docs/custom-board.md](docs/custom-board.md) |
| Changes the updates over the air | [docs/ota.md](docs/ota.md) |
| Changes a header or a route between the board and the server | [docs/protocol.md](docs/protocol.md) |
| Changes the order of a wake, or how a product tests it | [docs/testing.md](docs/testing.md) |
| Changes an example | its `README.md` in [examples/](examples/) |

## General rules when working in this codebase

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Goal-Driven Execution

**Define success criteria. Loop until verified. If tests exist, they must pass. If you weren't asked for tests, verify the code builds.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Code comments and documentation

### 1. Describe the present, not the change

Comments state how the code behaves now. They are not a changelog.

- No "changed to…", "now returns…", "previously…", "fixed so that…".
- No ticket or PR numbers standing in for an explanation.
- If a comment only makes sense to someone who saw the diff, cut it.

Git already holds the history, and a comment that narrates a change is stale the moment the next one lands.

### 2. Let the code carry the meaning

- Start a doc comment with a one-line summary of what the thing does.
- Inside a function body, reach for a better name, an extracted function, or a simpler conditional before reaching for a comment.
- If a body still seems to need one — a subtle contract, a load-bearing ordering, a trap the next reader will "tidy up" — ask before adding it.

Ask yourself: "Could I delete this comment by naming something better?" If yes, do that instead.

### 3. Say it once, and stop

- A sentence or two. A comment is not a design document.
- State what it does and what it hands back. Nothing more.
- Don't paraphrase the signature — the reader can see the parameters.
- Don't restate a system-wide idea in a low-level helper. Repeat an architectural rule everywhere and a reader starts hunting for the places it doesn't hold.

### 4. Assume competence

**Assume the reader has reasonable competence in the programming languages, principles, and practice.**

- Spend the words on what the code can't say: why this ordering, why this field is trusted without a guard, why this parse is a gate rather than a convenience.

The test: a comment that would read the same in any codebase isn't earning its place.

### 5. Plain language, not metaphor

**Name the thing itself — the function, the caller, the package, the type.**

- Borrowed imagery reads as precision but charges the reader a translation step.
- Tree and graph terms are the usual offenders: "low-level helper", not "leaf function"; "the packages that import it", not "its parents".
- Worse when the word is already taken — here "page" is a rendered image and "display" is the panel.

Ask yourself: "Does the metaphor explain this better than plain words would?" If you have to weigh it up, it doesn't.
