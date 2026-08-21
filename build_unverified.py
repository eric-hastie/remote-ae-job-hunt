"""Build unverified.html - AE roles sourced from job aggregators (Wellfound, HiringCafe)
that have NOT been confirmed against the company's own ATS board API.

These are deliberately kept separate from the main list. Some are real postings the
company never published to its own careers page (ContextQA is one), so "unverified"
means "not confirmed", NOT "not real". Date posted is shown so staleness is visible.
"""
import csv, re, os, sys, json, datetime, html

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TODAY = datetime.date(2026, 8, 3)

# The bar lives in scripts/bar.py so this page and the speedrun triage cannot
# drift apart on what counts as Mid-Market or where the experience ceiling is.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from bar import BAD, AE, MM_T, ENT_T, SMB_T, MM_B, ENT_B, base, seg, yoe_ok  # noqa: E402


published = {(r.get("Job Posting URL") or "").strip()
             for r in csv.DictReader(open(os.path.join(D, "latest.csv"), encoding="utf-8"))}
pub_co = {base(r["Company"])
          for r in csv.DictReader(open(os.path.join(D, "latest.csv"), encoding="utf-8"))}

rows = []

# ---- HiringCafe ---------------------------------------------------------
for r in csv.DictReader(open(os.path.join(D, "hiringcafe_raw.tsv"), encoding="utf-8"), delimiter="\t"):
    if str(r.get("Expired", "")).lower() == "true":
        continue
    t = r["Title"]
    if not AE.search(t) or BAD.search(t) or not yoe_ok(r["MinYOE"]):
        continue
    url = (r["ApplyURL"] or "").strip()
    if url in published:
        continue
    comp = ""
    if r["CompMin"]:
        comp = "$%s - $%s" % (f"{int(float(r['CompMin'])):,}", f"{int(float(r['CompMax'])):,}") \
            if r["CompMax"] else "$%s" % f"{int(float(r['CompMin'])):,}"
    rows.append(dict(co=r["Company"], seg=seg(t, r.get("Requirements", "")), title=t,
                     posted=r["Posted"], comp=comp, yoe=r["MinYOE"], loc=r["FoundVia"],
                     raw=(r["States"] or r["Countries"] or ""), src="HiringCafe",
                     ats=r["ATS"] or "", url=url,
                     already=base(r["Company"]) in pub_co))

# ---- Wellfound ----------------------------------------------------------
for r in csv.DictReader(open(os.path.join(D, "wellfound_raw.tsv"), encoding="utf-8"), delimiter="\t"):
    t = r["Title"]
    if not AE.search(t) or BAD.search(t):
        continue
    if r["FoundVia"] == "Remote" and "united states" not in (r["RemoteAccepted"] or "").lower():
        continue
    y = r["YrsMin"]
    if y and y.isdigit() and int(y) > 8:
        continue
    url = (r["WellfoundURL"] or "").strip()
    if url in published:
        continue
    rows.append(dict(co=r["Company"], seg=seg(t), title=t, posted=r["Posted"],
                     comp=r["Comp"], yoe=y, loc=r["FoundVia"], raw=r["Locations"] or "",
                     src="Wellfound", ats=r["ATS"] or "", url=url,
                     already=base(r["Company"]) in pub_co))

# dedupe on url
seen, ded = set(), []
for r in sorted(rows, key=lambda x: x["posted"], reverse=True):
    if r["url"] in seen:
        continue
    seen.add(r["url"])
    ded.append(r)
rows = ded


def age(p):
    try:
        d = datetime.date(*map(int, p.split("-")))
        return (TODAY - d).days
    except Exception:
        return None


for r in rows:
    r["age"] = age(r["posted"])

with open(os.path.join(D, "unverified.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["Company", "Segment", "Title", "Posted", "DaysOld", "Comp", "MinYOE",
                "Location", "RawLocation", "Source", "ATS", "AlreadyOnMainList", "URL"])
    for r in rows:
        w.writerow([r["co"], r["seg"], r["title"], r["posted"], r["age"] if r["age"] is not None else "",
                    r["comp"], r["yoe"], r["loc"], r["raw"], r["src"], r["ats"],
                    "Y" if r["already"] else "", r["url"]])

import collections
segs = collections.Counter(r["seg"] for r in rows)
fresh = sum(1 for r in rows if r["age"] is not None and r["age"] <= 30)
cos = len({base(r["co"]) for r in rows})

def esc(s):
    return html.escape(str(s or ""))

trs = []
for r in rows:
    a = r["age"]
    cls = "fresh" if (a is not None and a <= 30) else ("mid" if (a is not None and a <= 90) else "old")
    agetxt = ("%dd" % a) if a is not None else "?"
    trs.append(
        f'<tr data-seg="{esc(r["seg"])}" data-src="{esc(r["src"])}" data-age="{a if a is not None else 9999}">'
        f'<td class="co">{esc(r["co"])}{" <span class=chip>on main list</span>" if r["already"] else ""}</td>'
        f'<td><span class="seg s-{esc(r["seg"]).replace("/","-")}">{esc(r["seg"])}</span></td>'
        f'<td>{esc(r["title"])}</td>'
        f'<td class="{cls} num" data-sort="{a if a is not None else 9999}">{esc(r["posted"])}<span class="ago">{agetxt}</span></td>'
        f'<td>{esc(r["comp"])}</td><td class="num">{esc(r["yoe"])}</td>'
        f'<td>{esc(r["loc"])}</td><td>{esc(r["src"])}</td><td>{esc(r["ats"])}</td>'
        f'<td><a href="{esc(r["url"])}" target="_blank" rel="noopener">open</a></td></tr>')

NAV = ('<a href="index.html">Remote</a> &nbsp;·&nbsp; <a href="nyc.html">NYC</a> &nbsp;·&nbsp; '
       '<a href="sf.html">SF</a> &nbsp;·&nbsp; <a href="denver.html">Denver</a> &nbsp;·&nbsp; '
       '<a href="boston.html">Boston</a> &nbsp;·&nbsp; <a href="austin.html">Austin</a> &nbsp;·&nbsp; '
       '<b>Unverified Leads</b> &nbsp;·&nbsp; <a href="history.html">History &amp; Trends</a> '
       '&nbsp;·&nbsp; <a href="discards.html">Discards</a>')

page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unverified Leads - AE Market Map</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#e6edf3;--dim:#8b949e;--acc:#58a6ff}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
.wrap{{max-width:1400px;margin:0 auto;padding:28px 20px 60px}}
nav{{font-size:14px;color:var(--dim);margin-bottom:18px}} nav a{{color:var(--acc);text-decoration:none}}
h1{{margin:0 0 6px;font-size:26px}} .sub{{color:var(--dim);margin:0 0 18px;max-width:900px}}
.warn{{background:#2d2000;border:1px solid #6a4c00;border-radius:8px;padding:12px 14px;margin:0 0 18px;font-size:14px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 14px;font-size:13px}}
.stat b{{display:block;font-size:20px}}
.ctl{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}}
input,select{{background:var(--card);border:1px solid var(--line);color:var(--tx);border-radius:7px;padding:8px 10px;font-size:14px}}
input{{flex:1;min-width:220px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th,td{{padding:8px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:var(--bg);cursor:pointer;white-space:nowrap;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--dim)}}
th:hover{{color:var(--tx)}} td.num{{white-space:nowrap}} .co{{font-weight:600}}
a{{color:var(--acc)}}
.ago{{display:block;font-size:11px;color:var(--dim)}}
.fresh .ago{{color:#3fb950}} .mid .ago{{color:#d29922}} .old .ago{{color:#f85149}}
.seg{{font-size:11px;padding:2px 7px;border-radius:20px;border:1px solid var(--line);white-space:nowrap}}
.s-MM{{background:#0d2818;border-color:#238636;color:#7ee787}}
.s-MM-Ent{{background:#132a1c;border-color:#2ea043;color:#7ee787}}
.s-Ent{{background:#161b22;color:var(--dim)}}
.chip{{font-size:10px;background:#1f2937;border:1px solid var(--line);border-radius:10px;padding:1px 6px;color:var(--dim);font-weight:400}}
.hide{{display:none}}
</style></head><body><div class="wrap">
<nav>{NAV}</nav>
<h1>Unverified Leads</h1>
<p class="sub">Account Executive roles found on job aggregators (Wellfound, HiringCafe) that have <b>not</b> been confirmed against the company's own ATS board API. Everything here clears the same ICP screen as the main list.</p>
<div class="warn"><b>Unverified does not mean fake.</b> Some companies post to an aggregator and never publish the role on their own careers page or ATS feed (ContextQA is one). Others are stale listings the company forgot to take down. <b>Sort by Posted to judge</b> - a role posted this month is a very different bet from one posted last year.</div>
<div class="stats">
<div class="stat"><b>{len(rows)}</b>roles</div>
<div class="stat"><b>{cos}</b>companies</div>
<div class="stat"><b>{segs.get('MM',0)+segs.get('MM/Ent',0)}</b>MM / MM-Ent</div>
<div class="stat"><b>{fresh}</b>posted in last 30d</div>
</div>
<div class="ctl">
<input id="q" placeholder="Search company, title, ATS...">
<select id="seg"><option value="">All segments</option><option>MM</option><option>MM/Ent</option><option>Ent</option><option>SMB</option><option>Unspec</option></select>
<select id="src"><option value="">Both sources</option><option>HiringCafe</option><option>Wellfound</option></select>
<select id="age"><option value="9999">Any age</option><option value="30">Posted &lt;30d</option><option value="90">Posted &lt;90d</option><option value="365">Posted &lt;1y</option></select>
</div>
<table id="t"><thead><tr>
<th>Company</th><th>Segment</th><th>Title</th><th>Posted</th><th>Comp (often base)</th><th>Yrs</th><th>Loc</th><th>Source</th><th>ATS</th><th></th>
</tr></thead><tbody>
{chr(10).join(trs)}
</tbody></table>
<script>
const tb=document.querySelector('#t tbody');
function flt(){{
 const q=document.getElementById('q').value.toLowerCase(),
  s=document.getElementById('seg').value, sc=document.getElementById('src').value,
  a=+document.getElementById('age').value;
 [...tb.rows].forEach(r=>{{
  const ok=(!q||r.innerText.toLowerCase().includes(q))&&(!s||r.dataset.seg===s)
   &&(!sc||r.dataset.src===sc)&&(+r.dataset.age<=a);
  r.classList.toggle('hide',!ok);
 }});
}}
['q','seg','src','age'].forEach(id=>document.getElementById(id).addEventListener('input',flt));
document.querySelectorAll('#t th').forEach((th,i)=>th.addEventListener('click',()=>{{
 const rs=[...tb.rows], asc=th.dataset.asc!=='1'; th.dataset.asc=asc?'1':'0';
 rs.sort((x,y)=>{{
  const a=x.cells[i].dataset.sort??x.cells[i].innerText, b=y.cells[i].dataset.sort??y.cells[i].innerText;
  const na=parseFloat(a),nb=parseFloat(b);
  if(!isNaN(na)&&!isNaN(nb)) return asc?na-nb:nb-na;
  return asc?String(a).localeCompare(b):String(b).localeCompare(a);
 }});
 rs.forEach(r=>tb.appendChild(r));
}}));
document.getElementById('age').value='9999';
</script>
</div></body></html>"""

open(os.path.join(os.path.dirname(D), "unverified.html"), "w", encoding="utf-8").write(page)
print("unverified: %d roles / %d companies | MM+MM/Ent %d | fresh(<=30d) %d"
      % (len(rows), cos, segs.get("MM", 0) + segs.get("MM/Ent", 0), fresh))
print("segments:", dict(segs.most_common()))
