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

function cardInfo(root, nameRe) {
  if (!root) return { present: false, text: "", buttons: [] };
  const cards = Array.from(root.querySelectorAll(".shop-card"));
  const card = cards.find((el) => nameRe.test(el.textContent || ""));
  if (!card) return { present: false, text: "", buttons: [] };
  return {
    present: true,
    text: card.textContent || "",
    buttons: Array.from(card.querySelectorAll("button")).map((b) => (b.textContent || "").trim()),
  };
}

waitFor(() => {
  const inv = dom.window.document.getElementById("inv");
  return inv && /half loaf|wild onion|backpack/i.test(inv.textContent || "");
}).then(() => {
  const doc = dom.window.document;
  const inv = doc.getElementById("inv");
  const shop = doc.getElementById("shop");
  const packHalf = cardInfo(inv, /half loaf/i);
  const shopHalf = cardInfo(shop, /half loaf/i);
  const shopOnion = cardInfo(shop, /wild onion/i);
  const result = {
    packHalf: packHalf,
    shopHalf: shopHalf,
    shopOnion: shopOnion,
    invText: inv ? inv.textContent : "",
    shopText: shop ? shop.textContent : "",
  };
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(String((err && err.stack) || err));
  process.exit(1);
});
