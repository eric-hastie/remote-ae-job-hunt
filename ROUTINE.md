# Routine: Remote AE Market Map — operating spec

**This file is the source of truth for what the scheduled refresh does.** The cloud routine's job is:
*read this file, execute it exactly, then commit & push.* Change behavior by editing THIS FILE.

**Cadence (since 2026-07-02): runs every ~5 hours, 50 queue companies per run.** Be efficient — one
run's discovery work is bounded by the 50-company cap, not by verticals or loop-until-dry.

## Files

- **`data/latest.csv`** — canonical PUBLISHED list = companies that *currently* have a qualifying open
  role. Columns: `Company,Funding ($M),OTE,Segment,HQ,Remote,RepVue,Industry,Job Posting URL,Date Added`.
  **`Date Added` rules:** every NEW row gets today's UTC date (`YYYY-MM-DD`); never change an existing
  row's date (a Job-1 URL fix keeps the original date); a company dropped and later re-added gets the
  re-add date. build.py sorts the site newest-first by this column.
  **`Posted` rules:** the posting's own publish date (`YYYY-MM-DD`), taken from the SAME API response
  used to verify it — Greenhouse `first_published` (needs `?content=true`), Ashby `publishedAt`,
  Lever `createdAt` (epoch ms → UTC date). Blank if the ATS doesn't expose it (Workday/custom sites)
  — never guess. Unlike Date Added, a Job-1 URL fix DOES update `Posted` (it's a different posting).
- **`data/claude_universe.csv`** — the MEMORY: *every company ever evaluated*, win or not. Columns:
  `Company,Source,RepVue Score,Last Checked,Currently Open,Notes`. This is the dedup set so we never
  re-discover a company we've already considered. **It must grow every run** (see Job 2, step 4).
- **`data/scan_queue.csv`** — the DISCOVERY QUEUE: RepVue companies with score ≥ 80, best-score-first,
  minus everything already in `claude_universe.csv` at build time (2026-07-02: 1,003 companies).
  Columns: `Company,Slug` (Slug = starting guess for the ATS board token). The queue file itself is
  never edited by the routine — progress is tracked by recording checked companies into
  `claude_universe.csv`, so "next up" = first N queue rows not yet in the universe.
- `data/repvue_universe.csv` — gitignored/local-only (RepVue's proprietary data; not in cloud clones).
- `data/YYYY-MM-DD.csv` — dated snapshot of `latest.csv`, refreshed each run.

## Tool & cost rules

- **WebFetch / WebSearch ONLY for web access.** NEVER curl/wget/Bash to fetch URLs.
- Bash is allowed ONLY for git, `python3 build.py`, `python3 scripts/verify_links.py`, `date`, and
  file ops — not for open-ended research.
- **Work inline — do NOT spawn subagents.** Be token-conscious (this draws on a subscription quota):
  don't over-fan-out; stop a vertical as soon as it's dry (see loop rule).

## The bar (ICP — a role qualifies only if it clears ALL)

IC **Account Executive** (NOT SDR/BDR, NOT "Associate AE", NOT Director/VP/RVP) · segment **MM** or
**MM/Ent** preferred (pure **Ent** allowed but tagged so it sorts last) · **US-remote** (not
hybrid/office/non-US) · **OTE ~$150K–$340K** (blank if not reliably known — never guess) · **B2B SaaS** ·
**~4+ yrs** closing (reject 8+ senior-only and junior/BDR).

---

## Job 1 — Re-verify every row in `latest.csv`

**Run `python3 scripts/verify_links.py` FIRST** (Bash is allowed for this script). It deterministically
checks every row's job ID against the ATS's own JSON API (Greenhouse/Ashby/Lever — most rows) and
prints, for each broken row, the current AE postings on the same board with exact URLs copied from the
API. Do NOT re-verify API-covered rows by WebFetching posting pages — a dead Greenhouse posting returns
HTTP 200 and silently redirects to the full board (`?error=true`), so page-reads pass dead links
(this corrupted the list once; see URL-capture rules below).

Then act on the script's output:
- **DEAD/BROKEN with a qualifying replacement candidate** (IC AE, US-remote, right segment — read the
  JD if unsure): update the row's URL, copying the replacement URL **verbatim from the script output**.
- **DEAD/BROKEN with no qualifying candidate**: drop the row from `latest.csv` and set its
  `claude_universe.csv` row to `Currently Open = N` (update `Last Checked`).
- **UNKNOWN rows** (bot-blocked/JS-only sites — Workday, Salesforce, custom career sites): verify these
  the LLM way — WebFetch the careers site/sitemap, cross-check search-indexed copies of the company's
  own board. If liveness can't be established, keep the row but note it; never invent a new URL.

## URL-capture rules (apply to BOTH jobs — these prevent the two failure modes that broke the list)

1. **Copy URLs only from an ATS JSON API response** (`absolute_url` / `jobUrl` / `hostedUrl`) or, for
   non-API sites, the site's own sitemap/board page. NEVER record a URL from WebSearch results or
   aggregators (LinkedIn/Indeed/BuiltIn/etc. carry stale postings that soft-redirect on Greenhouse).
2. **Never retype or reconstruct a job ID.** Lever/Ashby IDs are 36-char UUIDs; retyping them from a
   fetched page produces hallucinated IDs (this happened: a working Highspot URL was overwritten with a
   nonexistent UUID). Copy-paste exactly, or don't write the URL.
3. **A fetch that lands on the company's full job board is a DEAD posting**, even with HTTP 200 —
   Greenhouse appends `?error=true` and shows the board. "The page mentions Account Executive" is NOT
   verification that THIS posting is live; only ID-present-in-board-API is.
4. **Verify remote from the JD text, not the board's location label.** Ashby "New York (Remote)" labels
   have meant hybrid-2-days-in-office in the JD body (Leapsome, Ironclad). Apply the existing
   remote-vs-boilerplate nuance rule below.
5. **Confirm the board belongs to the right company** — same-name collisions exist (an "Augment"
   logistics-AI company's AE role was once attributed to Augment Code).

## Which job this run does (decide at start; Job 1 runs EVERY run first)

Get `H=$(date -u +%H)` (runs fire at 03/08/13/18/23) and `D=$(date -u +%u)` (1 = Monday):

1. **Monday 18:00 UTC run** (`D==1 && H==18`) → **Job F — weekly funding-news sweep**.
2. Else, if `data/scan_queue.csv` still has companies not in `claude_universe.csv` → **Job 2 — queue scan**.
3. Else (queue dry): `H` in {13, 23} → **Job 3 — ATS-native search**; `H` in {03, 08, 18} →
   **Job 4 — re-check rotation**.

One job per run (plus Job 1). Do not combine or improvise beyond the selected job's budget.

## Job 2 — Scan the next 50 queue companies

1. Compute this run's batch: read `data/scan_queue.csv` top-to-bottom and take the **first 50 rows
   whose Company is NOT yet in `data/claude_universe.csv`** (match on the lowercased name before any
   " (" suffix — e.g. `Tableau (Salesforce)` matches `tableau`).
2. For each company, check for an open qualifying role (see The bar) via the ATS reference below —
   JSON endpoints first, `Slug` as the first board-token guess, then obvious variants, then ONE
   WebSearch (`{company} careers account executive`) to find the real board. Cap ~5 fetches + 1 search
   per company; unresolved after that = record as N / "ATS unresolved". Follow the URL-capture rules.
3. **Record EVERY company checked into `data/claude_universe.csv`** — winners AND losers:
   - qualifying role → add row `Currently Open = Y`, Notes = role/segment; add to `latest.csv`.
   - no qualifying role → add row `Currently Open = N`, Notes = the reason
     (no AE / not remote / wrong segment / senior-only / not B2B SaaS / ATS unresolved).
   - `Source = repvue`, `Last Checked` = today. This recording IS the queue's progress marker.
4. **Be terse per company** — fetch, decide against the bar, record one line, move on. No JD dumps in
   your working notes. If the session can't finish all 50, stop cleanly at a smaller number: every
   company actually checked must be recorded, and files must never be left half-updated.

Drop anything unverified — no "just in case." No fabrication; leave Funding/RepVue blank if unknown.

## Job 3 — ATS-native search (net-new startups, queue-dry runs at 13:00 & 23:00 UTC)

Find postings directly on the ATS platforms — the posting first, the company second. This catches
startups too new or obscure for RepVue.

1. Run ~8–10 WebSearch queries, rotating phrasing across runs, all scoped to hosted-board domains:
   `site:jobs.ashbyhq.com "account executive" mid-market remote`, same for
   `site:job-boards.greenhouse.io` and `site:jobs.lever.co`; vary with "commercial account executive",
   "AE" + "remote (US)", segment words ("mid market", "growth"), and without the segment word.
2. From the hits, collect candidate companies **not already in `claude_universe.csv`** (paren-aware
   base-name match). Search hits are LEADS, not verification — a hit may be a dead posting.
3. Verify each candidate on its board's JSON API per the ATS reference + URL-capture rules (the search
   hit tells you the board slug — confirm the posting ID is in the API response, then judge the bar:
   IC AE, US-remote from JD text, segment, OTE, B2B SaaS, company identity).
4. Record EVERY candidate evaluated into `claude_universe.csv` (`Source = ats-search`, Y/N + reason,
   `Last Checked` = today); winners → `latest.csv`. Budget: stop at 50 companies evaluated or when
   the query set is exhausted, whichever comes first.

## Job 4 — Re-check rotation (queue-dry runs at 03:00, 08:00, 18:00 UTC)

Re-check the universe for newly-opened roles: take the 50 `Currently Open = N` rows with the oldest
`Last Checked` (highest RepVue Score first as tiebreak), skipping rows whose Notes mark a permanent
disqualification (acquired / defunct / not B2B SaaS / different company), and run them through the
same check-and-record loop as Job 2 (update `Last Checked` + Notes; flips to Y go into `latest.csv`).
Roles churn — a company that had nothing last month may have an opening today.

## Job F — Weekly funding-news sweep (Monday 18:00 UTC run, replaces the other jobs that run)

Newly funded B2B SaaS companies hire AEs within weeks and are exactly the ones RepVue hasn't scored.

1. WebSearch for B2B SaaS funding announcements from the LAST 7 DAYS: "Series A/B/C" + "B2B SaaS"
   raise/funding round announcements, TechCrunch/Axios/BusinessWire funding roundups, "announced
   Series B" news queries. Prefer Series B/C (Series A is usually too early for a $150K+ OTE MM AE,
   but include any Series A explicitly scaling a sales team).
2. Build the candidate list; skip companies already in `claude_universe.csv`.
3. ATS-check each candidate per the reference + capture rules (find the board via ONE search if the
   company site doesn't link it; cap ~5 fetches + 1 search per company, same as Job 2).
4. Record EVERY candidate evaluated into `claude_universe.csv` (`Source = funding-news`, Y/N + reason,
   `Last Checked` = today); winners → `latest.csv`. Budget: up to 50 companies evaluated; most weeks
   the qualifying raise count will be far smaller — that's fine, do not pad the list.

## ATS reference (check these JSON endpoints first; `{slug}` = board token, try company name lowercased)

| ATS | Endpoint (GET JSON via WebFetch) |
|-----|-----|
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` (human: `https://job-boards.greenhouse.io/{slug}/jobs/{id}`) |
| **Ashby** | `https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` |
| **Lever** | `https://api.lever.co/v0/postings/{slug}?mode=json` |
| **SmartRecruiters** | `https://api.smartrecruiters.com/v1/companies/{slug}/postings` |
| **Workable** | `https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true` |
| **Recruitee** | `https://{slug}.recruitee.com/api/offers/` |
| **Rippling** | careers page `https://ats.rippling.com/{slug}/jobs` (read the page) |
| **Workday** | tenant-specific `{tenant}.wdN.myworkdayjobs.com`; no universal API — read careers page |

**Fallback:** WebFetch the company's `/careers` or `/jobs` page and read it. Unverifiable → not listed.

**Remote vs in-office (read carefully — this trips people up):** judge remote by THIS posting's own
designation, not by generic company-culture text. A posting explicitly labeled "Remote, United States"
**counts as remote** even if the body has boilerplate like "we value in-person collaboration / our hubs
are in office N days" — especially when the company ALSO runs separate city-specific postings for the
same role (the Remote posting exists for non-hub candidates). ONLY disqualify for remote when THIS role
states a specific in-office cadence (e.g. "expected in office 3+ days/week"). Example: Postman's Remote
MM-AE posting qualifies (distinct from its city postings); Checkr's Strategic AE does not ("3+ days").

> **NEVER gate on RepVue's `has_active_jobs` flag.** RepVue's job-posting data is stale/unreliable —
> that's the exact gap this project exists to fill. We check every company on its queue turn
> regardless of that flag.

*(Retired 2026-07-02: the weekly vertical-brainstorm rotation — it hit diminishing returns once the
universe covered the obvious names. Discovery is now the RepVue score-≥80 queue above.)*

## Finish

`python3 build.py` (regenerates `index.html` + `history.html` — NEVER hand-edit those) → copy
`latest.csv` to `data/$(date -u +%F).csv` → `git add -A` → commit
`Refresh <UTC date+hour>: +<added> -<dropped> ~<links fixed> | checked <n> (queue <remaining>)`
→ `git push origin main` (if rejected: `git pull --rebase` then push; **never force-push**) → print a
short summary: added, dropped, link fixes, companies checked, queue remaining, new total, universe size.
