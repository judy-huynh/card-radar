// Card Radar dashboard. Pure fetch + render; no framework. State comes from /api/state.
(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const money = (v, cur) => v == null ? '<span class="num na">—</span>' : (cur === "CAD" ? "C$ " : "") + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const gapCls = g => g == null ? "" : g <= -25 ? "c-good" : g <= -15 ? "c-warn" : "c-bad";
  const gapTxt = g => g == null ? '<span class="num na">—</span>' : `<span class="gap ${gapCls(g)}">${g > 0 ? "+" : ""}${Math.round(g)}%</span>`;
  const condPill = c => {
    const t = (c || "").toLowerCase();
    const cls = /damaged|poor|read desc|played/.test(t) ? "bad" : /lp|light|good|unspecified|^$/.test(t) ? "warn" : "good";
    return `<span class="pill ${cls}">${esc(c || "Condition unknown")}</span>`;
  };
  const age = ts => { if (!ts) return ""; const m = Math.round((Date.now() - new Date(ts.replace(" ", "T"))) / 60000); return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`; };

  async function api(path, opts) {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 1800); }

  function render(s) {
    const best = s.alerts.map(a => a.gap_pct).filter(g => g != null).sort((a, b) => a - b)[0];
    $("#scaninfo").innerHTML = s.last_scan
      ? `Last scan <b>${esc(s.last_scan.ran_at.slice(11, 16))}</b> · eBay US + CA · FX <b>1 USD = ${s.fx} CAD</b> · every ${s.interval} min`
      : `No scan yet · FX <b>1 USD = ${s.fx} CAD</b>`;
    $("#tiles").innerHTML = [
      ["Live alerts", s.alerts.length, `${s.alerts.filter(a => a.sent_at >= s.today).length} today`],
      ["Best gap right now", best == null ? "—" : `${Math.round(best)}%`, best == null ? "needs Collectr values" : ""],
      ["Alerts this week", s.stats.week, `${s.stats.bought} bought · ${s.stats.passed} passed`],
      ["Watching", s.watchlist.cards.filter(c => !c.paused).length, `cards · ${s.watchlist.marketplaces.length} markets`],
    ].map(([k, v, m]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}<small>${m}</small></div></div>`).join("");

    $("#alerts tbody").innerHTML = s.alerts.length ? s.alerts.map(a => `
      <tr id="alert-${a.id}" data-id="${a.id}">
        <td><div class="title">${esc(a.title)}</div><div class="meta">${a.marketplace === "EBAY_CA" ? "eBay CA" : "eBay US"} · ${esc(a.location || "")}${a.shipping != null ? ` · ship ${money(a.shipping, a.currency)}` : ""}</div></td>
        <td class="num">${money(a.price, a.currency)}</td>
        <td class="num">${money(a.landed_ca)}</td>
        <td class="num">${money(a.landed_nyc)}</td>
        <td class="num">${money(a.collectr_usd)}</td>
        <td class="num">${gapTxt(a.gap_pct)}</td>
        <td>${condPill(a.condition)}</td>
        <td>${esc(a.seller || "")}<div class="meta">${a.feedback ?? "?"} · ${a.feedback_pct ?? "?"}% · ${age(a.sent_at)}</div></td>
        <td><div class="acts"><a class="btn primary" href="${esc(a.url)}" target="_blank" rel="noopener">Open</a><button data-act="passed">Pass</button><button data-act="bought">Bought</button></div></td>
      </tr>`).join("") : `<tr><td colspan="9" class="empty">No open alerts. New listings that pass the watchlist appear here and on your phone.</td></tr>`;

    $("#watchlist tbody").innerHTML = s.watchlist.cards.map((c, i) => `
      <tr data-i="${i}">
        <td class="title">${esc(c.id)}</td>
        <td class="meta">${esc(c.query)}</td>
        <td class="num"><input class="th" id="gap-${i}" data-k="alert_gap_pct" value="${c.alert_gap_pct}" inputmode="numeric"></td>
        <td class="num"><input class="th" id="max-${i}" data-k="max_price_usd" value="${c.max_price_usd}" inputmode="numeric"></td>
        <td>${esc(c.condition)}</td>
        <td class="num">${s.hits[c.id] || 0}</td>
        <td><button class="pill ${c.paused ? "paused" : "active"}" data-k="paused">${c.paused ? "Paused" : "Active"}</button></td>
      </tr>`).join("");

    $("#log tbody").innerHTML = s.log.length ? s.log.map(a => `
      <tr><td>${esc(a.sent_at.slice(5, 16))}</td><td class="title">${esc(a.title)}</td><td class="num">${money(a.price, a.currency)}</td>
      <td class="num">${gapTxt(a.gap_pct)}</td><td>${esc(a.decision)}</td><td>${esc(a.outcome || "—")}</td></tr>`).join("")
      : `<tr><td colspan="6" class="empty">Nothing logged yet.</td></tr>`;
    focusHash();
  }

  function focusHash() {
    document.querySelectorAll("tr.focus").forEach(r => r.classList.remove("focus"));
    const id = (location.hash || "").slice(1), row = id && document.getElementById(id);
    if (row) { row.classList.add("focus"); row.scrollIntoView({ block: "center" }); }
  }

  async function load() {
    try { render(await api("/api/state")); }
    catch (e) {
      if (window.SAMPLE) { render(window.SAMPLE); $("#subtitle").innerHTML = 'Sourcing desk · WOTC-era targets · <b>example data</b>'; }
      else $("#scaninfo").textContent = "Server unreachable: " + e.message;
    }
  }

  document.addEventListener("click", async e => {
    const b = e.target.closest("button[data-act]");
    if (b) {
      const id = b.closest("tr").dataset.id;
      if (window.SAMPLE) { b.textContent = b.dataset.act === "bought" ? "Bought ✓" : "Passed"; return; }
      await api(`/api/alerts/${id}/decision`, { method: "POST", body: JSON.stringify({ decision: b.dataset.act }) });
      toast(b.dataset.act === "bought" ? "Marked bought" : "Passed"); load();
    }
    const p = e.target.closest("button[data-k=paused]");
    if (p) { if (window.SAMPLE) return; const i = p.closest("tr").dataset.i; await api(`/api/watchlist/${i}`, { method: "POST", body: JSON.stringify({ paused: p.textContent === "Active" }) }); load(); }
  });
  document.addEventListener("change", async e => {
    const inp = e.target.closest("input.th");
    if (!inp) return;
    const i = inp.closest("tr").dataset.i, v = Number(inp.value);
    if (window.SAMPLE) { toast("Saved (example)"); return; }
    if (Number.isNaN(v)) { toast("Enter a number"); return; }
    await api(`/api/watchlist/${i}`, { method: "POST", body: JSON.stringify({ [inp.dataset.k]: v }) });
    toast("Saved to watchlist.json");
  });
  addEventListener("hashchange", focusHash);
  load(); setInterval(load, 60000);
})();
