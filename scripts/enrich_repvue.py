#!/usr/bin/env python3
"""Fill blank RepVue scores in data/latest.csv from the local RepVue library.

data/repvue_universe.csv is a gitignored local pull of RepVue's company list
(name, slug, industry, repvue_score, ...). Scores there are a point-in-time
snapshot and go stale, which is fine: a stale score is still a useful signal
about the sales org, and the column is blank for most rows today.

Matching is exact-on-normalized-name only. Normalization lowercases, strips
punctuation/whitespace, drops a trailing legal suffix, and uses the base name
before a parenthetical (matching the paren-aware dedup used elsewhere in the
repo). Fuzzy/substring matching is deliberately NOT done: "Chorus" vs
"Chorus.ai" style near-misses are cheap to leave blank and expensive to get
wrong.

Usage:
  python3 scripts/enrich_repvue.py            # dry run, prints what would change
  python3 scripts/enrich_repvue.py --write    # write latest.csv (+ claude_universe.csv)
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "data" / "latest.csv"
UNIVERSE = ROOT / "data" / "claude_universe.csv"
REPVUE = ROOT / "data" / "repvue_universe.csv"

SUFFIXES = {"inc", "inc.", "llc", "ltd", "corp", "co", "company", "gmbh", "plc", "sa", "ag", "bv", "ab", "oy", "as"}

# Normalized names that collide with a DIFFERENT company in RepVue. Verified by
# hand; add here rather than loosening the matcher. Reviewing method: compare our
# Industry + the ATS slug in the posting URL against RepVue's industry bucket.
COLLISIONS = {
    "capsule",   # ours = capsule.video (AI video); RepVue's Capsule = the pharmacy (Healthcare)
}


def normalize(name: str) -> str:
    """Company name -> comparison key."""
    n = (name or "").strip().lower()
    n = n.split("(")[0]                      # paren-aware base: "8am (f/k/a AffiniPay)" -> "8am"
    n = re.sub(r"\s*[,\-|/]\s*(the|an?)\b.*$", "", n)
    n = n.replace("&", " and ")
    words = re.split(r"[\s,]+", n)
    while words and words[-1].strip(".") in SUFFIXES:
        words.pop()
    n = " ".join(words)
    n = re.sub(r"[^a-z0-9]+", "", n)          # drop punctuation entirely: "chorus.ai" -> "chorusai"
    return n


def load_repvue():
    """normalized name -> (display name, score). Ambiguous keys are dropped."""
    best, dupe = {}, set()
    for r in csv.DictReader(REPVUE.open()):
        score = (r.get("repvue_score") or "").strip()
        if not score:
            continue
        key = normalize(r.get("name", ""))
        if not key:
            continue
        if key in best and best[key][1] != score:
            dupe.add(key)
            continue
        best.setdefault(key, (r.get("name", ""), score))
    for k in dupe | COLLISIONS:
        best.pop(k, None)
    return best, dupe


def fmt(score: str) -> str:
    """RepVue shows whole numbers; the API returns e.g. '87.31'."""
    try:
        return str(int(round(float(score))))
    except ValueError:
        return score


def enrich(path: Path, name_col: str, score_col: str, lib, write: bool):
    rows = list(csv.DictReader(path.open()))
    fields = rows[0].keys() if rows else []
    filled, already, missed = [], 0, []
    for r in rows:
        if (r.get(score_col) or "").strip():
            already += 1
            continue
        hit = lib.get(normalize(r[name_col]))
        if hit:
            r[score_col] = fmt(hit[1])
            filled.append((r[name_col], hit[0], r[score_col]))
        else:
            missed.append(r[name_col])
    if write and filled:
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(fields))
            w.writeheader()
            w.writerows(rows)
    return rows, filled, already, missed


def main():
    write = "--write" in sys.argv
    if not REPVUE.exists():
        # The library is gitignored and local-only, so cloud clones don't have it.
        print(f"{REPVUE.name} not present (local-only file) - nothing to enrich.")
        return
    lib, dupes = load_repvue()
    print(f"RepVue library: {len(lib)} usable scored names ({len(dupes)} names dropped as ambiguous)\n")

    for path, name_col, score_col in ((LATEST, "Company", "RepVue"), (UNIVERSE, "Company", "RepVue Score")):
        rows, filled, already, missed = enrich(path, name_col, score_col, lib, write)
        cov = already + len(filled)
        print(f"{path.name}: {len(rows)} rows | had {already} | +{len(filled)} new | now {cov} ({cov*100//max(len(rows),1)}%) | {len(missed)} not in library")
        for co, rvname, sc in sorted(filled, key=lambda x: -float(x[2]))[:15]:
            note = f"  (matched RepVue '{rvname}')" if rvname.lower() != co.lower() else ""
            print(f"    {sc:>4}  {co}{note}")
        if len(filled) > 15:
            print(f"    ... and {len(filled)-15} more")
        print()

    print("WROTE files." if write else "Dry run - re-run with --write to apply, then `python3 build.py`.")


if __name__ == "__main__":
    main()
