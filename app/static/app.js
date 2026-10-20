"use strict";

// ---------- Helpers ----------

const $ = (sel, root = document) => root.querySelector(sel);
const AGES = [1, 2, 3, 4, 5, 6, 7];
// Soft accent colours for category tiles; picked by category id so they stay stable.
const PALETTE = ["#e8846b", "#f0b44c", "#8cbf6a", "#5fb3a8", "#6a9fd8", "#9b86d6", "#d97fb0", "#c99a6b"];

const state = {
  categories: [],
  age: loadAge(),
  query: "",
  navDepth: 0,
};

function loadAge() {
  try { return Number(localStorage.getItem("age")) || null; } catch { return null; }
}
function saveAge(age) {
  try { age ? localStorage.setItem("age", age) : localStorage.removeItem("age"); } catch {}
}

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(c));
  }
  return el;
}

async function api(path, { method = "GET", json, body } = {}) {
  const opts = { method, headers: {} };
  if (json !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(json);
  } else if (body) {
    opts.body = body;
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail; } catch {}
    const err = new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

function colorFor(id) {
  return PALETTE[(id - 1 + PALETTE.length) % PALETTE.length];
}

function ageLabel(g) {
  if (g.age_min && g.age_max) return g.age_min === g.age_max ? `${g.age_min} a` : `${g.age_min}–${g.age_max} a`;
  if (g.age_min) return `alates ${g.age_min} a`;
  if (g.age_max) return `kuni ${g.age_max} a`;
  return null;
}

function gamesWord(n) {
  return n === 1 ? "1 mäng" : `${n} mängu`;
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 2500);
}

function showError(err) {
  console.error(err);
  toast(err.status ? "Midagi läks valesti. Proovi uuesti." : "Serveriga ei saa ühendust.");
}

// ---------- Routing ----------
// #/              home: categories
// #/koik          all games
// #/kategooria/3  games in a category
// #/mang/5        one game

function go(hash) {
  state.navDepth++;
  location.hash = hash;
}

function back() {
  if (state.navDepth > 0) {
    state.navDepth--;
    history.back();
  } else {
    location.replace("#/");
  }
}

window.addEventListener("hashchange", render);
$("#back-btn").addEventListener("click", back);

async function render() {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const view = $("#view");
  const isHome = !parts[0];
  $("#back-btn").hidden = isHome;
  $("#menu-btn").hidden = parts[0] !== "kategooria";
  $("#actionbar").hidden = parts[0] === "mang";
  try {
    if (parts[0] === "mang") await renderGame(view, Number(parts[1]));
    else if (parts[0] === "kategooria") await renderCategory(view, Number(parts[1]));
    else if (parts[0] === "koik") await renderGameList(view, { title: "Kõik mängud" });
    else await renderHome(view);
  } catch (err) {
    if (err.status === 404) {
      location.replace("#/");
      return;
    }
    showError(err);
  }
  window.scrollTo(0, 0);
}

function setTitle(text) {
  $("#title").textContent = text;
  document.title = text === "Mängukogu" ? text : `${text} · Mängukogu`;
}

// ---------- Shared pieces ----------

function ageFilterBar(onChange) {
  const bar = h("div", { class: "chips scroll", role: "group", "aria-label": "Vanus" });
  for (const age of [null, ...AGES]) {
    bar.append(h("button", {
      type: "button",
      class: "chip",
      "aria-pressed": String(state.age === age),
      onclick: (e) => {
        state.age = age;
        saveAge(age);
        for (const b of bar.children) b.setAttribute("aria-pressed", String(b === e.currentTarget));
        onChange();
      },
    }, age ? `${age} a` : "Kõik vanused"));
  }
  return bar;
}

function gameCard(g) {
  const first = g.categories[0];
  const thumb = g.thumb_url
    ? h("img", { src: g.thumb_url, alt: "", loading: "lazy" })
    : h("span", { class: "thumb-letter", style: `background:${first ? colorFor(first.id) : "var(--muted-bg)"}` },
        g.name.charAt(0).toUpperCase());
  const age = ageLabel(g);
  return h("a", { class: "game-card", href: `#/mang/${g.id}`, onclick: () => state.navDepth++ },
    h("div", { class: "thumb" }, thumb),
    h("div", { class: "game-info" },
      h("strong", {}, g.name),
      age && h("span", { class: "age-badge" }, age),
      g.categories.length > 0 && h("span", { class: "game-cats" }, g.categories.map((c) => c.name).join(" · ")),
    ),
  );
}

function gameList(games, emptyText) {
  if (!games.length) return h("p", { class: "empty" }, emptyText);
  return h("div", { class: "game-list" }, games.map(gameCard));
}

async function loadCategories() {
  state.categories = await api("/api/categories");
  return state.categories;
}

// ---------- Home ----------

async function renderHome(view) {
  setTitle("Mängukogu");
  const search = h("input", {
    type: "search",
    class: "search",
    placeholder: "Otsi mängu…",
    "aria-label": "Otsi mängu",
    autocomplete: "off",
    value: state.query,
  });
  const results = h("div");

  async function refresh() {
    const q = state.query.trim();
    if (q) {
      const params = new URLSearchParams({ q });
      if (state.age) params.set("age", state.age);
      const games = await api(`/api/games?${params}`);
      results.replaceChildren(gameList(games, "Ühtegi mängu ei leitud."));
    } else {
      results.replaceChildren(await categoryGrid());
    }
  }

  let timer;
  search.addEventListener("input", () => {
    state.query = search.value;
    clearTimeout(timer);
    timer = setTimeout(() => refresh().catch(showError), 200);
  });

  view.replaceChildren(
    h("div", { class: "toolbar" }, search, ageFilterBar(() => refresh().catch(showError))),
    results,
  );
  await refresh();
}

async function categoryGrid() {
  const cats = await loadCategories();
  let total = null;
  // With an age filter on, count only games for that age.
  let counts = Object.fromEntries(cats.map((c) => [c.id, c.game_count]));
  const params = state.age ? `?age=${state.age}` : "";
  const games = await api(`/api/games${params}`);
  total = games.length;
  if (state.age) {
    counts = {};
    for (const g of games) for (const c of g.categories) counts[c.id] = (counts[c.id] || 0) + 1;
  }

  const tile = (href, name, count, color, extraClass = "") =>
    h("a", { class: `cat-tile ${extraClass}`, href, style: `--accent:${color}`, onclick: () => state.navDepth++ },
      h("span", { class: "cat-name" }, name),
      h("span", { class: "cat-count" }, gamesWord(count || 0)),
    );

  return h("div", { class: "cat-grid" },
    tile("#/koik", "Kõik mängud", total, "var(--primary)", "all"),
    cats.map((c) => tile(`#/kategooria/${c.id}`, c.name, counts[c.id], colorFor(c.id))),
  );
}

// ---------- Game lists ----------

async function renderGameList(view, { title, categoryId }) {
  setTitle(title);
  const list = h("div");
  async function refresh() {
    const params = new URLSearchParams();
    if (categoryId) params.set("category", categoryId);
    if (state.age) params.set("age", state.age);
    const games = await api(`/api/games?${params}`);
    const emptyText = state.age
      ? "Selle vanuse jaoks pole siin veel mänge."
      : "Siin pole veel mänge. Lisa esimene mäng allolevast nupust.";
    list.replaceChildren(gameList(games, emptyText));
  }
  view.replaceChildren(h("div", { class: "toolbar" }, ageFilterBar(() => refresh().catch(showError))), list);
  await refresh();
}

let currentCategory = null;

async function renderCategory(view, id) {
  if (!state.categories.length) await loadCategories();
  currentCategory = state.categories.find((c) => c.id === id);
  if (!currentCategory) {
    const err = new Error("not found");
    err.status = 404;
    throw err;
  }
  await renderGameList(view, { title: currentCategory.name, categoryId: id });
}

// ---------- Game detail ----------

let currentGame = null;

async function renderGame(view, id) {
  const g = await api(`/api/games/${id}`);
  currentGame = g;
  setTitle(g.name);
  const age = ageLabel(g);
  view.replaceChildren(
    h("article", { class: "game-detail" },
      g.image_url
        ? h("a", { href: g.image_url, target: "_blank", class: "hero" }, h("img", { src: g.image_url, alt: g.name }))
        : null,
      h("h2", {}, g.name),
      age && h("p", { class: "age-badge big" }, `Vanus: ${age}`),
      g.categories.length > 0 && h("div", { class: "chips wrap" },
        g.categories.map((c) =>
          h("a", { class: "chip", href: `#/kategooria/${c.id}`, style: `--accent:${colorFor(c.id)}`,
                   onclick: () => state.navDepth++ }, c.name)),
      ),
      h("section", { class: "notes" },
        h("h3", {}, "Märkmed"),
        g.notes ? h("p", {}, g.notes) : h("p", { class: "muted" }, "Märkmeid pole."),
      ),
      h("div", { class: "detail-actions" },
        h("button", { type: "button", class: "primary", onclick: () => openGameForm(g) }, "Muuda"),
        h("button", { type: "button", class: "danger-text", onclick: () => deleteGame(g) }, "Kustuta mäng"),
      ),
    ),
  );
}

async function deleteGame(g) {
  if (!(await confirmDialog(`Kas kustutada mäng „${g.name}“?`))) return;
  try {
    await api(`/api/games/${g.id}`, { method: "DELETE" });
    toast("Mäng kustutatud");
    back();
  } catch (err) {
    showError(err);
  }
}

// ---------- Dialog plumbing ----------

for (const dlg of document.querySelectorAll("dialog")) {
  dlg.addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) dlg.close();
    // Tap on the dimmed backdrop closes small dialogs.
    else if (e.target === dlg && dlg.classList.contains("small")) dlg.close();
  });
}

function confirmDialog(text) {
  const dlg = $("#confirm-dialog");
  $("#confirm-text").textContent = text;
  return new Promise((resolve) => {
    const yes = $("#confirm-yes");
    const onYes = () => { dlg.close("yes"); };
    yes.addEventListener("click", onYes, { once: true });
    dlg.addEventListener("close", () => {
      yes.removeEventListener("click", onYes);
      resolve(dlg.returnValue === "yes");
      dlg.returnValue = "";
    }, { once: true });
    dlg.showModal();
  });
}

// ---------- Category add / rename / delete ----------

let editingCategory = null;

function openCategoryForm(category = null) {
  editingCategory = category;
  const form = $("#category-form");
  form.reset();
  form.name.value = category ? category.name : "";
  $("#category-dialog-title").textContent = category ? "Nimeta kategooria ümber" : "Uus kategooria";
  $("#category-error").hidden = true;
  $("#category-dialog").showModal();
  form.name.focus();
}

$("#add-category-btn").addEventListener("click", () => openCategoryForm());

$("#category-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const name = form.name.value.trim();
  const errEl = $("#category-error");
  if (!name) {
    errEl.textContent = "Sisesta kategooria nimi.";
    errEl.hidden = false;
    return;
  }
  try {
    if (editingCategory) {
      await api(`/api/categories/${editingCategory.id}`, { method: "PUT", json: { name } });
      toast("Kategooria nimetatud ümber");
    } else {
      await api("/api/categories", { method: "POST", json: { name } });
      toast("Kategooria lisatud");
    }
    $("#category-dialog").close();
    await loadCategories();
    render();
  } catch (err) {
    if (err.status === 409) {
      errEl.textContent = "Selle nimega kategooria on juba olemas.";
      errEl.hidden = false;
    } else {
      showError(err);
    }
  }
});

$("#menu-btn").addEventListener("click", () => {
  if (!currentCategory) return;
  $("#category-menu-title").textContent = currentCategory.name;
  $("#category-menu").showModal();
});

$("#rename-category-btn").addEventListener("click", () => {
  $("#category-menu").close();
  openCategoryForm(currentCategory);
});

$("#delete-category-btn").addEventListener("click", async () => {
  $("#category-menu").close();
  const c = currentCategory;
  const text = c.game_count
    ? `Kas kustutada kategooria „${c.name}“? Mängud jäävad alles, neilt kaob ainult see kategooria.`
    : `Kas kustutada kategooria „${c.name}“?`;
  if (!(await confirmDialog(text))) return;
  try {
    await api(`/api/categories/${c.id}`, { method: "DELETE" });
    toast("Kategooria kustutatud");
    await loadCategories();
    back();
  } catch (err) {
    showError(err);
  }
});

// ---------- Game add / edit ----------

const photo = { file: null, remove: false, objectUrl: null };
let editingGame = null;

for (const sel of ["#age-min", "#age-max"]) {
  const select = $(sel);
  select.append(h("option", { value: "" }, "–"), ...AGES.map((a) => h("option", { value: a }, String(a))));
}

function setPhotoPreview(src) {
  const img = $("#photo-preview");
  img.hidden = !src;
  $("#photo-empty").hidden = !!src;
  $("#photo-remove-btn").hidden = !src;
  if (src) img.src = src;
  else img.removeAttribute("src");
}

async function openGameForm(game = null, presetCategoryId = null) {
  editingGame = game;
  const form = $("#game-form");
  form.reset();
  $("#game-error").hidden = true;
  $("#game-dialog-title").textContent = game ? "Muuda mängu" : "Uus mäng";
  if (photo.objectUrl) URL.revokeObjectURL(photo.objectUrl);
  Object.assign(photo, { file: null, remove: false, objectUrl: null });

  form.name.value = game?.name ?? "";
  form.notes.value = game?.notes ?? "";
  form.age_min.value = game?.age_min ?? "";
  form.age_max.value = game?.age_max ?? "";
  setPhotoPreview(game?.thumb_url ?? null);

  const cats = state.categories.length ? state.categories : await loadCategories();
  const selected = new Set(game ? game.categories.map((c) => c.id) : presetCategoryId ? [presetCategoryId] : []);
  $("#category-picker").replaceChildren(
    ...cats.map((c) =>
      h("button", {
        type: "button",
        class: "chip",
        "data-id": c.id,
        style: `--accent:${colorFor(c.id)}`,
        "aria-pressed": String(selected.has(c.id)),
        onclick: (e) => {
          const b = e.currentTarget;
          b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
        },
      }, c.name)),
  );
  $("#game-dialog").showModal();
  $(".sheet-body").scrollTop = 0;
}

$("#add-game-btn").addEventListener("click", () => {
  const presetCategory = location.hash.startsWith("#/kategooria/") ? currentCategory?.id : null;
  openGameForm(null, presetCategory).catch(showError);
});

$("#photo-camera-btn").addEventListener("click", () => $("#photo-camera").click());
$("#photo-file-btn").addEventListener("click", () => $("#photo-file").click());
$("#photo-remove-btn").addEventListener("click", () => {
  photo.file = null;
  photo.remove = true;
  setPhotoPreview(null);
});

for (const input of [$("#photo-camera"), $("#photo-file")]) {
  input.addEventListener("change", () => {
    const file = input.files[0];
    input.value = "";
    if (!file) return;
    if (photo.objectUrl) URL.revokeObjectURL(photo.objectUrl);
    photo.file = file;
    photo.remove = false;
    photo.objectUrl = URL.createObjectURL(file);
    setPhotoPreview(photo.objectUrl);
  });
}

// Phone photos are several MB; shrink before upload so it is quick on mobile data.
async function shrinkPhoto(file, maxSide = 2000) {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size < 1.5e6) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.88));
    return blob || file;
  } catch {
    return file; // the server can handle the original too
  }
}

$("#game-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const errEl = $("#game-error");
  const name = form.name.value.trim();
  if (!name) {
    errEl.textContent = "Sisesta mängu nimi.";
    errEl.hidden = false;
    form.name.focus();
    return;
  }
  const payload = {
    name,
    notes: form.notes.value,
    age_min: form.age_min.value ? Number(form.age_min.value) : null,
    age_max: form.age_max.value ? Number(form.age_max.value) : null,
    category_ids: [...document.querySelectorAll("#category-picker .chip[aria-pressed=true]")].map((b) => Number(b.dataset.id)),
  };

  const saveBtn = $("#game-save");
  saveBtn.disabled = true;
  saveBtn.textContent = "Salvestan…";
  try {
    let game = editingGame
      ? await api(`/api/games/${editingGame.id}`, { method: "PUT", json: payload })
      : await api("/api/games", { method: "POST", json: payload });
    let message = editingGame ? "Muudatused salvestatud" : "Mäng lisatud";
    if (photo.file) {
      const body = new FormData();
      body.append("file", await shrinkPhoto(photo.file), "pilt.jpg");
      try {
        game = await api(`/api/games/${game.id}/image`, { method: "PUT", body });
      } catch {
        message = "Mäng salvestati, aga pilti ei õnnestunud üles laadida.";
      }
    } else if (photo.remove && editingGame?.image_url) {
      game = await api(`/api/games/${game.id}/image`, { method: "DELETE" });
    }
    $("#game-dialog").close();
    toast(message);
    await loadCategories();
    if (editingGame) render();
    else go(`#/mang/${game.id}`);
  } catch (err) {
    showError(err);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "Salvesta";
  }
});

render();
