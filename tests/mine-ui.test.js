const { JSDOM } = require("jsdom");
const fs = require("fs");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const html = fs.readFileSync(process.argv[3], "utf8");

const { VirtualConsole } = require("jsdom");
const vc = new VirtualConsole();
vc.on("jsdomError", (err) => {
  console.error(err);
});

const commands = [];

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable",
  url: "http://127.0.0.1:8790/",
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(window) {
    try { window.localStorage.setItem("lantern-farm-art-pack", "storybook"); } catch (err) {}
    window.fetch = async function (url, opts) {
      const path = String(url);
      if (path.indexOf("/api/state") !== -1) {
        return { ok: true, status: 200, json: async () => payload };
      }
      if (path.indexOf("/api/do") !== -1) {
        let command = "";
        try {
          command = JSON.parse((opts && opts.body) || "{}").command || "";
        } catch (err) {}
        commands.push(command);
        return {
          ok: true,
          status: 200,
          json: async () => Object.assign({}, payload, { ok: true, message: "ok", command: command }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    };
  },
});

function waitFor(check, tries) {
  return new Promise((resolve, reject) => {
    let n = 0;
    const tick = () => {
      try {
        if (check()) return resolve();
      } catch (err) {
        return reject(err);
      }
      n += 1;
      if (n > (tries || 80)) return reject(new Error("timeout waiting for render"));
      setTimeout(tick, 20);
    };
    tick();
  });
}

function press(key, shifts) {
  const ev = new dom.window.KeyboardEvent("keydown", {
    key: key,
    code: "Key" + String(key).toUpperCase(),
    bubbles: true,
    cancelable: true,
    shiftKey: !!shifts,
  });
  dom.window.document.dispatchEvent(ev);
}

function tileButtons() {
  const box = dom.window.document.getElementById("tile-actions");
  return Array.from((box && box.querySelectorAll("button")) || []).map((b) => (b.textContent || "").trim());
}

function clickNamed(re) {
  const box = dom.window.document.getElementById("tile-actions");
  const btn = Array.from((box && box.querySelectorAll("button")) || []).find((b) => re.test((b.textContent || "").trim()));
  if (!btn) return false;
  btn.click();
  return true;
}

const mode = process.env.MINE_UI_MODE || "entrance";

waitFor(() => {
  const box = dom.window.document.getElementById("tile-actions");
  if (!box) return false;
  const text = box.textContent || "";
  if (mode === "entrance") return /enter mine/i.test(text);
  if (mode === "inside") return /climb|leave mine|mine|rest|strike|flee/i.test(text);
  if (mode === "noturn") {
    const input = dom.window.document.getElementById("debug-cmd");
    const status = dom.window.document.getElementById("debug-cmd-status");
    return !!(input && (input.disabled || (status && /turn/i.test(status.textContent || ""))));
  }
  return false;
}).then(async () => {
  const result = {
    tileButtons: tileButtons(),
    keysText: (dom.window.document.getElementById("keys") && dom.window.document.getElementById("keys").textContent) || "",
    hasDebug: !!dom.window.document.getElementById("debug-cmd"),
    commands: commands.slice(),
  };

  if (mode === "entrance") {
    result.clickedEnter = clickNamed(/enter mine/i);
    await new Promise((resolve) => setTimeout(resolve, 40));
    result.commandsAfterClick = commands.slice();

    const input = dom.window.document.getElementById("debug-cmd");
    const form = dom.window.document.getElementById("debug-console");
    const status = dom.window.document.getElementById("debug-cmd-status");
    const options = Array.from((dom.window.document.getElementById("debug-cmd-list") || {}).options || []).map((o) => o.value);
    result.debugOptionsIncludeEnter = options.indexOf("enter mine") !== -1;
    input.value = "not a real action";
    form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    result.rejectedStatus = (status && status.textContent) || "";
    result.commandsAfterReject = commands.slice();
    input.value = "enter mine";
    form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 40));
    result.commandsAfterDebug = commands.slice();
    result.debugInputAfterSend = input.value;

    // Fresh E press after click already sent one enter mine; still fine to record.
    press("e");
    await new Promise((resolve) => setTimeout(resolve, 40));
    result.commandsAfterE = commands.slice();
  }

  if (mode === "noturn") {
    const input = dom.window.document.getElementById("debug-cmd");
    const form = dom.window.document.getElementById("debug-console");
    const status = dom.window.document.getElementById("debug-cmd-status");
    result.debugDisabled = !!(input && input.disabled);
    if (input) input.value = "enter mine";
    if (form) form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
    result.noturnStatus = (status && status.textContent) || "";
    result.commandsAfterNoturn = commands.slice();
  }

  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
