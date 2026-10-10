const THUMB = new URLSearchParams(location.search).get("mode") === "thumbnail";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = (v, d = 0) => (v == null ? "–" : (v * 100).toFixed(d) + "%");
const FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "discount", "tax", "total", "line_items"];
const SHORT = { vendor: "vendor", invoice_number: "number", invoice_date: "date", due_date: "due", currency: "currency",
  subtotal: "subtotal", discount: "discount", tax: "tax", total: "total", line_items: "lines" };
const KIND = { digital: "Digital PDFs", scan: "Scans", hard_scan: "Poor scans" };
const LEG = [["ok", "correct, passed", "#2C5A41", ""], ["anomaly", "vendor error, flagged", "#E9C46A", ""],
  ["false_alarm", "correct, sent to review", "transparent", "inset 0 0 0 1.5px #8FB3E8"],
  ["caught", "wrong, caught", "#8FB3E8", ""], ["silent", "wrong, missed", "#E4735C", ""]];

if (window.mermaid) mermaid.initialize({ startOnLoad: false, theme: "base", securityLevel: "loose",
  themeVariables: { darkMode: true, background: "#0E1014", fontFamily: "IBM Plex Sans, Segoe UI, sans-serif", fontSize: "14px",
    primaryColor: "#171A21", primaryTextColor: "#EEE9DF", primaryBorderColor: "#5A606B", lineColor: "#8C929C",
    clusterBkg: "#111318", clusterBorder: "#2A2F38", edgeLabelBackground: "#0E1014", titleColor: "#9097A3" },
  flowchart: { curve: "basis", htmlLabels: true } });

const legend = (el) => { el.innerHTML = LEG.map(([, t, bg, sh]) => `<span><i style="background:${bg};box-shadow:${sh}"></i>${t}</span>`).join(""); };

function matrixT(el, docs) {
  if (!docs?.length) docs = Array.from({ length: 30 }, (_, i) => ({ file: `INV${String(i + 1).padStart(3, "0")}`, cells: {} }));
  const head = `<span></span>` + docs.map((d, i) => `<span class="mx-num">${(i + 1) % 5 === 0 ? i + 1 : ""}</span>`).join("");
  const rows = FIELDS.map((f) => `<span class="mx-row">${SHORT[f]}</span>` +
    docs.map((d) => `<span class="mx-cell ${d.cells?.[f] || ""}"></span>`).join("")).join("");
  el.innerHTML = `<div class="matrix" style="grid-template-columns:auto repeat(${docs.length}, 1fr);gap:4px">${head}${rows}</div>`;
}

function matrix(el, docs, opts = {}) {
  if (!docs?.length) docs = Array.from({ length: opts.placeholder || 30 }, (_, i) => ({ file: `INV${String(i + 1).padStart(3, "0")}`, cells: {} }));
  const cols = `auto repeat(${FIELDS.length}, ${opts.cell || "minmax(14px, 26px)"})`;
  const head = `<span></span>` + FIELDS.map((f) => `<span class="mx-head">${SHORT[f]}</span>`).join("");
  const rows = docs.map((d) => `<span class="mx-row">${esc(d.file.replace(/\.(pdf|jpg|png)$/i, ""))}${d.kind === "scan" ? " ◦" : ""}</span>` +
    FIELDS.map((f) => `<span class="mx-cell ${d.cells?.[f] || ""}" title="${esc(d.file)} · ${f}: ${(d.cells?.[f] || "").replace("_", " ")}"></span>`).join("")).join("");
  el.innerHTML = `<div class="matrix" style="grid-template-columns:${cols};gap:${opts.gap || 3}px">${head}${rows}</div>`;
}

async function flow() {
  try {
    const d = await (await fetch("/api/flowchart?view=pipeline")).json();
    $("flow").innerHTML = (await mermaid.render("m" + Date.now(), d.mermaid)).svg;
  } catch (e) { $("flow").innerHTML = `<p class="muted">Could not draw the flowchart (${esc(e.message || e)}).</p>`; }
}

function renderPage(d) {
  const ev = d.eval, s = ev?.summary;
  $("app").hidden = false;
  $("banner").hidden = !!ev;
  if (s) {
    $("kicker").textContent = `Evaluation · ${ev.meta.documents} invoices · ${ev.meta.model}`;
    $("headline").innerHTML = `<em>${pct(s.auto_approved_fully_correct)}</em> of the invoices Folio approved on its own were fully correct.`;
    $("lede").textContent = `${pct(s.straight_through_rate)} of invoices needed no human at all. Anything the checks couldn't confirm, including every poor-quality scan, went to a person. ${s.silent_errors} of ${s.fields} fields were wrong without being flagged.`;
  }
  $("figures").innerHTML = [
    [s ? pct(s.field_accuracy, 1) : "–", "fields correct before review"],
    [s ? pct(s.straight_through_rate) : "–", "invoices auto-approved"],
    [s ? pct(s.auto_approved_fully_correct) : "–", "of auto-approved fully correct"],
    [d.stress ? pct(d.stress.overall.rate) : "–", "injected mistakes caught"],
    [s ? `${s.traps_caught}/${s.traps}` : "–", "vendor arithmetic errors caught"],
    [s ? "$" + s.cost_per_doc_usd.toFixed(4) : "–", "cost per invoice"],
    [s ? (s.duration_avg_ms / 1000).toFixed(1) + "s" : "–", "average time per invoice"],
  ].map(([v, l]) => `<div><b class="num">${v}</b><span>${l}</span></div>`).join("");
  legend($("legend"));
  matrixT($("matrix"), ev?.documents);
  $("fields").innerHTML = (ev?.by_field || FIELDS.map((f) => ({ field: f }))).map((f) => {
    const n = (f.ok || 0) + (f.anomaly || 0) + (f.false_alarm || 0) + (f.caught || 0) + (f.silent || 0) || 1;
    const seg = (k, c) => `<i style="width:${((f[k] || 0) / n) * 100}%;background:${c}"></i>`;
    return `<div class="fbar"><span class="mono">${SHORT[f.field]}</span><span class="track">${seg("ok", "#2C5A41")}${seg("anomaly", "#E9C46A")}${seg("false_alarm", "#34507A")}${seg("caught", "#8FB3E8")}${seg("silent", "#E4735C")}</span><span class="num" style="text-align:right">${pct(f.accuracy)}</span></div>`;
  }).join("");
  $("kinds").innerHTML = (ev?.by_kind || [{ group: "digital" }, { group: "scan" }, { group: "hard_scan" }]).map((g) => `
    <div><h3>${KIND[g.group] || g.group}</h3><b class="num">${pct(g.field_accuracy, 1)}</b>
    <span class="muted">fields correct · ${g.documents ?? "–"} invoices<br>${g.silent_errors ?? "–"} silent errors · ${pct(g.straight_through_rate)} auto-approved</span></div>`).join("");
  const st = d.stress;
  $("stressHead").textContent = st ? `${pct(st.overall.rate)} of ${st.overall.n} injected mistakes caught` : "Run python -m eval.stress";
  $("stressLede").textContent = st ? `Digital PDFs ${pct(st.by_kind.digital?.rate)}, scans ${pct(st.by_kind.scan?.rate)}. Realistic reading mistakes were injected into the model's own extractions, one at a time.` : "";
  $("stress").innerHTML = st ? `<thead><tr><th>Injected mistake</th><th>Kind</th><th>Digital PDFs</th><th>Scans</th><th>Caught by</th></tr></thead><tbody>` +
    st.by_mutation.map((m) => { const c = (a) => a.rate == null ? "–" : `<span style="color:${a.rate >= 0.95 ? "var(--ok)" : a.rate >= 0.5 ? "var(--gold)" : "var(--bad)"}">${pct(a.rate)}</span> <span class="muted">${a.caught}/${a.n}</span>`;
      return `<tr><td>${esc(m.mutation)}</td><td class="muted">${m.type}</td><td class="num">${c(m.digital)}</td><td class="num">${c(m.scan)}</td><td class="muted mono" style="font-size:12px">${esc(m.checks.join(", ") || "none")}</td></tr>`; }).join("") + "</tbody>"
    : `<tbody><tr><td class="muted">No stress test yet.</td></tr></tbody>`;
  $("runMeta").textContent = ev ? `run ${ev.meta.run_at.replace("T", " ").slice(0, 16)} UTC` : "";
  $("docs").innerHTML = ev ? `<thead><tr><th>Document</th><th>Type</th><th>Outcome</th><th>Failed checks</th><th>Silent</th><th>Time</th><th>Cost</th></tr></thead><tbody>` +
    ev.documents.map((x) => {
      const sil = Object.values(x.cells).filter((c) => c === "silent").length;
      return `<tr><td class="mono">${esc(x.file)}${x.trap ? ' <span class="tag gold">vendor error</span>' : ""}</td><td>${x.kind}</td>
      <td><span class="tag ${x.status === "auto_approved" ? "ok" : x.status === "failed" ? "bad" : "review"}">${esc(x.status.replace("_", " "))}</span></td>
      <td class="muted">${esc(x.failed_checks.join(", "))}</td><td class="num" style="color:${sil ? "var(--bad)" : "inherit"}">${sil}</td>
      <td class="num">${(x.duration_ms / 1000).toFixed(1)}s</td><td class="num">$${x.cost_usd.toFixed(4)}</td></tr>`;
    }).join("") + "</tbody>" : `<tbody><tr><td class="muted">No evaluation yet.</td></tr></tbody>`;
  $("railFoot").textContent = `${d.live.documents} processed on this server`;
  return flow();
}

function renderThumb(d) {
  document.body.classList.add("thumb-mode");
  $("thumb").hidden = false;
  const ev = d.eval, s = ev?.summary;
  $("tBig").textContent = s ? pct(s.auto_approved_fully_correct) : "–";
  $("tCap").innerHTML = `of auto-approved invoices<br><span>were fully correct</span>`;
  $("tFigs").innerHTML = [[s ? pct(s.straight_through_rate) : "–", "no human needed"], [s ? s.silent_errors : "–", "silent errors"],
    [s ? "$" + s.cost_per_doc_usd.toFixed(3) : "–", "per invoice"]].map(([v, l]) => `<div><b class="num">${v}</b><span>${l}</span></div>`).join("");
  $("tLabel").textContent = s ? `${s.documents} invoices × 10 fields, scored against ground truth` : "Every field of every invoice";
  matrixT($("tMatrix"), ev?.documents);
  const st = d.stress;
  $("tKinds").innerHTML = [
    ["Injected mistakes caught", st ? pct(st.overall.rate) : "–", st ? `${st.overall.caught} of ${st.overall.n} realistic misreads` : "stress test"],
    ["On digital PDFs", st ? pct(st.by_kind.digital?.rate) : "–", "checked against the PDF text"],
    ["Vendor arithmetic errors", s ? `${s.traps_caught} of ${s.traps}` : "–", "invoices that don't add up, flagged"],
  ].map(([k, v, sub]) => `<div><span class="t-k">${k}</span><b class="num">${v}</b><span>${sub}</span></div>`).join("");
  legend($("tLegend"));
  $("tWater").hidden = !!ev;
}

(async () => {
  try {
    const d = await (await fetch("/api/dashboard")).json();
    if (THUMB) renderThumb(d); else await renderPage(d);
  } catch (e) { document.body.innerHTML = `<p style="padding:40px">Could not load data: ${esc(e.message)}. Is the server running?</p>`; }
  finally { await document.fonts?.ready; window.__ready = true; }
})();