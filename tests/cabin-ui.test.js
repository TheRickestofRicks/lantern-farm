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

waitFor(() => {
  const box = dom.window.document.getElementById("tile-actions");
  const keys = dom.window.document.getElementById("keys");
  if (!box || !keys) return false;
  return /enter cabin/i.test(box.textContent || "") || /enter cabin/i.test(keys.textContent || "");
}).then(async () => {
  const keysText = (dom.window.document.getElementById("keys") && dom.window.document.getElementById("keys").textContent) || "";

  press("Enter");
  await new Promise((resolve) => setTimeout(resolve, 40));
  const commandsAfterPlainEnter = commands.slice();

  press("e");
  await new Promise((resolve) => setTimeout(resolve, 40));
  const commandsAfterE = commands.slice();

  press("e", true);
  await new Promise((resolve) => setTimeout(resolve, 40));
  const box = dom.window.document.getElementById("end-note");
  const noteFocused = !!(box && dom.window.document.activeElement === box);
  if (box) {
    box.value = "";
    box.dispatchEvent(new dom.window.KeyboardEvent("keydown", {
      key: "Enter",
      code: "Enter",
      bubbles: true,
      cancelable: true,
    }));
  }
  await new Promise((resolve) => setTimeout(resolve, 40));
  const commandsAfterShiftEEnter = commands.slice();

  process.stdout.write(JSON.stringify({
    keysText: keysText,
    commandsAfterPlainEnter: commandsAfterPlainEnter,
    commandsAfterE: commandsAfterE,
    noteFocused: noteFocused,
    commandsAfterShiftEEnter: commandsAfterShiftEEnter,
  }));
  process.exit(0);
}).catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
