# Routine: Remote AE Market Map - operating spec

**This file is the source of truth for what the scheduled refresh does.** The cloud routine's job is:
*read this file, execute it exactly, then commit & push.* Change behavior by editing THIS FILE.

**Cadence (since 2026-07-02): runs every ~5 hours, 50 queue companies per run.** Be efficient - one
run's discovery work is bounded by the 50-company cap, not by verticals or loop-until-dry.

## Files

- **`data/latest.csv`** - canonical PUBLISHED list = companies that *currently* have a qualifying open
  role. Columns: `Company,Funding ($M),OTE,Title,Segment,HQ,Remote,RepVue,Industry,Job Posting URL,Date Added,Posted,Location,Status`.
  **`Location` is a controlled page key, not free text.** It must be exactly one of `Remote` / `NYC` /
  `SF` / `Denver` / `Boston` / `Austin`. build.py filters it into six pages (index=Remote, nyc.html,
  sf.html, denver.html, boston.html, austin.html); any other value renders on NO page, so the row
  counts in the CSV while being published nowhere. A metro-anchored remote role whose city has no
  page (Chicago, Detroit, or a region such as "Southeast") belongs on `Remote`.
  **`Status`** = `Verified` (posting confirmed live in an ATS API / clean
  fetch) or `Needs check` (real but only corroborated via search/mirror - surfaced for manual review, not
  discarded).
  **`Date Added` rules:** every NEW row gets today's UTC date (`YYYY-MM-DD`); never change an existing
  row's date (a Job-1 URL fix keeps the original date); a company dropped and later re-added gets the
  re-add date. build.py sorts the site newest-first by this column.
  **`Posted` rules:** the posting's own publish date (`YYYY-MM-DD`), taken from the SAME API response
  used to verify it - Greenhouse `first_published` (needs `?content=true`), Ashby `publishedAt`,
  Lever `createdAt` (epoch ms → UTC date). Blank if the ATS doesn't expose it (Workday/custom sites)
  - never guess. Unlike Date Added, a Job-1 URL fix DOES update `Posted` (it's a different posting).
- **`data/claude_universe.csv`** - the MEMORY: *every company ever evaluated*, win or not. Columns:
  `Company,Source,RepVue Score,Last Checked,Currently Open,Notes`. This is the dedup set so we never
  re-discover a company we've already considered. **It must grow every run** (see Job 2, step 4).
- **`data/scan_queue.csv`** is the SCAN RING. Two blocks, in this order: a **seed block** of companies
  from the a16z speedrun board that the pipeline has never evaluated (`Source = a16z-speedrun`, no
  score), then every RepVue company at score **≥ 76**, best-score-first (4,075 companies).
  Columns: `Company,Slug,Score,Source` (Slug = starting guess for the ATS board token).
  **The seed block is first on purpose:** every RepVue row is a re-check by definition, since RepVue
  has zero net-new companies left at ≥76, and a company nobody has opened a board for outyields a
  re-check. Inside the seed block the order comes from the board's own labels: companies it says hire sales
  first, then remote-first before hybrid before onsite-leaning. That is an ORDER, not a filter:
  nothing is excluded, and a company at the back still gets its own ATS checked. `refill_queue.py`
  preserves any row whose `Source` is not `repvue`.
  It is a ring, not a well: Job 2 walks it 50 per run, and on reaching the bottom it starts a new
  cycle **from the top, at the highest scores**. It never goes dry. On its 2 slots/day (~100
  companies/day) a full cycle is ~40 days, which is the right re-check cadence anyway (roles churn on
  a monthly scale; a re-check inside 3-4 weeks yields almost nothing).
  **The score floor is 76.** Below that the yield turns Enterprise-heavy and the sales orgs are weak
  - MM density is concentrated in the top score ranks. `scripts/refill_queue.py` refuses a lower
  floor. Lowering it is Eric's decision, never the routine's.
- **`data/queue_cycle.txt`** - the ring CURSOR: the date the current cycle opened. A queue row is
  eligible when its `Last Checked` in `claude_universe.csv` is earlier than that date (or absent).
  Never edit it by hand; `scripts/next_batch.py` reads it, advances it, and reports position.
- **`data/speedrun_companies.csv`** is the a16z speedrun board's company list, 1,509 employers with
  the board's own `RemotePosture` (remote-first / hybrid-friendly / onsite-leaning), `Functions`
  (which job families it hires for, including `sales`), open-role count and collection memberships.
  Committed, because it is public sitemap data and the cloud clone has no other company library.
  **`SalesRoles = 0` is NOT evidence a company has no AE role.** This board carries only a slice of
  some employers' postings. 1Password is labelled as hiring sales while listing none.
- `data/speedrun_raw.tsv`, `data/speedrun_triage.csv` are gitignored working files for Job S.
- `data/repvue_universe.csv` - gitignored/local-only (RepVue's proprietary data; not in cloud clones).
- `data/YYYY-MM-DD.csv` - dated snapshot of `latest.csv`, refreshed each run.

## Tool & cost rules

- **WebFetch / WebSearch ONLY for web access.** NEVER curl/wget/Bash to fetch URLs.
- Bash is allowed ONLY for git, `python3 build.py`, `python3 scripts/verify_links.py`,
  `python3 scripts/next_batch.py`, `python3 scripts/backfill_comp.py`, `python3 scripts/enrich_repvue.py`,
  `date`, and file ops - not for open-ended research.
- **Work inline - do NOT spawn subagents.** Be token-conscious (this draws on a subscription quota):
  don't over-fan-out; stop a vertical as soon as it's dry (see loop rule).

## The bar (ICP - a role qualifies only if it clears ALL)

IC **Account Executive** (NOT SDR/BDR, NOT Director/VP/RVP; **"Associate AE" IS allowed** - it is a
closing IC role and is explicitly in scope) · segment **MM** or
**MM/Ent** preferred (pure **Ent** allowed but tagged so it sorts last) · **US-remote OR based in
NYC / SF / Denver / Boston / Austin** - set `Location` = `Remote` / `NYC` / `SF` / `Denver` /
`Boston` / `Austin` accordingly (build.py renders one page per location); other cities and
non-US are excluded (a role in two = one row per applicable location). Boston/Austin are
priority physical-AI hubs · **NO COMP FLOOR - see the comp rule below**
(record OTE when known; blank if not reliably known - never guess) · **B2B SaaS** ·
**required experience 0-8 yrs**.

**COMP RULE - THERE IS NO SALARY FLOOR. Do not reject any role on a low posted salary.**
Job boards and ATS feeds almost always publish **BASE salary, not OTE**. For an AE, base is
typically ~50% of OTE, so a posting showing "$80-90K" is usually a ~$160-180K OTE role. Screening a
posted number against an OTE floor is comparing two different quantities and silently kills good
roles. (This happened: a $100K floor was applied to base-salary figures and dropped Cyberhaven among
others. Removed 2026-08-03, same class of mistake as the experience floor.) Record the posted number
and note whether it is base or OTE when the posting says; never drop a row for being "too low".

**THERE IS NO EXPERIENCE FLOOR. This is a hard rule - do not reintroduce one.** The only experience
test is the CEILING: reject a posting only if it demands MORE than ~8 yrs closing. Early-career,
associate-level, and unstated-experience AE roles all qualify, in every segment including MM. Never
filter on years because a posting asks for less than Eric has; his own tenure is not a floor and never
was. (A `~4+ yrs` floor was previously inferred from Eric's background and applied globally - it was
wrong, it was never specified, and it is what made MM results thin. Removed 2026-08-03.)

Set `Status` = `Verified` normally; `Needs check` if the posting is real but only
search/mirror-corroborated (never fully dropped - it's surfaced for manual review).

**PHYSICAL-AI EXCEPTION (deliberate pivot target - Eric wants into Physical AI):** Physical AI = AI that
perceives/acts in the physical world - **robotics, autonomous vehicles, drones/UAV, perception & sensors
(lidar/radar/vision), embodied AI / world models, simulation & synthetic data for physical systems,
industrial / Industry-4.0 automation, machine vision, spatial computing / AR-VR, edge AI for physical
devices, smart-infrastructure autonomy**. For these companies, LOWER the bar - the global OTE floor is
now ~$100K so comp is no longer a separate carve-out, but still accept **hardware / RaaS / AI software**
(do NOT require pure SaaS) and treat the experience range leniently. Tag `Industry` starting with `Physical AI - ` (e.g.
`Physical AI - autonomous vehicles`) so these are filterable. Physical AI is a priority vertical for the
Job 3 rotation - rotate its niches in (robotics/AMR, AV/self-driving, drones/UAV, perception/lidar,
embodied-AI/world-models, simulation/synthetic-data, industrial-AI, spatial computing, edge-AI,
smart-infra, surgical/agricultural/defense robotics).

---

## Job 1 - Re-verify every row in `latest.csv`

**Run `python3 scripts/verify_links.py` FIRST** (Bash is allowed for this script). It deterministically
checks every row's job ID against the ATS's own JSON API (Greenhouse/Ashby/Lever - most rows) and
prints, for each broken row, the current AE postings on the same board with exact URLs copied from the
API. Do NOT re-verify API-covered rows by WebFetching posting pages - a dead Greenhouse posting returns
HTTP 200 and silently redirects to the full board (`?error=true`), so page-reads pass dead links
(this corrupted the list once; see URL-capture rules below).

**Then run `python3 scripts/backfill_comp.py --write`.** It fills blank OTE cells from the ATS's own
JSON API. Never record "no comp stated" from a WebFetch of a posting PAGE: Ashby, HireBridge, Workable
and Workday render the description client-side, so WebFetch returns only the page shell and the comp
range looks absent when the posting plainly publishes it (this is why LifeLoop, Vercel, Plaid and ~55
others were blank). The board APIs carry it as a structured field.

**Base vs OTE:** the column is named OTE but ATS feeds publish BASE far more often. For an AE, base is
roughly half of OTE, so `$60,000-$70,000` may be base against a ~$130K OTE. Suffix the value with
` base` whenever the source says base - never silently conflate the two, and never screen on the
number (see the ICP bar: there is no comp floor or ceiling).

Rows the script prints as `NEEDS_BROWSER` are on non-API hosts and can only be read in a real browser -
leave them blank rather than guessing.

**Also run `python3 scripts/backfill_titles.py --write`** to populate the `Title` column. When adding a
row by hand, always fill Title - the publish-time dedupe reads the territory out of it.

### Publishing rule: one role per company per page

`latest.csv` keeps EVERY qualifying role (it is the dataset). `build.py` decides what gets published,
collapsing each company to a single row per geo page:

1. **Segment** - MM beats MM/Ent beats unspecified beats Ent.
2. **Geography** - furthest west wins, read from the job title against the `WEST` map in build.py
   (so Armadin's six territories resolve to Southwest).
3. **Recency** - most recently posted, then most recently added.

The kept row shows a `+N` pill so a company with more openings is visible rather than silently trimmed.
Duplicate rows sharing one posting URL are dropped outright (the Remote listing wins, else westernmost).
Do NOT prune `latest.csv` to achieve this - the dedupe is a render-time decision and must stay reversible.

Then act on the verify script's output:
- **DEAD/BROKEN with a qualifying replacement candidate** (IC AE, US-remote, right segment - read the
  JD if unsure): update the row's URL, copying the replacement URL **verbatim from the script output**.
- **DEAD/BROKEN with no qualifying candidate**: drop the row from `latest.csv` and set its
  `claude_universe.csv` row to `Currently Open = N` (update `Last Checked`).
- **UNKNOWN rows** (bot-blocked/JS-only sites - Workday, Salesforce, custom career sites): verify these
  the LLM way - WebFetch the careers site/sitemap, cross-check search-indexed copies of the company's
  own board. If liveness can't be established, keep the row but note it; never invent a new URL.

## URL-capture rules (apply to BOTH jobs - these prevent the two failure modes that broke the list)

1. **Copy URLs only from an ATS JSON API response** (`absolute_url` / `jobUrl` / `hostedUrl`) or, for
   non-API sites, the site's own sitemap/board page. NEVER record a URL from WebSearch results or
   aggregators (LinkedIn/Indeed/BuiltIn/etc. carry stale postings that soft-redirect on Greenhouse).
2. **Never retype or reconstruct a job ID.** Lever/Ashby IDs are 36-char UUIDs; retyping them from a
   fetched page produces hallucinated IDs (this happened: a working Highspot URL was overwritten with a
   nonexistent UUID). Copy-paste exactly, or don't write the URL.
3. **A fetch that lands on the company's full job board is a DEAD posting**, even with HTTP 200 -
   Greenhouse appends `?error=true` and shows the board. "The page mentions Account Executive" is NOT
   verification that THIS posting is live; only ID-present-in-board-API is.
4. **Verify remote from the JD text, not the board's location label.** Ashby "New York (Remote)" labels
   have meant hybrid-2-days-in-office in the JD body (Leapsome, Ironclad). Apply the existing
   remote-vs-boilerplate nuance rule below.
5. **Confirm the board belongs to the right company** - same-name collisions exist (an "Augment"
   logistics-AI company's AE role was once attributed to Augment Code).

## Job S: sweep the a16z speedrun board (EVERY run, before the scheduled job)

Costs no model tokens and takes about two minutes, so it does **not** take a slot from Job 2, 3 or F.
Bash is allowed for these three scripts.

```
python3 scripts/harvest_speedrun.py     # sitemap -> closing-sales pages -> data/speedrun_raw.tsv
python3 scripts/triage_speedrun.py      # apply the bar + confirm each id in the company's own ATS
python3 scripts/merge_speedrun.py       # publish winners, record judged companies, seed the ring
```

**What makes this board worth a standing slot:** every job page carries a schema.org JobPosting block
holding the company, the first-posted date, the remote flag, the applicant location requirement, the
posted salary, the full job description, and the apply link on the company's OWN ATS carrying that
job's native id. So a row arrives already meeting the URL-capture rules below, and its segment is
read from the description in the same fetch. First full pull, 2026-08-21: **100 of 100 rows that
cleared remote + US + IC + the experience ceiling were confirmed live in their own ATS feed.**

**Read the counts, they are the health check.** `harvest_speedrun.py` prints `sent / parsed / no
JobPosting block / fetch errors` and `triage_speedrun.py` prints one verdict per row. A non-zero
**fetch errors** means the pull is SHORT and no total from that run can be trusted. Rerun before
recording anything. A page with no JobPosting block is a property of the source and is fine to skip.

**If the ATS JSON APIs are unreachable** (the cloud environment could not reach
boards-api.greenhouse.io or api.ashbyhq.com as of 2026-07-02; unconfirmed since), run
`python3 scripts/triage_speedrun.py --no-verify` and set those rows' `Status` to `Needs check`
rather than `Verified`. Never publish an unverified row as Verified to keep a run productive.

**Do not record a speedrun company as checked unless a posting of theirs was actually read.**
`merge_speedrun.py` already enforces this. The board is not a complete mirror of anyone's careers
page, so "no AE role listed here" is not a finding, and writing it into `claude_universe.csv` would
make every future run skip that company forever.

## Which job this run does (decide at start; Job 1 runs EVERY run first)

Get `H=$(date -u +%H)` (runs fire at 03/08/13/18/23) and `D=$(date -u +%u)` (1 = Monday). Jobs 1 and S run first every time and take no slot from the choice below:

1. **Monday 18:00 UTC** (`D==1 && H==18`) → **Job F - weekly fresh-startup sweep**.
2. **`H` in {13, 18, 23}** → **Job 3 - vertical startup search** (3 discovery slots/day).
3. **`H` in {03, 08}** → **Job 2 - ring scan** (2 re-check slots/day).

**This split is Eric's, set 2026-08-16, and a run does not get to reassign it.** The reasoning, so
it is not re-litigated every run: net-new companies now come ONLY from Jobs 3 and F, because the
ring is entirely RepVue companies and RepVue has zero net-new left at score ≥76 (all 4,075 already
evaluated). Job 3 has also earned the slots on yield - **24.9% of the companies it checked had a
qualifying role (90 of 361), against 6.8% for the RepVue scan (279 of 4,121)** - and the ring's rate
will fall below its own 6.8%, since every ring pass from here is a re-check rather than a first look.

Two ring slots = ~100 companies/day = a **~40-day cycle**. That is intentional: role churn is
monthly, so a slower ring loses almost nothing, and re-checking a company inside 3-4 weeks has
repeatedly yielded ~nothing.

**Job 4 is retired.** The ring's wrap-around IS the re-check rotation, in score order, over more
companies than Job 4 covered. Its section is kept below only as the reference for re-check judgment.

One job per run (plus Jobs 1 and S). Do not combine or improvise beyond the selected job's budget.

## Job 2 - Scan the next 50 ring companies

1. Compute this run's batch with **`python3 scripts/next_batch.py 50`** - do NOT pick rows by eye.
   It prints the 50 highest-scored companies not yet visited in this cycle, advances the cycle
   marker when the ring wraps, and reports ring position on stderr. If its stderr says `WRAPPED`,
   say so in the commit summary: the ring restarted at the top scores and this run is re-checking
   companies rather than seeing them for the first time.
2. For each company, check for an open qualifying role (see The bar) via the ATS reference below -
   JSON endpoints first, `Slug` as the first board-token guess, then obvious variants, then ONE
   WebSearch (`{company} careers account executive`) to find the real board. Cap ~5 fetches + 1 search
   per company; unresolved after that = record as N / "ATS unresolved". Follow the URL-capture rules.
3. **Record EVERY company checked into `data/claude_universe.csv`** - winners AND losers:
   - qualifying role → `Currently Open = Y`, Notes = role/segment; add to `latest.csv`.
   - no qualifying role → `Currently Open = N`, Notes = the reason
     (no AE / not remote / wrong segment / senior-only / not B2B SaaS / ATS unresolved).
   - `Source = repvue`, `Last Checked` = today. **`Last Checked` is the ring's progress marker** -
     a company is done for this cycle once its date is on or after `data/queue_cycle.txt`.
   - **The ring re-checks companies that are already in the universe, so UPDATE the existing row in
     place (`Last Checked`, `Currently Open`, Notes) - never append a second row for a company that
     is already there.** One row per company, always. Preserve the original `Source`.
   - **Quote fields when you write CSV.** Company names contain commas (`Tellius, Inc.`) and an
     unquoted write shifts every later column: three universe rows carry corrupted data from exactly
     this. Write with a CSV writer, not string concatenation.
4. **Be terse per company** - fetch, decide against the bar, record one line, move on. No JD dumps in
   your working notes. If the session can't finish all 50, stop cleanly at a smaller number: every
   company actually checked must be recorded, and files must never be left half-updated.

Drop anything unverified - no "just in case." No fabrication; leave Funding/RepVue blank if unknown.

**Never type a RepVue score from memory or from a web page.** The only source is the local library
(`data/repvue_universe.csv`) via `scripts/enrich_repvue.py` - see RepVue enrichment under Finish.

## Job 3 - Vertical startup search (net-new startups; runs at 13:00, 18:00 & 23:00 UTC)

Find postings directly on the ATS platforms - the posting first, the company second. This is the
primary net-new engine: it catches startups too new or too obscure for RepVue, which is now the only
place net-new companies come from. **Search ALL EIGHT hosted-board domains, not just three** - the
extra platforms are where smaller, newer companies live.

**The six verticals, set by Eric 2026-08-16. Do not add, drop or substitute one inside a run:**

| Vertical | Query terms to pair with the board domain |
|---|---|
| fintech / payments | `fintech`, `payments`, `banking`, `treasury` |
| devtools / infra | `developer tools`, `infrastructure`, `observability`, `platform engineering` |
| data / analytics | `data platform`, `analytics`, `data infrastructure`, `warehouse` |
| robotics | `robotics`, `automation`, `warehouse robotics` |
| physical AI | `physical AI`, `embodied AI`, `autonomy`, `industrial AI` |
| AI infra | `AI infrastructure`, `LLM`, `inference`, `AI platform`, `agents` |

The first three are the MM-density picks: a 2026-07-15 sweep of them returned 4 winners, ALL of them
MM, the best MM yield of anything tried. The last three are the AI-native picks: `robotics` and
`physical-ai` sweeps hit 4-of-7 and 4-of-6 qualifying rates, the highest in the file, though on
samples that small treat them as promising rather than proven. Healthtech is NOT on this list.

1. Run ~10-12 WebSearch queries this run, all scoped to hosted-board domains, **rotating so
   consecutive runs never repeat the same query** (stale queries re-find the same names). Seed this
   run's position in the matrix from the clock - e.g. `R=$(( (10#$(date -u +%j) * 5 + 10#$(date -u +%H)) ))` -
   and step through the **vertical × domain × phrasing** matrix so every run advances; the full cycle
   repeats only after the matrix is exhausted.
   - **vertical** (the outer axis - every run covers ONE vertical, so the six rotate across two days):
     take `V = R % 6` against the table above and use that vertical's terms for all this run's queries.
   - **domains** (cycle across runs): `site:jobs.ashbyhq.com`, `site:job-boards.greenhouse.io`,
     `site:jobs.lever.co`, `site:jobs.smartrecruiters.com`, `site:apply.workable.com`,
     `site:*.recruitee.com`, `site:ats.rippling.com`, `site:*.myworkdayjobs.com`
   - **phrasing**: `"account executive"` / `"commercial account executive"` /
     `"mid-market account executive"` / `"AE" "remote"`
   - Query shape: `<domain> <phrasing> <one vertical term>`. Bias toward
     `"mid-market account executive"` and `"commercial account executive"` - deep ATS search skews
     Enterprise, and MM is what the list is short on. Do NOT bias to Strategic/Enterprise/Director.
   - **Name the vertical in the run summary** so yield per vertical stays measurable. That number is
     what justifies keeping or cutting a vertical later, and nobody can reconstruct it after the fact.
2. From the hits, collect candidate companies **not already in `claude_universe.csv`** (paren-aware
   base-name match). Search hits are LEADS, not verification - a hit may be a dead posting.
3. Verify each candidate on its board's JSON API per the ATS reference + URL-capture rules (the search
   hit tells you the board slug - confirm the posting ID is in the API response, then judge the bar:
   IC AE, US-remote from JD text, segment, OTE, B2B SaaS, company identity).
   - **Recency signal (better than waiting for a funding headline):** read each posting's publish date
     from the SAME API response (Greenhouse `first_published`, Ashby `publishedAt`, Lever `createdAt`)
     and prioritize roles posted in the last ~30 days - a brand-new AE posting at an unknown small
     company is the strongest "scaling sales right now" signal (record it as `Posted`).
   - **GTM-cluster signal:** a never-before-seen board carrying a CLUSTER of fresh GTM roles (an AE
     *plus* a sales-manager / RevOps / first-GTM-hire posting) is a net-new sales org standing up -
     treat as high-priority net-new.
4. Record EVERY candidate evaluated into `claude_universe.csv`, Y/N + reason, `Last Checked` = today;
   winners → `latest.csv`. **`Source` = `ats-` plus this run's vertical** - `ats-fintech`,
   `ats-devtools`, `ats-data`, `ats-robotics`, `ats-physical-ai`, `ats-ai-infra` - never a bare
   `ats-search`. The Source column is the only per-vertical yield record that exists. Budget: stop at
   50 companies evaluated or when the query set is exhausted, whichever comes first.

## Job 4 - RETIRED (superseded by the ring wrap in Job 2; kept as re-check reference)

Re-check the universe for newly-opened roles: take the 100 `Currently Open = N` rows with the oldest
`Last Checked` (highest RepVue Score first as tiebreak), skipping rows whose Notes mark a permanent
disqualification (acquired / defunct / not B2B SaaS / different company), and run them through the
same check-and-record loop as Job 2 (update `Last Checked` + Notes; flips to Y go into `latest.csv`).
Roles churn - a company that had nothing last month may have an opening today.

## Job F - Weekly fresh-startup sweep (Monday 18:00 UTC run, replaces the other jobs that run)

Reach companies too new for RepVue AND before/without a funding headline. Funding news is just ONE of
three lead feeders here - the posting is the real signal, so pull leads from all three, then run the
SAME ATS-verify pipeline on the merged candidate list.

**Feeders - gather leads from all three (leads only; verification happens in step 4):**
1. **Funding news - last 7 days.** WebSearch "Series A/B/C" + "B2B SaaS" raise/round announcements,
   TechCrunch/Axios/BusinessWire funding roundups. Prefer Series B/C (Series A is usually too early for
   a $100K+ OTE MM AE, but include any Series A explicitly scaling a sales team).
2. **YC companies hiring AEs.** WebSearch the public YC directory / "Work at a Startup" for B2B SaaS
   companies with open AE / GTM roles (e.g. `site:ycombinator.com/companies "account executive"`, recent
   batches + "account executive remote"). YC-backed = net-new by definition.
3. **Wellfound (AngelList).** WebSearch `site:wellfound.com "account executive" remote` and variants for
   startup AE postings. Leads ONLY - Wellfound listings go stale, so never record a Wellfound URL.

**Verify + record:**
4. Merge the three lead lists; drop anything already in `claude_universe.csv` (paren-aware base-name
   match). ATS-check each remaining candidate on its own board's JSON API per the ATS reference +
   URL-capture rules (find the board via ONE search if the company site doesn't link it; cap ~5 fetches
   + 1 search per company). Apply the **recency + GTM-cluster signals** from Job 3.
5. Record EVERY candidate evaluated into `claude_universe.csv` (`Source =` the feeder it came from -
   `funding-news` / `yc` / `wellfound`; Y/N + reason; `Last Checked` = today); winners → `latest.csv`.
   Budget: up to 50 companies evaluated across all feeders; most weeks the qualifying count is small -
   that's fine, do not pad the list.

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
| **Workday** | tenant-specific `{tenant}.wdN.myworkdayjobs.com`; no universal API - read careers page |

**Fallback:** WebFetch the company's `/careers` or `/jobs` page and read it. Unverifiable → not listed.

**Posting-api blind spot (Ashby & similar) - DON'T record "no AE" on the API alone:** some companies
publish AE/sales roles on their own careers page and via direct posting URLs
(`jobs.ashbyhq.com/{slug}/{uuid}` resolves live) but EXCLUDE them from the public posting-api board
feed. So an ATS board that returns real roles but **ZERO sales/AE/GTM roles** is a RED FLAG for any
plausible sales-led B2B SaaS (RepVue-scored, clear GTM motion) - before recording "no AE", do ONE
fallback: WebSearch `{company} account executive site:jobs.ashbyhq.com/{slug}` (or `{company} careers
account executive`, or fetch `/careers`). If a live IC-AE posting resolves, verify it and record the
direct posting URL. (Found via **Linear**: RepVue 97, AE roles live on linear.app/careers but absent
from the Ashby posting-api feed - a false "no AE" for weeks.)
**The bigger cause is usually WRONG ATS, not feed-omission:** a company often runs a DIFFERENT ATS than
the slug guess (Greenhouse / Lever / Workable / Workday / its own site), so an Ashby-only check finds
nothing. ALWAYS fetch the company's `/careers` page - it links the real ATS. (Confirmed 2026-07-15: the
company Greenhouse, Alloy, FOSSA, Businessolver run on Greenhouse; Saviynt on Lever; Action1 on
Workable; Workday on its own - all had live qualifying AE roles a plain Ashby-slug check missed.)

**Remote vs in-office (read carefully - this trips people up):** judge remote by THIS posting's own
designation, not by generic company-culture text. A posting explicitly labeled "Remote, United States"
**counts as remote** even if the body has boilerplate like "we value in-person collaboration / our hubs
are in office N days" - especially when the company ALSO runs separate city-specific postings for the
same role (the Remote posting exists for non-hub candidates). ONLY disqualify for remote when THIS role
states a specific in-office cadence (e.g. "expected in office 3+ days/week"). Example: Postman's Remote
MM-AE posting qualifies (distinct from its city postings); Checkr's Strategic AE does not ("3+ days").

> **NEVER gate on RepVue's `has_active_jobs` flag.** RepVue's job-posting data is stale/unreliable -
> that's the exact gap this project exists to fill. We check every company on its queue turn
> regardless of that flag.

*(Retired 2026-07-02: the weekly vertical-brainstorm rotation - it hit diminishing returns once the
universe covered the obvious names. Discovery is now the RepVue score-≥80 queue above.)*

## No em or en dashes, and the four places they legitimately live

This file and every script here were swept clean on 2026-08-21
(`python3 ~/.claude/projects/-Users-erichastie/memory/_hub/verify.py dashes $(git ls-files '*.md' '*.py')`).
Four lines still contain one, and all four are the CODE THAT STRIPS THEM: `build.py`'s `clean()`,
`scripts/backfill_titles.py`, and the `dash()` helper in each aggregator harvester. Rewriting those
disables the normalizer and lets a dash reach a published page. **A future sweep must skip any line
containing `.replace(` or a dash character class.** Everything else in this repo stays clean.

`data/*.csv` is a separate matter and is NOT swept. A job title is a quoted fact: RigUp really did
post "Senior Account Executive - Downstream" with an en dash. `build.py` converts them at render
time, so the CSV stays truthful and the page stays clean. Never edit a title to satisfy a lint.

## Finish

**RepVue enrichment (LOCAL RUNS ONLY).** Before `build.py`, run
`python3 scripts/enrich_repvue.py --write`. It fills blank `RepVue` / `RepVue Score` cells in
`latest.csv` and `claude_universe.csv` by exact-normalized-name match against the local
`data/repvue_universe.csv` library, so every newly discovered company that RepVue already rates
picks up its score automatically. Scores are a point-in-time snapshot and go stale - that is
accepted; they are a directional read on the sales org, not a live figure. The script only fills
blanks (it never overwrites a hand-entered score), skips names RepVue rates ambiguously, and carries
a hand-verified `COLLISIONS` set for same-name-different-company traps (e.g. Capsule the AI video
company vs Capsule the pharmacy) - add to that set rather than loosening the matcher. **Cloud runs
skip this**: the library is gitignored and absent from cloud clones, so the script no-ops there and
new rows simply stay blank until the next local run backfills them.

**Snapshot BEFORE building, not after.** `build.py`'s history page reads the dated snapshots in
`data/`, not `latest.csv`, so building first leaves `history.html` showing the PREVIOUS run's
"roles right now" every single time. Caught 2026-08-21, when it read 1,110 against a real 1,177.

**Run the loss gate FIRST, as its own step, before the snapshot copy and before anything is
built or committed:**

```
python3 scripts/check_no_silent_loss.py --dropped <the number this run means to remove>
```

It compares `latest.csv` against the last committed version and refuses when rows or whole
companies have vanished in bulk. **If it exits non-zero, STOP.** Do not snapshot, do not build,
do not commit, do not push. Recover with `git show HEAD:data/latest.csv > data/latest.csv` and
redo this run's edits on top of the recovered file.

Why it exists: on 2026-08-25 and 2026-08-26 two runs rewrote `latest.csv` from a partial read of
it and lost the tail. They reported `-1` while actually removing 358 and 366 rows, 291 and 313
whole companies. Every step downstream behaved perfectly, because a truncated CSV is a valid CSV.
658 verified roles are still missing and nothing in the pipeline noticed for five days.
**Never write `latest.csv` from rows read into context. Edit it in place with a script, or
append to what is already on disk.** The gate runs in a separate step from the write on purpose:
a check in the same command block as the thing it guards cannot stop it.

Then: copy `latest.csv` to `data/$(date -u +%F).csv` → `python3 build.py` (regenerates `index.html` +
`history.html` + `discards.html` - NEVER hand-edit those; `discards.html` lists every
`Currently Open = N` universe row with its Notes as the discard reason) → `git add -A` → commit
`Refresh <UTC date+hour>: +<added> -<dropped> ~<links fixed> | checked <n> (ring <walked>/<size>)`
where `<walked>/<size>` is the cycle position from `scripts/next_batch.py` stderr; append ` WRAPPED`
when this run started a new cycle. The subject line is the health diagnostic - `git log --oneline`
alone should show whether the ring is advancing, so never omit the position.
→ `git push origin main` (if rejected: `git pull --rebase` then push; **never force-push**) → print a
short summary: added, dropped, link fixes, companies checked, ring position, new total, universe size.
