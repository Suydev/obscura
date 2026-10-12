# Agent-facing UI verification — four missing MCP primitives

Observed while verifying a 9-route static build of a real app on aarch64/Termux
(obscura `0.1.0-dev+143668f`).

**Status:** Issues are disabled on this fork (`POST /repos/Suydev/obscura/issues` → **410**).
Written up here as proposals. Not filed upstream.

## The short version

The MCP is a good observation tool and a poor test harness. That is a legitimate design — it is
built to look at pages, not to gate commits. The problem is that the *load-bearing* part of "prove
this UI works" cannot be expressed through the MCP at all, so every verification ends up as
hand-written scripts while the MCP does the easy half.

The four below are ordered by how much they actually cost.

---

## 1. No cross-call session or state persistence — **biggest one**

Every tool call is effectively a fresh browser session. There is no context reuse, so:

- Authentication must be **replayed on every single call**.
- Any multi-step flow (login → navigate → interact → assert) re-does its setup.
- A script performing 9 route checks re-authenticates 9 times.

Concretely: verifying a 9-route app required driving onboarding to completion before `/settings` would
load at all. Under stateless calls that sequence must be repeated for every check against that route.

**Proposed:** an addressable context that outlives a call.

```
ctx = browser_context({ storageDir, persist: true })
browser_context_use(ctx)        # subsequent calls reuse cookies/localStorage/session
```

Session persistence is the single highest-leverage addition for agentic UI work: it is what makes the
difference between "one flow" and "one flow per assertion."

## 2. No accessibility-tree snapshot

`browser_snapshot` does not exist in this build. For UI work the useful artifact is the a11y tree —
**role, name, checked, value, focusable** — not `innerHTML` and not a screenshot.

This is why the same number kept having to be hand-derived:

> "44 controls" took a script rather than one call.

An agent comparing a preview build against the real app needs exactly the a11y tree: it is the one
representation where "is this control present, named identically, and in the same state" is
answerable, and where a difference is a *semantic* difference rather than a pixel diff.

**Proposed:**

```
browser_snapshot({ format: "a11y" })
// -> [{ role: "button", name: "Save Changes", checked: null, focused: false }, ...]
```

Also worth exposing the node **ref** used by `browser_click` in that output, so a snapshot can be
acted on directly without a parallel lookup.

## 3. `browser_evaluate` returns double-encoded plain text

The return value comes back as a string, not a typed/JSON value. Consequences on every call:

- A `JSON.parse` wrapper and a try/catch.
- Truncation or escaping surprises with large objects.
- No distinction between `undefined`, `null`, and the string `"undefined"` — which matters directly,
  because `undefined` appearing in the DOM is one of the failure modes being hunted.

**Proposed:** return JSON directly, with a size guard and a documented truncation marker.

## 4. `browser_screenshot` rejects unknown schema keys

Passing `format` fails **every** shot, with no useful error — not an ignored field, not a clear
rejection. A schema error should either be honoured or reported precisely.

**Proposed:** validate against the schema and return something like
`unknown parameter "format"; supported: width, height, filePath, fullPage, quality`.

---

## Related: aggregate assertion and batch interaction

The companion gap. There is no "click every control on every route" and no verdict-returning
assertion, so both require scripts. If batch interaction and structured aggregate assertions existed,
most of the verification above would live in one place.

```js
browser_assert({
  routes: ["/", "/dashboard", "/settings"],
  noTemplateLeaks: ["{{", "undefined", "NaN"],
  consoleClean: true,
})
// -> { pass: false, failures: [{ route: "/settings", why: "2 dead controls", detail: [...] }] }
```

Per-route structured failures matter more than the boolean: a boolean says something is wrong,
per-route failures say where, which is the difference between one round trip and one per route.

---

## Not an MCP problem, but recorded here because it caused a wrong conclusion

**The aarch64 PNG encoder casts screenshots dark.** Measured live on the same origin, the DOM reports
`--bg: #ffffff` and `data-theme="light"`, while the PNG renders dark.

This caused an agent to conclude that its screenshots were of the **real app** rather than the build —
a confident, wrong conclusion that survived review and cost a full work cycle before anyone re-measured
the DOM instead of trusting the image.

Two lessons, both general:

1. **A screenshot's appearance is not evidence of origin.** Use a DOM assertion for that.
2. On aarch64 specifically, treat screenshot colour as unreliable — it is a known encoder artefact,
   not a signal.

---

## Summary table

| # | Gap | Cost | Proposal |
|---|---|---|---|
| 1 | No session/state persistence | Re-auth per call; multi-step flows unusable | addressable, persistent `browser_context` |
| 2 | No a11y-tree snapshot | control counts need scripts | `browser_snapshot({format:"a11y"})` |
| 3 | `browser_evaluate` double-encodes | parse wrapper every call; `undefined` ambiguous | return JSON with truncation marker |
| 4 | Screenshot rejects unknown keys | every shot fails, error unhelpful | validate and name the bad key |

Plus, separately documented: no primitive to serve a local directory at a known origin, which is the
hard blocker for verifying local builds at all.