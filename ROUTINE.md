# Routine: Remote AE Market Map — operating spec

**This file is the source of truth for what the scheduled refresh does.** The Claude.ai routine's
job is simply: *clone this repo, read this file, execute it exactly, then commit & push.* Change the
behavior by editing THIS FILE — no need to touch the cloud routine's prompt.

---

## Output contract (don't break these)

- `data/latest.csv` is canonical. Columns, in order:
  `Company,Funding ($M),OTE,Segment,HQ,Remote,RepVue,Industry,Job Posting URL`
- Segment values: `MM`, `MM/Ent`, `Ent`, `SMB/MM` (MM-friendly ones sort to the top).
- After editing `latest.csv`, run **`python3 build.py`** to regenerate `index.html` and `history.html`.
  **Never hand-edit `index.html`.**
- Snapshot the run as `data/YYYY-MM-DD.csv` (copy of the final `latest.csv`).
- Commit with message `Weekly refresh YYYY-MM-DD: +N, -M (verticals: ...)` and push.
- Use plain hyphens, never em/en dashes (build.py normalizes, but keep data clean).

## The bar (ICP — a role qualifies only if it clears ALL of these)

- **Role:** individual-contributor **Account Executive**. NOT SDR/BDR, NOT "Associate AE", NOT Director/VP/RVP.
- **Segment:** Mid-Market or MM/Ent preferred. Pure Enterprise is allowed but tagged `Ent` so it sorts last.
- **Experience:** ~4+ yrs closing. Reject senior-only ("8+ yrs") and junior/BDR-level.
- **Remote:** must be **US remote** (not hybrid, not office-bound, not non-US).
- **Comp:** ~$150K–$340K OTE (leave blank if not reliably verifiable — never guess).
- **Type:** B2B SaaS.

---

## What each run does — TWO jobs

### Job 1 — Re-verify every existing posting in `latest.csv`

For each row, re-fetch its posting and confirm it is **still open, still remote-US, still IC AE**.
- If the URL 404s / role is closed / no longer remote → **remove the row**.
- If the company clearly still has an equivalent open qualifying role at a new URL → update the URL.
- Use the **ATS reference** below to check fast via JSON endpoints before falling back to the careers page.

### Job 2 — Discover net-new companies

Fan out research agents by **vertical** (this run's rotation — see Rotation). For each vertical, run
finder passes **loop-until-dry**:

1. Propose companies in the vertical that are **NOT** already on the exclusion set
   (= every company in `latest.csv` ∪ the dedup sheet ∪ everything found earlier in this run
   ∪ `data/claude_universe.csv` once it exists).
2. For each proposed company, **verify** an open qualifying role exists (ATS reference below). Capture the posting URL.
3. Keep the verified ones; record every company evaluated (kept or rejected, with reason) into the run log.
4. **Repeat passes on the same vertical until a pass returns 0 net-new qualifying companies**
   (one fully dry pass), capped at **4 passes per vertical** to bound cost.

A company makes the list only if its posting is fetched and confirmed open + remote-US + IC AE.
**Drop anything unverified — no "just in case."** Each agent reports what it excluded and why
(not remote / wrong segment / closed / senior-only) as proof real filtering happened.

---

## ATS reference (check these JSON endpoints first — fast and reliable)

Use **WebFetch** only (never Bash/curl). `{slug}` = the company's board token (try the company name
lowercased, no spaces; adjust if the first try 404s).

| ATS | Endpoint (GET JSON) |
|-----|---------------------|
| **Greenhouse** | `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` |
| **Ashby** | `https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` |
| **Lever** | `https://api.lever.co/v0/postings/{slug}?mode=json` |
| **SmartRecruiters** | `https://api.smartrecruiters.com/v1/companies/{slug}/postings` |
| **Workable** | `https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true` |
| **Recruitee** | `https://{slug}.recruitee.com/api/offers/` |
| **Rippling** | careers page under `ats.rippling.com/{slug}/jobs` (no clean public JSON — read the page) |
| **Workday** | tenant-specific (`{tenant}.wdN.myworkdayjobs.com`); no universal API — read the careers page / search the role |

**Fallback for any company not on the above:** WebFetch the company's `/careers` or `/jobs` page
directly and read it. If a role can't be verified open + remote-US, it does **not** go on the list.

When a posting includes structured comp (Ashby `includeCompensation`, some Greenhouse), capture the OTE.

---

## Rotation (current: weekly)

Each run scans **2 rotating verticals** (loop-until-dry within each). Rotate through:
`dev tools & infra/observability/data` · `fintech/payments/accounting/BI` ·
`vertical SaaS` · `horizontal SaaS` · `AI-native B2B SaaS` · `security/DevSecOps (lower priority)`.

> **Phase 2 (pending — do not implement until the universe files exist and we size it):**
> Switch discovery from vertical-brainstorm to **universe-driven rotation**. Inputs:
> `data/repvue_universe.csv` (all RepVue cos + score — Eric pulls via browser) and
> `data/claude_universe.csv` (every company Claude has evaluated, accumulating). Move to a **daily**
> run that checks one rotating **slice** of the union universe per day, sized so every company is
> re-checked ~once/week. Weekly, also run one vertical-brainstorm pass to find net-new companies to
> ADD to `claude_universe.csv`. The found-open-role subset stays in `latest.csv`. Chunk size +
> cadence get finalized once we know the universe count.

## Dedup sources

- `data/latest.csv` — the current published list (primary exclusion set).
- Master Google Sheet `1isGMPqH3YpSIMUolmo59mIijiuvplQMeCvAqeuBEn1A`, tab "Copy of Claude list"
  (gid 1623716953) — pass these names into each agent's prompt as an exclusion list.
- `data/claude_universe.csv` — once it exists, also exclude/track against it.

## Finish

`python3 build.py` → verify counts → copy `latest.csv` to `data/YYYY-MM-DD.csv` → commit → push.
