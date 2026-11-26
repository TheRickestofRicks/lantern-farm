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

function press(key) {
  const ev = new dom.window.KeyboardEvent("keydown", {
    key: key,
    code: "Key" + key.toUpperCase(),
    bubbles: true,
    cancelable: true,
  });
  dom.window.document.dispatchEvent(ev);
}

waitFor(() => {
  const keys = dom.window.document.getElementById("keys");
  const text = (keys && keys.textContent) || "";
  return /U/.test(text) && /unearth/i.test(text) && !/till/i.test(text);
}).then(async () => {
  const keysText = dom.window.document.getElementById("keys").textContent || "";
  press("u");
  await new Promise((resolve) => setTimeout(resolve, 40));
  const toastEl = dom.window.document.getElementById("toast") || dom.window.document.querySelector(".toast, #message, #flash");
  const toast1 = (toastEl && toastEl.textContent) || "";
  press("u");
  await new Promise((resolve) => setTimeout(resolve, 40));
  const toast = toast1 || ((toastEl && toastEl.textContent) || "");
  const result = {
    keysText: keysText,
    commands: commands.slice(),
    toast: toast,
  };
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(String((err && err.stack) || err));
  process.exit(1);
});
