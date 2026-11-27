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
        return {
          ok: true,
          status: 200,
          json: async () => payload,
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
      if (n > (tries || 50)) return reject(new Error("timeout waiting for render"));
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
  const head = dom.window.document.getElementById("area-head");
  return head && /town|market/i.test(head.textContent || "");
}).then(async () => {
  const doc = dom.window.document;
  const shopBtn = doc.getElementById("open-shop");
  const shopModal = doc.getElementById("shop-modal");
  const tiles = Array.from(doc.getElementById("grid").querySelectorAll("button.tile"));
  const toastBefore = (doc.getElementById("toast") && doc.getElementById("toast").textContent) || "";
  const shopOpenBeforeS = !!(shopModal && !shopModal.hidden);
  press("s");
  await new Promise((resolve) => setTimeout(resolve, 40));
  const shopOpenAfterS = !!(shopModal && !shopModal.hidden);
  const toastAfterS = (doc.getElementById("toast") && doc.getElementById("toast").textContent) || "";
  if (shopBtn && !shopBtn.hidden && !shopBtn.disabled && !shopOpenAfterS) {
    shopBtn.click();
  }
  await new Promise((resolve) => setTimeout(resolve, 40));
  const shopOpenAfterClick = !!(shopModal && !shopModal.hidden);
  const stallBtns = Array.from(doc.querySelectorAll("#inv .item-actions button")).map((b) => (b.textContent || "").trim());
  const result = {
    head: doc.getElementById("area-head").textContent,
    labels: tiles.map((el) => {
      const lab = el.querySelector(".label");
      return lab ? lab.textContent : "";
    }),
    titles: tiles.map((el) => el.getAttribute("title") || el.getAttribute("aria-label") || ""),
    stallButtons: stallBtns,
    tileCount: tiles.length,
    shopHidden: !!(shopBtn && shopBtn.hidden),
    shopDisabled: !!(shopBtn && shopBtn.disabled),
    shopText: shopBtn ? (shopBtn.textContent || "").trim() : "",
    keysText: (doc.getElementById("keys") && doc.getElementById("keys").textContent) || "",
    shopOpenBeforeS: shopOpenBeforeS,
    shopOpenAfterS: shopOpenAfterS,
    shopOpenAfterClick: shopOpenAfterClick,
    toastBefore: toastBefore,
    toastAfterS: toastAfterS,
    atStore: !!payload.at_store,
    atStall: !!payload.at_stall,
    atForge: !!payload.at_forge,
  };
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(String((err && err.stack) || err));
  process.exit(1);
});
