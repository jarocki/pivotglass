#!/usr/bin/env node

/** Reproducible browser QA and current-feature screenshots for v0.9.6. */

import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const url = process.argv[2] ?? "http://127.0.0.1:8765/";
const output = resolve(process.argv[3] ?? "docs/media");
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = mkdtempSync(join(tmpdir(), "pivotglass-v096-chrome-"));
mkdirSync(output, { recursive: true });

const child = spawn(chrome, [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--no-first-run",
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });

const debuggerUrl = await new Promise((resolveUrl, reject) => {
  let buffer = "";
  const timer = setTimeout(() => reject(new Error("Chrome debugging endpoint timed out")), 10_000);
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    buffer += chunk;
    const match = buffer.match(/DevTools listening on (ws:\/\/[^\s]+)/);
    if (match) {
      clearTimeout(timer);
      resolveUrl(match[1]);
    }
  });
  child.on("exit", (code) => reject(new Error(`Chrome exited before QA: ${code}`)));
});

const socket = new WebSocket(debuggerUrl);
await new Promise((resolveOpen, reject) => {
  socket.addEventListener("open", resolveOpen, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let commandId = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(String(event.data));
  if (!message.id || !pending.has(message.id)) return;
  const { resolve: resolveCommand, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolveCommand(message.result ?? {});
});

function command(method, params = {}, sessionId) {
  const id = ++commandId;
  return new Promise((resolveCommand, reject) => {
    pending.set(id, { resolve: resolveCommand, reject });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}

const { targetId } = await command("Target.createTarget", { url });
const { sessionId } = await command("Target.attachToTarget", { targetId, flatten: true });
const page = (method, params = {}) => command(method, params, sessionId);
await page("Page.enable");
await page("Runtime.enable");
await page("Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});

const pause = (milliseconds) => new Promise((resolvePause) => setTimeout(resolvePause, milliseconds));
async function evaluate(expression) {
  const result = await page("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result?.value;
}
async function ready() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (await evaluate("document.readyState === 'complete' && Boolean(document.querySelector('main'))")) {
      await evaluate("document.fonts.ready.then(() => true)");
      await pause(180);
      return;
    }
    await pause(100);
  }
  throw new Error("Pivotglass did not become ready");
}
async function reload() {
  await page("Page.reload", { ignoreCache: true });
  await ready();
}
async function capture(name) {
  const shot = await page("Page.captureScreenshot", { format: "png", fromSurface: true });
  writeFileSync(join(output, name), Buffer.from(shot.data, "base64"));
}
async function post(path, body) {
  return evaluate(`fetch(${JSON.stringify(path)}, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(body)})}).then(async r => ({ok:r.ok,status:r.status,body:await r.json()}))`);
}

const failures = [];
const receipts = [];
const modes = ["default", "sensei", "the_computer", "full_troll", "detective", "the_sprawl", "m4tr1x"];
const qaWorkspace = `release-media-v096-${Date.now()}`;

try {
  await ready();
  const learning = await post("/api/command", { command: `workspace learn ${qaWorkspace}` });
  if (!learning.ok) {
    throw new Error(`learning workspace failed: ${JSON.stringify(learning)}`);
  }
  await reload();

  for (const mode of modes) {
    const switched = await post("/api/mode", { name: mode });
    if (!switched.ok) failures.push(`${mode}: mode switch returned ${switched.status}`);
    for (const display of ["day", "night"]) {
      await evaluate(`localStorage.setItem('pivotglass.display', ${JSON.stringify(display)}); localStorage.setItem('pivotglass.effects','reduced')`);
      await reload();
      await evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent?.trim() === 'VISUALIZE'))?.click()`);
      await pause(160);
      await evaluate(`(() => { const select=[...document.querySelectorAll('select')].find(node => [...node.options].some(option => option.textContent?.includes('Investigation constellation'))); if(!select) return false; const option=[...select.options].find(item => item.textContent?.includes('Investigation constellation')); select.value=option.value; select.dispatchEvent(new Event('change',{bubbles:true})); return true; })()`);
      await pause(180);
      const audit = await evaluate(`(() => {
        const main=document.querySelector('main'); const wrap=document.querySelector('.constellation-matrix-wrap'); const matrix=document.querySelector('.constellation-matrix'); const row=matrix?.querySelector('tbody tr'); const cell=row?.querySelector('.lite-brite-cell');
        if(!main||!wrap||!matrix||!row||!cell) return {missing:true};
        const before=row.getBoundingClientRect(); const point=cell.getBoundingClientRect();
        return {missing:false,docWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,display:main.classList.contains('display-day')?'day':'night',matrixBackground:getComputedStyle(matrix).backgroundColor,control:getComputedStyle(main).getPropertyValue('--control').trim(),surface:getComputedStyle(main).getPropertyValue('--surface').trim(),wrapWidth:wrap.getBoundingClientRect().width,matrixWidth:matrix.getBoundingClientRect().width,row:{x:before.x,y:before.y,width:before.width,height:before.height},point:{x:point.x+point.width/2,y:point.y+point.height/2}};
      })()`);
      if (audit.missing) {
        failures.push(`${mode}/${display}: Constellation missing`);
        continue;
      }
      await pause(300);
      audit.row = await evaluate(`(() => { const r=document.querySelector('.constellation-matrix tbody tr')?.getBoundingClientRect(); return r&&{x:r.x,y:r.y,width:r.width,height:r.height}; })()`);
      await page("Input.dispatchMouseEvent", { type: "mouseMoved", x: audit.point.x, y: audit.point.y });
      await pause(160);
      const after = await evaluate(`(() => { const r=document.querySelector('.constellation-matrix tbody tr')?.getBoundingClientRect(); return r&&{x:r.x,y:r.y,width:r.width,height:r.height}; })()`);
      const delta = Math.max(...Object.keys(after).map((key) => Math.abs(after[key] - audit.row[key])));
      if (delta > 0.5) failures.push(`${mode}/${display}: hover moved a row by ${delta}px`);
      if (audit.docWidth !== audit.clientWidth) failures.push(`${mode}/${display}: document overflow ${audit.docWidth}/${audit.clientWidth}`);
      if (audit.display !== display) failures.push(`${mode}/${display}: requested display did not apply`);
      if (display === "day" && /rgb\((?:0|1|2|3|4|5|6|7|8|9|1\d|2\d),/.test(audit.matrixBackground)) failures.push(`${mode}/${display}: matrix remained dark (${audit.matrixBackground})`);
      if (audit.matrixWidth + 24 < audit.wrapWidth) failures.push(`${mode}/${display}: matrix does not fill its viewport`);
      receipts.push({ mode, display, ...audit, hoverDelta: delta });
      if (mode === "default" && display === "day") await capture("pivotglass-visualize-v0.9.6.png");
    }
  }

  await post("/api/mode", { name: "default" });
  await evaluate("localStorage.setItem('pivotglass.display','night')");
  await reload();
  await capture("pivotglass-cockpit-v0.9.6.png");

  await evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent?.trim() === 'VISUALIZE'))?.click()`);
  await pause(120);
  await evaluate(`document.querySelector('.document-intake > summary')?.click()`);
  await pause(100);
  const upload = await evaluate(`(() => { const input=document.querySelector('.document-intake input[type=file]'); if(!input) return false; const file=new File(['Indicator 198.51.100.42 contacted release-example.test during the synthetic exercise.'], 'release-example.txt', {type:'text/plain'}); const transfer=new DataTransfer(); transfer.items.add(file); input.files=transfer.files; input.dispatchEvent(new Event('change',{bubbles:true})); return true; })()`);
  if (!upload) failures.push("document file input missing");
  await evaluate(`([...document.querySelectorAll('.document-intake button')].find(button => button.textContent?.includes('PREVIEW LOCALLY')))?.click()`);
  await pause(350);
  const preview = await evaluate("Boolean(document.querySelector('.document-preview')) && Boolean([...document.querySelectorAll('button')].find(button => button.textContent?.includes('INGEST INTO WORKSPACE')))");
  if (!preview) failures.push("preview or explicit ingest control missing");
  await evaluate(`([...document.querySelectorAll('.document-intake button')].find(button => button.textContent?.includes('INGEST INTO WORKSPACE')))?.click()`);
  await pause(450);
  const library = await evaluate(`({receipt:Boolean(document.querySelector('.document-receipt')),items:document.querySelectorAll('.document-library li').length,rawBytesExposed:document.body.innerText.includes('SW5kaWNhdG9yIDE5OC41MS4xMDAuNDI=')})`);
  if (!library.receipt || library.items < 1 || library.rawBytesExposed) failures.push(`document admission UI failed: ${JSON.stringify(library)}`);
  await capture("pivotglass-document-library-v0.9.6.png");

  await reload();
  await evaluate(`([...document.querySelectorAll('button')].find(button => button.textContent?.trim() === 'VISUALIZE'))?.click()`);
  await pause(120);
  const persisted = await evaluate("document.querySelectorAll('.document-library li').length");
  if (persisted < 1) failures.push("document library did not survive refresh");
  await evaluate(`(() => { const select=[...document.querySelectorAll('select')].find(node => [...node.options].some(option => option.textContent?.includes('Investigation pivot trail'))); const option=select&&[...select.options].find(item => item.textContent?.includes('Investigation pivot trail')); if(!select||!option)return false;select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));return true; })()`);
  await pause(180);
  const timeline = await evaluate("document.querySelectorAll('.pivot-trail li').length");
  if (timeline < 1) failures.push("chronological pivot trail did not render");
  await capture("pivotglass-pivot-timeline-v0.9.6.png");

  for (const [width, height] of [[320, 800], [1024, 768], [1440, 1000]]) {
    await page("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width === 320 });
    await pause(120);
    const sizing = await evaluate("({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth})");
    if (sizing.scroll !== sizing.client) failures.push(`${width}px: document overflow ${sizing.scroll}/${sizing.client}`);
  }

  writeFileSync(join(output, "pivotglass-web-qa-v0.9.6.json"), JSON.stringify({ schema: "pivotglass-web-qa-1.0", url, receipts, failures }, null, 2));
  const restored = await post("/api/command", { command: "workspace switch default" });
  if (!restored.ok) failures.push("could not restore the default workspace after QA");
  const removed = await post("/api/command", { command: `workspace delete ${qaWorkspace} --confirm ${qaWorkspace}` });
  if (!removed.ok) failures.push("could not remove the isolated QA workspace");
  if (failures.length) throw new Error(failures.join("\n"));
  console.log(`PASS: ${receipts.length} theme/display combinations, hover stability, document admission/library, pivot timeline, and 3 responsive widths`);
} finally {
  socket.close();
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolveExit) => child.once("exit", resolveExit)),
    pause(2_000),
  ]);
  try {
    rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  } catch (error) {
    console.warn(`Temporary Chrome profile requires later cleanup: ${error.message}`);
  }
}
