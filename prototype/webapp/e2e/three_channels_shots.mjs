// The demo video's flow on the three-channel offline stack (three_channels_stack.py),
// driven like real people: Ada and Bruno use the web app in a browser; Discord and
// Slack members act through the stack's control API, which runs the real Discord
// bridge and Slack hub. Then it saves:
//   docs/screens/three-web.png      the real web app (Ada), card "Confirmed by Ada"
//   docs/screens/three-discord.png  the Discord channel, drawn from the exact embed and buttons the bot sent
//   docs/screens/three-slack.png    the Slack channel, drawn from the exact Block Kit the bot sent
//   docs/screens/three-payloads.json  those payloads, as recorded
//
//   cd prototype && python webapp/e2e/three_channels_stack.py &   then   node webapp/e2e/three_channels_shots.mjs
import { chromium } from "playwright";
import { writeFileSync, mkdirSync } from "node:fs";
import { signUp } from "./account.mjs";

const WEB = "http://127.0.0.1:8190";
const CONTROL = "http://127.0.0.1:8192";
const OUT = new URL("../docs/screens/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const call = async (path, body) => {
  const response = await fetch(CONTROL + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return response.json();
};
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function personalCode(page) {
  await page.getByRole("button", { name: "Connect Slack or Discord" }).click();
  await page.getByRole("button", { name: "Get my personal code" }).click();
  const command = await page.locator(".connect__command code", { hasText: "/coordinator me" }).textContent();
  await page.getByRole("button", { name: "Done", exact: true }).click();
  return command.trim().split(" ").pop();
}

const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
const ada = await (await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 })).newPage();
await ada.goto(WEB + "/");
await ada.getByRole("link", { name: "Open your space" }).click();
await signUp(ada, "Ada");
await ada.getByRole("button", { name: "New project" }).click();
await ada.locator("#c-project").fill("How we get to school");
await ada.getByRole("button", { name: "Create the space" }).click();
await ada.getByRole("heading", { name: "How we get to school" }).waitFor();
const code = (await ada.locator(".invite code").textContent()).trim();

const bruno = await (await browser.newContext()).newPage();
await bruno.goto(`${WEB}/?code=${code}`);
await signUp(bruno, "Bruno");
await bruno.getByRole("button", { name: "Join the space" }).click();
await bruno.locator(".members").getByText("Ada").waitFor();

// Discord and Slack: paste the space's invite link in the channel.
const link = `${WEB}/join/${code}`;
console.log("discord link:", await call("/discord/say", { who: "Ada", text: link }));
console.log("slack link:", await call("/slack/say", { who: "Bruno", text: link }));
// One person, one member: Ada and Bruno are the same people on the web, Discord and Slack.
console.log("ada me:", (await call("/discord/me", { who: "Ada", code: await personalCode(ada) })).text);
console.log("bruno me discord:", (await call("/discord/me", { who: "Bruno", code: await personalCode(bruno) })).text);
console.log("ada me slack:", (await call("/slack/me", { who: "Ada", code: await personalCode(ada) })).text);
console.log("bruno me slack:", (await call("/slack/me", { who: "Bruno", code: await personalCode(bruno) })).text);

await call("/slack/say", { who: "Bruno", text: "the 3 sources are final, links in the doc" });
await call("/discord/say", { who: "Chiara", text: "class 3B gave us 25 paper forms back" });
await call("/discord/say", { who: "Chiara", text: "typing them into the sheet now" });
await call("/discord/say", { who: "Bruno", text: "not me, I'm finishing the sources" });
await call("/discord/say", { who: "Ada", text: "we also need the results printed for the charts" });

let payloads;
for (let i = 0; i < 100; i += 1) {
  payloads = await call("/payloads");
  if (payloads.discord.some((m) => m.kind === "card") && payloads.slack.some((m) => m.blocks)) break;
  await pause(100);
}
await call("/slack/say", { who: "Bruno", text: "anything left for me before Monday?" });
console.log("click:", await call("/discord/click", { who: "Ada", action: "confirm" }));
await pause(800);
await call("/slack/say", { who: "Bruno", text: "oh nice, Ada took it on Discord 👍" });
await call("/discord/say", { who: "Chiara", text: "all 25 paper forms are in the sheet" });
await pause(800);
payloads = await call("/payloads");
writeFileSync(OUT + "three-payloads.json", JSON.stringify(payloads, null, 2));

// The real web app, as Ada sees it (the setup guide and Quick access put away).
await ada.locator(".card", { hasText: "Confirmed by Ada" }).waitFor();
for (const name of ["Hide", "Hide quick access"]) {
  const button = ada.getByRole("button", { name, exact: true });
  if (await button.count()) await button.first().click();
}
await ada.locator(".card", { hasText: "Confirmed by Ada" }).scrollIntoViewIfNeeded();
await ada.getByText("all 25 paper forms are in the sheet").waitFor();
await ada.screenshot({ path: OUT + "three-web.png" });

// Discord and Slack: their channel, drawn from what the bot really sent.
const page = await (await browser.newContext({ viewport: { width: 760, height: 640 }, deviceScaleFactor: 2 })).newPage();
await page.setContent(discordHtml(payloads.discord));
await page.screenshot({ path: OUT + "three-discord.png", fullPage: true });
await page.setContent(slackHtml(payloads.slack));
await page.screenshot({ path: OUT + "three-slack.png", fullPage: true });
await browser.close();
console.log("saved in", OUT);

// ---------------------------------------------------------------------------

function esc(text) {
  return String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function md(text) {
  // Discord markdown, the little the cards use: **bold**, *italic*, `code`, line breaks.
  return esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
}
function mrkdwn(text) {
  // Slack mrkdwn (already escaped by the bot): *bold*, _italic_, `code`, line breaks.
  return String(text ?? "").replace(/\*(.+?)\*/g, "<b>$1</b>").replace(/(^|\s)_(.+?)_/g, "$1<i>$2</i>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
}
function when(at) {
  return new Date(at * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
function avatar(who) {
  const AVATAR = { Ada: "#C2410C", Bruno: "#2563EB", Chiara: "#0F766E" };
  const mark = `<img src="${WEB}/brand/cadence-icon-512.png" alt="">`;
  return who === "Cadence" ? `<div class="av av--bot">${mark}</div>` : `<div class="av" style="background:${AVATAR[who] ?? "#555"}">${who[0]}</div>`;
}

function discordHtml(items) {
  const rows = items.map((m) => {
    const head = `<div class="head"><b>${esc(m.who)}</b>${m.who === "Cadence" ? '<span class="app">APP</span>' : ""}<span class="time">Today at ${when(m.at)}</span></div>`;
    if (m.kind !== "card") return `<div class="msg">${avatar(m.who)}<div>${head}<div class="text">${md(m.text)}</div></div></div>`;
    const e = m.embed;
    const colour = "#" + (e.color ?? 0x5865f2).toString(16).padStart(6, "0");
    const fields = (e.fields ?? []).map((f) => `<div class="field"><div class="fname">${md(f.name)}</div><div>${md(f.value)}</div></div>`).join("");
    const rowsOfButtons = [0, 1].map((r) => (m.buttons ?? []).filter((b) => (b.row ?? 0) === r)).filter((row) => row.length);
    const buttons = rowsOfButtons.map((row) => `<div class="btns">${row.map((b) => `<span class="btn btn--${b.style}">${esc(b.label)}</span>`).join("")}</div>`).join("");
    return `<div class="msg">${avatar("Cadence")}<div>${head}<div class="embed" style="border-color:${colour}"><div class="etitle">${md(e.title)}</div><div class="edesc">${md(e.description)}</div>${fields}<div class="foot">${md(e.footer?.text)}</div></div>${buttons}</div></div>`;
  });
  return `<!doctype html><html><head><style>
    body{margin:0;background:#313338;color:#dbdee1;font:15px/1.4 "gg sans","Noto Sans",Helvetica,Arial,sans-serif}
    .bar{height:48px;display:flex;align-items:center;padding:0 16px;border-bottom:1px solid #26282c;color:#f2f3f5;font-weight:600}
    .bar span{color:#80848e;margin-right:6px;font-size:20px}
    .list{padding:12px 16px 20px}
    .msg{display:flex;gap:14px;margin-top:14px}
    .av{width:40px;height:40px;border-radius:50%;flex:none;display:grid;place-items:center;color:#fff;font-weight:700}
    .av--bot img{width:40px;height:40px;border-radius:50%}
    .head{display:flex;gap:8px;align-items:center}.head b{color:#f2f3f5}
    .app{background:#5865f2;color:#fff;font-size:10px;font-weight:700;border-radius:3px;padding:0 4px;line-height:15px}
    .time{color:#949ba4;font-size:12px}
    .embed{margin-top:6px;max-width:460px;background:#2b2d31;border-left:4px solid;border-radius:4px;padding:10px 14px 12px}
    .etitle{color:#f2f3f5;font-weight:600}.edesc{margin-top:4px}
    .field{margin-top:8px}.fname{color:#f2f3f5;font-weight:600;font-size:14px}
    .foot{margin-top:10px;font-size:12px;color:#b5bac1}
    .btns{display:flex;gap:8px;margin-top:8px}
    .btn{padding:4px 14px;border-radius:4px;font-size:14px;font-weight:500;color:#fff;background:#4e5058}
    .btn--success{background:#248046}.btn--primary{background:#5865f2}
    code{background:#1e1f22;border-radius:3px;padding:0 3px;font-size:13px}
  </style></head><body><div class="bar"><span>#</span>presentation</div><div class="list">${rows.join("")}</div></body></html>`;
}

function slackHtml(posts) {
  const rows = posts.map((p) => {
    const head = `<div class="head"><b>${esc(p.who)}</b>${p.who === "Cadence" ? '<span class="app">APP</span>' : ""}<span class="time">${when(p.at)}</span></div>`;
    if (!p.blocks) return `<div class="msg">${avatar(p.who)}<div>${head}<div>${p.who === "Cadence" ? mrkdwn(p.text) : esc(p.text)}</div></div></div>`;
    const blocks = p.blocks.map((b) => {
      if (b.type === "section") return `<div class="sec">${mrkdwn(b.text.text)}</div>`;
      if (b.type === "context") return `<div class="ctx">${b.elements.map((e) => mrkdwn(e.text)).join(" ")}</div>`;
      if (b.type === "actions") return `<div class="btns">${b.elements.map((e) => `<span class="btn ${e.style === "primary" ? "btn--primary" : ""}">${esc(e.text.text)}</span>`).join("")}</div>`;
      return "";
    });
    return `<div class="msg">${avatar("Cadence")}<div>${head}${blocks.join("")}</div></div>`;
  });
  return `<!doctype html><html><head><style>
    body{margin:0;background:#fff;color:#1d1c1d;font:15px/1.46 Lato,"Helvetica Neue",Helvetica,Arial,sans-serif}
    .bar{height:49px;display:flex;align-items:center;padding:0 20px;border-bottom:1px solid #e2e2e2;font-weight:900;font-size:18px}
    .list{padding:8px 20px 20px}
    .msg{display:flex;gap:10px;margin-top:14px}
    .av{width:36px;height:36px;border-radius:6px;flex:none;display:grid;place-items:center;color:#fff;font-weight:700}
    .av--bot img{width:36px;height:36px;border-radius:6px}
    .head{display:flex;gap:8px;align-items:baseline}.head b{font-weight:900}
    .app{background:#e8e8e8;color:#616061;font-size:10px;font-weight:700;border-radius:2px;padding:0 3px}
    .time{color:#616061;font-size:12px}
    .sec{margin-top:6px}.ctx{margin-top:6px;font-size:13px;color:#616061}
    .btns{display:flex;gap:8px;margin-top:8px}
    .btn{border:1px solid #bbb;border-radius:4px;padding:3px 12px;font-weight:700;font-size:14px}
    .btn--primary{background:#007a5a;border-color:#007a5a;color:#fff}
    code{background:#f6f6f6;border:1px solid #ddd;border-radius:3px;padding:0 3px;font-size:12px;color:#e01e5a}
  </style></head><body><div class="bar"># school-talk</div><div class="list">${rows.join("")}</div></body></html>`;
}
