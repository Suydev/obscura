# Issue 1 — No primitive to serve a local directory at a known origin

**Type:** Feature
**Repo:** https://github.com/Suydev/obscura

> **Filing note:** `POST /repos/Suydev/obscura/issues` returns **410 — "Issues has been disabled in
> this repository."** This is the full text, ready to paste once issues are re-enabled (or to file on
> the upstream repo). Nothing was posted.

## Summary

The MCP exposes no way to serve a local directory. There is no static-server tool and no `file://`
navigation, so any local build under development is unreachable until the agent hand-writes a static
server in a shell script.

This is the hard blocker. Every other gap is ergonomics; this one makes a class of work impossible
without leaving the MCP.

## What an agent has to do today

```js
// serve-preview.mjs — 1,509 bytes, written by hand, re-written by every agent
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
// ... route table, MIME map, no-cache headers
```

Then every agent rediscovers that:

- The server must expose the build at the **site root**, not under a subpath. A build served at
  `/preview/index.html` cannot prove it renders "from its own origin" — the real app also answers on
  `/`, so the two are indistinguishable from a screenshot alone.
- `file://` is not a substitute; it changes relative-path resolution, which is exactly what you want
  to test.

## Concrete failure this caused

Verifying a static build of a 9-route app:

1. Agent A screenshotted the build and got a **dark** UI.
2. Agent A concluded "these screenshots are of the real app, not the preview," and reported the demo
   unproven.
3. That conclusion was wrong on two counts, and cost a full work cycle before anyone re-checked:
   - `:8802` was serving `docs/` correctly; the build lived at `/preview/`. The build *had* been
     screenshotted correctly.
   - The dark rendering was an **encoder artefact** — measured live on the same origin,
     `data-theme="light"`, `--bg: #ffffff`, `bodyBg: rgb(255,255,255)`.
4. The build was later proven from a purpose-built server on a different port, `ROOT = docs/preview`,
   where `/` *is* the build and no path can reach the real app.

The generalizable lesson: **without a primitive that binds "serve this directory at the origin,"
every origin-identity claim rests on inference from pixels.** That is a weak foundation, and here it
produced a confidently wrong conclusion that survived two agents.

## Proposed surface

Not necessarily a new server — the missing thing is the ability to declare an origin:

```
serve({ root: "/abs/path/to/build", port: "auto" })  -> { origin: "http://127.0.0.1:PORT", stop() }
```

- `port: "auto"` avoids the collisions that come from agents hardcoding 8802/8811 and colliding with
  each other.
- Serving at `/` is the default because origin identity is the whole point.
- `stop()` matters: agents currently leak a listener per run.

A file URL that reports as a distinct, inspectable origin would also satisfy this if the
implementation preference differs.

## Evidence

- Build: 9 routes, 0 dead controls, 0 template leaks, console clean, proven from
  `ROOT = docs/preview` on an isolated port.
- Identity had to be asserted by a harness probe emitting `{build: true, origin: "..."}` — i.e. the
  agent had to build its own mechanism because the MCP offered none.
- Prior work: `~/iso-sync/preview/VERIFICATION.md`, `~/iso-sync/preview/serve/serve-preview.mjs`.

## Environment

aarch64 Android / Termux, obscura `0.1.0-dev+143668f`.