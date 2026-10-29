// Card Radar dashboard. No framework: fetch /api/state, render, post edits back.
// When window.SAMPLE exists (GitHub Pages / design preview) it renders that instead and edits stay local.
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const usd = v => v == null ? "—" : Math.round(v).toLocaleString("en-US");
  const ask = (v, cur) => v == null ? "—" : `${Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 })} <span class="src">${esc(cur)}</span>`;
  const gapCls = g => g == null ? "" : g <= -20 ? "c-good" : g <= -5 ? "c-warn" : "";
  const gap = g => g == null ? "—" : `<span class="gap ${gapCls(g)}">${g > 0 ? "+" : ""}${Math.round(g)}%</span>`;
  const MP_COUNTRY = { EBAY_US: "US", EBAY_CA: "CA", EBAY_GB: "GB", EBAY_AU: "AU", EBAY_DE: "DE" };
  const market = l => `${esc(MP[l.marketplace] || l.marketplace)}${l.item_country && l.item_country !== MP_COUNTRY[l.marketplace] ? ` · ships from ${esc(l.item_country)}` : ""}`;
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const MP = { EBAY_US: "eBay US", EBAY_CA: "eBay CA", EBAY_GB: "eBay UK", EBAY_AU: "eBay AU", EBAY_DE: "eBay DE" };
  const AGENT_JOBS = {
    catalog: "Pulls every target card and its TCGplayer price, daily",
    fx: "Exchange rates, daily",
    decider: "Matches, values and scores each listing",
    notifier: "Sends ntfy pushes",
    watchdog: "Health checks and the daily digest",
  };
  const variant = s => (s || "").replace("Holofoil", "Holo").replace("Unlimited Holo", "Unlimited holo");
  const ago = ts => {
    if (!ts) return "—";
    const m = Math.round((Date.now() - new Date(ts.replace(" ", "T"))) / 60000);
    return m < 1 ? "now" : m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
  };
  const SAMPLE = window.SAMPLE || null;
  let S = null, feedTab = "all", valTarget = null;

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

  function cardCell(l) {
    const name = l.name ? `${esc(l.name)} ${esc(l.number)}` : esc(l.title);
    const sub = l.name ? `${esc(l.set_name)} · ${esc(variant(l.subtype))}${l.grade ? " · " + esc(l.grade) : ""}` : "";
    return `<div class="title"><a class="cardlink" href="${esc(l.url)}" target="_blank" rel="noopener">${name}</a></div>
      <div class="meta">${sub}${sub ? " · " : ""}${market(l)}</div>
      ${l.name ? `<div class="meta rawtitle">${esc(l.title)}</div>` : ""}`;
  }
  function landedCell(l) {
    const d = l.landed || {}, keys = Object.keys(d).sort((a, b) => d[a].usd - d[b].usd);
    if (!keys.length) return "—";
    const fmt = k => `${usd(d[k].usd)}${d[k].ship_estimated ? "*" : ""} <span class="unit">${esc(k)}</span>`;
    return fmt(keys[0]) + (keys[1] ? `<span class="alt">${esc(keys[1])} ${usd(d[keys[1]].usd)}${d[keys[1]].ship_estimated ? "*" : ""}</span>` : "");
  }
  const valueCell = l => l.value_usd == null ? `<span class="c-warn">unknown</span><span class="src">add Collectr value</span>`
    : `${usd(l.value_usd)}<span class="src">${esc(l.value_source || "")}</span>`;
  function condCell(l) {
    const c = l.condition;
    const cls = !c ? "warn" : c === "NM" ? "good" : c === "LP" ? "warn" : "bad";
    const label = { NM: "Near mint", LP: "Lightly played", MP: "Moderately played", HP: "Heavily played", DMG: "Damaged" }[c] || "Not stated";
    return `<span class="pill ${cls}">${label}</span>${l.confidence && l.confidence !== "high" ? `<div class="meta">${esc(l.confidence)} confidence match</div>` : ""}`;
  }

  function render(s) {
    S = s;
    const lr = s.last_run;
    const markets = (s.markets || []).map(m => (MP[m] || m).replace("eBay ", "")).join(", ");
    $("#scaninfo").innerHTML = (lr ? `Last scan <b>${esc(lr.started.slice(11, 16))}</b> · every ${s.interval_min} min` : "No scan yet")
      + ` · eBay ${esc(markets)} · 1 USD = <b>${s.fx.cad ? s.fx.cad.toFixed(4) : "?"}</b> CAD · calls ${usd(s.budget.used)} / ${usd(s.budget.limit)}`;
    const problems = s.agents.filter(a => a.last_error_at && (!a.last_ok || a.last_error_at > a.last_ok));
    const pill = $("#syspill");
    pill.className = "syspill " + (problems.length ? "bad" : s.agents.length ? "ok" : "");
    pill.textContent = problems.length ? `${problems.length} agent${problems.length > 1 ? "s" : ""} need attention` : s.agents.length ? "All agents OK" : "Agents not started";

    if (s.example && !$(".example-banner")) {
      $("header").insertAdjacentHTML("afterend", `<div class="example-banner">Design preview with example data. The live dashboard runs on the iMac and is reached over Tailscale.</div>`);
    }

    const open = s.deals.filter(d => d.decision === "open");
    const best = open.map(d => d.gap_pct).filter(g => g != null).sort((a, b) => a - b)[0];
    const bestDeal = open.find(d => d.gap_pct === best);
    $("#tiles").innerHTML = [
      ["Open deals", open.length, `${s.stats.pushes_24h} pushed in 24 h`],
      ["Best gap now", best == null ? "—" : `${Math.round(best)}%`, bestDeal ? `${bestDeal.name} ${bestDeal.number}` : "no deals open"],
      ["Deals this week", s.stats.deals_week, `${s.stats.bought_week} bought · ${s.stats.passed_week} passed`],
      ["New listings 24 h", s.stats.new_24h, `across ${(s.markets || []).length} eBay sites`],
    ].map(([k, v, m]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}<small>${esc(m)}</small></div></div>`).join("");

    $("#deals tbody").innerHTML = open.length ? open.map(d => `
      <tr id="alert-${d.alert_id}" data-id="${d.alert_id}">
        <td class="c-card">${cardCell(d)}${d.kind === "seeded" ? `<div class="meta">already listed when this market was first scanned</div>` : ""}</td>
        <td class="num c-ask" data-label="Ask">${ask(d.price, d.currency)}</td>
        <td class="num c-landed" data-label="Landed US$">${landedCell(d)}</td>
        <td class="num c-value" data-label="Value US$">${valueCell(d)}</td>
        <td class="num c-gap">${d.tier === "LISTED" ? `<span class="tier LISTED">LISTED</span>` : gap(d.gap_pct)}</td>
        <td class="c-cond">${condCell(d)}</td>
        <td class="c-seller">${esc(d.seller || "")}<div class="meta">${d.feedback ?? "?"} · ${d.feedback_pct ?? "?"}% · ${ago(d.sent_at)}</div></td>
        <td class="c-acts"><div class="acts"><a class="btn primary" href="${esc(d.url)}" target="_blank" rel="noopener">Open</a><button data-act="passed">Pass</button><button data-act="bought">Bought</button></div></td>
      </tr>`).join("")
      : `<tr><td colspan="8" class="empty">No open deals. When a target lists under your threshold it lands here and on your phone.</td></tr>`;

    const tiers = ["all", "DEAL", "LISTED", "WATCH", "SEEN", "REJECT"];
    const counts = { all: s.feed.length };
    s.feed.forEach(l => counts[l.tier] = (counts[l.tier] || 0) + 1);
    $("#feedtabs").innerHTML = tiers.map(t => `<button role="tab" data-tab="${t}" aria-selected="${t === feedTab}">${t === "all" ? "All" : t[0] + t.slice(1).toLowerCase()}<span class="count">${counts[t] || 0}</span></button>`).join("");
    const rows = s.feed.filter(l => feedTab === "all" || l.tier === feedTab).slice(0, 150);
    $("#feed tbody").innerHTML = rows.length ? rows.map(l => `
      <tr>
        <td>${ago(l.first_seen)}</td>
        <td>${l.name ? `<div class="title"><a class="cardlink" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)} ${esc(l.number)}</a></div><div class="meta">${esc(variant(l.subtype))}</div><div class="meta rawtitle">${esc(l.title)}</div>`
          : `<div><a class="cardlink" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a></div>`}</td>
        <td>${market(l)}</td>
        <td class="num">${landedCell(l)}</td>
        <td class="num">${l.tier === "REJECT" ? "—" : valueCell(l)}</td>
        <td class="num">${l.tier === "REJECT" ? '<span class="na">—</span>' : gap(l.gap_pct)}</td>
        <td><span class="tier ${esc(l.tier)}">${esc(l.tier)}</span><div class="reason">${esc(l.reason || "")}</div></td>
      </tr>`).join("")
      : `<tr><td colspan="7" class="empty">${s.feed.length ? "Nothing in this tab." : "Nothing found yet. Results appear after the first scan."}</td></tr>`;

    $("#targets tbody").innerHTML = s.targets.map(t => {
      const c = s.target_counts[t.id] || {};
      return `<tr data-id="${esc(t.id)}">
        <td class="title">${esc(t.label)}<div class="meta">${esc(t.queries.join(" · "))}</div></td>
        <td class="num"><input class="th" id="push-${esc(t.id)}" data-k="push_gap_pct" value="${t.push_gap_pct}" inputmode="decimal" aria-label="Push gap for ${esc(t.label)}"></td>
        <td class="num"><input class="th" id="watch-${esc(t.id)}" data-k="watch_gap_pct" value="${t.watch_gap_pct}" inputmode="decimal" aria-label="Watch gap for ${esc(t.label)}"></td>
        <td class="num"><input class="th" id="min-${esc(t.id)}" data-k="min_value_usd" value="${t.min_value_usd}" inputmode="decimal" aria-label="Minimum value for ${esc(t.label)}"></td>
        <td class="num"><input class="th" id="max-${esc(t.id)}" data-k="max_price_usd" value="${t.max_price_usd}" inputmode="decimal" aria-label="Maximum landed for ${esc(t.label)}"></td>
        <td class="num">${plural((c.DEAL || 0) + (c.LISTED || 0), "deal")}<div class="meta">${Object.values(c).reduce((a, b) => a + b, 0)} found</div></td>
        <td><button class="pill ${t.paused ? "paused" : "active"}" data-toggle="paused">${t.paused ? "Paused" : "Active"}</button></td>
      </tr>`;
    }).join("");

    const sel = $("#valtarget");
    if (!sel.options.length) {
      sel.innerHTML = s.targets.map(t => `<option value="${esc(t.id)}">${esc(t.label)}</option>`).join("");
      valTarget = s.targets[0] && s.targets[0].id;
      loadValues();
    }

    const agents = s.agents.slice().sort((a, b) => a.agent.localeCompare(b.agent));
    $("#agents tbody").innerHTML = agents.length ? agents.map(a => {
      const bad = a.last_error_at && (!a.last_ok || a.last_error_at > a.last_ok);
      const job = AGENT_JOBS[a.agent] || (a.agent.startsWith("scout:") ? `Searches ${MP[a.agent.slice(6)] || a.agent.slice(6)}` : "");
      return `<tr><td class="title">${esc(a.agent.replace("scout:", "scout · "))}</td><td class="meta">${esc(job)}</td>
        <td>${a.last_ok ? ago(a.last_ok) + " ago" : "never"}</td>
        <td class="${bad ? "err" : "meta"}">${a.last_error_at ? esc(ago(a.last_error_at)) + " ago · " + esc(a.last_error) : "—"}</td>
        <td class="meta">${esc(a.detail || "")}</td></tr>`;
    }).join("") : `<tr><td colspan="5" class="empty">No agent has run yet.</td></tr>`;
    $("#runs tbody").innerHTML = s.runs.length ? s.runs.map(r => `<tr><td>${esc(r.started.slice(5, 16))}</td><td class="num">${r.calls}</td>
      <td class="num">${r.results}</td><td class="num">${r.new_listings}</td><td class="num">${r.pushes}</td>
      <td class="${r.errors.length ? "err" : "meta"}">${esc(r.errors.slice(0, 2).join(" · ") || "ok")}</td></tr>`).join("")
      : `<tr><td colspan="6" class="empty">No scans yet.</td></tr>`;

    $("#log tbody").innerHTML = s.log.length ? s.log.map(a => `<tr><td>${esc((a.sent_at || "").slice(5, 16))}</td>
      <td class="title">${a.name ? esc(a.name + " " + a.number) : esc(a.title)}</td><td class="num">${usd(a.landed_usd)}</td>
      <td class="num">${usd(a.value_usd)}</td><td class="num">${gap(a.gap_pct)}</td><td>${esc(a.decision)}</td><td>${esc(a.outcome || "—")}</td></tr>`).join("")
      : `<tr><td colspan="7" class="empty">Pass or Bought a deal and it moves here. Add what happened later so thresholds can be tuned from evidence.</td></tr>`;

    focusHash();
  }

  async function loadValues() {
    if (!valTarget) return;
    let rows;
    try { rows = SAMPLE ? (SAMPLE.values[valTarget] || []) : await api(`/api/values?target=${encodeURIComponent(valTarget)}`); }
    catch (e) { toast(e.message); return; }
    $("#values tbody").innerHTML = rows.length ? rows.map(c => `<tr data-key="${esc(c.card_key)}">
      <td><div class="title">${c.tcg_url ? `<a class="cardlink" href="${esc(c.tcg_url)}" target="_blank" rel="noopener">${esc(c.name)} ${esc(c.number)}</a>` : esc(c.name + " " + c.number)}</div><div class="meta">${esc(variant(c.subtype))}</div></td>
      <td class="num">${c.market == null ? `<span class="c-warn">no sales</span>` : usd(c.market)}</td>
      <td class="num"><input class="th ov" id="ov-${esc(c.card_key)}" value="${c.override_usd ?? ""}" placeholder="—" inputmode="decimal" aria-label="Collectr value for ${esc(c.name)}"></td>
    </tr>`).join("") : `<tr><td colspan="3" class="empty">No cards loaded yet. The catalog agent fills this on its first run.</td></tr>`;
  }

  function focusHash() {
    document.querySelectorAll("tr.focus").forEach(r => r.classList.remove("focus"));
    const id = (location.hash || "").slice(1);
    if (!/^alert-\d+$/.test(id)) return;
    const row = document.getElementById(id);
    if (row) { row.classList.add("focus"); row.scrollIntoView({ block: "center" }); }
  }

  async function load() {
    if (SAMPLE) return render(SAMPLE);
    try { render(await api("/api/state")); }
    catch (e) { $("#scaninfo").textContent = "Can't reach the Card Radar server: " + e.message; }
  }

  document.addEventListener("click", async e => {
    const tab = e.target.closest("button[data-tab]");
    if (tab) { feedTab = tab.dataset.tab; render(S); return; }
    const act = e.target.closest("button[data-act]");
    if (act) {
      const tr = act.closest("tr"), id = tr.dataset.id, decision = act.dataset.act;
      if (SAMPLE) { tr.classList.add("decided"); toast(decision === "bought" ? "Marked bought (example)" : "Passed (example)"); return; }
      try { await api(`/api/alerts/${id}/decision`, { method: "POST", body: JSON.stringify({ decision }) }); toast(decision === "bought" ? "Marked bought" : "Passed"); load(); }
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
    if (e.target.id === "valtarget") { valTarget = e.target.value; loadValues(); return; }
    const inp = e.target.closest("input.th");
    if (!inp) return;
    const raw = inp.value.trim().replace(/[$,%\s]/g, "");
    if (raw !== "" && Number.isNaN(Number(raw))) { toast("Enter a number"); return; }
    if (SAMPLE) { toast("Saved (example)"); return; }
    try {
      if (inp.classList.contains("ov")) {
        await api("/api/overrides", { method: "POST", body: JSON.stringify({ card_key: inp.closest("tr").dataset.key, value_usd: raw === "" ? null : Number(raw) }) });
        toast(raw === "" ? "Back to TCGplayer value" : "Collectr value saved"); loadValues();
      } else {
        if (raw === "") { toast("Enter a number"); return; }
        await api(`/api/targets/${inp.closest("tr").dataset.id}`, { method: "POST", body: JSON.stringify({ [inp.dataset.k]: Number(raw) }) });
        toast("Saved to targets.json");
      }
      load();
    } catch (err) { toast(err.message); }
  });

  addEventListener("hashchange", focusHash);
  load();
  if (!SAMPLE) setInterval(() => { if (!document.querySelector("input:focus")) load(); }, 60000);
})();
