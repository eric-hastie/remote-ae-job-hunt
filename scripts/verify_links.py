#!/usr/bin/env python3
"""Deterministically verify every Job Posting URL in data/latest.csv.

Checks the job ID against the ATS's own JSON API (Greenhouse / Ashby / Lever —
covers most rows) instead of fetching posting pages, because dead postings often
return HTTP 200 with a soft redirect to the full board (e.g. Greenhouse
`?error=true`), which fools page-based checks. Non-API hosts get a plain HTTP
check with dead-marker heuristics and are flagged for manual/LLM review.

Usage:
    python3 scripts/verify_links.py            # human-readable report
    python3 scripts/verify_links.py --json     # JSON to stdout (for the routine)

Statuses:
    LIVE        posting id confirmed present on the ATS board API
    DEAD_ID     board exists, this job id is gone (posting taken down)
    BOARD_GONE  the board slug 404s (company moved ATS or slug was wrong)
    BAD_URL     URL malformed or not a human posting page (e.g. an API endpoint)
    HTTP_LIVE   non-API site: page fetched, mentions the role (best effort)
    HTTP_DEAD   non-API site: 404/410 or explicit dead marker
    UNKNOWN     could not determine (bot-blocked, JS-only) -> manual check

Exit code: number of DEAD/BROKEN rows (0 = all clean), capped at 100.

For DEAD/BROKEN rows on Greenhouse/Ashby/Lever the report lists current AE
postings from the same board (title, location, exact URL from the API) as
replacement candidates. URLs in replacements are copied verbatim from the API
response — safe to paste into latest.csv.
"""
import csv, json, re, sys, os, urllib.request, urllib.error
from urllib.parse import urlparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(REPO, "data", "latest.csv")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)

board_cache = {}
def get_board(kind, org):
    key = (kind, org)
    if key in board_cache:
        return board_cache[key]
    api = {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{org}/jobs",
        "greenhouse_eu": f"https://boards-api.eu.greenhouse.io/v1/boards/{org}/jobs",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true",
        "lever": f"https://api.lever.co/v0/postings/{org}?mode=json",
    }[kind]
    code, body = fetch(api)
    if kind == "greenhouse_eu" and (code != 200 or not body):
        # EU-hosted boards are usually served by the global API too
        code, body = fetch(f"https://boards-api.greenhouse.io/v1/boards/{org}/jobs")
        kind = "greenhouse"
    jobs = None
    if code == 200 and body:
        try:
            data = json.loads(body)
            if kind.startswith("greenhouse"):
                jobs = [{"id": str(j["id"]), "title": j["title"],
                         "loc": (j.get("location") or {}).get("name", ""),
                         "url": j.get("absolute_url", "")} for j in data.get("jobs", [])]
            elif kind == "ashby":
                jobs = [{"id": str(j.get("id", "")), "title": j.get("title", ""),
                         "loc": (j.get("location") or "") + (" (Remote)" if j.get("isRemote") else ""),
                         "url": j.get("jobUrl") or j.get("applyUrl", "")} for j in data.get("jobs", [])]
            elif kind == "lever":
                jobs = [{"id": str(j.get("id", "")), "title": j.get("text", ""),
                         "loc": (j.get("categories") or {}).get("location", "") or "",
                         "url": j.get("hostedUrl", "")} for j in data]
        except Exception:
            jobs = None
    board_cache[key] = (code, jobs)
    return code, jobs

def ae_matches(jobs):
    out = []
    for j in jobs or []:
        t = j["title"].lower()
        if "account executive" not in t:
            continue
        if re.search(r"\b(sdr|bdr|associate|director|vp|manager, )\b", t):
            continue
        out.append(j)
    return out

DEAD_MARKERS = ["no longer available", "no longer accepting", "job not found",
                "position has been filled", "posting is closed",
                "doesn't exist", "job you are looking for"]

def classify(url):
    p = urlparse(url)
    host, path = p.netloc.lower(), p.path
    m = re.match(r"(?:job-)?boards(?:-api)?\.(eu\.)?greenhouse\.io", host)
    if m:
        if "boards-api" in host:
            seg = path.split("/")
            org = seg[3] if len(seg) > 3 else ""
            return "BAD_URL", org, "greenhouse_eu" if m.group(1) else "greenhouse", None
        mm = re.match(r"/([^/]+)/jobs/(\d+)", path)
        if not mm:
            return "BAD_URL", "", "greenhouse", None
        org, jid = mm.group(1), mm.group(2)
        kind = "greenhouse_eu" if m.group(1) else "greenhouse"
        code, jobs = get_board(kind, org)
        if jobs is None:
            return ("BOARD_GONE" if code == 404 else "UNKNOWN"), org, kind, jid
        if not jobs:  # empty board = API likely disabled (e.g. Deel), can't verify
            return "UNKNOWN", org, kind, jid
        return ("LIVE" if any(j["id"] == jid for j in jobs) else "DEAD_ID"), org, kind, jid
    if host == "jobs.ashbyhq.com":
        mm = re.match(r"/([^/]+)/([0-9a-f-]{36})", path)
        if not mm:
            return "BAD_URL", "", "ashby", None
        org, jid = mm.group(1), mm.group(2)
        code, jobs = get_board("ashby", org)
        if jobs is None:
            return ("BOARD_GONE" if code in (404, 400) else "UNKNOWN"), org, "ashby", jid
        if not jobs:
            return "UNKNOWN", org, "ashby", jid
        return ("LIVE" if any(j["id"] == jid for j in jobs) else "DEAD_ID"), org, "ashby", jid
    if host == "jobs.lever.co":
        mm = re.match(r"/([^/]+)/([0-9a-f-]{36})", path)
        if not mm:
            return "BAD_URL", "", "lever", None
        org, jid = mm.group(1), mm.group(2)
        code, jobs = get_board("lever", org)
        if jobs is None:
            return ("BOARD_GONE" if code == 404 else "UNKNOWN"), org, "lever", jid
        if not jobs:
            return "UNKNOWN", org, "lever", jid
        return ("LIVE" if any(j["id"] == jid for j in jobs) else "DEAD_ID"), org, "lever", jid
    code, body = fetch(url)
    if code is None:
        return "UNKNOWN", "", "http", None
    if code in (404, 410):
        return "HTTP_DEAD", "", "http", None
    if code != 200:
        return "UNKNOWN", "", "http", None
    low = body.lower()
    if any(mk in low for mk in DEAD_MARKERS) and "account executive" not in low:
        return "HTTP_DEAD", "", "http", None
    return ("HTTP_LIVE" if "account executive" in low else "UNKNOWN"), "", "http", None

def main():
    as_json = "--json" in sys.argv
    rows = list(csv.DictReader(open(CSV_PATH)))
    report = []
    for i, r in enumerate(rows):
        url = r["Job Posting URL"].strip()
        status, org, kind, jid = classify(url)
        entry = {"company": r["Company"], "segment": r["Segment"], "url": url,
                 "status": status, "ats": kind, "org": org}
        if status in ("DEAD_ID", "BOARD_GONE", "BAD_URL"):
            _, jobs = board_cache.get((kind, org), (None, None))
            entry["replacements"] = ae_matches(jobs)[:5] if jobs else []
        report.append(entry)
        if not as_json:
            print(f"[{i+1}/{len(rows)}] {status:10s} {r['Company']}", flush=True)

    broken = [e for e in report if e["status"] in ("DEAD_ID", "BOARD_GONE", "BAD_URL", "HTTP_DEAD")]
    unknown = [e for e in report if e["status"] == "UNKNOWN"]
    if as_json:
        json.dump({"rows": report, "broken": len(broken), "unknown": len(unknown)},
                  sys.stdout, indent=1)
    else:
        print(f"\n=== {len(broken)} broken, {len(unknown)} unknown (manual check), "
              f"{len(report) - len(broken) - len(unknown)} live ===")
        for e in broken:
            print(f"\n{e['status']}  {e['company']}  ({e['segment']})\n  was: {e['url']}")
            for rp in e.get("replacements", []):
                print(f"  candidate: {rp['title']} | {rp['loc']} | {rp['url']}")
        if unknown:
            print("\nUNKNOWN (verify manually / via LLM):")
            for e in unknown:
                print(f"  {e['company']}: {e['url']}")
    sys.exit(min(len(broken), 100))

if __name__ == "__main__":
    main()
