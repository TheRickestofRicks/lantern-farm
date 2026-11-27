const { JSDOM } = require("jsdom");
const fs = require("fs");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const html = fs.readFileSync(process.argv[3], "utf8");
const mode = process.env.CABIN_E_MODE || "floor";
const presses = parseInt(process.env.CABIN_E_PRESSES || "1", 10);

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

function visible(id) {
  const el = dom.window.document.getElementById(id);
  if (!el) return false;
  return !el.hidden;
}

waitFor(() => {
  const keys = dom.window.document.getElementById("keys");
  const text = (keys && keys.textContent) || "";
  // The static HTML already mentions E interact and farm verbs. Wait until
  // renderKeys has replaced it with the area-aware legend (no till in the
  // cabin, town, hills, or mine).
  return /\bE\b/.test(text) && /interact/i.test(text) && !/till/i.test(text);
}).then(async () => {
  const keysText = (dom.window.document.getElementById("keys") && dom.window.document.getElementById("keys").textContent) || "";
  const count = Number.isFinite(presses) && presses > 0 ? presses : 1;
  for (let i = 0; i < count; i++) {
    press("e");
    await new Promise((resolve) => setTimeout(resolve, 40));
  }
  const toast = dom.window.document.getElementById("toast");
  const book = dom.window.document.getElementById("recipe-book");
  const endEl = dom.window.document.getElementById("end-confirm");
  const result = {
    mode: mode,
    keysText: keysText,
    commands: commands.slice(),
    chestOpen: visible("chest-modal"),
    tableOpen: visible("table-modal"),
    recipeOpen: !!(book && book.open && !book.hidden),
    endConfirmShown: !!(endEl && !endEl.hidden),
    endConfirmText: (endEl && !endEl.hidden) ? (endEl.textContent || "") : "",
    toast: (toast && toast.textContent) || "",
  };
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(String((err && err.stack) || err));
  process.exit(1);
});
