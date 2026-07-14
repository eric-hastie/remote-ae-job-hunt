# Remote AE Market Map

A hand-verified dataset of **remote US Account Executive openings** at B2B SaaS companies. I built it with an AI-assisted research pipeline that screens every role against a defined ideal-candidate profile (ICP) and confirms every posting is actually live before it makes the list.

**[→ View the live site](https://eric-hastie.github.io/remote-ae-job-hunt/)**

---

## Why

Scraped job boards bury a handful of great fits under hundreds of mismatched listings, and I got tired of digging. So I flipped the process - **define the bar first, then verify and filter** - and only roles that actually qualify make the cut. (Think of it as running proper discovery on the job market instead of cold-scrolling it.)

## How I built it

| Step | What happened |
|------|---------------|
| **1 · Defined the ICP** | IC Account Executive, Mid-Market / Enterprise B2B SaaS, US-remote, ~$150-340K OTE, ~4+ yrs closing experience. |
| **2 · Fanned out by vertical** | Parallel research across five lanes - dev tools & infra, fintech & data, vertical SaaS, AI-native, and security - for diverse results. |
| **3 · Verified every posting** | Each role confirmed live, remote, and IC-level against the company's own ATS (Greenhouse / Ashby). Anything I couldn't verify got dropped - **no fabricated or stale listings.** |
| **4 · De-duped & segmented** | Screened against a 64-company master list to keep only net-new finds, then tagged by segment so mid-market roles sort to the top. |

## The numbers

- **222** verified, qualified roles (as of July 13, 2026 - the pipeline refreshes weekly, so the live site runs ahead of this page)
- **104** mid-market-friendly (the qualifying lane)
- **222** companies represented - one qualified role per company
- **100%** of postings verified live against company ATS; everything off-profile filtered out

## Where this goes next

Here's the part I'm genuinely excited about: this doubles as a prototype for **territory intelligence** in a sales role. Job postings are one of the cleanest buying signals in B2B sales - a company opening a RevOps role, standing up a new region, or scaling its CS team is telling you about budget and active initiatives before the intent-data vendors catch it. Point this same pipeline at a sales territory and it surfaces timing signals on target accounts. And because every run is snapshotted, the signal compounds: an account's week-over-week hiring history tells a story that sharpens account planning - sustained hiring suggests expansion (and the right moment to upsell), a freeze can flag churn risk, and a new leader hints at the next initiative.

## Tech & automation

`data/latest.csv` is the canonical dataset; `build.py` regenerates the site (`index.html` plus a History & Trends page) from it - no external dependencies, vanilla-JS search/filter/sort. A scheduled cloud agent re-runs the whole pipeline every week: it re-verifies every live link, scans rotating verticals for net-new roles, writes a dated snapshot, rebuilds, and commits. Every run is version-controlled, so the dated snapshots double as a running time series of how the market moves. Hosted free on GitHub Pages.

## Caveats

Snapshot verified June 2026; postings turn over quickly, so confirm a role is still open before applying. Funding and RepVue figures come from public sources and may be approximate (where I couldn't verify a number reliably, I left it blank rather than guess).

---

*I'm Eric Hastie - I built this as a demonstration of GTM research, data curation, and AI-assisted workflow design.*
