# Watch agent sessions live

Obscura is headless, so an agent driving it through MCP, Puppeteer, or Playwright works invisibly. The CDP screencast surface lets you stream what the browser sees to a local tab while the agent works, which helps when supervising long tasks or debugging what an agent clicked.

This guide builds a small live viewer on top of `obscura serve`. It uses only Node's built-in modules and its native WebSocket client (Node 21+).

## How it works

> Note for Android/Termux. `obscura serve` runs its WebSocket server with a
> userspace async runtime, and that runtime is incompatible with the proot
> translation layer used to run it on Android. The server serves HTTP fine, but
> each WebSocket client connection can make it crash with an `os error 38
> (Function not implemented)`. Run the tool on native Linux/VM instead. If you
> must use Termux, a fresh `obscura serve` survives for a while; restart it when
> it dies.

1. Start the CDP server:

```bash
obscura serve --port 9222
```

2. Run the viewer script below:

```bash
node watch.mjs
```

3. Open http://localhost:8080 in a browser. The first frame is the blank page; navigate it to see live updates:

```bash
curl "http://localhost:8080/navigate?url=https://example.com"
```

The script attaches to the CDP endpoint, captures the current page twice a second with `Page.captureScreenshot`, and forwards JPEG frames to your browser over Server-Sent Events.

```js
#!/usr/bin/env node
// Live view for obscura serve.
//
// Streams what a headless obscura browser sees to any local browser tab,
// so you can watch an agent (MCP, Puppeteer, Playwright) work in real time.
//
// Usage:
//   obscura serve --port 9222
//   node tools/live-view.mjs [cdpPort] [httpPort]
//
// No dependencies. Requires Node 21+ (native WebSocket).
//
// A passive viewer cannot receive Page.startScreencast frames once an agent
// session takes over, because those frames stream to the driving session.
// Instead we poll Page.captureScreenshot, which always reflects the current
// page state regardless of which session navigated.

import http from "node:http";

const cdpPort = process.argv[2] ?? 9222;
const httpPort = Number(process.argv[3] ?? 8080);
const INTERVAL_MS = 500; // capture cadence while running

const clients = new Set();
let latest = null;
let sessionId = null;
let ws = null;
let call = null;
let generation = 0;

const page = `
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Obscura live view</title>
<style>body{margin:0;background:#111;display:grid;place-items:center;height:100vh}
img{max-width:100%;max-height:100%}</style></head>
<body><img id="s" alt="live page">
<script>
const img = document.getElementById("s");
let old = null;
const es = new EventSource("/events");
es.onmessage = (e) => {
  const bytes = Uint8Array.from(atob(e.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "image/jpeg" }));
  img.src = url;
  if (old) URL.revokeObjectURL(old);
  old = url;
};
</script></body>
</html>`;

const server = http.createServer((req, res) => {
  if (req.url === "/events") {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-store",
      Connection: "keep-alive",
    });
    res.socket.setNoDelay(true);
    if (latest) res.write(`data:${latest}\n\n`);
    clients.add(res);
    req.on("close", () => clients.delete(res));
  } else if (req.url.startsWith("/navigate")) {
    const url = new URL(req.url, "http://x").searchParams.get("url");
    if (url && sessionId) {
      const full = url.startsWith("http") ? url : `https://${url}`;
      call("Page.navigate", { url: full }, sessionId).catch(() => {});
    }
    res.writeHead(204);
    res.end();
  } else if (req.url === "/favicon.ico") {
    res.writeHead(204);
    res.end();
  } else {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(page);
  }
});

server.on("error", (err) => {
  console.error(`cannot listen on port ${httpPort}: ${err.message}`);
  process.exit(1);
});

server.listen(httpPort, "127.0.0.1", () => {
  console.log(`live view: http://localhost:${httpPort}`);
});

function broadcast(base64) {
  latest = base64;
  for (const res of clients) {
    try {
      if (res.writable) res.write(`data:${base64}\n\n`);
    } catch {
      clients.delete(res);
    }
  }
}

function connect() {
  const gen = ++generation;
  sessionId = null;
  ws = new WebSocket(`ws://127.0.0.1:${cdpPort}/devtools/browser`);

  let id = 0;
  const pending = new Map();
  call = (method, params = {}, sess) =>
    new Promise((resolve, reject) => {
      const mid = ++id;
      const timer = setTimeout(() => {
        pending.delete(mid);
        reject(new Error(`${method} timed out`));
      }, 15000);
      pending.set(mid, {
        resolve: (v) => { clearTimeout(timer); resolve(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      const msg = { id: mid, method, params };
      if (sess) msg.sessionId = sess;
      try {
        ws.send(JSON.stringify(msg));
      } catch (e) {
        clearTimeout(timer);
        pending.delete(mid);
        reject(e);
      }
    });

  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? p.reject(new Error(msg.error.message)) : p.resolve(msg.result);
    }
  });
  ws.addEventListener("close", () => {
    if (gen !== generation) return;
    sessionId = null;
    setTimeout(connect, 2000);
  });
  ws.addEventListener("error", () => {});

  // race open against close/error so a refused connection retries
  // instead of hanging forever while obscura serve is not running
  new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("close", () => reject(new Error("connection closed before open")), { once: true });
    ws.addEventListener("error", () => reject(new Error("connect failed")), { once: true });
  })
    .then(async () => {
      // reuse a page target an agent session may already created
      const { targetInfos } = await call("Target.getTargets");
      const existing = targetInfos.find((t) => t.type === "page");
      if (existing) {
        // pre-existing target: attach explicitly and use the session id
        const attached = await call("Target.attachToTarget", {
          targetId: existing.targetId,
          flatten: true,
        });
        sessionId = attached.sessionId;
      } else {
        // a freshly created target is auto-attached under "{targetId}-session"
        const created = await call("Target.createTarget", { url: "about:blank" });
        sessionId = `${created.targetId}-session`;
      }
      await call("Page.enable", {}, sessionId);
      loop();
    })
    .catch(retry);
}

function retry(err) {
  console.error(err.message);
  sessionId = null;
  setTimeout(connect, 2000);
}

let lastSent = null;

async function loop() {
  const gen = generation;
  while (gen === generation && ws?.readyState === WebSocket.OPEN && sessionId) {
    try {
      const shot = await call("Page.captureScreenshot", { format: "jpeg", quality: 70 }, sessionId);
      if (shot.data && shot.data.length > 100 && shot.data !== lastSent) {
        lastSent = shot.data;
        broadcast(shot.data);
      }
    } catch {
      // transient failures during navigation are normal
    }
    await new Promise((r) => setTimeout(r, INTERVAL_MS));
  }
}

process.on("SIGINT", () => {
  try { ws?.close(); } catch {}
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 500);
});

connect();
```

## Things worth knowing

- **Why captureScreenshot polling instead of screencast.** `Page.startScreencast` frames stream to the CDP session that drives the page, so once an agent session takes over, a passive viewer session stops receiving frames. It also only produces frames when the page paints something new. This captures the page that this script owns. If a separate agent session drives a different page, its paints do not appear here, because captures are scoped to the session that drives a page; navigate from this session (via `/navigate` above or by attaching a client to the same flattened session).
- **Acknowledge every frame.** Without `Page.screencastFrameAck`, frame delivery stops.
- **One client per page socket.** If an agent's CDP client already holds the page's `webSocketDebuggerUrl`, connecting to it again fails with `503`. Attach through the browser endpoint instead (`ws://127.0.0.1:9222/devtools/browser`) using `Target.attachToTarget` with `flatten: true`, then pass the returned session id as `sessionId` on every command.
- **Still images vs continuous view.** The MCP server exposes `browser_screenshot` for one-shot captures. Screencast is the right tool when you want to watch continuously; it stays CDP-only by design.

## Verifying

With `obscura serve` running and the viewer open:

1. Navigate from another client, for example `obscura fetch https://example.com` through a separate worker, or any Puppeteer/Playwright/MCP session connected to port 9222.
2. The tab shows the page within a second of it painting.
3. Closing the viewer tab and reopening it resumes from the most recent frame.
