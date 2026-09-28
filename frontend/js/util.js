// shared helpers + app state

const app = document.getElementById("app");

const state = {
  user: null,        // logged in user, or null for guests
  config: {},        // { mode, polly }
  categories: [],    // all categories with their buyers
  lastResult: null,  // scorecard from the last call, for the results page
  plan: null,        // { plan: guest/free/pro, calls_left, gauntlet_left, free_category, ... }
};

function $(id) {
  return document.getElementById(id);
}

// escape text before putting it in HTML
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmt(n) {
  return Number(n || 0).toLocaleString("en-US");
}

function money(n) {
  return "$" + fmt(n);
}

function initials(name) {
  const clean = name.replace(/[^\p{L} ]/gu, "").replace(/^(Dr|Mr|Ms|Mrs) /, "").trim();
  return clean.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

function stars(n) {
  return `<span class="stars">${"★".repeat(n)}<span class="off">${"★".repeat(5 - n)}</span></span>`;
}

function avatar(name, color, size = "") {
  return `<div class="avatar ${size}" style="background:${esc(color)}">${esc(initials(name))}</div>`;
}

// buyers use the darker of their two colors with white initials
function buyerAvatar(name, colors, size = "") {
  return `<div class="avatar ${size}" style="background:${colors[1]};color:#fff">${esc(initials(name))}</div>`;
}

// lives left in the gauntlet and spot the mistake (out of 3)
function hearts(n) {
  return `<span class="hp">${"♥".repeat(n)}<span class="gone">${"♥".repeat(3 - n)}</span></span>`;
}

function timeAgo(iso) {
  const sec = (Date.now() - new Date(iso).getTime()) / 1000;
  if (sec < 60) return "just now";
  if (sec < 3600) return Math.floor(sec / 60) + "m ago";
  if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
  return Math.floor(sec / 86400) + "d ago";
}

async function api(path, body, method) {
  const res = await fetch(path, {
    method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (${res.status})`);
  return data;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function go(hash) {
  location.hash = hash;
}

// buyers people built themselves, by id (filled in by build.js)
const customBuyers = {};

function findCharacter(id) {
  for (const cat of state.categories) {
    for (const c of cat.characters) {
      if (c.id === id) return c;
    }
  }
  return customBuyers[id] || null;
}

const CUSTOM_CATEGORY = {
  id: "custom", name: "Your buyers", call_type: "phone", you_are: "a sales rep",
  labels: { meeting: "Book the meeting", close: "Close the deal", upsell: "Land the upsell" },
};

function findCategory(id) {
  return state.categories.find((c) => c.id === id) || (id === "custom" ? CUSTOM_CATEGORY : undefined);
}

// the industry for a buyer. custom buyers carry their own "you are" and phone/door setting
function categoryFor(c) {
  if (c.custom) return { ...CUSTOM_CATEGORY, you_are: c.you_are, call_type: c.call_type };
  return findCategory(c.category);
}

async function refreshCategories() {
  const [cats, plan] = await Promise.all([api("/api/categories"), api("/api/plan")]);
  state.categories = cats;
  state.plan = plan;
}

const OUTCOME_TEXT = {
  closed: "Deal closed",
  meeting_booked: "Meeting booked",
  follow_up: "Warm lead",
  hung_up: "They hung up",
  ended: "No deal",
  completed: "Completed",
};
