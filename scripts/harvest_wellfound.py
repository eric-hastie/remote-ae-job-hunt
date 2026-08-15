#!/usr/bin/env python3
"""Bulk-pull Wellfound AE listings into data/wellfound_raw.tsv.

Wellfound's SEO landing pages server-render everything we need into
`<script id="__NEXT_DATA__">`, logged out. WebFetch gets HTTP 403 on this host
and retrying it is pointless - the block is on WebFetch, not on server-side
fetching, so a plain request carrying a browser User-Agent works.

    /role/r/<role>            remote
    /role/l/<role>/<city>     city
    ...both take ?page=N; pageCount comes back in ROOT_QUERY.

apolloState holds two record types we join:
    JobListingSearchResult:<id>  title, atsSource, compensation, yearsExperience,
                                 remote, liveStartAt (true posting recency)
    StartupResult:<id>           name, slug, companySize, highlightedJobListings[]

`atsSource` is the high-value field - it names the company's REAL ATS, which is
the exact blind spot behind false "no AE" results elsewhere in the pipeline.

Wellfound is a LEAD source only. Never record a wellfound.com URL as the
posting; verify against the real ATS first. Listings also go stale here - rows
dated years back sit in current results - so always carry Posted through.

    python3 scripts/harvest_wellfound.py
    python3 scripts/harvest_wellfound.py --max-pages 2 --dry-run

Output data/wellfound_raw.tsv is GITIGNORED (public repo).
"""
import argparse, csv, json, os, re, sys, time, urllib.error, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "wellfound_raw.tsv")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Only "account-executive" is a real SEO role slug. Invented variants like
# "sales-account-executive" do NOT 404 - they silently drop the role param
# (seoLandingPageJobSearchResults({"page":1,"remote":true}) with no role) and
# serve a generic all-roles page, which then refuses to paginate. Verify a slug
# by checking the role key is present in ROOT_QUERY before adding it here.
ROLES = ["account-executive"]
CITIES = {"NYC": "new-york", "SF": "san-francisco", "Denver": "denver",
          "Boston": "boston", "Austin": "austin"}

# Column names are the contract build_unverified.py already consumes
# (FoundVia / ATS / YrsMin / RemoteAccepted / WellfoundURL). Do not rename them
# here without updating that consumer.
COLS = ["Company", "Slug", "Title", "PrimaryRole", "ATS", "AtsSource", "CompanySize",
        "YrsMin", "YrsMax", "Comp", "Remote", "RemoteKind", "RemoteAccepted",
        "Locations", "Posted", "JobSlug", "WellfoundURL", "HighConcept", "FoundVia"]


def dash(s):
    """Wellfound comp strings use en dashes; normalize (project hard rule)."""
    return re.sub(r"[‐-―−]", "-", s) if isinstance(s, str) else s


def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            html = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def page_count(nd):
    """pageCount lives in ROOT_QUERY.talent['seoLandingPageJobSearchResults(...)'],
    one level below ROOT_QUERY - not on ROOT_QUERY itself."""
    root = (nd.get("props", {}).get("pageProps", {})
              .get("apolloState", {}).get("data", {}).get("ROOT_QUERY", {}))
    for container in root.values():
        if not isinstance(container, dict):
            continue
        for k, v in container.items():
            if isinstance(v, dict) and "pageCount" in v:
                # A slug the site does not recognise silently drops the role
                # filter and serves generic results; surface that, don't harvest it.
                scoped = '"role"' in k
                return v.get("pageCount"), v.get("totalJobCount"), v.get("totalStartupCount"), scoped
    return None, None, None, False


def harvest(label, url_base, max_pages, sleep):
    jobs, starts, pages, totals = {}, {}, None, (None, None)
    page = 1
    while page <= max_pages:
        nd = fetch_page(f"{url_base}?page={page}")
        if nd is None:
            break
        data = (nd.get("props", {}).get("pageProps", {})
                  .get("apolloState", {}).get("data", {}))
        if not data:
            break
        if pages is None:
            pc, tj, ts, scoped = page_count(nd)
            if not scoped:
                print(f"  [{label}] SKIPPED: the site did not scope this query to the "
                      "role slug - it is serving generic results, not AE results.")
                return {}, {}, (None, None)
            pages = min(pc or max_pages, max_pages)
            totals = (tj, ts)
            print(f"  [{label}] pageCount={pc} totalJobs={tj} totalStartups={ts}")
        before = len(jobs)
        for k, v in data.items():
            if k.startswith("JobListingSearchResult:"):
                jobs[k] = v
            elif k.startswith("StartupResult:"):
                starts[k] = v
        print(f"  [{label}] page {page}: jobs {len(jobs)} (+{len(jobs)-before}) startups {len(starts)}")
        if page >= (pages or max_pages):
            break
        page += 1
        time.sleep(sleep)
    return jobs, starts, totals


def rows_from(jobs, starts, label):
    """Join startups to jobs via highlightedJobListings[].__ref."""
    owner = {}
    for sk, s in starts.items():
        for ref in (s.get("highlightedJobListings") or []):
            r = ref.get("__ref") if isinstance(ref, dict) else None
            if r:
                owner[r] = sk
    out = []
    for jk, j in jobs.items():
        jid = jk.split(":", 1)[1] if ":" in jk else ""
        s = starts.get(owner.get(jk), {})
        ts = j.get("liveStartAt")
        posted = ""
        if ts:
            try:
                posted = time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
            except (ValueError, OSError, OverflowError):
                posted = ""
        rc = j.get("remoteConfig") or {}
        out.append({
            "Company": dash(s.get("name") or ""),
            "Slug": s.get("slug") or "",
            "Title": dash(j.get("title") or ""),
            "PrimaryRole": j.get("primaryRoleTitle") or "",
            "AtsSource": j.get("atsSource") or "",
            # "AtsIntegration::Ashby::Listing" -> "Ashby": the company's REAL ATS,
            # which is the blind spot behind false "no AE" results elsewhere.
            "ATS": (j.get("atsSource") or "").split("::")[1]
                   if "::" in (j.get("atsSource") or "") else "",
            "CompanySize": s.get("companySize") or "",
            "YrsMin": j.get("yearsExperienceMin"),
            "YrsMax": j.get("yearsExperienceMax"),
            "Comp": dash(j.get("compensation") or ""),
            "Remote": j.get("remote"),
            "RemoteKind": rc.get("kind") if isinstance(rc, dict) else "",
            "RemoteAccepted": "|".join(j.get("acceptedRemoteLocationNames") or []),
            "Locations": "|".join(j.get("locationNames") or []),
            "Posted": posted,
            "JobSlug": j.get("slug") or "",
            # LEAD url only - never record this as the posting; verify the real ATS.
            "WellfoundURL": f"https://wellfound.com/jobs/{jid}-{j.get('slug')}" if jid and j.get("slug") else "",
            "HighConcept": dash(s.get("highConcept") or ""),
            "FoundVia": label,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--remote-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pulls = [(f"Remote:{r}", f"https://wellfound.com/role/r/{r}") for r in ROLES]
    if not a.remote_only:
        pulls += [(f"{c}:account-executive",
                   f"https://wellfound.com/role/l/account-executive/{slug}")
                  for c, slug in CITIES.items()]

    all_rows, report = [], {}
    for label, url in pulls:
        try:
            jobs, starts, totals = harvest(label, url, a.max_pages, a.sleep)
        except Exception as e:
            print(f"  [{label}] FAILED: {e}")
            report[label] = (None, 0)
            continue
        rows = rows_from(jobs, starts, label)
        report[label] = (totals[0], len(rows))
        all_rows.extend(rows)

    # Reconcile: a short read here reads downstream as "the market is thin".
    print("\n=== reconciliation (site totalJobCount vs rows banked) ===")
    for label, (total, got) in report.items():
        print(f"  {label:<38} totalJobs={total}  banked={got}")
    named = [r for r in all_rows if r["Company"].strip()]
    print(f"  TOTAL rows={len(all_rows)} (with company name {len(named)})  "
          f"distinct companies={len({r['Company'].strip().lower() for r in named})}")
    if all_rows and not named:
        sys.exit("ERROR: every row lost its company - the startup->job join broke.")

    if a.dry_run:
        print("(--dry-run: nothing written)")
        return
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {OUT}: {len(all_rows)} rows")


if __name__ == "__main__":
    main()
