# Issue 2 — No batch interaction or aggregate assertion: can't drive a full UI sweep

**Type:** Feature
**Repo:** https://github.com/Suydev/obscura

> **Filing note:** `POST /repos/Suydev/obscura/issues` returns **410 — "Issues has been disabled in
> this repository."** This is the full text, ready to paste once issues are re-enabled (or to file on
> the upstream repo). Nothing was posted.

## Summary

The MCP is an excellent observation tool and a poor test harness. Every capability needed to *prove a
UI works* — bulk interaction and aggregate pass/fail — is missing, so agents write throwaway scripts
for the proof while using the MCP for observation.

The dividing line observed in practice:

- **MCP is used for:** navigate, snapshot, console messages, screenshots, single clicks, evaluate.
- **Scripts are used for:** hosting, looping over many elements, and returning a verdict.

That split is correct. It only becomes a problem when the verdict — the part that gates a commit —
cannot be produced through the MCP at all.

## Gap 1 — `browser_click` handles exactly one element ref

There is no "click all matching this selector." Verifying a 9-route app with ~250 controls means
~250 individual MCP calls, each consuming a context window with a snapshot. That is the single
biggest driver of the cost of this kind of work, and it is why an agent here died on
`Prompt is too long` before finishing.

Measured context cost in the failed run: `Bash` output was **837,134 chars = 54% of all context**,
while `Read` was **13 KB** — roughly 62× cheaper. Interaction is the loop that fills the window.

## Gap 2 — no aggregate assertion

`browser_snapshot` and `browser_console_messages` return observations, not verdicts. Nothing in the
MCP answers:

- Do all 9 routes render without error?
- Are there any controls that do nothing when clicked (dead controls)?
- Did any template placeholder leak into the output (`{{...}}`, `undefined`, `NaN`)?
- Is the console clean?

All four are one JS expression each when written as a script. None are expressible today. The agent
had to write four separate probe files (`probe-counts.mjs`, `probe-groups.mjs`, `probe-dead.mjs`,
`audit.mjs`) — each a few KB, each a re-implementation of something the browser already knows.

## Gap 3 — no exit code

Scripts return an exit code, so a gate can be `npm test`-style: green/red, CI-enforceable. MCP calls
return text that a human or agent must interpret. Every gate in this project had to be re-expressed
as a script for this reason alone — including the negative controls that caught four separate real
bugs.

## Gap 4 — no uniform capture sweep

Screenshotting 9 routes at a fixed 1280×900 is 9 calls in the MCP and one function in a script.
Minor on its own; listed because it is the same missing "do this N times" primitive.

## Proposed surface

Two additions would cover gaps 1–3; gap 4 follows from either.

```
// batch interaction
browser_batch({ steps: [
  { click: "text=Save" },
  { click: "css=[data-testid=next]" },
  { waitFor: "text=Welcome" },
]})

// aggregate assertion — returns a verdict, not a page dump
browser_assert({
  routes: ["/", "/dashboard", "/settings"],
  renders: true,
  noTemplateLeaks: ["{{", "undefined", "NaN"],
  consoleClean: true,
})  ->  { pass: false, failures: [{ route: "/settings", why: "2 dead controls", detail: [...] }] }
```

The important property is that `browser_assert` returns **structured failures per route**, not a
boolean. A boolean tells you something is wrong; per-route failures tell you where, which is the
difference between one round trip and one round trip per route.

## Note on when to reach for a script

Not anti-script, and not an argument for removing capability. Scripts were still the right call for
this work, and the issue is that the *MCP could not do the load-bearing part*. A well-specified batch
and assert pair would let the whole verification live in one place, with the MCP doing what it is
already better at: looking at the page.

## Evidence

- 9 routes × ~250 controls, 0 dead controls / 0 template leaks / console clean — all produced by
  hand-written probes in `~/iso-sync/preview/serve/`, not by the MCP.
- Context-cost figures measured from a failed agent transcript (Bash 837,134 chars vs Read 13 KB).
- See `~/iso-sync/preview/VERIFICATION.md` for the full verification record.

## Environment

aarch64 Android / Termux, obscura `0.1.0-dev+143668f`.