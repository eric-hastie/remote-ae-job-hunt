# Remote AE Market Map

A hand-verified dataset of **remote US Account Executive openings** at B2B SaaS companies, built with an AI-assisted research pipeline that screens against a defined ideal-candidate profile (ICP) and verifies every posting is live.

**[→ View the live site](https://eric-hastie.github.io/remote-ae-job-hunt/)**

---

## Why

Scraped job boards bury a handful of good fits under hundreds of mismatched listings. This project does the opposite - it **defines the bar first, then verifies and filters**, so only roles that actually qualify make the list.

## How it was built

| Step | What happened |
|------|---------------|
| **1 · Defined the ICP** | IC Account Executive, Mid-Market / Enterprise B2B SaaS, US-remote, ~$150-340K OTE, ~4+ yrs closing experience. |
| **2 · Fanned out by vertical** | Parallel research across five lanes - dev tools & infra, fintech & data, vertical SaaS, AI-native, and security - for diverse results. |
| **3 · Verified every posting** | Each role confirmed live, remote, and IC-level against the company's own ATS (Greenhouse / Ashby). Unverifiable roles were dropped - **no fabricated or stale listings.** |
| **4 · De-duped & segmented** | Screened against a 64-company master list to keep only net-new finds, then tagged by segment so mid-market roles sort to the top. |

## The numbers

- **55** verified, qualified roles
- **27** mid-market-friendly (the qualifying lane)
- **5** industry verticals
- **100%** of postings verified live against company ATS
- **120+** companies evaluated; everything off-profile filtered out

## Where this goes next

This is also a prototype for **territory intelligence** in a sales role. Job postings are one of the cleanest buying signals in B2B sales - a company opening a RevOps role, standing up a new region, or scaling its CS team signals budget and active initiatives before intent-data vendors catch it. Pointed at a sales territory, the same pipeline surfaces timing signals on target accounts. And because every run is snapshotted, the signal compounds: an account's week-over-week hiring history tells a story that sharpens account planning - sustained hiring suggests expansion and the right moment to upsell, a freeze can flag churn risk, and a new leader hints at the next initiative.

## Tech & automation

`data/latest.csv` is the canonical dataset; `build.py` regenerates the site (`index.html` plus a History & Trends page) from it - no external dependencies, vanilla-JS search/filter/sort. A scheduled cloud agent re-runs the whole pipeline every week: it re-verifies every live link, scans rotating verticals for net-new roles, writes a dated snapshot, rebuilds, and commits. Every run is version-controlled, so the dated snapshots double as a running time series of how the market moves. Hosted free on GitHub Pages.

## Caveats

Snapshot verified June 2026; postings turn over quickly, so confirm a role is still open before applying. Funding and RepVue figures are from public sources and may be approximate (left blank where not reliably verifiable rather than guessed).

---

*Built by Eric Hastie as a demonstration of GTM research, data curation, and AI-assisted workflow design.*
