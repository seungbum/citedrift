"use strict";
const CLASSES = {
  still_supported: {label: "Still supported", color: "--c-still", icon: "✓"},
  content_changed: {label: "Content changed", color: "--c-changed", icon: "Δ"},
  uncertain: {label: "Uncertain", color: "--c-uncert", icon: "~"},
  link_lost: {label: "Link lost", color: "--c-lost", icon: "✕"},
  unverifiable: {label: "Could not check", color: "--c-unver", icon: "?"},
  never_supported: {label: "Not fully supported in 2023", color: "--c-never", icon: "–"},
};
const BAR = ["still_supported", "content_changed", "uncertain", "link_lost", "unverifiable"];
const STATES = {ok: "same URL", moved: "moved (same content)", dead: "dead", soft404: "error page",
  away: "redirected elsewhere", blocked: "bot wall", filtered: "network filter", skipped: "not requested",
  transient: "server/TLS error"};
const ENGINES = {bing_chat: "Bing Chat", neeva: "NeevaAI", perplexity: "Perplexity", you: "YouChat"};
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const pct = (x) => (100 * x).toFixed(1) + "%";
let DATA = null, view = [], shown = 0;

// ---------- tabs ----------
document.querySelectorAll("nav button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("on", x === b));
  for (const s of ["explore", "check", "about"]) $(s).classList.toggle("hidden", s !== b.dataset.tab);
  if (b.dataset.tab === "check") probeLocal();
});

// ---------- word diff (LCS) ----------
function diff(a, b) {
  const A = a.split(/\s+/).filter(Boolean), B = b.split(/\s+/).filter(Boolean);
  if (A.length * B.length > 250000) return [esc(a), esc(b)];
  const n = A.length, m = B.length, L = Array.from({length: n + 1}, () => new Uint16Array(m + 1));
  const key = (w) => w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    L[i][j] = key(A[i]) === key(B[j]) ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const oa = [], ob = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (key(A[i]) === key(B[j])) { oa.push(esc(A[i])); ob.push(esc(B[j])); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) oa.push(`<del>${esc(A[i++])}</del>`);
    else ob.push(`<ins>${esc(B[j++])}</ins>`);
  }
  while (i < n) oa.push(`<del>${esc(A[i++])}</del>`);
  while (j < m) ob.push(`<ins>${esc(B[j++])}</ins>`);
  return [oa.join(" "), ob.join(" ")];
}

// ---------- summary ----------
function tip(e, html) { const t = $("tip"); t.innerHTML = html; t.style.display = "block";
  t.style.left = (e.clientX + 14) + "px"; t.style.top = (e.clientY + 10) + "px"; }
function untip() { $("tip").style.display = "none"; }

function summary() {
  const s = DATA.summary, m = DATA.meta;
  const ll = s.classes.link_lost || 0, cc = s.classes.content_changed || 0, un = s.classes.uncertain || 0;
  $("hero").innerHTML = `
    <div><div class="num">${pct(ll / s.checkable)}</div>
      <div class="lab">of the checkable citations that annotators judged fully supporting in ${m.then_label} have lost their link by
      ${m.now_label} (dead, error page, or redirect to a different document; n = ${s.checkable.toLocaleString()} checkable).</div></div>
    <div><div class="num">+${pct(cc / s.checkable)}</div>
      <div class="lab">are still online but flagged as <b>content changed</b>: the judge no longer finds support <i>and</i> the
      annotator's evidence is gone. ${pct(un / s.checkable)} more are uncertain. Flags are evidence for a reader, not verdicts.</div></div>
    <div><div class="num">${s.n_pairs.toLocaleString()}</div><div class="lab">statement–citation pairs from four
      generative search engines (${m.source}), ${s.n_urls.toLocaleString()} distinct URLs.</div></div>`;
  $("barTitle").textContent = `Outcome in ${m.now_label} for citations judged fully supporting in ${m.then_label}, by engine. Click a segment to filter.`;
  $("legend").innerHTML = BAR.map((c) => `<span><span class="sw" style="background:var(${CLASSES[c].color})"></span>${CLASSES[c].icon} ${CLASSES[c].label}</span>`).join("");
  const rows = [["all", "All engines"], ...Object.keys(s.by_engine).map((e) => [e, ENGINES[e] || e])];
  let html = "", tbl = `<table class="t"><tr><th>Engine</th>${BAR.map((c) => `<th>${CLASSES[c].label}</th>`).join("")}<th>Lost (link or content) among checkable</th></tr>`;
  for (const [e, name] of rows) {
    const c = e === "all" ? s.classes : s.by_engine[e].classes;
    const tot = BAR.reduce((a, k) => a + (c[k] || 0), 0);
    html += `<div class="name">${esc(name)}</div><div class="bar">` + BAR.filter((k) => c[k]).map((k) =>
      `<div class="seg ${k === "unverifiable" || k === "uncertain" ? "unver" : ""}" data-e="${e}" data-c="${k}" style="flex:${c[k]};background-color:var(${CLASSES[k].color})"
        data-tip="${esc(name)} · ${CLASSES[k].label}: ${c[k]} of ${tot} (${pct(c[k] / tot)})">${c[k] / tot > 0.07 ? pct(c[k] / tot) : ""}</div>`).join("") +
      `</div><div class="n">n = ${tot}</div>`;
    const r = e === "all" ? s : s.by_engine[e];
    tbl += `<tr><td>${esc(name)}</td>${BAR.map((k) => `<td>${c[k] || 0}</td>`).join("")}<td>${r.lost_any} / ${r.checkable} (${pct(r.lost_any / r.checkable)})</td></tr>`;
  }
  $("bars").innerHTML = html;
  $("table").innerHTML = tbl + "</table>";
  document.querySelectorAll(".seg").forEach((el) => {
    el.onmousemove = (ev) => tip(ev, el.dataset.tip);
    el.onmouseleave = untip;
    el.onclick = () => { $("fEngine").value = el.dataset.e === "all" ? "" : el.dataset.e; $("fClass").value = el.dataset.c;
      $("fLabel").value = "complete_support"; filter(); $("list").scrollIntoView({behavior: "smooth"}); };
  });
}

// ---------- list ----------
function card(it) {
  const C = CLASSES[it.c];
  const host = (() => { try { return new URL(it.u).hostname.replace(/^www\./, ""); } catch { return it.u; } })();
  const sc = (x) => x == null ? "—" : x.toFixed(2);
  let then = it.ev23 ? esc(it.ev23) : "<span class='note'>(no annotator evidence)</span>";
  let now = it.evn ? esc(it.evn) : `<span class="note">${it.lg === "reachable" ? "(no close match on the current page)" : "(page not readable: " + esc(STATES[it.ls] || it.ls) + ")"}</span>`;
  if (it.ev23 && it.evn) [then, now] = diff(it.ev23, it.evn);
  return `<div class="card ${it.c}">
    <div class="cls" style="color:var(${["--c-unver", "--c-uncert"].includes(C.color) ? "--muted" : C.color})">${C.icon} ${C.label}</div>
    <div class="stmt">${esc(it.s)}</div>
    <div class="meta"><span>${esc(ENGINES[it.e] || it.e)}</span><a href="${esc(it.u)}" target="_blank" rel="noopener noreferrer">${esc(host)}</a>
      <span class="pill">2023 annotator: <b>${esc(it.l.replace("_", " "))}</b></span>
      <span class="pill">judge 2023 <b>${sc(it.p23)}</b></span>
      <span class="pill">link now: <b>${esc(STATES[it.ls] || it.ls)}</b></span>
      <span class="pill">judge now <b>${sc(it.pn)}</b></span></div>
    <div class="tl"><div><h4>Evidence in ${DATA.meta.then_label} (annotator)</h4><div class="box">${then}</div></div>
      <div><h4>Closest sentence in ${DATA.meta.now_label}</h4><div class="box">${now}</div></div></div>
    <details><summary>Query</summary><div class="note">${esc(it.q)}</div></details>
  </div>`;
}

function filter() {
  const e = $("fEngine").value, c = $("fClass").value, s = $("fState").value, l = $("fLabel").value;
  const t = $("fText").value.trim().toLowerCase();
  view = DATA.items.filter((it) => (!e || it.e === e) && (!c || it.c === c) && (!s || it.ls === s) && (!l || it.l === l) &&
    (!t || (it.s + " " + it.q + " " + it.u).toLowerCase().includes(t)));
  shown = 0; $("list").innerHTML = ""; more();
}
function more() {
  const next = view.slice(shown, shown + 30);
  $("list").insertAdjacentHTML("beforeend", next.map(card).join(""));
  shown += next.length;
  $("count").textContent = `${view.length.toLocaleString()} pair${view.length === 1 ? "" : "s"}`;
  $("moreBtn").classList.toggle("hidden", shown >= view.length);
}
$("moreBtn").onclick = more;
for (const id of ["fEngine", "fClass", "fState", "fLabel"]) $(id).onchange = filter;
$("fText").oninput = () => { clearTimeout(window._t); window._t = setTimeout(filter, 200); };

// ---------- local check mode ----------
let LOCAL = null;
async function probeLocal() {
  if (LOCAL !== null) return;
  try { const r = await fetch("api/health"); LOCAL = r.ok ? await r.json() : false; } catch { LOCAL = false; }
  $("checkStatus").innerHTML = LOCAL && LOCAL.models
    ? `Local verifier is running on this machine${LOCAL.explain ? " (explanations available)" : ""}.`
    : `<span class="warn">This is the static explorer: checking needs the local server.</span> Run
       <code>python app/server.py</code> from the repository (one GPU with ~4&nbsp;GB, or ~10&nbsp;GB with explanations) and open
       <code>http://127.0.0.1:8765</code>.`;
  $("explain").disabled = !(LOCAL && LOCAL.explain);
  $("datasetThen").disabled = !(LOCAL && LOCAL.dataset_then);
  $("browserCheck").disabled = !(LOCAL && LOCAL.browser);
}
$("exampleBtn").onclick = () => {
  const ex = DATA.example;
  $("answer").value = ex.answer; $("urls").value = ex.urls.join("\n"); $("citedAt").value = ex.cited_at || "";
  $("datasetThen").checked = !$("datasetThen").disabled;
};
function checkCard(x) {
  const C = CLASSES[x.class];
  const [a, b] = x.excerpt_then && x.excerpt_now ? diff(x.excerpt_then, x.excerpt_now) : [esc(x.excerpt_then), esc(x.excerpt_now)];
  const thenLab = x.score_then == null ? ({ok: "—", provided: "—", no_capture: "no archive capture",
    not_requested: "no date given"}[x.archive] || "archive lookup failed") : x.score_then.toFixed(2);
  return `<div class="card ${x.class}" data-order="${x.order ? x.order.join(",") : ""}">
    <div class="cls" style="color:var(${["--c-unver", "--c-uncert"].includes(C.color) ? "--muted" : C.color})">${C.icon} ${C.label}</div>
    <div class="stmt">${esc(x.statement)} <span class="note">[${x.citation}]</span></div>
    <div class="meta"><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.url)}</a>
      <span class="pill">link now: <b>${esc(STATES[x.link_state] || x.link_state)}</b>${x.browser_rechecked ? " (browser)" : ""}</span>
      <span class="pill">then <b>${thenLab}</b></span>
      <span class="pill">now <b>${x.score_now == null ? "—" : x.score_now.toFixed(2)}</b></span></div>
    <div class="tl"><div><h4>Then${x.snapshot ? " (archived " + x.snapshot.slice(0, 8) + ")" : x.archive === "provided" ? " (dataset text, 2023)" : ""}</h4><div class="box">${a || "<span class='note'>—</span>"}</div></div>
      <div><h4>Now</h4><div class="box">${b || "<span class='note'>—</span>"}</div></div></div>
    ${x.explanation ? `<div class="note" style="margin-top:6px"><b>Why:</b> ${esc(x.explanation)}</div>` : ""}</div>`;
}

$("runBtn").onclick = async () => {
  await probeLocal();
  if (!(LOCAL && LOCAL.models)) return;
  const body = {answer: $("answer").value, urls: $("urls").value.split("\n").map((x) => x.trim()).filter(Boolean),
    cited_at: $("citedAt").value || null, explain: $("explain").checked, dataset_then: $("datasetThen").checked,
    browser: $("browserCheck").checked};
  $("checkOut").innerHTML = `<div class="panel note" id="progress">Starting…</div><div id="cards"></div>`;
  $("runBtn").disabled = true;
  const t0 = performance.now(), cnt = {}, items = [];
  let plan = null;
  const progress = (msg) => { $("progress").innerHTML = msg; };
  const summary = () => Object.entries(cnt).map(([k, v]) => `${CLASSES[k].icon} ${CLASSES[k].label} ${v}`).join(" · ");
  try {
    const r = await fetch("api/check_stream", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    if (!r.ok) throw new Error((await r.json()).detail || r.status);
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const ev = JSON.parse(buf.slice(0, nl)); buf = buf.slice(nl + 1);
        if (ev.type === "plan") { plan = ev; progress(`Checking ${ev.n_pairs} statement–citation pairs on ${ev.n_urls} page(s)…`); }
        else if (ev.type === "page") {
          const host = (() => { try { return new URL(ev.url).hostname.replace(/^www\./, ""); } catch { return ev.url; } })();
          progress(`Page ${ev.i} of ${plan.n_urls}: <b>${esc(host)}</b> — ${esc(STATES[ev.link_state] || ev.link_state)}${ev.browser_rechecked ? " (opened in a browser)" : ""}. Judging… ${summary()}`);
        } else if (ev.type === "item") {
          const x = ev.item; items.push(x); cnt[x.class] = (cnt[x.class] || 0) + 1;
          items.sort((p, q) => p.order[0] - q.order[0] || p.order[1] - q.order[1]);
          $("cards").innerHTML = items.map(checkCard).join("");
        } else if (ev.type === "done") {
          progress(`${items.length} statement–citation pairs checked in ${((performance.now() - t0) / 1000).toFixed(1)} s: ${summary()}`);
        }
      }
    }
  } catch (e) { progress(`<span class="warn">Check failed: ${esc(e.message)}</span>`); }
  $("runBtn").disabled = false;
};


// ---------- boot ----------
fetch("explorer.json").then((r) => r.json()).then((d) => {
  DATA = d;
  for (const e of Object.keys(d.summary.by_engine)) $("fEngine").insertAdjacentHTML("beforeend", `<option value="${e}">${ENGINES[e] || e}</option>`);
  for (const c of [...BAR, "never_supported"]) $("fClass").insertAdjacentHTML("beforeend", `<option value="${c}">${CLASSES[c].label}</option>`);
  for (const [k, v] of Object.entries(STATES)) $("fState").insertAdjacentHTML("beforeend", `<option value="${k}">${v}</option>`);
  $("aboutBody").innerHTML = d.about;
  $("foot").innerHTML = d.footer;
  summary(); filter();
});
