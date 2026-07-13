#!/usr/bin/env python3
"""Regenerate index.html from data/latest.csv.

Usage: python3 build.py
Reads data/latest.csv (the canonical dataset), sorts rows MM -> MM/Ent -> Ent,
computes the headline stats, and writes a fully self-contained index.html.
No third-party dependencies.
"""
import csv, json, os, datetime, glob, re

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = "eric-hastie/remote-ae-job-hunt"
CSV_PATH = os.path.join(ROOT, "data", "latest.csv")

def tier(seg):
    # pure mid-market first, then MM/Ent hybrids, then pure enterprise
    if seg in ("MM", "SMB/MM"): return 0
    if "MM" in seg: return 1
    return 2

def clean(v):
    # normalize em/en dashes to plain hyphens so weekly data never reintroduces them
    return v.replace("—", "-").replace("–", "-") if isinstance(v, str) else v

def load():
    with open(CSV_PATH, newline="") as f:
        r = list(csv.DictReader(f))
    rows = [{
        "company": clean(x["Company"]), "funding": clean(x["Funding ($M)"]), "ote": clean(x["OTE"]),
        "segment": clean(x["Segment"]), "hq": clean(x["HQ"]), "remote": clean(x["Remote"]),
        "repvue": clean(x["RepVue"]), "industry": clean(x["Industry"]), "url": clean(x["Job Posting URL"]),
        "added": clean(x.get("Date Added", "")),
        "posted": clean(x.get("Posted", "")),
    } for x in r]
    rows.sort(key=lambda x: tier(x["segment"]))            # stable within date
    rows.sort(key=lambda x: x["added"], reverse=True)      # newest first
    return rows

TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Remote AE Market Map - Verified Account Executive Roles</title>
<meta name="description" content="A hand-verified dataset of remote US Account Executive roles at B2B SaaS companies, built with an AI-assisted research pipeline.">
<style>
:root{
  --bg:#0f1115; --panel:#171a21; --panel2:#1d212a; --line:#2a2f3a;
  --txt:#e7eaf0; --muted:#9aa3b2; --accent:#6c8cff; --accent2:#41d3a3;
  --mm:#1f6f54; --mmtxt:#7ff0c8; --ent:#3a3f4b; --enttxt:#c3c9d4;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
header{padding:64px 0 28px;border-bottom:1px solid var(--line)}
.eyebrow{color:var(--accent2);font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-size:12px;margin:0 0 14px}
h1{font-size:40px;line-height:1.12;margin:0 0 14px;font-weight:740;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:18px;max-width:680px;margin:0}
.byline{margin-top:22px;color:var(--muted);font-size:14px}
.byline b{color:var(--txt)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:34px 0 8px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.stat .n{font-size:28px;font-weight:720;letter-spacing:-.02em}
.stat .l{color:var(--muted);font-size:13px;margin-top:4px}
section.about{padding:40px 0 8px}
h2{font-size:22px;margin:0 0 14px;letter-spacing:-.01em}
.about p{color:#cdd3de;max-width:760px}
.method{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px}
@media(max-width:760px){.method{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:30px}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.card h3{margin:0 0 6px;font-size:15px;color:var(--accent2)}
.card p{margin:0;color:var(--muted);font-size:14px}
.controls{position:sticky;top:0;z-index:5;background:var(--bg);
  padding:22px 0 14px;margin-top:36px;border-bottom:1px solid var(--line);
  display:flex;gap:12px;flex-wrap:wrap;align-items:center}
#q{flex:1;min-width:220px;background:var(--panel2);border:1px solid var(--line);color:var(--txt);
  padding:11px 14px;border-radius:10px;font-size:14px;outline:none}
#q:focus{border-color:var(--accent)}
.seg{display:flex;gap:6px;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:4px}
.seg button{background:transparent;border:0;color:var(--muted);padding:7px 14px;border-radius:7px;cursor:pointer;font-size:13px;font-weight:600}
.seg button.on{background:var(--accent);color:#0b0d12}
.count{color:var(--muted);font-size:13px;white-space:nowrap}
.tablewrap{overflow-x:auto;margin:18px 0 60px;border:1px solid var(--line);border-radius:12px}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:900px}
thead th{position:sticky;top:0;background:var(--panel2);text-align:left;padding:13px 14px;
  font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);
  border-bottom:1px solid var(--line);cursor:pointer;user-select:none;white-space:nowrap}
thead th:hover{color:var(--txt)}
thead th .arw{opacity:.5;font-size:10px}
tbody td{padding:13px 14px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--panel)}
.co{font-weight:650;font-size:15px}
.ind{color:var(--muted);font-size:12.5px;margin-top:2px}
.badge{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;white-space:nowrap}
.b-mm{background:var(--mm);color:var(--mmtxt)}
.b-ent{background:var(--ent);color:var(--enttxt)}
.ote{font-variant-numeric:tabular-nums}
.apply{font-weight:600;white-space:nowrap}
.muted{color:var(--muted)}
footer{border-top:1px solid var(--line);padding:30px 0 70px;color:var(--muted);font-size:13px}
footer .wrap{max-width:760px}
.note{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent2);
  border-radius:8px;padding:14px 16px;margin:16px 0;color:#cdd3de;font-size:13.5px}
</style>
</head>
<body>
<header><div class="wrap">
  <p class="eyebrow">B2B SaaS · Sales · Market Research</p>
  <h1>Remote AE Market Map</h1>
  <p class="sub">A hand-verified dataset of remote US <b>Account Executive</b> openings at B2B SaaS companies - built with an AI-assisted research pipeline that screens against a defined ICP and verifies every posting is live.</p>
  <p class="byline">Compiled by <b>Eric Hastie</b> · Data verified __DATEHUMAN__ · <span class="muted">a portfolio project</span></p>
  <p class="byline" style="margin-top:6px"><b>Current roles</b> &nbsp;·&nbsp; <a href="history.html">History &amp; Trends →</a></p>
  <div class="stats">
    <div class="stat"><div class="n">__TOTAL__</div><div class="l">verified, qualified roles</div></div>
    <div class="stat"><div class="n">__MM__</div><div class="l">mid-market-friendly</div></div>
    <div class="stat"><div class="n">5</div><div class="l">industry verticals</div></div>
    <div class="stat"><div class="n">100%</div><div class="l">postings verified live</div></div>
  </div>
</div></header>
<section class="about"><div class="wrap">
  <h2>About this project</h2>
  <p>While job-searching, I got tired of scraped job boards that bury a handful of good fits under hundreds of mismatched listings. So I built a research workflow that does the opposite: it defines a precise ideal-candidate profile, then <b>verifies and filters first</b> - only surfacing roles that actually clear the bar. It re-runs weekly, so the data stays current and the history doubles as a view into how the remote-AE market is moving.</p>
  <div class="method">
    <div class="card"><h3>1 · Defined the ICP</h3><p>Individual-contributor AE, Mid-Market / Enterprise B2B SaaS, US-remote, ~$150-340K OTE, ~4+ yrs closing. The bar is explicit, so nothing off-profile gets through.</p></div>
    <div class="card"><h3>2 · Fanned out by vertical</h3><p>Parallel research across five lanes - dev tools &amp; infra, fintech &amp; data, vertical SaaS, AI-native, and security - so the results are diverse, not the same five household names.</p></div>
    <div class="card"><h3>3 · Verified every posting</h3><p>Each role was confirmed live, remote, and IC-level against the company's own ATS (Greenhouse / Ashby). Anything unverifiable was dropped - <b>zero fabricated or stale listings</b>.</p></div>
    <div class="card"><h3>4 · De-duped &amp; segmented</h3><p>Screened against a 64-company master list to keep only net-new finds, then tagged by segment so mid-market roles (the qualifying lane) sort to the top.</p></div>
  </div>
  <h2 style="margin-top:34px">Where this goes next</h2>
  <p>Beyond my own search, this is a working prototype for <b>territory intelligence</b>. Job postings are one of the cleanest buying signals in B2B sales: a company opening a RevOps role, standing up a new region, or scaling its CS or implementation team telegraphs budget, active initiatives, and pain points well before any intent-data vendor flags them. In a sales seat I'll point this same pipeline at my book of business, scanning target accounts' careers pages to surface timing signals and catch org and leadership changes.</p>
  <p>And because every run is snapshotted, the signal compounds over time. An account's week-over-week hiring history tells a story that sharpens <b>account planning</b>: sustained hiring points to expansion and the right moment to upsell, a sudden freeze can flag churn risk, and a new leader or function hints at where the next initiative is headed. The same engine that keeps this dataset current becomes a running intelligence feed on the accounts that matter most.</p>
  <p>That idea is now a working tool: I built it into <a href="https://eric-hastie.github.io/territory-radar/" target="_blank" rel="noopener"><b>Territory Radar</b></a> - a live dashboard that scores a sales territory on exactly these signals and tracks each account's momentum week over week.</p>

  <div class="note">Filter and search the full dataset below. Every <b>Apply</b> link points to the live job posting that was verified during research. Mid-market roles are flagged in green.</div>
</div></section>
<div class="wrap">
  <div class="controls">
    <input id="q" type="search" placeholder="Search company, industry, or location…" autocomplete="off">
    <div class="seg" id="seg">
      <button data-seg="all" class="on">All</button>
      <button data-seg="mm">Mid-market</button>
      <button data-seg="ent">Enterprise</button>
    </div>
    <span class="count" id="count"></span>
  </div>
  <div class="tablewrap">
    <table>
      <thead><tr>
        <th data-k="added">Added <span class="arw"></span></th>
        <th data-k="posted">Posted <span class="arw"></span></th>
        <th data-k="company">Company <span class="arw"></span></th>
        <th data-k="funding">Funding ($M) <span class="arw"></span></th>
        <th data-k="ote">OTE <span class="arw"></span></th>
        <th data-k="segment">Segment <span class="arw"></span></th>
        <th data-k="hq">HQ <span class="arw"></span></th>
        <th data-k="repvue">RepVue <span class="arw"></span></th>
        <th>Posting</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
</div>
<footer><div class="wrap">
  <p><b>Methodology note.</b> This is a snapshot verified __DATEHUMAN__; job postings turn over quickly, so confirm a role is still open before applying. Funding and RepVue figures are from public sources and may be approximate (blank where not reliably verifiable rather than guessed). All companies shown are net-new relative to a separately maintained master list.</p>
  <p>Built by Eric Hastie as a demonstration of GTM research, data curation, and AI-assisted workflow design. Refreshed automatically each week.</p>
</div></footer>
<script>
const DATA = __DATA__;
const tbody=document.getElementById('rows');
const q=document.getElementById('q');
const count=document.getElementById('count');
let seg='all', sortK=null, sortDir=1;
function isMM(r){return r.segment.includes('MM')}
function segLabel(r){const cls=isMM(r)?'b-mm':'b-ent';return '<span class="badge '+cls+'">'+r.segment+'</span>';}
function fundDisp(r){return r.funding? (isNaN(r.funding)? r.funding : '$'+r.funding+'M') : '<span class="muted">-</span>'}
function num(v){const n=parseFloat(String(v).replace(/[^0-9.]/g,''));return isNaN(n)?-1:n}
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const BUILD_DATE='__BUILDDATE__';
function fmtAdded(d){
  if(!d) return '<span class="muted">-</span>';
  const [y,m,dd]=d.split('-');
  const label=MONTHS[+m-1]+' '+(+dd);
  const days=(new Date(BUILD_DATE)-new Date(d))/86400000;
  return days<=7 ? '<b style="color:var(--accent2)">'+label+'</b>' : '<span class="muted">'+label+'</span>';
}
function render(){
  const term=q.value.trim().toLowerCase();
  let list=DATA.filter(r=>{
    if(seg==='mm' && !isMM(r))return false;
    if(seg==='ent' && isMM(r))return false;
    if(!term)return true;
    return (r.company+' '+r.industry+' '+r.hq).toLowerCase().includes(term);
  });
  if(sortK){
    list=list.slice().sort((a,b)=>{
      let av=a[sortK], bv=b[sortK];
      if(sortK==='funding'||sortK==='repvue'){av=num(av);bv=num(bv);return (av-bv)*sortDir}
      return String(av).localeCompare(String(bv))*sortDir;
    });
  }
  tbody.innerHTML=list.map(r=>`
    <tr>
      <td class="ote" style="white-space:nowrap">${fmtAdded(r.added)}</td>
      <td class="ote" style="white-space:nowrap">${fmtAdded(r.posted)}</td>
      <td><div class="co">${r.company}</div><div class="ind">${r.industry||''}</div></td>
      <td>${fundDisp(r)}</td>
      <td class="ote">${r.ote||'<span class=muted>-</span>'}</td>
      <td>${segLabel(r)}</td>
      <td class="muted">${r.hq||''}</td>
      <td>${r.repvue?('<b>'+r.repvue+'</b>'):'<span class=muted>-</span>'}</td>
      <td><a class="apply" href="${r.url}" target="_blank" rel="noopener">Apply →</a></td>
    </tr>`).join('');
  count.textContent=list.length+' of '+DATA.length+' roles';
}
document.querySelectorAll('#seg button').forEach(b=>b.onclick=()=>{
  seg=b.dataset.seg;
  document.querySelectorAll('#seg button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');render();
});
document.querySelectorAll('thead th[data-k]').forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;
  if(sortK===k){sortDir*=-1}else{sortK=k;sortDir=1}
  document.querySelectorAll('thead th .arw').forEach(a=>a.textContent='');
  th.querySelector('.arw').textContent=sortDir>0?'▲':'▼';
  render();
});
q.oninput=render;
render();
</script>
</body>
</html>'''

def parse_ote_mid(s):
    """Best-effort midpoint of an OTE string like '$170-262K' or '$250K' (in $K)."""
    nums = [int(n) for n in re.findall(r'(\d{2,3})\s*[kK]', s)]
    nums = [n for n in nums if 80 <= n <= 600]
    if not nums:
        nums = [int(n) for n in re.findall(r'\b(\d{3})\b', s) if 80 <= int(n) <= 600]
    if not nums:
        return None
    return (min(nums) + max(nums)) / 2

def snapshots():
    """Load every data/YYYY-MM-DD.csv snapshot, compute metrics + week-over-week diffs."""
    snaps = []
    for f in glob.glob(os.path.join(ROOT, "data", "*.csv")):
        m = re.match(r'(\d{4}-\d{2}-\d{2})\.csv$', os.path.basename(f))
        if not m:
            continue  # skips latest.csv
        with open(f, newline="") as fh:
            rows = list(csv.DictReader(fh))
        otes = [o for o in (parse_ote_mid(r["OTE"]) for r in rows) if o]
        mm = sum(1 for r in rows if "MM" in r["Segment"])
        snaps.append({
            "date": m.group(1), "total": len(rows), "mm": mm, "ent": len(rows) - mm,
            "avg_ote": round(sum(otes) / len(otes)) if otes else None,
            "companies": sorted(clean(r["Company"]) for r in rows),
        })
    snaps.sort(key=lambda s: s["date"])
    for i, s in enumerate(snaps):
        prev = set(snaps[i - 1]["companies"]) if i else set()
        cur = set(s["companies"])
        s["added"] = sorted(cur - prev) if i else []
        s["dropped"] = sorted(prev - cur) if i else []
        s["first"] = (i == 0)
    for s in snaps:
        del s["companies"]
    return snaps

HISTORY_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>History & Trends - Remote AE Market Map</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--panel2:#1d212a;--line:#2a2f3a;--txt:#e7eaf0;--muted:#9aa3b2;--accent:#6c8cff;--accent2:#41d3a3;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.55}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:880px;margin:0 auto;padding:0 20px}
header{padding:56px 0 24px;border-bottom:1px solid var(--line)}
.eyebrow{color:var(--accent2);font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-size:12px;margin:0 0 12px}
h1{font-size:34px;margin:0 0 12px;font-weight:740;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:17px;max-width:620px;margin:0}
.byline{margin-top:18px;color:var(--muted);font-size:14px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:30px 0 0}
@media(max-width:680px){.stats{grid-template-columns:repeat(2,1fr)}}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.stat .n{font-size:24px;font-weight:720}.stat .l{color:var(--muted);font-size:12.5px;margin-top:3px}
section{padding:36px 0 0}
h2{font-size:20px;margin:0 0 14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.legend{display:flex;gap:18px;margin-top:10px;font-size:12.5px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}
.wk{border-bottom:1px solid var(--line);padding:14px 0}.wk:last-child{border-bottom:0}
.wkhead{font-size:14.5px;margin-bottom:8px}
.wkrow{display:flex;gap:8px;align-items:baseline;margin:4px 0;flex-wrap:wrap}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);min-width:52px}
.chip{display:inline-block;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;margin:2px 0}
.chip.add{background:#1f6f54;color:#7ff0c8}.chip.drop{background:#3a3f4b;color:#c3c9d4}
.up{color:#41d3a3;font-weight:700}.down{color:#ff7a7a;font-weight:700}.muted{color:var(--muted)}
footer{border-top:1px solid var(--line);margin-top:40px;padding:26px 0 60px;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<header><div class="wrap">
  <p class="eyebrow">B2B SaaS · Sales · Market Research</p>
  <h1>History &amp; Trends</h1>
  <p class="sub">How the remote-AE market is moving over time. This dataset is re-verified and re-scanned automatically every week; each run is snapshotted so the changes are tracked, not overwritten.</p>
  <p class="byline"><a href="./">← Current roles</a> &nbsp;·&nbsp; <span class="muted">updated __DATEHUMAN__</span></p>
  <div class="stats">
    <div class="stat"><div class="n">__WEEKS__</div><div class="l">weekly snapshots</div></div>
    <div class="stat"><div class="n">__CURRENT__</div><div class="l">roles right now</div></div>
    <div class="stat"><div class="n">__NETCHG__</div><div class="l">net change since start</div></div>
    <div class="stat"><div class="n">__AVGOTE__</div><div class="l">avg OTE (current)</div></div>
  </div>
</div></header>

<div class="wrap">
  <section>
    <h2>Open roles over time</h2>
    <div class="panel"><div id="chart"></div></div>
  </section>
  <section>
    <h2>Weekly changelog</h2>
    <div class="panel" id="log"></div>
  </section>
</div>

<footer><div class="wrap">
  Trends are computed from the dated snapshots in <code>data/</code>. Avg OTE is a best-effort midpoint of posted ranges and is directional. Built by Eric Hastie · auto-refreshed weekly.
</div></footer>

<script>
const M = __METRICS__;
const REPO = "__REPO__";

function drawChart(){
  const w=720,h=300,pad={l:40,r:16,t:16,b:42};
  const iw=w-pad.l-pad.r, ih=h-pad.t-pad.b, n=M.length;
  const maxv=Math.max(...M.map(d=>d.total),1);
  const X=i=> n<=1 ? pad.l+iw/2 : pad.l+iw*i/(n-1);
  const Y=v=> pad.t+ih*(1-v/maxv);
  const series=[{k:'total',c:'#6c8cff',l:'Total'},{k:'mm',c:'#41d3a3',l:'MM-friendly'},{k:'ent',c:'#9aa3b2',l:'Enterprise'}];
  let s=`<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Open roles over time">`;
  for(let g=0;g<=4;g++){const v=Math.round(maxv*g/4),yy=Y(v);
    s+=`<line x1="${pad.l}" y1="${yy}" x2="${w-pad.r}" y2="${yy}" stroke="#2a2f3a"/>`;
    s+=`<text x="${pad.l-8}" y="${yy+4}" fill="#9aa3b2" font-size="11" text-anchor="end">${v}</text>`;}
  const step=Math.max(1,Math.ceil(n/8));
  M.forEach((d,i)=>{ if(i%step===0||i===n-1) s+=`<text x="${X(i)}" y="${h-pad.b+18}" fill="#9aa3b2" font-size="10" text-anchor="middle">${d.date.slice(5)}</text>`;});
  series.forEach(se=>{
    if(n>1) s+=`<polyline points="${M.map((d,i)=>X(i)+','+Y(d[se.k])).join(' ')}" fill="none" stroke="${se.c}" stroke-width="2.5"/>`;
    M.forEach((d,i)=> s+=`<circle cx="${X(i)}" cy="${Y(d[se.k])}" r="3.5" fill="${se.c}"/>`);
  });
  s+=`</svg><div class="legend">`+series.map(se=>`<span><i style="background:${se.c}"></i>${se.l}</span>`).join('')+`</div>`;
  document.getElementById('chart').innerHTML=s;
}
function drawLog(){
  const chips=(a,c)=> a.length? a.map(x=>`<span class="chip ${c}">${x}</span>`).join(' ') : '<span class="muted">-</span>';
  document.getElementById('log').innerHTML = M.slice().reverse().map((d,ri)=>{
    const prev = M[M.length-2-ri];
    const delta = prev ? d.total-prev.total : 0;
    const dt = delta>0?`<span class="up">+${delta}</span>`:delta<0?`<span class="down">${delta}</span>`:`<span class="muted">±0</span>`;
    const snap=`https://github.com/${REPO}/blob/main/data/${d.date}.csv`;
    const head=`<div class="wkhead"><b>${d.date}</b> · ${d.total} roles ${dt} · avg OTE ${d.avg_ote?('$'+d.avg_ote+'K'):'-'} · <a href="${snap}" target="_blank" rel="noopener">snapshot ↗</a></div>`;
    if(d.first) return `<div class="wk">${head}<div class="wkrow"><span class="muted">Initial dataset of ${d.total} verified roles.</span></div></div>`;
    return `<div class="wk">${head}
      <div class="wkrow"><span class="lbl">Added</span> ${chips(d.added,'add')}</div>
      <div class="wkrow"><span class="lbl">Closed</span> ${chips(d.dropped,'drop')}</div></div>`;
  }).join('');
}
drawChart(); drawLog();
</script>
</body>
</html>'''

def main():
    today = datetime.date.today()
    human = today.strftime("%B %-d, %Y") if os.name != "nt" else today.strftime("%B %d, %Y")

    rows = load()
    total = len(rows)
    mm = sum(1 for x in rows if "MM" in x["segment"])
    out = (TEMPLATE
           .replace("__DATA__", json.dumps(rows))
           .replace("__TOTAL__", str(total))
           .replace("__MM__", str(mm))
           .replace("__BUILDDATE__", today.isoformat())
           .replace("__DATEHUMAN__", human))
    with open(os.path.join(ROOT, "index.html"), "w") as f:
        f.write(out)
    print(f"built index.html: {total} roles ({mm} MM-friendly), verified {human}")

    snaps = snapshots()
    if snaps:
        net = snaps[-1]["total"] - snaps[0]["total"]
        avg = snaps[-1]["avg_ote"]
        hist = (HISTORY_TEMPLATE
                .replace("__METRICS__", json.dumps(snaps))
                .replace("__REPO__", REPO)
                .replace("__DATEHUMAN__", human)
                .replace("__WEEKS__", str(len(snaps)))
                .replace("__CURRENT__", str(snaps[-1]["total"]))
                .replace("__NETCHG__", f"+{net}" if net >= 0 else str(net))
                .replace("__AVGOTE__", f"${avg}K" if avg else "-"))
        with open(os.path.join(ROOT, "history.html"), "w") as f:
            f.write(hist)
        print(f"built history.html: {len(snaps)} snapshots, net {net:+d} since {snaps[0]['date']}")

if __name__ == "__main__":
    main()
