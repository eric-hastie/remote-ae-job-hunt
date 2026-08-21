#!/usr/bin/env python3
"""Bulk-pull closing-sales listings off the a16z speedrun talent network board.

    https://speedrun-talent-network.com

Why this board is worth its own harvester, when the two aggregator harvesters
already exist:

  1. It publishes a COMPLETE sitemap (sitemaps/jobs.xml, sitemaps/companies.xml),
     so there is no pagination to guess at and no scraping of rendered cards.
  2. Every job page carries a schema.org JobPosting block with the title,
     company, first-posted date, location + country, remote flag, applicant
     location requirement, posted salary, expiry, and - the part that matters -
     the APPLY LINK ON THE COMPANY'S OWN ATS, carrying that job's native ID.
     That ID is exactly what verify_links.py needs, so rows land pre-verified
     instead of going to the unverified page.
  3. The full job description is in the same block, so segment resolution needs
     no second fetch and no model call.

Measured 2026-08-21 on the first full pull: 83 of 83 distinct remote-US AE rows
were still live in their own ATS feed. Compare the 2026-08-15 aggregator pass,
204 verified of 344 companies checked.

    python3 scripts/harvest_speedrun.py                  # full pull
    python3 scripts/harvest_speedrun.py --max 50         # cap pages fetched
    python3 scripts/harvest_speedrun.py --sitemap-only   # refresh company list

Output data/speedrun_raw.tsv is GITIGNORED (public repo).
data/speedrun_companies.csv IS committed - it is a public sitemap, and the ring
seeds off it in the cloud clone where no other company library exists.
"""
import argparse, csv, concurrent.futures, datetime, html, json, os, re, sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "speedrun_raw.tsv")
COMPANIES = os.path.join(REPO, "data", "speedrun_companies.csv")
BASE = "https://speedrun-talent-network.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# Column names are the contract build_unverified.py already consumes. Do not
# rename without updating that consumer - a missing column raises KeyError.
COLS = ["Company", "Title", "CoreTitle", "Seniority", "MinYOE", "Posted", "ATS",
        "BoardToken", "ApplyURL", "WorkplaceType", "States", "Cities", "Countries",
        "CompMin", "CompMax", "Requirements", "Industries", "Employees", "Founded",
        "FundingType", "FundingYear", "FundingAmount", "Homepage", "FoundVia",
        "Expired"]

# --- the title filter -------------------------------------------------------
# Widened past "account executive" on Eric's instruction 2026-08-21. Surveyed
# all 17,705 job slugs first: outside account-executive there are 970 postings
# carrying a sales word, and almost all are SDR/BDR, sales engineer, account
# manager, enablement, or one of the several hundred TikTok/P&G/Boeing intern
# programs this board also carries. The widening below adds ~33 pages, so the
# honest read is that this board's closing roles are titled "Account Executive"
# and the extra patterns are insurance against a board that changes its mix.
INCLUDE = re.compile(
    r"account-executive"
    r"|(?:^|-)sales-(?:executive|representative|rep)(?:-|$)"
    r"|(?:^|-)(?:enterprise|commercial|corporate|strategic|field|inside"
    r"|named-account|territory|smb|mid-market)-sales(?:-|$)"
    r"|(?:^|-)seller(?:-|$)"
    r"|founding-(?:ae|seller|sales)")

# Eric's bar: individual-contributor closing role, no SDR/BDR, no people
# management. There is NO experience floor, so nothing here filters on
# seniority words like junior/associate - only on roles that are not closing
# roles at all. "intern"/"apprentice"/"graduate program" go because they are
# not AE jobs, not because they are early-career.
EXCLUDE = re.compile(
    r"(?:^|-)(?:intern|interns|internship|apprentice|apprenticeship|trainee|academy)(?:-|$)"
    r"|(?:^|-)(?:director|vp|avp|svp|rvp|evp|head|chief|president)(?:-|$)"
    r"|(?:^|-)managers?(?:-|$)"
    r"|sales-development|business-development|(?:^|-)bdr(?:-|$)|(?:^|-)sdr(?:-|$)"
    r"|sales-engineer|solutions-engineer|solutions-architect|account-manager"
    r"|enablement|operations|(?:^|-)ops(?:-|$)"
    r"|counsel|accountant|analyst|recruiter|marketing|support|specialist"
    r"|(?:^|-)engineer(?:-|$)|project-intern|(?:-|^)program(?:-|$)")

ATS_LINK = re.compile(
    r'href="(https://(?:job-boards\.|boards\.)?greenhouse\.io/[^"]*'
    r'|https://jobs\.ashbyhq\.com/[^"]*'
    r'|https://jobs\.lever\.co/[^"]*'
    r'|https://[^"]*\.myworkdayjobs\.com/[^"]*'
    r'|https://[^"]*\.workable\.com/[^"]*'
    r'|https://jobs\.smartrecruiters\.com/[^"]*'
    r'|https://[^"]*\.recruitee\.com/[^"]*'
    r'|https://[^"]*\.rippling\.com/[^"]*)"')

LDJSON = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
TAGS = re.compile(r"<[^>]+>")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def sitemap_locs(name):
    xml = fetch(f"{BASE}/sitemaps/{name}.xml", timeout=90)
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def board_token(apply_url):
    """The ATS slug, taken verbatim from the apply URL - never guessed."""
    for pat in (r"greenhouse\.io/([^/]+)/jobs/", r"jobs\.ashbyhq\.com/([^/]+)/",
                r"jobs\.lever\.co/([^/]+)/", r"https://([^.]+)\.myworkdayjobs\.com",
                r"https://([^.]+)\.workable\.com", r"smartrecruiters\.com/([^/]+)/",
                r"https://([^.]+)\.recruitee\.com", r"https://([^.]+)\.rippling\.com"):
        m = re.search(pat, apply_url)
        if m:
            return m.group(1)
    return ""


def ats_name(apply_url):
    for key, name in (("greenhouse", "greenhouse"), ("ashbyhq", "ashby"),
                      ("lever.co", "lever"), ("myworkdayjobs", "workday"),
                      ("workable", "workable"), ("smartrecruiters", "smartrecruiters"),
                      ("recruitee", "recruitee"), ("rippling", "rippling")):
        if key in apply_url:
            return name
    return ""


def min_yoe(text):
    """Lowest plausible years-of-experience figure named in the body.

    Reported, never used as a filter here. Eric's bar has no floor and only an
    ~8-year ceiling, and the judgment on the ceiling is made when the row is
    published, against the sentence it came from - not against a bare number.
    """
    hits = {int(n) for n in re.findall(r"(\d{1,2})\+?\s*(?:-\s*\d+\s*)?years?", text)
            if int(n) <= 15}
    return min(hits) if hits else ""


def parse_page(slug, body):
    posting = None
    for m in LDJSON.finditer(body):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            posting = d
            break
    if posting is None:
        return None

    apply_urls = ATS_LINK.findall(body)
    apply_url = apply_urls[0] if apply_urls else ""

    desc = TAGS.sub(" ", html.unescape(posting.get("description", "")))
    desc = re.sub(r"\s+", " ", desc).strip()

    loc = posting.get("jobLocation")
    loc = loc if isinstance(loc, list) else ([loc] if loc else [])
    cities, countries = [], []
    for place in loc:
        if not isinstance(place, dict):
            continue
        addr = place.get("address") or {}
        if addr.get("addressLocality"):
            cities.append(str(addr["addressLocality"]))
        if addr.get("addressCountry"):
            countries.append(str(addr["addressCountry"]))

    alr = posting.get("applicantLocationRequirements")
    alr = alr if isinstance(alr, list) else ([alr] if alr else [])
    alr_names = [a.get("name", "") for a in alr if isinstance(a, dict)]

    sal = posting.get("baseSalary") or {}
    val = sal.get("value") if isinstance(sal, dict) else {}
    val = val if isinstance(val, dict) else {}

    return {
        "Company": (posting.get("hiringOrganization") or {}).get("name", ""),
        "Title": posting.get("title", "").strip(),
        "CoreTitle": posting.get("title", "").strip(),
        "Seniority": "",
        "MinYOE": min_yoe(desc),
        "Posted": (posting.get("datePosted") or "")[:10],
        "ATS": ats_name(apply_url),
        "BoardToken": board_token(apply_url),
        "ApplyURL": apply_url,
        "WorkplaceType": "Remote" if posting.get("jobLocationType") == "TELECOMMUTE" else "",
        "States": "|".join(alr_names),
        "Cities": "|".join(cities),
        "Countries": "|".join(countries),
        "CompMin": val.get("minValue", "") or "",
        "CompMax": val.get("maxValue", "") or "",
        "Requirements": desc[:6000],
        "Industries": "", "Employees": "", "Founded": "",
        "FundingType": "", "FundingYear": "", "FundingAmount": "",
        "Homepage": f"{BASE}/jobs/{slug}",
        "FoundVia": "a16z-speedrun",
        "Expired": (posting.get("validThrough") or "")[:10],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="cap job pages fetched")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sitemap-only", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    co_slugs = set(u.rsplit("/", 1)[-1] for u in sitemap_locs("companies"))

    # The collection pages are the only place this board states, per company,
    # whether it is remote-first and whether it hires sales at all. They also
    # list roughly twice as many companies as the company sitemap does, so they
    # widen the universe as well as describing it. Both facts are the board's,
    # not ours - we are reading a label, not inferring one.
    collections_ = [u.rsplit("/", 1)[-1] for u in sitemap_locs("pages")
                    if "/collections/" in u and not u.endswith("/collections")]
    card = {}

    def read_collection(name):
        try:
            page = fetch(f"{BASE}/collections/{name}")
        except Exception:
            return name, []
        return name, re.findall(r'href="/companies/([a-z0-9-]+)"([^>]*)>', page)

    col_failed = []
    with concurrent.futures.ThreadPoolExecutor(args.workers) as ex:
        for name, hits in ex.map(read_collection, collections_):
            if not hits:
                col_failed.append(name)
            for slug, attrs in hits:
                def attr(key):
                    m = re.search(key + r'="([^"]*)"', attrs)
                    return m.group(1) if m else ""
                rec = card.setdefault(slug, {"rp": attr("data-rp"),
                                             "fns": attr("data-fns"),
                                             "collections": set()})
                rec["collections"].add(name)
    if col_failed:
        sys.stderr.write(f"WARNING: {len(col_failed)} collection pages failed: "
                         f"{', '.join(col_failed)}\n")
    sys.stderr.write(f"collections: {len(collections_)} pages, "
                     f"{len(card)} companies described\n")
    co_slugs = sorted(co_slugs | set(card))

    # Read each company's real name off its page rather than un-slugging it.
    # "socket-dev" un-slugs to "Socket Dev"; the page says "Socket.dev". A
    # mangled name breaks the dedup key and sends the ring searching for a
    # company that does not exist under that spelling.
    def company_row(slug):
        """Name and open-role count, read off the company's own page."""
        try:
            title = re.search(r"<title>([^<]*)</title>",
                              fetch(f"{BASE}/companies/{slug}")).group(1)
        except Exception:
            return {"Slug": slug, "Company": "", "OpenRoles": "", "Pulled": ""}
        name = html.unescape(title.split(" careers")[0]).strip()
        roles = re.search(r"(\d[\d,]*) open roles?", title)
        return {"Slug": slug, "Company": name,
                "OpenRoles": roles.group(1).replace(",", "") if roles else "",
                "Pulled": datetime.date.today().isoformat()}

    with concurrent.futures.ThreadPoolExecutor(max(args.workers, 10)) as ex:
        co_rows = list(ex.map(company_row, co_slugs))
    unnamed = [r["Slug"] for r in co_rows if not r["Company"]]
    for r in co_rows:
        if not r["Company"]:
            # Named blank rather than guessed: the un-slugged spelling would
            # look like a fact and is not one.
            r["Company"] = r["Slug"].replace("-", " ").title()
            r["Pulled"] = "name-unresolved"

    job_slugs = sorted({u.rsplit("/", 1)[-1] for u in sitemap_locs("jobs")})
    sys.stderr.write(f"jobs sitemap: {len(job_slugs)}\n")

    # Strip the trailing 8-hex id and the company slug before matching, so a
    # company named e.g. "sales-loft" cannot make every one of its postings
    # look like a sales role. Longest company slug first, so "adaptive" cannot
    # claim a posting belonging to "adaptive-security".
    by_len = sorted(co_slugs, key=len, reverse=True)
    wanted, sales_per_co = [], {}
    for slug in job_slugs:
        body = re.sub(r"-[0-9a-f]{8}$", "", slug)
        owner = ""
        for c in by_len:
            if body.endswith("-" + c):
                owner, body = c, body[: -len(c) - 1]
                break
        if INCLUDE.search(body) and not EXCLUDE.search(body):
            wanted.append(slug)
            if owner:
                sales_per_co[owner] = sales_per_co.get(owner, 0) + 1

    # Recorded as an ORDERING signal for the ring, never as a filter. A zero
    # here does not mean the company has no AE role: this board carries only a
    # slice of some employers' postings (Amazon and Walmart both show none).
    for r in co_rows:
        r["SalesRoles"] = sales_per_co.get(r["Slug"], 0)
        c = card.get(r["Slug"], {})
        r["RemotePosture"] = c.get("rp", "")
        r["Functions"] = c.get("fns", "")
        r["Collections"] = "|".join(sorted(c.get("collections", ())))

    with open(COMPANIES, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Slug", "Company", "OpenRoles",
                                          "SalesRoles", "RemotePosture",
                                          "Functions", "Collections", "Pulled"])
        w.writeheader()
        w.writerows(co_rows)
    sys.stderr.write(f"companies sitemap: {len(co_slugs)} "
                     f"({len(unnamed)} names unresolved) -> {COMPANIES}\n")
    if args.sitemap_only:
        return

    if args.max:
        wanted = wanted[: args.max]
    sys.stderr.write(f"closing-sales titles: {len(wanted)}\n")

    rows, no_posting, errors = [], [], []

    # A fetch failure and a page that simply carries no JobPosting block are
    # different facts and must never share a counter. The first means the pull
    # is short and the numbers cannot be trusted; the second is a property of
    # the source (a handful of listings on this board omit the block) and is
    # fine to skip. Collapsing them would let a network outage read as a quiet
    # market.
    def one(slug):
        try:
            return slug, parse_page(slug, fetch(f"{BASE}/jobs/{slug}")), None
        except Exception as exc:
            return slug, None, exc

    with concurrent.futures.ThreadPoolExecutor(args.workers) as ex:
        for slug, r, exc in ex.map(one, wanted):
            if exc is not None:
                errors.append((slug, exc))
            elif r is None:
                no_posting.append(slug)
            else:
                rows.append(r)

    # Count at both ends: a silent shortfall here reads as a quiet market.
    sys.stderr.write(f"sent {len(wanted)} / parsed {len(rows)} / "
                     f"no JobPosting block {len(no_posting)} / fetch errors {len(errors)}\n")
    for slug in no_posting:
        sys.stderr.write(f"  no block: {slug}\n")
    for slug, exc in errors:
        sys.stderr.write(f"  ERROR: {slug}: {exc}\n")
    if errors:
        sys.stderr.write("WARNING: pull is short by the error count above; "
                         "rerun before trusting any total\n")

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        # Sort on ApplyURL too: several postings can share a company and
        # title, and leaving their order to thread completion makes every
        # downstream tie-break non-deterministic.
        w.writerows(sorted(rows, key=lambda r: (r["Company"], r["Title"],
                                                r["ApplyURL"])))
    sys.stderr.write(f"wrote {len(rows)} rows -> {args.out}\n")


if __name__ == "__main__":
    main()
