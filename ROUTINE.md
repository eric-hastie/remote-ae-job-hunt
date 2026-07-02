# Routine: Remote AE Market Map — operating spec

**This file is the source of truth for what the scheduled refresh does.** The cloud routine's job is:
*read this file, execute it exactly, then commit & push.* Change behavior by editing THIS FILE.

## Files

- **`data/latest.csv`** — canonical PUBLISHED list = companies that *currently* have a qualifying open
  role. Columns: `Company,Funding ($M),OTE,Segment,HQ,Remote,RepVue,Industry,Job Posting URL`.
- **`data/claude_universe.csv`** — the MEMORY: *every company ever evaluated*, win or not. Columns:
  `Company,Source,RepVue Score,Last Checked,Currently Open,Notes`. This is the dedup set so we never
  re-discover a company we've already considered. **It must grow every run** (see Job 2, step 4).
- **`data/repvue_universe.csv`** — *(Phase 2, pending Eric's browser pull)* all RepVue companies + scores.
- `data/YYYY-MM-DD.csv` — dated snapshot of `latest.csv` each run.

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

## Job 2 — Discover net-new companies

Rotate verticals to control cost (see Rotation). For each vertical in this run, run finder passes
**loop-until-dry**:

1. Propose qualifying companies in the vertical that are **NOT already in `data/claude_universe.csv`**
   (the full memory — winners AND past no-role evaluations) and not found earlier this run.
2. **Verify** each proposed company has an open qualifying role via the ATS reference / careers page.
   Capture the human-facing posting URL.
3. **Repeat passes on the same vertical until a pass yields 0 net-new qualifying companies** (one fully
   dry pass), capped at **4 passes per vertical** to bound cost.
4. **Record EVERY company you evaluated this run into `data/claude_universe.csv`** — not just winners:
   - new winner → add row, `Currently Open = Y`, Notes = role/segment.
   - evaluated but no qualifying role (closed, wrong segment, not remote, senior-only) → add row,
     `Currently Open = N`, Notes = the reason.
   - Set `Last Checked` to today on every row you touched. This is what makes future runs skip
     already-considered companies and spend effort on genuinely new ones.
5. Add the winners (Currently Open = Y) to `latest.csv`.

Drop anything unverified — no "just in case." No fabrication; leave Funding/RepVue blank if unknown.

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

## Rotation (current: weekly)

Get ISO week `W` (`date -u +%V`). Verticals: [0] Dev tools/infra/observability/data · [1]
Fintech/payments/accounting/BI · [2] Vertical & horizontal SaaS (sales/martech, HR, healthcare, fleet,
construction) · [3] AI-native B2B SaaS · [4] Cybersecurity/DevSecOps/GRC (lower priority). Cover TWO
per run: `W mod 5` and `(W+1) mod 5`, each loop-until-dry.

> **Phase 2 (pending — do NOT implement until `data/repvue_universe.csv` exists and we size it):**
> switch discovery to **universe-driven rotation** — daily runs that each check one rotating *slice*
> of `claude_universe.csv` ∪ `repvue_universe.csv` for newly-opened roles, sized so every company is
> re-checked ~weekly, plus a weekly vertical-brainstorm pass to ADD net-new companies to the universe.
> Chunk size + cadence finalized once we know the universe count.
>
> **NEVER gate on RepVue's `has_active_jobs` flag.** RepVue's job-posting data is stale/unreliable —
> that's the exact gap this project exists to fill. We search every company on its rotation turn
> regardless of that flag; it is stored for reference only and must never filter the universe.

## Finish

`python3 build.py` (regenerates `index.html` + `history.html` — NEVER hand-edit those) → copy
`latest.csv` to `data/$(date -u +%F).csv` → `git add -A` → commit
`Weekly refresh <today>: +<added>, -<dropped> (verticals: <names>)` → `git push origin main`
(if rejected: `git pull --rebase` then push; **never force-push**) → print a short summary:
added, dropped, link fixes, new total, universe size, verticals scanned.
