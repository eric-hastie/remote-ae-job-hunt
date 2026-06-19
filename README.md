# Remote AE Market Map

A hand-verified dataset of **remote US Account Executive openings** at B2B SaaS companies, built with an AI-assisted research pipeline that screens against a defined ideal-candidate profile (ICP) and verifies every posting is live.

**[→ View the live site](https://eric-hastie.github.io/remote-ae-job-hunt/)**

---

## Why

Scraped job boards bury a handful of good fits under hundreds of mismatched listings. This project does the opposite — it **defines the bar first, then verifies and filters**, so only roles that actually qualify make the list.

## How it was built

| Step | What happened |
|------|---------------|
| **1 · Defined the ICP** | IC Account Executive, Mid-Market / Enterprise B2B SaaS, US-remote, ~$150–340K OTE, ~4+ yrs closing experience. |
| **2 · Fanned out by vertical** | Parallel research across five lanes — dev tools & infra, fintech & data, vertical SaaS, AI-native, and security — for diverse results. |
| **3 · Verified every posting** | Each role confirmed live, remote, and IC-level against the company's own ATS (Greenhouse / Ashby). Unverifiable roles were dropped — **no fabricated or stale listings.** |
| **4 · De-duped & segmented** | Screened against a 64-company master list to keep only net-new finds, then tagged by segment so mid-market roles sort to the top. |

## The numbers

- **55** verified, qualified roles
- **27** mid-market-friendly (the qualifying lane)
- **5** industry verticals
- **100%** of postings verified live against company ATS
- **120+** companies evaluated; everything off-profile filtered out

## Tech

A single self-contained `index.html` — no build step, no dependencies. Search, segment filters, and column sorting in vanilla JavaScript. Hosted free on GitHub Pages.

## Caveats

Snapshot verified June 2026; postings turn over quickly, so confirm a role is still open before applying. Funding and RepVue figures are from public sources and may be approximate (left blank where not reliably verifiable rather than guessed).

---

*Built by Eric Hastie as a demonstration of GTM research, data curation, and AI-assisted workflow design.*
