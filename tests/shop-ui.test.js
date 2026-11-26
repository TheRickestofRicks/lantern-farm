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

function sectionInfo(root, title) {
  if (!root) return { present: false, text: "", buttons: [], commands: [] };
  const want = (title || "").trim().toLowerCase();
  const titles = Array.from(root.querySelectorAll(".shop-section-title, .recipe-book-head"));
  const start = titles.find((el) => (el.textContent || "").trim().toLowerCase() === want);
  if (!start) return { present: false, text: "", buttons: [], commands: [] };
  const bits = [];
  const buttons = [];
  const commands = [];
  function collect(node) {
    if (!node) return;
    bits.push(node.textContent || "");
    const src = node.querySelectorAll ? node.querySelectorAll("button") : [];
    Array.from(src).forEach((b) => {
      if (!b.classList.contains("chest-toggle")) buttons.push((b.textContent || "").trim());
    });
    if (node.matches && node.matches("button") && !node.classList.contains("chest-toggle")) {
      buttons.push((node.textContent || "").trim());
    }
  }
  if (start.classList.contains("chest-toggle")) {
    const body = start.parentElement && start.parentElement.querySelector(".chest-section-body");
    collect(body || start.nextElementSibling);
    return { present: true, text: bits.join(" | "), buttons: buttons, commands: commands };
  }
  let el = start.nextElementSibling;
  while (el && !el.classList.contains("shop-section-title") && !el.classList.contains("chest-section")) {
    collect(el);
    el = el.nextElementSibling;
  }
  return { present: true, text: bits.join(" | "), buttons: buttons, commands: commands };
}

waitFor(() => {
  const inv = dom.window.document.getElementById("inv");
  return inv && /Backpack/i.test(inv.textContent || "");
}).then(() => {
  const doc = dom.window.document;
  const shop = doc.getElementById("shop");
  const inv = doc.getElementById("inv");
  const chestHeading = inv && (inv.querySelector(".chest-section .recipe-book-head, .chest-section .chest-toggle"));
  const status = doc.getElementById("status");
  const energyEl = status && status.querySelector(".stat.energy");
  const shopBackpack = sectionInfo(shop, "From the backpack");
  const shopChest = sectionInfo(shop, "Cabin chest");
  const invChest = sectionInfo(inv, "Cabin chest");
  const invPack = sectionInfo(inv, "Backpack");
  const allBtns = Array.from(doc.querySelectorAll("button")).map((b) => (b.textContent || "").trim());
  const toggle = inv && inv.querySelector(".chest-toggle");
  const chestOpenBefore = !!(toggle && toggle.getAttribute("aria-expanded") === "true");
  let chestStorageBefore = null;
  try { chestStorageBefore = dom.window.localStorage.getItem("lanternFarm.cabinChestOpen"); } catch (err) {}
  let chestOpenAfterClick = null;
  let chestStorageAfterClick = null;
  let chestHiddenAfterClick = null;
  if (toggle) {
    toggle.click();
    const body = inv.querySelector(".chest-section-body");
    chestOpenAfterClick = toggle.getAttribute("aria-expanded") === "true";
    chestHiddenAfterClick = !!(body && body.hidden);
    try { chestStorageAfterClick = dom.window.localStorage.getItem("lanternFarm.cabinChestOpen"); } catch (err) {}
  }
  const result = {
    shopBackpackPresent: shopBackpack.present,
    shopBackpackText: shopBackpack.text,
    shopBackpackButtons: shopBackpack.buttons,
    shopChestPresent: shopChest.present,
    shopChestText: shopChest.text,
    shopChestButtons: shopChest.buttons,
    shopKitchenPresent: sectionInfo(shop, "Kitchen").present,
    shopBackpackDropPresent: sectionInfo(shop, "Backpack").present,
    recipeCraftButtons: Array.from(doc.querySelectorAll("#recipe-book-body button")).map((b) => (b.textContent || "").trim()),
    invChestPresent: invChest.present,
    invChestText: invChest.text,
    invChestButtons: invChest.buttons,
    invChestHeading: chestHeading ? (chestHeading.textContent || "").trim() : "",
    invChestHeadingClass: chestHeading ? chestHeading.className : "",
    energyHud: energyEl ? (energyEl.textContent || "").replace(/\s+/g, " ").trim() : "",
    energyHudClass: energyEl ? energyEl.className : "",
    energyHudLabel: energyEl ? (energyEl.getAttribute("aria-label") || "") : "",
    invPackText: invPack.text,
    invText: inv ? inv.textContent : "",
    shopText: shop ? shop.textContent : "",
    shopMetas: Array.from((shop && shop.querySelectorAll(".shop-meta")) || []).map((el) => (el.textContent || "").trim()),
    shopTitles: Array.from((shop && shop.querySelectorAll(".shop-card")) || []).map((el) => el.getAttribute("title") || ""),
    shopCardNames: Array.from((shop && shop.querySelectorAll(".shop-card > div > b, .shop-card b")) || []).map((el) => (el.textContent || "").trim()),
    eatButtons: allBtns.filter((t) => /^Eat/i.test(t)),
    chestTogglePresent: !!(inv && inv.querySelector(".chest-toggle")),
    chestOpen: chestOpenBefore,
    chestStorage: (function () { try { return dom.window.localStorage.getItem("lanternFarm.cabinChestOpen"); } catch (err) { return null; } })(),
    chestOrder: Array.from((inv && inv.querySelectorAll(".chest-card[data-item]")) || []).map((c) => c.getAttribute("data-item")),
    chestOpenAfterClick: chestOpenAfterClick,
    chestStorageAfterClick: chestStorageAfterClick,
    chestHiddenAfterClick: chestHiddenAfterClick,
  };
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}).catch((err) => {
  console.error(String((err && err.stack) || err));
  process.exit(1);
});
