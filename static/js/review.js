const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "discount", "tax", "total"];
const NUMERIC = new Set(["subtotal", "discount", "tax", "total"]);
const STATUS = { auto_approved: ["Auto-approved", "ok"], needs_review: ["Needs review", "review"], approved: ["Approved", "ok"],
  rejected: ["Rejected", "bad"], failed: ["Failed", "bad"], processing: ["Processing", "gold"], new: ["New", ""] };
let docs = [], current = new URLSearchParams(location.search).get("doc");
const tag = (s) => { const [t, c] = STATUS[s] || [s, ""]; return `<span class="tag ${c}">${esc(t)}</span>`; };
const fmt = (v, cur) => v == null ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (cur ? " " + cur : "");

async function loadList() {
  docs = await (await fetch("/api/documents")).json();
  $("list").innerHTML = docs.length ? docs.map((d) => `
    <div class="item" data-id="${d.id}" tabindex="0" aria-current="${String(d.id) === String(current)}">
      <span class="v">${esc(d.vendor || d.filename)}</span><span class="amt">${d.total != null ? fmt(d.total) : ""}</span>
      <span class="f">${esc(d.filename)}${d.flagged ? ` · ${d.flagged} to check` : ""}</span><span>${tag(d.status)}</span>
    </div>`).join("") : `<p class="muted" style="padding:18px">No documents yet.</p>`;
  document.querySelectorAll(".item").forEach((el) => {
    el.onclick = () => open(el.dataset.id);
    el.onkeydown = (e) => { if (e.key === "Enter") open(el.dataset.id); };
  });
  $("railFoot").textContent = `${docs.length} document${docs.length === 1 ? "" : "s"}`;
}

async function open(id) {
  current = id;
  history.replaceState(null, "", `/review?doc=${id}`);
  document.querySelectorAll(".item").forEach((el) => el.setAttribute("aria-current", String(el.dataset.id === String(id))));
  const r = await fetch(`/api/documents/${id}`);
  if (!r.ok) return;
  render(await r.json());
}

function render(d) {
  const ext = d.extracted || {}, val = (d.validation || {}).fields || {}, corr = d.corrected || {};
  const pages = Array.from({ length: d.pages || 0 }, (_, i) => `<img src="/api/documents/${d.id}/page/${i + 1}" alt="Page ${i + 1} of ${esc(d.filename)}">`).join("");
  $("stage").innerHTML = pages || `<div class="empty"><span class="big">No preview</span>${esc(d.error || "")}</div>`;
  const flagged = Object.entries(val).filter(([, v]) => v.status !== "ok");
  const checks = (d.validation || {}).checks || [];
  const passed = checks.filter((c) => c.passed).length;
  const cur = (corr.currency ?? ext.currency?.value) || "";
  const rows = FIELDS.map((f) => {
    const st = val[f] || { status: "ok", reasons: [] };
    const v = corr[f] ?? ext[f]?.value;
    return `<div class="frow ${st.status !== "ok" ? "flag" : ""}">
      <span class="dot ${st.status === "ok" ? "ok" : "review"}" title="${st.status === "ok" ? "passed every check" : "needs a human check"}"></span>
      <label for="f_${f}">${f.replace(/_/g, " ")}</label>
      <input id="f_${f}" data-field="${f}" value="${esc(v ?? "")}" ${NUMERIC.has(f) ? 'inputmode="decimal"' : ""}>
      ${ext[f]?.evidence ? `<div class="ev">read as “${esc(ext[f].evidence)}”</div>` : ""}
      ${st.reasons.map((x) => `<div class="why">${esc(x)}</div>`).join("")}
    </div>`;
  }).join("");
  const items = corr.line_items ?? ext.line_items ?? [];
  const li = val.line_items || { status: "ok", reasons: [] };
  $("ledger").innerHTML = `
    <div class="verdict">
      ${tag(d.status)} <span class="tag">${esc(d.kind || "")}</span>
      <h2>${esc(ext.vendor?.value || d.filename)}</h2>
      <p class="muted">${d.status === "failed" ? esc(d.error) : flagged.length
        ? `${flagged.length} field${flagged.length > 1 ? "s" : ""} need a human check. ${passed} of ${checks.length} checks passed.`
        : `Every field passed all ${checks.length} checks.`}</p>
    </div>
    ${rows}
    <div class="frow ${li.status !== "ok" ? "flag" : ""}" style="grid-template-columns:14px 1fr">
      <span class="dot ${li.status === "ok" ? "ok" : "review"}"></span>
      <div><label style="padding:0">line items</label>
        <table class="items"><thead><tr><th>Description</th><th class="n">Qty</th><th class="n">Unit</th><th class="n">Amount</th></tr></thead>
        <tbody>${items.map((it) => `<tr><td>${esc(it.description)}</td><td class="n">${it.quantity ?? ""}</td><td class="n">${fmt(it.unit_price)}</td><td class="n">${fmt(it.amount)}</td></tr>`).join("")}</tbody></table>
        ${li.reasons.map((x) => `<div class="why" style="margin-top:6px">${esc(x)}</div>`).join("")}</div>
    </div>
    ${d.status === "failed" ? "" : `<div class="actions">
      <button type="button" id="approve">${flagged.length ? "Approve with my edits" : "Approve"}</button>
      <button type="button" class="danger" id="reject">Reject</button>
      <button type="button" class="line" id="rerun">Read again</button></div>
      <p class="muted" style="font-size:12.5px">Edited values override the extraction in the Excel and CSV exports.</p>`}
    <div class="steps"><h3 style="margin-bottom:6px">Pipeline steps</h3>${(d.events || []).map((e) => `
      <div><span class="mono">${esc(e.step)}</span><span class="muted">${esc(e.detail)}</span><span class="mono muted">${(e.duration_ms / 1000).toFixed(1)}s</span></div>`).join("")}
      <p class="muted mono" style="margin-top:8px">${(d.duration_ms / 1000).toFixed(1)}s · $${(d.cost_usd || 0).toFixed(4)} · <a href="/flowchart?view=trace&doc=${d.id}">trace</a></p></div>`;

  const send = async (decision) => {
    const corrections = {};
    document.querySelectorAll("[data-field]").forEach((inp) => {
      const f = inp.dataset.field, orig = ext[f]?.value;
      let v = inp.value.trim() === "" ? null : inp.value.trim();
      if (v !== null && NUMERIC.has(f)) v = Number(v.replace(/,/g, ""));
      if (String(v ?? "") !== String(orig ?? "")) corrections[f] = v;
    });
    const r = await fetch(`/api/documents/${d.id}/review`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, corrections }) });
    if (r.ok) { await loadList(); render(await r.json()); } else alert((await r.json()).detail || "Failed");
  };
  if ($("approve")) {
    $("approve").onclick = () => send("approve");
    $("reject").onclick = () => send("reject");
    $("rerun").onclick = async () => {
      $("rerun").disabled = true; $("rerun").textContent = "Reading…";
      const r = await fetch(`/api/documents/${d.id}/reprocess`, { method: "POST" });
      const data = await r.json();
      if (!r.ok) { alert(data.detail || "Failed"); return; }
      await loadList(); render(data);
    };
  }
}

async function upload(file) {
  $("busy").hidden = false;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/documents", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) { alert(data.detail || "Upload failed"); return; }
    await loadList(); open(data.id);
  } catch { alert("Can't reach the server. Is `python -m app.main` running?"); }
  finally { $("busy").hidden = true; }
}

const drop = $("drop");
$("file").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
drop.onkeydown = (e) => { if (e.key === "Enter") $("file").click(); };
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]));

loadList().then(() => { if (current) open(current); });
