#!/usr/bin/env python3
"""Bulk-pull HiringCafe AE listings into data/hiringcafe_raw.tsv.

HiringCafe is a Next.js pages-router app. Everything we need is in the
server-rendered payload, so this fetches server-side with a browser UA - no
Chrome, no clipboard transport. Loop:

    GET /_next/data/{buildId}/index.json?searchState={json}&page={N}

buildId rotates on every deploy, so it is re-read from the homepage each run,
never hardcoded. Pagination is the &page= QUERY PARAM - putting `page` inside
searchState silently returns page 0 forever, so ssrPage is asserted each fetch.

The bar (see the project spec): Individual Contributor / Sales / Full Time /
industries=Software / roleYoeRange=[0,8].

  - NO compensation filter. HiringCafe's yearly_min/max_compensation is BASE
    salary, not OTE, and AE base is ~half of OTE, so any comp threshold
    compares two different quantities and silently drops good roles.
  - NO experience floor. Only the 8-year ceiling. Associate/entry AE qualify.
  - NO companyKeywords. ["B2B","SaaS"] with AND is a 94% over-filter: it matches
    literal company-description prose. Measured 2026-08-15: 2,297 jobs without
    it, 148 with. industries=["Software"] is the B2B SaaS proxy instead.

Remote pulls use workplace_types=["Remote"]; city pulls leave it empty so the
city pages keep onsite/hybrid roles, matching the city-pages spec.

    python3 scripts/harvest_hiringcafe.py              # remote + all cities
    python3 scripts/harvest_hiringcafe.py --remote-only
    python3 scripts/harvest_hiringcafe.py --max-pages 3 --dry-run

Output data/hiringcafe_raw.tsv is GITIGNORED (public repo).
"""
import argparse, csv, json, os, re, sys, time, urllib.parse, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "hiringcafe_raw.tsv")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Location objects are minted by /api/ai-search/parse-filters and stored VERBATIM
# in hiringcafe_locations.json. Do not hand-build them: each carries an
# Elasticsearch `id` and an address_components block whose short_name must be the
# code ("US", "NY"), not the long name. Reconstructing one by hand returns
# total=0 - a silent empty result, not an error. Re-mint with --remint.
LOCATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "hiringcafe_locations.json")
MINT_QUERIES = {
    "Remote": "account executive software sales remote in the United States",
    "NYC": "account executive software sales in New York City",
    "SF": "account executive software sales in San Francisco",
    "Denver": "account executive software sales in Denver Colorado",
    "Boston": "account executive software sales in Boston Massachusetts",
    "Austin": "account executive software sales in Austin Texas",
}


def load_locations():
    if not os.path.exists(LOCATIONS):
        sys.exit(f"ERROR: {LOCATIONS} missing - re-mint with --remint.")
    return json.load(open(LOCATIONS))


def remint():
    """Re-ask the site's filter parser for each location object and pin it."""
    out = {}
    for label, q in MINT_QUERIES.items():
        url = "https://hiringcafe.com/api/ai-search/parse-filters?query=" + urllib.parse.quote(q)
        locs = (get_json(url).get("suggestedFilters") or {}).get("locations")
        if not locs:
            print(f"  {label}: parser returned no locations - keeping any existing pin")
            continue
        loc = locs[0]
        # Remote pins workplace_types; city pulls leave it empty on purpose so
        # onsite/hybrid roles survive for the city pages.
        loc["workplace_types"] = ["Remote"] if label == "Remote" else []
        out[label] = loc
        print(f"  {label}: {loc.get('formatted_address')} id={loc.get('id')}")
        time.sleep(0.4)
    if out:
        json.dump(out, open(LOCATIONS, "w"), indent=1)
        print(f"wrote {LOCATIONS}")


def search_state(loc):
    return {
        "searchQuery": "Account Executive",
        "departments": ["Sales"],
        "roleTypes": ["Individual Contributor"],
        "commitmentTypes": ["Full Time"],
        "locations": [loc],
        "roleYoeRange": [0, 8],
        "industries": ["Software"],
    }


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def build_id():
    """Re-read every run - it rotates on every deploy."""
    req = urllib.request.Request("https://hiringcafe.com/", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        sys.exit("ERROR: no __NEXT_DATA__ on hiringcafe.com - page shape changed.")
    bid = json.loads(m.group(1)).get("buildId")
    if not bid:
        sys.exit("ERROR: __NEXT_DATA__ present but buildId missing.")
    return bid


def dash(s):
    """Normalize en/em dashes to hyphens on the way out (project hard rule)."""
    return re.sub(r"[‐-―−]", "-", s) if isinstance(s, str) else s


# Column names are the contract build_unverified.py already consumes
# (FoundVia / ATS / Countries / Requirements). Do not rename them here without
# updating that consumer - a missing column raises KeyError mid-build.
COLS = ["Company", "Title", "CoreTitle", "Seniority", "MinYOE", "Posted", "ATS",
        "BoardToken", "ApplyURL", "WorkplaceType", "States", "Cities", "Countries",
        "CompMin", "CompMax", "Requirements", "Industries", "Employees", "Founded",
        "FundingType", "FundingYear", "FundingAmount", "Homepage", "FoundVia",
        "Expired"]


def row_of(hit, pull):
    v = hit.get("v5_processed_job_data") or {}
    c = hit.get("enriched_company_data") or {}
    ms = v.get("estimated_publish_date_millis")
    posted = ""
    if ms:
        try:
            posted = time.strftime("%Y-%m-%d", time.gmtime(int(ms) / 1000))
        except (ValueError, OSError, OverflowError):
            posted = ""
    return {
        "Company": dash(c.get("name") or hit.get("company_name") or ""),
        "Title": dash(hit.get("job_title") or v.get("core_job_title") or ""),
        "CoreTitle": dash(v.get("core_job_title") or ""),
        "Seniority": v.get("seniority_level") or "",
        "MinYOE": v.get("min_industry_and_role_yoe"),
        "Posted": posted,
        "ATS": hit.get("source") or "",
        "BoardToken": hit.get("board_token") or "",
        "ApplyURL": hit.get("apply_url") or "",
        "WorkplaceType": v.get("workplace_type") or "",
        "States": "|".join(v.get("workplace_states") or []),
        "Cities": "|".join(v.get("workplace_cities") or []),
        "Countries": "|".join(v.get("workplace_countries") or []),
        "CompMin": v.get("yearly_min_compensation"),
        "CompMax": v.get("yearly_max_compensation"),
        "Requirements": dash(v.get("requirements_summary") or ""),
        "Industries": "|".join(c.get("industries") or []),
        "Employees": c.get("nb_employees"),
        "Founded": c.get("year_founded"),
        "FundingType": c.get("latest_funding_type") or "",
        "FundingYear": c.get("latest_funding_year"),
        "FundingAmount": c.get("latest_funding_amount"),
        "Homepage": c.get("homepage_uri") or "",
        "FoundVia": pull,
        "Expired": hit.get("is_expired"),
    }


def harvest(label, loc, bid, max_pages, sleep):
    state = search_state(loc)
    rows, page, total, seen = [], 0, None, set()
    hits_seen, ended = 0, "page-cap"
    while page < max_pages:
        url = (f"https://hiringcafe.com/_next/data/{bid}/index.json"
               f"?searchState={urllib.parse.quote(json.dumps(state))}&page={page}")
        try:
            pp = get_json(url)["pageProps"]
        except Exception as e:
            print(f"  [{label}] page {page} failed: {e} - stopping this pull")
            ended = "ERROR"
            break
        if total is None:
            total = pp.get("ssrTotalCount")
            print(f"  [{label}] total={total} companies={pp.get('ssrCompanyCount')}")
        # The page param is the ONLY thing that advances results; verify it did.
        if pp.get("ssrPage") not in (page, None):
            print(f"  [{label}] ssrPage={pp.get('ssrPage')} != {page} - pagination "
                  "broke, stopping rather than looping on page 0")
            ended = "PAGINATION-BROKE"
            break
        hits = pp.get("ssrHits") or []
        if not hits:
            ended = "empty-page"
            break
        hits_seen += len(hits)
        for h in hits:
            key = h.get("id") or h.get("apply_url")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            rows.append(row_of(h, label))
        print(f"  [{label}] page {page}: +{len(hits)} hits (rows {len(rows)})")
        if pp.get("ssrIsLastPage"):
            ended = "last-page"
            break
        page += 1
        time.sleep(sleep)
    return rows, total, hits_seen, ended


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote-only", action="store_true")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remint", action="store_true",
                    help="re-ask the filter parser for the location objects, then exit")
    a = ap.parse_args()

    if a.remint:
        remint()
        return

    locs = load_locations()
    bid = build_id()
    print(f"buildId {bid}")
    labels = ["Remote"] if a.remote_only else [k for k in MINT_QUERIES if k in locs]

    all_rows, expected = [], {}
    for label in labels:
        rows, total, hits_seen, ended = harvest(label, locs[label], bid, a.max_pages, a.sleep)
        expected[label] = (total, len(rows), hits_seen, ended)
        all_rows.extend(rows)

    # Reconcile. ssrTotalCount counts individual JOBS while ssrHits returns
    # grouped job CARDS, so banked-vs-total is not a like-for-like comparison
    # and flagging it would cry wolf. The checks that mean something: did the
    # loop actually reach the last page, and were hits lost on the way in?
    print("\n=== reconciliation ===")
    incomplete = []
    for label, (total, got, hits_seen, ended) in expected.items():
        dropped = hits_seen - got
        flag = "" if ended == "last-page" else f"  <-- INCOMPLETE ({ended})"
        if ended != "last-page":
            incomplete.append(label)
        print(f"  {label:<8} api_jobs={total:<6} cards={hits_seen:<6} banked={got:<6} "
              f"dup_dropped={dropped:<5} ended={ended}{flag}")
    if incomplete:
        print(f"  WARNING: {', '.join(incomplete)} did not exhaust - "
              "treat these as partial, not as a thin market.")
    companies = len({r["Company"].strip().lower() for r in all_rows if r["Company"].strip()})
    print(f"  TOTAL rows={len(all_rows)}  distinct companies={companies}")

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
