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
- Bash is allowed ONLY for git, `python3 build.py`, `date`, and file ops — not for research.
- **Work inline — do NOT spawn subagents.** Be token-conscious (this draws on a subscription quota):
  don't over-fan-out; stop a vertical as soon as it's dry (see loop rule).

## The bar (ICP — a role qualifies only if it clears ALL)

IC **Account Executive** (NOT SDR/BDR, NOT "Associate AE", NOT Director/VP/RVP) · segment **MM** or
**MM/Ent** preferred (pure **Ent** allowed but tagged so it sorts last) · **US-remote** (not
hybrid/office/non-US) · **OTE ~$150K–$340K** (blank if not reliably known — never guess) · **B2B SaaS** ·
**~4+ yrs** closing (reject 8+ senior-only and junior/BDR).

---

## Job 1 — Re-verify every row in `latest.csv`

WebFetch each row's posting. If it's closed/404/redirected-to-stub, find that company's current open
US-remote IC-AE posting and update the URL; if the company has **no** qualifying open AE role anymore,
**drop the row** from `latest.csv` and set its `claude_universe.csv` row to `Currently Open = N`
(update `Last Checked`). Use the ATS reference below to check fast before falling back to careers pages.

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

## Finish

`python3 build.py` (regenerates `index.html` + `history.html` — NEVER hand-edit those) → copy
`latest.csv` to `data/$(date -u +%F).csv` → `git add -A` → commit
`Weekly refresh <today>: +<added>, -<dropped> (verticals: <names>)` → `git push origin main`
(if rejected: `git pull --rebase` then push; **never force-push**) → print a short summary:
added, dropped, link fixes, new total, universe size, verticals scanned.
