const { JSDOM } = require("jsdom");
const fs = require("fs");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const html = fs.readFileSync(process.argv[3], "utf8");

const { VirtualConsole } = require("jsdom");
const vc = new VirtualConsole();
vc.on("jsdomError", (err) => {
  console.error(err);
});

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable",
  url: "http://127.0.0.1:8790/",
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(window) {
    try { window.localStorage.setItem("lantern-farm-art-pack", "storybook"); } catch (err) {}
    window.fetch = async function (url) {
      const path = String(url);
      if (path.indexOf("/api/state") !== -1) {
        return { ok: true, status: 200, json: async () => payload };
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

waitFor(() => {
  const head = dom.window.document.getElementById("area-head");
  const grid = dom.window.document.getElementById("grid");
  if (!head || !grid) return false;
  return /cabin/i.test(head.textContent || "") && grid.querySelectorAll("button.tile").length === 9;
}).then(() => {
  const doc = dom.window.document;
  const inv = doc.getElementById("inv");
  const chest = inv && inv.querySelector(".chest-section");
  const result = {
    head: doc.getElementById("area-head").textContent,
    labels: Array.from(doc.getElementById("grid").querySelectorAll(".label")).map((el) => el.textContent),
    tileCount: doc.getElementById("grid").querySelectorAll("button.tile").length,
    imgSrcs: Array.from(doc.getElementById("grid").querySelectorAll("img")).map((el) => el.getAttribute("src") || ""),
    invChestPresent: !!(chest && /CABIN CHEST/i.test(chest.textContent || "")),
  };
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(String((err && err.stack) || err));
  process.exit(1);
});
