import "./style.css";
import { initializeAuth, request } from "./api.js";
import {
  chartSegments,
  formatMoney,
  priceStatus,
  createGeneration,
} from "./model.js";
const $ = (id) => document.getElementById(id);
const state = {
  page: 1,
  days: 30,
  selected: null,
  list: [],
  demo: false,
  section: "games",
  listRequest: 0,
  chartRequest: 0,
  viewRequest: 0,
};
const workspace = createGeneration(),
  searchGeneration = createGeneration();
const stale = () =>
  Object.assign(new Error("Discarded old response"), { stale: true });
const guarded =
  (transport) =>
  async (...args) => {
    const version = workspace.current();
    try {
      const result = await transport(...args);
      if (!workspace.isCurrent(version)) throw stale();
      return result;
    } catch (error) {
      if (!workspace.isCurrent(version)) throw stale();
      throw error;
    }
  };
let auth,
  call = guarded(request),
  selection = null;
const text = (tag, value, className) => {
  const n = document.createElement(tag);
  n.textContent = value;
  if (className) n.className = className;
  return n;
};
const date = (v) => (v ? new Date(v).toLocaleString() : "Not checked yet");
const showError = (error) => {
  if (error.stale) return;
  $("notice").textContent = error.message || "Connection failed. Please retry.";
  if (!state.demo && [401, 403].includes(error.status)) {
    workspace.advance();
    ++state.listRequest;
    ++state.chartRequest;
    ++state.viewRequest;
    state.selected = null;
    clearChart("Select a game below");
    $("dashboard").hidden = true;
    $("login").hidden = false;
    document.querySelector("nav").hidden = true;
    $("login-state").textContent = error.message;
    $("retry").hidden = error.status !== 403;
  }
};
async function busy(button, action) {
  button.disabled = true;
  try {
    await action();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
}
async function summary() {
  const data = await call("/summary");
  $("game-count").textContent = data.games;
  $("deal-count").textContent = data.at_target;
  $("stale-count").textContent = data.stale;
  $("unknown-count").textContent = data.unknown;
  $("last-check").textContent =
    "Latest recorded observation: " + date(data.last_observed);
}
async function loadList() {
  const seq = ++state.listRequest;
  $("rows").replaceChildren();
  const pending = document.createElement("tr");
  const pendingCell = text("td", "Loading your games…", "empty-cell");
  pendingCell.colSpan = 5;
  pending.append(pendingCell);
  $("rows").append(pending);
  const params = new URLSearchParams({
    page: state.page,
    limit: 10,
    q: $("search").value,
    status: $("filter").value,
    sort: $("sort").value,
  });
  const result = await call("/games?" + params);
  if (seq !== state.listRequest) return;
  if (!result.items.length && state.page > 1) {
    state.page = 1;
    return loadList();
  }
  state.list = result.items;
  $("rows").replaceChildren();
  for (const game of result.items) {
    const tr = document.createElement("tr");
    tr.classList.toggle("selected", game.id === state.selected?.id);
    const name = document.createElement("td"),
      button = text("button", game.title, "row-title");
    button.setAttribute("aria-pressed", String(game.id === state.selected?.id));
    button.onclick = () => selectGame(game).catch(showError);
    name.append(
      button,
      text("small", "PC · " + (game.store || "Awaiting first check")),
    );
    tr.append(name);
    tr.append(
      text("td", formatMoney(game.price)),
      text(
        "td",
        game.target_price == null
          ? "Historical low"
          : formatMoney(game.target_price),
      ),
    );
    const status = priceStatus(game),
      cell = document.createElement("td");
    cell.append(
      text(
        "span",
        {
          deal: "At target",
          watching: "Watching",
          stale: "Stale price",
          unknown: "Not checked",
        }[status],
        "badge " + status,
      ),
    );
    tr.append(cell);
    const controls = document.createElement("td");
    controls.className = "actions-cell";
    const edit = text("button", "Edit target", "edit");
    edit.setAttribute("aria-label", "Edit target for " + game.title);
    edit.onclick = () =>
      busy(edit, async () => {
        const value = prompt(
          "Target price in ₹. Leave blank for historical-low alerts.",
          game.target_price ?? "",
        );
        if (value === null) return;
        const target = value.trim() === "" ? null : Number(value);
        if (
          target !== null &&
          (!Number.isFinite(target) || target < 0 || target > 1000000)
        )
          throw new Error("Enter a price between ₹0 and ₹1,000,000.");
        await call("/games/" + game.id, {
          method: "PATCH",
          body: JSON.stringify({ target_price: target }),
        });
        if (state.selected?.id === game.id)
          state.selected = { ...state.selected, target_price: target };
        await refresh();
      });
    const remove = text("button", "Remove", "edit");
    remove.setAttribute("aria-label", "Remove " + game.title);
    remove.onclick = () =>
      busy(remove, async () => {
        if (!confirm("Remove " + game.title + " and its recorded history?"))
          return;
        await call("/games/" + game.id, { method: "DELETE" });
        if (state.selected?.id === game.id) {
          state.selected = null;
          ++state.chartRequest;
          clearChart("Select a game below");
        }
        await refresh();
      });
    controls.append(edit, remove);
    tr.append(controls);
    $("rows").append(tr);
  }
  if (!result.items.length) {
    const row = document.createElement("tr"),
      cell = text(
        "td",
        "No games match. Change your filters or add a game.",
        "empty-cell",
      );
    cell.colSpan = 5;
    row.append(cell);
    $("rows").append(row);
  }
  $("page-label").textContent = result.total
    ? `${(state.page - 1) * 10 + 1}–${Math.min(state.page * 10, result.total)} of ${result.total} games`
    : "No matching games";
  $("previous").disabled = state.page === 1;
  $("next").disabled = state.page * 10 >= result.total;
  if (!state.selected && result.items.length) await selectGame(result.items[0]);
}
function clearChart(title) {
  $("chart-title").textContent = title;
  $("chart").replaceChildren();
  $("points").replaceChildren();
  $("chart-stats").textContent = "";
  $("chart-note").textContent = "Select a game to see its recorded prices.";
}
async function selectGame(game) {
  state.selected = game;
  const seq = ++state.chartRequest;
  clearChart(game.title);
  $("chart-note").textContent = "Loading history…";
  const data = await call(`/games/${game.id}/history?days=${state.days}`);
  if (seq !== state.chartRequest) return;
  state.selected = { ...game, ...data.game };
  drawChart(data.points, state.selected);
  for (const row of $("rows").children) {
    const button = row.querySelector(".row-title");
    if (button) {
      const selected = button.textContent === game.title;
      row.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    }
  }
}
function svgNode(tag, attributes, content) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attributes)) n.setAttribute(k, v);
  if (content != null) n.textContent = content;
  return n;
}
function drawChart(points, game) {
  const svg = $("chart");
  svg.replaceChildren();
  $("points").replaceChildren();
  $("chart-title").textContent = game.title;
  $("chart-stats").textContent =
    "Target: " +
    (game.target_price == null
      ? "Historical low"
      : formatMoney(game.target_price));
  $("chart-note").textContent = points.length
    ? `${points.length} observations over ${state.days} days. Store can change; gaps longer than 36 hours are shown as breaks.`
    : "No recorded prices in this date range. Try a longer range or wait for the next check.";
  svg.setAttribute(
    "aria-label",
    `${game.title}: ${points.length} recorded prices in ${state.days} days`,
  );
  if (!points.length) return;
  const times = points.map((p) => Date.parse(p.fetched_at)),
    end = Date.now(),
    start = end - state.days * 86400000;
  const prices = points.map((p) => Number(p.price));
  if (game.target_price != null) prices.push(Number(game.target_price));
  const min = Math.max(0, Math.min(...prices) * 0.85),
    max = Math.max(min + 100, Math.max(...prices) * 1.1);
  const x = (t) => 66 + ((t - start) / (end - start)) * 625,
    y = (v) => 196 - ((v - min) / (max - min)) * 163;
  for (let i = 0; i < 4; i++) {
    const v = min + ((max - min) * i) / 3,
      yy = y(v);
    svg.append(
      svgNode("path", { d: `M66 ${yy}H697`, stroke: "#40364d" }),
      svgNode("text", { x: 0, y: yy + 4 }, formatMoney(Math.round(v))),
    );
  }
  if (game.target_price != null)
    svg.append(
      svgNode("path", {
        d: `M66 ${y(game.target_price)}H697`,
        stroke: "#e83987",
        "stroke-width": 2,
        "stroke-dasharray": "5 6",
      }),
    );
  for (const segment of chartSegments(points)) {
    let d = `M${x(Date.parse(segment[0].fetched_at))} ${y(Number(segment[0].price))}`;
    for (const point of segment.slice(1))
      d += `H${x(Date.parse(point.fetched_at))}V${y(Number(point.price))}`;
    svg.append(
      svgNode("path", {
        d,
        stroke: "#aaa1ff",
        "stroke-width": 2.5,
        fill: "none",
      }),
    );
  }
  points.forEach((point, i) => {
    const mark = svgNode("circle", {
      cx: x(times[i]),
      cy: y(Number(point.price)),
      r: 3,
      fill: "#cec7ff",
    });
    mark.append(
      svgNode(
        "title",
        {},
        `${date(point.fetched_at)} · ${point.store} · ${formatMoney(point.price)}`,
      ),
    );
    svg.append(mark);
  });
  svg.append(
    svgNode("text", { x: 66, y: 227 }, new Date(start).toLocaleDateString()),
    svgNode("text", { x: 650, y: 227 }, "Today"),
  );
  for (const point of points.slice().reverse()) {
    const tr = document.createElement("tr");
    [date(point.fetched_at), point.store, formatMoney(point.price)].forEach(
      (v) => tr.append(text("td", v)),
    );
    $("points").append(tr);
  }
}
async function refresh() {
  await Promise.all([summary(), loadList()]);
  if (state.selected) await selectGame(state.selected);
}
async function enter() {
  const me = await call("/me");
  $("account").textContent = me.email || "Your private workspace";
  $("notice").textContent = "";
  $("login").hidden = true;
  $("dashboard").hidden = false;
  document.querySelector("nav").hidden = false;
  $("signout").hidden = false;
  $("demo-banner").hidden = !state.demo;
  await refresh();
}
async function section(name) {
  state.section = name;
  const seq = ++state.viewRequest;
  document
    .querySelectorAll("[data-page]")
    .forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  $("games-view").hidden = name !== "games";
  $("other-view").hidden = name === "games";
  $("add").hidden = name !== "games";
  if (name === "games") return;
  const panel = $("other-view");
  panel.replaceChildren(text("p", "Loading…", "muted"));
  const data = await call("/" + name);
  if (seq !== state.viewRequest) return;
  panel.replaceChildren(
    text(
      "h2",
      {
        watches: "Your watches",
        activity: "Recent game alerts",
        settings: "Alert preferences",
      }[name],
    ),
  );
  if (name === "settings") {
    const form = document.createElement("form");
    form.className = "setting-form";
    const label = text("label", "Notification email"),
      input = document.createElement("input");
    input.type = "email";
    input.maxLength = 254;
    input.value = data.email || "";
    input.placeholder = "Leave blank to disable email";
    label.append(input);
    const save = text("button", "Save preferences", "primary");
    form.append(
      label,
      save,
      text(
        "p",
        "Discord alerts continue as configured. Email delivery also requires the server’s email provider to be configured.",
        "hint",
      ),
    );
    form.onsubmit = (e) => {
      e.preventDefault();
      busy(save, async () => {
        await call("/settings", {
          method: "PATCH",
          body: JSON.stringify({ email: input.value.trim() || null }),
        });
        $("notice").textContent = "Preferences saved.";
      });
    };
    panel.append(form);
    return;
  }
  if (!data.items.length) {
    panel.append(text("p", "Nothing here yet.", "muted"));
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "table-scroll";
  const table = document.createElement("table");
  const head = document.createElement("tr");
  (name === "watches"
    ? ["Watch", "Latest price", "Target", "Observed"]
    : ["Game", "Alert price", "Sent"]
  ).forEach((v) => head.append(text("th", v)));
  const thead = document.createElement("thead");
  thead.append(head);
  table.append(thead);
  const tbody = document.createElement("tbody");
  for (const row of data.items) {
    const tr = document.createElement("tr");
    (name === "watches"
      ? [
          row.name,
          formatMoney(row.price),
          formatMoney(row.target_price),
          date(row.fetched_at),
        ]
      : [row.title, formatMoney(row.price), date(row.notified_at)]
    ).forEach((v) => tr.append(text("td", v)));
    tbody.append(tr);
  }
  table.append(tbody);
  wrap.append(table);
  panel.append(wrap);
  if (name === "watches")
    panel.append(
      text(
        "p",
        "Watch checks use the home-server runner. Prices may remain stale during maintenance.",
        "hint",
      ),
    );
}
$("previous").onclick = () => {
  state.page--;
  loadList().catch(showError);
};
$("next").onclick = () => {
  state.page++;
  loadList().catch(showError);
};
let debounce;
$("search").oninput = () => {
  clearTimeout(debounce);
  ++state.listRequest;
  debounce = setTimeout(() => {
    state.page = 1;
    loadList().catch(showError);
  }, 250);
};
for (const id of ["filter", "sort"])
  $(id).onchange = () => {
    state.page = 1;
    loadList().catch(showError);
  };
document.querySelectorAll("[data-days]").forEach(
  (button) =>
    (button.onclick = () => {
      state.days = Number(button.dataset.days);
      document
        .querySelectorAll("[data-days]")
        .forEach((b) => b.classList.toggle("active", b === button));
      if (state.selected) selectGame(state.selected).catch(showError);
    }),
);
document
  .querySelectorAll("[data-page]")
  .forEach(
    (button) =>
      (button.onclick = () => section(button.dataset.page).catch(showError)),
  );
$("add").onclick = () => {
  searchGeneration.advance();
  $("save-game").disabled = false;
  $("game-form").reset();
  selection = null;
  $("match").textContent = "";
  $("dialog-error").textContent = "";
  $("save-game").textContent = "Find game";
  $("game-dialog").showModal();
};
$("game-dialog").addEventListener("close", () => searchGeneration.advance());
$("cancel-add").onclick = () => {
  searchGeneration.advance();
  $("game-dialog").close();
};
$("new-title").oninput = () => {
  searchGeneration.advance();
  $("save-game").disabled = false;
  selection = null;
  $("save-game").textContent = "Find game";
  $("match").textContent = "";
};
$("game-form").onsubmit = async (e) => {
  e.preventDefault();
  const version = searchGeneration.current();
  const button = $("save-game");
  button.disabled = true;
  $("dialog-error").textContent = "";
  try {
    if (!selection) {
      const found = await call("/search", {
        method: "POST",
        body: JSON.stringify({ title: $("new-title").value }),
      });
      if (!searchGeneration.isCurrent(version) || !$("game-dialog").open)
        return;
      selection = found.selection;
      $("match").textContent = "Confirm this match: " + found.title + " · PC";
      button.textContent = "Confirm and track";
    } else {
      await call("/games", {
        method: "POST",
        body: JSON.stringify({
          selection,
          target_price:
            $("new-target").value === "" ? null : Number($("new-target").value),
        }),
      });
      $("game-dialog").close();
      $("notice").textContent =
        "Game tracked. A price will appear after its next scheduled check.";
      await refresh();
    }
  } catch (error) {
    if (searchGeneration.isCurrent(version) && !error.stale)
      $("dialog-error").textContent = error.message;
  } finally {
    if (searchGeneration.isCurrent(version)) button.disabled = false;
  }
};
$("demo").onclick = () =>
  busy($("demo"), async () => {
    const { demoRequest } = await import("./demo.js");
    workspace.advance();
    ++state.listRequest;
    ++state.chartRequest;
    ++state.viewRequest;
    state.selected = null;
    state.page = 1;
    state.demo = true;
    call = guarded(demoRequest);
    clearChart("Select a game below");
    await enter();
  });
$("signout").onclick = () =>
  busy($("signout"), async () => {
    if (auth && !state.demo) {
      const { error } = await auth.auth.signOut();
      if (error) throw error;
    }
    location.assign("/");
  });
$("retry").onclick = () => busy($("retry"), enter);
$("google").disabled = true;
$("google").onclick = () =>
  busy($("google"), async () => {
    const { error } = await auth.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: location.origin + "/" },
    });
    if (error) throw error;
  });
(async () => {
  try {
    auth = await initializeAuth();
    $("google").disabled = false;
    const {
      data: { session },
      error,
    } = await auth.auth.getSession();
    history.replaceState(null, "", location.pathname);
    if (error) throw error;
    if (state.demo) return;
    if (session) {
      $("signout").hidden = false;
      await enter();
    } else
      $("login-state").textContent = "Google sign-in · approved members only";
  } catch (error) {
    if (!state.demo) {
      $("login-state").textContent = error.message;
      showError(error);
    }
  }
})();
