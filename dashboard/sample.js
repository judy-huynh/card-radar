// Example data for the design mock only. The live app never loads this file.
window.SAMPLE = {
  fx: 1.38, interval: 5, today: "2026-10-28",
  last_scan: { ran_at: "2026-10-28 10:42:00" },
  stats: { week: 14, bought: 2, passed: 9 },
  hits: { "skyridge-holo": 3, "lc-reverse-holo": 4, "dark-gengar": 3, "aquapolis-holo": 2, "southern-islands": 1, "expedition-holo": 1 },
  watchlist: { marketplaces: ["EBAY_US", "EBAY_CA"], cards: [
    { id: "lc-reverse-holo", query: "Legendary Collection reverse holo", alert_gap_pct: 25, max_price_usd: 1500, condition: "NM", paused: false },
    { id: "southern-islands", query: "Southern Islands pokemon card", alert_gap_pct: 20, max_price_usd: 300, condition: "NM / LP", paused: false },
    { id: "skyridge-holo", query: "Skyridge holo pokemon", alert_gap_pct: 25, max_price_usd: 1200, condition: "NM", paused: false },
    { id: "aquapolis-holo", query: "Aquapolis holo pokemon", alert_gap_pct: 25, max_price_usd: 800, condition: "NM", paused: false },
    { id: "dark-gengar", query: "Dark Gengar Neo Destiny holo", alert_gap_pct: 20, max_price_usd: 200, condition: "NM / LP", paused: false },
    { id: "expedition-holo", query: "Expedition holo pokemon", alert_gap_pct: 30, max_price_usd: 400, condition: "NM", paused: true }
  ] },
  alerts: [
    { id: 1042, title: "Skyridge Crystal Lugia 149/144 Holo", marketplace: "EBAY_CA", location: "Toronto, CA", shipping: 15, price: 610, currency: "CAD", landed_ca: 452, landed_nyc: null, collectr_usd: 655, gap_pct: -31, condition: "Near Mint", seller: "tdotcards", feedback: 1204, feedback_pct: 99.8, sent_at: "2026-10-28 10:30:00", url: "#" },
    { id: 1041, title: "Dark Gengar 6/105 Neo Destiny Holo", marketplace: "EBAY_US", location: "Ohio, US", shipping: 5, price: 118, currency: "USD", landed_ca: 139, landed_nyc: 124, collectr_usd: 165, gap_pct: -25, condition: "Lightly Played", seller: "mlb_cardz", feedback: 312, feedback_pct: 100, sent_at: "2026-10-28 10:04:00", url: "#" },
    { id: 1039, title: "Legendary Collection Charizard 3/110 Reverse Holo", marketplace: "EBAY_US", location: "California, US", shipping: 0, price: 1250, currency: "USD", landed_ca: 1452, landed_nyc: 1268, collectr_usd: 1400, gap_pct: -9, condition: "Read description", seller: "fastflip88", feedback: 41, feedback_pct: 96.1, sent_at: "2026-10-28 09:40:00", url: "#" }
  ],
  log: [
    { sent_at: "2026-10-28 10:30:00", title: "Skyridge Crystal Lugia 149/144 Holo", price: 452, currency: "USD", gap_pct: -31, decision: "open", outcome: null },
    { sent_at: "2026-10-27 21:15:00", title: "Aquapolis Crystal Kingdra 148/147 Holo", price: 388, currency: "USD", gap_pct: -25, decision: "bought", outcome: "Arrived NM · listed on TCGplayer" },
    { sent_at: "2026-10-27 16:03:00", title: "Expedition Charizard 6/165 Holo", price: 290, currency: "USD", gap_pct: -6, decision: "passed", outcome: "Sold 2 h later at ask" },
    { sent_at: "2026-10-26 11:40:00", title: "Dark Gengar 6/105 Holo", price: 97, currency: "USD", gap_pct: -41, decision: "passed", outcome: "12 feedback, 1 photo · likely fake" },
    { sent_at: "2026-10-25 09:12:00", title: "Southern Islands Mew 1/18", price: 44, currency: "USD", gap_pct: -27, decision: "bought", outcome: "Arrived LP, not NM · hold" }
  ]
};
