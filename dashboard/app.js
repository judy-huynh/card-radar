// Card Radar dashboard. Four views (Deals, Leads, Values, Settings), every long list paged.
// No framework: fetch /api/state, render the current view, post edits back.
// When window.SAMPLE exists (GitHub Pages / design preview) it renders that and edits stay local.
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const usd = v => v == null ? "—" : Math.round(v).toLocaleString("en-US");
  const gapCls = g => g == null ? "" : g <= -20 ? "c-good" : g <= -5 ? "c-warn" : "";
  // Potential return = value − landed cost, before selling fees; % is on what you'd pay.
  const ret = l => {
    if (l.gap_pct == null || l.value_usd == null || l.landed_usd == null) return '<span class="na">—</span>';
    const p = l.value_usd - l.landed_usd, pct = p / l.landed_usd * 100;
    return `<span class="gap ${gapCls(l.gap_pct)}">${p >= 0 ? "+" : "−"}$${usd(Math.abs(p))}</span><span class="alt">${p >= 0 ? "+" : "−"}${Math.abs(Math.round(pct))}%</span>`;
  };
  const MP = { TCGPLAYER: "TCGplayer", EBAY_US: "eBay US", EBAY_CA: "eBay CA", EBAY_GB: "eBay UK", EBAY_AU: "eBay AU", EBAY_DE: "eBay DE" };
  const MP_COUNTRY = { TCGPLAYER: "US", EBAY_US: "US", EBAY_CA: "CA", EBAY_GB: "GB", EBAY_AU: "AU", EBAY_DE: "DE" };
  const AGENTS = {
    catalog: ["Card values", "TCGplayer prices for every target card, daily"],
    fx: ["Exchange rates", "Daily currency rates"],
    decider: ["Scoring", "Matches and scores each listing"],
    notifier: ["Phone alerts", "Sends ntfy pushes"],
    watchdog: ["Watchdog", "Warns you when something breaks"],
  };
  const PAGE = { deals: 10, log: 10, feed: 20, values: 20 };
  const VIEWS = ["deals", "leads", "values", "settings"];
  const SAMPLE = window.SAMPLE || null;
  let S = null, view = "deals", feedTab = "look", valTarget = null, valRows = [];
  const page = { deals: 0, log: 0, feed: 0, values: 0 };

  const variant = s => (s || "").replace("Holofoil", "Holo");
  const market = l => `${esc(MP[l.marketplace] || l.marketplace)}${l.item_country && l.item_country !== MP_COUNTRY[l.marketplace] ? ` · from ${esc(l.item_country)}` : ""}`;
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const ago = ts => {
    if (!ts) return "—";
    const m = Math.round((Date.now() - new Date(ts.replace(" ", "T"))) / 60000);
    return m < 1 ? "now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
  };

  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `${path}: ${r.status}`);
    return j;
  }
  let toastTimer;
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2000);
  }

  // ---- sorting: click a column header; every list starts at the highest potential return --------
  const profit = l => (l.value_usd == null || l.landed_usd == null || l.gap_pct == null) ? null : l.value_usd - l.landed_usd;
  const COND_RANK = { NM: 5, LP: 4, MP: 3, HP: 2, DMG: 1 };
  const SORT_KEYS = {
    card: l => ((l.name ? l.name + " " + l.number : l.title) || "").toLowerCase(),
    where: l => MP[l.marketplace] || l.marketplace || "",
    landed: l => l.landed_usd, value: l => l.value_usd, ret: profit,
    cond: l => COND_RANK[l.condition] || 0,
    tcg: c => c.market, collectr: c => c.override_usd,
  };
  const sortBy = { deals: ["ret", -1], feed: ["ret", -1], values: ["tcg", -1] };
  function sorted(table, rows) {
    const [key, dir] = sortBy[table], get = SORT_KEYS[key];
    const unsure = l => l.confidence === "low" ? 1 : 0;   // a "sure" match always ranks above an unsure one
    return rows.slice().sort((a, b) => {
      if (table === "feed" && unsure(a) !== unsure(b)) return unsure(a) - unsure(b);
      const x = get(a), y = get(b);
      if (x == null || y == null) return (x == null) - (y == null);   // blanks last either way
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
  }
  function markHeaders() {
    $$("th[data-sort]").forEach(th => {
      const [key, dir] = sortBy[th.closest("table").id === "feed" ? "feed" : th.closest("table").id];
      const on = th.dataset.sort === key;
      th.setAttribute("aria-sort", on ? (dir < 0 ? "descending" : "ascending") : "none");
      if (!on) return;
      // tint the whole sorted column so it's obvious which one is driving the order
      const table = th.closest("table"), i = th.cellIndex;
      table.querySelectorAll("td.sorted").forEach(td => td.classList.remove("sorted"));
      table.querySelectorAll("tbody tr").forEach(tr => tr.cells.length > i && tr.cells[i].classList.add("sorted"));
    });
  }
  const dealsOpen = () => sorted("deals", S.deals.filter(d => d.decision === "open"));

  // ---- paging ------------------------------------------------------------
  function slice(key, rows) {
    const size = PAGE[key], pages = Math.max(1, Math.ceil(rows.length / size));
    page[key] = Math.min(page[key], pages - 1);
    return rows.slice(page[key] * size, page[key] * size + size);
  }
  function pager(key, total) {
    const el = $(`#pg-${key}`), size = PAGE[key];
    if (total <= size) { el.innerHTML = ""; return; }
    const from = page[key] * size + 1, to = Math.min(total, from + size - 1);
    el.innerHTML = `<span>${from}–${to} of ${total}</span><span class="acts">
      <button data-page="${key}" data-dir="-1" ${page[key] === 0 ? "disabled" : ""}>Previous</button>
      <button data-page="${key}" data-dir="1" ${to >= total ? "disabled" : ""}>Next</button></span>`;
  }

  // ---- cells -------------------------------------------------------------
  function cardCell(l, withSeller) {
    const name = l.name ? `${esc(l.name)} ${esc(l.number)}` : esc(l.title);
    const bits = [l.name && `${esc(l.set_name)} · ${esc(variant(l.subtype))}`, l.grade && esc(l.grade), market(l),
                  withSeller && l.feedback != null && `seller ${l.feedback} feedback`].filter(Boolean);
    return `<div class="cardcell">${thumb(l)}<div class="cardtext"><div class="title"><a class="cardlink" href="${esc(l.url)}" target="_blank" rel="noopener">${name}</a></div>
      ${mine(l)}<div class="meta">${bits.join(" · ")}</div>${warnLine(l)}</div></div>`;
  }
  // Listing photo; a plain card-shaped tile when there is none (TCGplayer rows, the preview)
  const thumb = l => `<span class="thumb">${l.image ? `<img src="${esc(l.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</span>`;

  // ★ = one of the six targets Judy listed. Anything rejected (other cards, lots, Japanese…) never gets it.
  function mine(l) {
    if (l.tier === "REJECT" || !l.name) return "";
    const t = S.targets.find(x => x.id === l.target_id);
    return `<span class="mine" title="Matches one of your six targets">★ Match · ${esc(t ? t.label : l.target_id)}</span>`;
  }

  const warnLine = l => /check photos/.test(l.reason || "") ? `<div class="reason c-warn">⚠ ${esc(l.reason.split(" · ").slice(1).join(" · "))}</div>` : "";
  function landedCell(l) {
    const d = l.landed || {}, keys = Object.keys(d).sort((a, b) => d[a].usd - d[b].usd);
    if (!keys.length) return "—";
    const k = keys[0];
    return `${usd(d[k].usd)}${d[k].ship_estimated ? "*" : ""} <span class="unit">${esc(k)}</span>`;
  }
  const valueCell = l => l.value_usd == null ? `<span class="c-warn">unknown</span>`
    : `${usd(l.value_usd)}<span class="src">${esc(l.value_source || "")}</span>`;
  function condCell(l) {
    const c = l.condition;
    const cls = !c ? "warn" : c === "NM" ? "good" : c === "LP" ? "warn" : "bad";
    const label = { NM: "Near mint", LP: "Light play", MP: "Moderate play", HP: "Heavy play", DMG: "Damaged" }[c] || "Not stated";
    return `<span class="pill ${cls}">${label}</span>`;
  }

  // ---- views -------------------------------------------------------------
  function renderHeader(s) {
    const lr = s.last_run;
    $("#scaninfo").textContent = lr ? `Last scan ${ago(lr.started)}` : "No scan yet";
    const problems = s.agents.filter(a => a.last_error_at && (!a.last_ok || a.last_error_at > a.last_ok));
    const pill = $("#syspill");
    pill.className = "syspill " + (problems.length ? "bad" : s.agents.length ? "ok" : "");
    $(".radar").classList.toggle("down", problems.length > 0);
    pill.textContent = problems.length === 1 ? problems[0].last_error.split(":")[0].replace(/ \(\d+\)$/, "") : problems.length ? plural(problems.length, "issue") : "All systems OK";
    const open = s.deals.filter(d => d.decision === "open");
    const nd = $("#n-deals"); nd.textContent = open.length || ""; nd.classList.toggle("hot", open.length > 0);
    $("#n-leads").textContent = "";
    if (s.example && !$(".example-banner")) {
      $("header").insertAdjacentHTML("afterend", `<div class="example-banner">Design preview with example data. The live dashboard runs on the iMac over Tailscale.</div>`);
    }
  }

  function renderDeals(s) {
    const open = s.deals.filter(d => d.decision === "open");
    const best = open.filter(d => profit(d) != null).sort((a, b) => profit(b) - profit(a))[0];
    $("#tiles").innerHTML = [
      ["To review", open.length, `${open.filter(d => d.tier === "DEAL").length} under threshold`],
      ["Best potential return", best ? `+$${usd(profit(best))}` : "—", best ? `${best.name} ${best.number}` : ""],
      ["Pushed this week", s.stats.deals_week, `${s.stats.bought_week} bought`],
    ].map(([k, v, m]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}${m ? `<small>${esc(m)}</small>` : ""}</div></div>`).join("");

    const rows = slice("deals", dealsOpen());
    $("#deals tbody").innerHTML = rows.length ? rows.map(d => `
      <tr id="alert-${d.alert_id}" data-id="${d.alert_id}">
        <td class="c-card">${cardCell(d, true)}</td>
        <td class="num c-landed" data-label="Landed US$">${landedCell(d)}<span class="alt">ask ${Number(d.price).toLocaleString("en-US")} ${esc(d.currency)}</span></td>
        <td class="num c-value" data-label="Value US$">${valueCell(d)}</td>
        <td class="num c-gap">${d.gap_pct == null ? `<span class="tier LISTED">NO VALUE</span>` : ret(d)}</td>
        <td class="c-cond">${condCell(d)}</td>
        <td class="c-acts"><div class="acts"><a class="btn primary" href="${esc(d.url)}" target="_blank" rel="noopener">Open</a><button data-act="passed">Pass</button><button data-act="bought">Bought</button></div></td>
      </tr>`).join("")
      : `<tr><td colspan="6" class="empty">Nothing to review. New listings of your six cards show up here and on your phone.</td></tr>`;
    pager("deals", open.length);

    $("#n-log").textContent = s.log.length ? `(${s.log.length})` : "";
    const logRows = slice("log", s.log);
    $("#log tbody").innerHTML = logRows.length ? logRows.map(a => `<tr>
      <td><div class="title">${a.name ? esc(a.name + " " + a.number) : esc(a.title)}</div><div class="meta">${esc((a.sent_at || "").slice(5, 16))}</div></td>
      <td class="num">${usd(a.landed_usd)}</td><td class="num">${usd(a.value_usd)}</td>
      <td>${esc(a.decision)}</td><td>${esc(a.outcome || "—")}</td></tr>`).join("")
      : `<tr><td colspan="5" class="empty">Nothing yet. Pass or Bought a deal and it moves here.</td></tr>`;
    pager("log", s.log.length);
  }

  const FEED_TABS = [
    ["look", "Worth a look", l => ["DEAL", "LISTED", "WATCH"].includes(l.tier)],
    ["all", "All", () => true],
    ["seen", "At market", l => l.tier === "SEEN"],
    ["reject", "Rejected", l => l.tier === "REJECT"],
  ];
  function renderLeads(s) {
    const tabs = FEED_TABS.map(([k, label, f]) => [k, label, s.feed.filter(f)]);
    $("#feedtabs").innerHTML = tabs.map(([k, label, rows]) =>
      `<button role="tab" data-tab="${k}" aria-selected="${k === feedTab}">${label}<span class="count">${rows.length}</span></button>`).join("");
    let rows = tabs.find(t => t[0] === feedTab)[2];
    const tcg = rows.some(l => l.marketplace === "TCGPLAYER");
    $("#feednote").hidden = !tcg;
    rows = sorted("feed", rows);
    const shown = slice("feed", rows);
    $("#feed tbody").innerHTML = shown.length ? shown.map(l => `
      <tr${mine(l) ? ' class="onlist"' : ""}>
        <td><div class="cardcell">${thumb(l)}<div class="cardtext">${l.name ? `<div class="title"><a class="cardlink" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)} ${esc(l.number)}</a></div>${mine(l)}<div class="meta">${esc(l.set_name)} · ${esc(variant(l.subtype))}${l.grade ? " · " + esc(l.grade) : ""}</div>`
          : `<div class="rawtitle"><a class="cardlink" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a></div>`}</div></div></td>
        <td>${market(l)}<div class="meta">${ago(l.first_seen)}</div></td>
        <td class="num">${landedCell(l)}</td>
        <td class="num">${l.tier === "REJECT" ? '<span class="na">—</span>' : valueCell(l)}</td>
        <td class="num">${l.tier === "REJECT" ? '<span class="na">—</span>' : ret(l)}</td>
        <td><span class="tier ${esc(l.tier)}">${esc(l.tier)}</span><div class="reason">${/^[+-]?\d+% vs value$/.test(l.reason || "") ? "" : esc(l.reason || "")}</div></td>
      </tr>`).join("")
      : `<tr><td colspan="6" class="empty">${s.feed.length ? "Nothing here." : "Nothing found yet. Results appear after the first scan."}</td></tr>`;
    pager("feed", rows.length);
  }

  async function loadValues() {
    if (!valTarget) return;
    try { valRows = SAMPLE ? (SAMPLE.values[valTarget] || []) : await api(`/api/values?target=${encodeURIComponent(valTarget)}`); }
    catch (e) { toast(e.message); return; }
    renderValues();
  }
  function renderValues() {
    const rows = slice("values", sorted("values", valRows));
    markHeaders();
    $("#values tbody").innerHTML = rows.length ? rows.map(c => `<tr data-key="${esc(c.card_key)}">
      <td><div class="title">${c.tcg_url ? `<a class="cardlink" href="${esc(c.tcg_url)}" target="_blank" rel="noopener">${esc(c.name)} ${esc(c.number)}</a>` : esc(c.name + " " + c.number)}</div><div class="meta">${esc(variant(c.subtype))}</div></td>
      <td class="num">${c.market == null ? `<span class="c-warn">no sales</span>` : usd(c.market)}</td>
      <td class="num"><input class="th ov" id="ov-${esc(c.card_key)}" value="${c.override_usd ?? ""}" placeholder="—" inputmode="decimal" aria-label="Collectr value for ${esc(c.name)}"></td>
    </tr>`).join("") : `<tr><td colspan="3" class="empty">No cards loaded yet.</td></tr>`;
    pager("values", valRows.length);
  }

  function renderSettings(s) {
    const every = !!s.push_every_listing;
    document.querySelectorAll("#pushmode button").forEach(b => b.setAttribute("aria-selected", String((b.dataset.push === "1") === every)));
    $("#pushnote").textContent = every
      ? "Every new listing of the six cards pushes, whatever the price. Deals are marked DEAL. Lots, fakes, Japanese copies and other cards never push."
      : "Only listings under the push gap below, or with no known value, push. Everything else waits in Leads.";
    $("#targets tbody").innerHTML = s.targets.map(t => `<tr data-id="${esc(t.id)}">
      <td class="title">${esc(t.label)}</td>
      <td class="num"><input class="th" id="push-${esc(t.id)}" data-k="push_gap_pct" value="${t.push_gap_pct}" inputmode="decimal" aria-label="Push gap for ${esc(t.label)}"></td>
      <td class="num"><input class="th" id="min-${esc(t.id)}" data-k="min_value_usd" value="${t.min_value_usd}" inputmode="decimal" aria-label="Minimum value for ${esc(t.label)}"></td>
      <td class="num"><input class="th" id="max-${esc(t.id)}" data-k="max_price_usd" value="${t.max_price_usd}" inputmode="decimal" aria-label="Maximum landed for ${esc(t.label)}"></td>
      <td><button class="pill ${t.paused ? "paused" : "active"}" data-toggle="paused">${t.paused ? "Paused" : "Active"}</button></td>
    </tr>`).join("");
    $("#targets2 tbody").innerHTML = s.targets.map(t => {
      const c = s.target_counts[t.id] || {};
      return `<tr data-id="${esc(t.id)}"><td class="title">${esc(t.label)}</td>
        <td class="num"><input class="th" id="watch-${esc(t.id)}" data-k="watch_gap_pct" value="${t.watch_gap_pct}" inputmode="decimal" aria-label="Watch gap for ${esc(t.label)}"></td>
        <td class="num">${Object.values(c).reduce((a, b) => a + b, 0)}</td></tr>`;
    }).join("");
    $("#agents tbody").innerHTML = s.agents.length ? s.agents.slice().sort((a, b) => a.agent.localeCompare(b.agent)).map(a => {
      const bad = a.last_error_at && (!a.last_ok || a.last_error_at > a.last_ok);
      const [name, job] = AGENTS[a.agent] || (a.agent.startsWith("scout:") ? [`Search · ${MP[a.agent.slice(6)] || a.agent.slice(6)}`, "Finds new listings"] : [a.agent, ""]);
      return `<tr><td><div class="title">${esc(name)}</div><div class="meta">${esc(job)}</div></td>
        <td>${a.last_ok ? ago(a.last_ok) : "never"}</td>
        <td class="${bad ? "err" : "meta"}">${a.last_error_at ? esc(a.last_error) : "—"}</td></tr>`;
    }).join("") : `<tr><td colspan="3" class="empty">Nothing has run yet.</td></tr>`;
    $("#runs tbody").innerHTML = s.runs.length ? s.runs.map(r => `<tr><td>${esc(r.started.slice(5, 16))}</td><td class="num">${r.calls}</td>
      <td class="num">${r.results}</td><td class="num">${r.new_listings}</td><td class="num">${r.pushes}</td>
      <td class="${r.errors.length ? "err" : "meta"}">${esc(r.errors.slice(0, 2).join(" · ") || "ok")}</td></tr>`).join("")
      : `<tr><td colspan="6" class="empty">No scans yet.</td></tr>`;
    const sel = $("#valtarget");
    if (!sel.options.length) {
      sel.innerHTML = s.targets.map(t => `<option value="${esc(t.id)}">${esc(t.label)}</option>`).join("");
      valTarget = s.targets[0] && s.targets[0].id;
    }
  }

  function render(s) {
    S = s;
    renderHeader(s);
    renderSettings(s);   // also fills the Values target picker
    if (view === "deals") renderDeals(s);
    if (view === "leads") renderLeads(s);
    if (view === "values" && !valRows.length) loadValues();
    markHeaders();
  }

  // ---- routing: #deals #leads #values #settings, plus #alert-N and #system --------------
  function route() {
    const h = (location.hash || "").slice(1);
    const alert = /^alert-(\d+)$/.exec(h);
    view = alert ? "deals" : h === "system" ? "settings" : VIEWS.includes(h) ? h : "deals";
    $$("[data-panel]").forEach(p => { p.hidden = p.dataset.panel !== view; });
    $$("#views a").forEach(a => { if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    if (alert && S) {   // jump to the page that holds the tapped alert
      const open = dealsOpen();
      const i = open.findIndex(d => String(d.alert_id) === alert[1]);
      if (i >= 0) page.deals = Math.floor(i / PAGE.deals);
    }
    if (S) render(S);
    if (alert) {
      $$("tr.focus").forEach(r => r.classList.remove("focus"));
      const row = document.getElementById(h);
      if (row) { row.classList.add("focus"); row.scrollIntoView({ block: "center" }); }
    }
    if (h === "system") { const el = $("#system"); if (el) el.scrollIntoView(); }
  }

  async function load() {
    if (SAMPLE) { S = SAMPLE; return route(); }
    try { S = await api("/api/state"); route(); }
    catch (e) { $("#scaninfo").textContent = "Can't reach the Card Radar server: " + e.message; }
  }

  // ---- events --------------------------------------------------------------
  document.addEventListener("click", async e => {
    const th = e.target.closest("th[data-sort]");
    if (th) {
      const table = th.closest("table").id, cur = sortBy[table];
      // same column flips direction; a new column starts high-to-low for numbers, A–Z for names
      sortBy[table] = cur[0] === th.dataset.sort ? [cur[0], -cur[1]] : [th.dataset.sort, ["card", "where"].includes(th.dataset.sort) ? 1 : -1];
      page[table] = 0;
      if (table === "values") renderValues(); else render(S);
      return;
    }
    const pg = e.target.closest("button[data-page]");
    if (pg) {
      const k = pg.dataset.page; page[k] += Number(pg.dataset.dir);
      if (k === "values") renderValues(); else render(S);
      $(`#pg-${k}`).previousElementSibling.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    const tab = e.target.closest("button[data-tab]");
    if (tab) { feedTab = tab.dataset.tab; page.feed = 0; renderLeads(S); return; }
    const act = e.target.closest("button[data-act]");
    if (act) {
      const tr = act.closest("tr"), id = tr.dataset.id, decision = act.dataset.act;
      if (SAMPLE) { tr.classList.add("decided"); toast(decision === "bought" ? "Marked bought (example)" : "Passed (example)"); return; }
      try { await api(`/api/alerts/${id}/decision`, { method: "POST", body: JSON.stringify({ decision }) }); toast(decision === "bought" ? "Marked bought" : "Passed"); load(); }
      catch (err) { toast(err.message); }
      return;
    }
    const pm = e.target.closest("#pushmode button");
    if (pm) {
      const on = pm.dataset.push === "1";
      if (SAMPLE) { toast("Saved (example)"); return; }
      try { await api("/api/settings/push_every_listing", { method: "POST", body: JSON.stringify({ on }) }); toast(on ? "Every listing will push" : "Deals only"); load(); }
      catch (err) { toast(err.message); }
      return;
    }
    const tog = e.target.closest("button[data-toggle=paused]");
    if (tog) {
      const id = tog.closest("tr").dataset.id, paused = tog.textContent.trim() === "Active";
      if (SAMPLE) { toast("Saved (example)"); return; }
      try { await api(`/api/targets/${id}`, { method: "POST", body: JSON.stringify({ paused }) }); toast(paused ? "Paused" : "Active"); load(); }
      catch (err) { toast(err.message); }
    }
  });

  document.addEventListener("change", async e => {
    if (e.target.id === "valtarget") { valTarget = e.target.value; page.values = 0; loadValues(); return; }
    const inp = e.target.closest("input.th");
    if (!inp) return;
    const raw = inp.value.trim().replace(/[$,%\s]/g, "");
    if (raw !== "" && Number.isNaN(Number(raw))) { toast("Enter a number"); return; }
    if (SAMPLE) { toast("Saved (example)"); return; }
    try {
      if (inp.classList.contains("ov")) {
        await api("/api/overrides", { method: "POST", body: JSON.stringify({ card_key: inp.closest("tr").dataset.key, value_usd: raw === "" ? null : Number(raw) }) });
        toast(raw === "" ? "Back to TCGplayer value" : "Collectr value saved");
      } else {
        if (raw === "") { toast("Enter a number"); return; }
        await api(`/api/targets/${inp.closest("tr").dataset.id}`, { method: "POST", body: JSON.stringify({ [inp.dataset.k]: Number(raw) }) });
        toast("Saved");
      }
      load();
    } catch (err) { toast(err.message); }
  });

  $("#bulksave").addEventListener("click", async () => {
    const text = $("#bulktext").value, out = $("#bulkresult");
    if (!text.trim()) { out.textContent = "Paste at least one line."; return; }
    if (SAMPLE) { out.textContent = "Saved (example)."; return; }
    try {
      const r = await api("/api/overrides/bulk", { method: "POST", body: JSON.stringify({ target_id: valTarget, text }) });
      out.innerHTML = `Saved ${r.saved}.` + (r.unmatched.length ? ` Not saved: ${r.unmatched.map(u => `<b>${esc(u.line)}</b> (${esc(u.why)})`).join("; ")}` : "");
      if (!r.unmatched.length) $("#bulktext").value = "";
      loadValues(); load();
    } catch (err) { out.textContent = err.message; }
  });

  addEventListener("hashchange", route);
  route();
  load();
  if (!SAMPLE) setInterval(() => { if (!document.querySelector("input:focus, textarea:focus")) load(); }, 60000);
})();
