#!/usr/bin/env python3
"""Rebuild data/scan_queue.csv from the local RepVue universe.

The discovery queue is a finite well: RepVue companies at/above a score threshold,
minus every company already evaluated (data/claude_universe.csv). Job 2 walks it
until it's dry. When it dries up, re-run this to refill with the next score band.

    python3 scripts/refill_queue.py            # default threshold 78.0
    python3 scripts/refill_queue.py 76         # lower the bar to 76.0
    python3 scripts/refill_queue.py --dry-run  # report counts, don't write

Reads (both local; repvue_universe.csv is gitignored — this is a LOCAL step, the
cloud clone can't run it):
    data/repvue_universe.csv  cols: name,slug,industry,repvue_score,...
    data/claude_universe.csv  the dedup memory (every company ever evaluated)
Writes:
    data/scan_queue.csv       cols: Company,Slug  (best-score-first, net-new only)

Dedup matches the routine's rule: lowercase name, dropped " (...)" suffix, so
"Tableau (Salesforce)" collides with "tableau".
"""
import csv, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPVUE = os.path.join(REPO, "data", "repvue_universe.csv")
UNIVERSE = os.path.join(REPO, "data", "claude_universe.csv")
QUEUE = os.path.join(REPO, "data", "scan_queue.csv")


def base(name):
    """Dedup key: lowercase, strip a ' (...)' suffix, trim."""
    return name.split(" (")[0].strip().lower()


def main():
    args = [a for a in sys.argv[1:]]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    threshold = float(args[0]) if args else 78.0

    if not os.path.exists(REPVUE):
        sys.exit(f"ERROR: {REPVUE} not found. RepVue data is local-only (gitignored) — "
                 "run this on the machine that has it, not in a cloud clone.")

    evaluated = {base(r["Company"]) for r in csv.DictReader(open(UNIVERSE, newline=""))}

    rows = []
    for r in csv.DictReader(open(REPVUE, newline="")):
        try:
            score = float(r["repvue_score"])
        except (ValueError, KeyError):
            continue
        if score >= threshold and base(r["name"]) not in evaluated:
            rows.append((score, r["name"], r["slug"]))
    rows.sort(key=lambda x: x[0], reverse=True)  # best score first

    print(f"threshold >= {threshold:g}  |  evaluated (universe): {len(evaluated)}  "
          f"|  net-new for queue: {len(rows)}")
    if rows:
        print(f"  score range: {rows[0][0]:.1f} -> {rows[-1][0]:.1f}")
        print(f"  first: {rows[0][1]}   last: {rows[-1][1]}")
    if dry_run:
        print("(--dry-run: scan_queue.csv NOT written)")
        return

    with open(QUEUE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Company", "Slug"])
        for _, name, slug in rows:
            w.writerow([name, slug])
    print(f"wrote {QUEUE}: {len(rows)} companies")


if __name__ == "__main__":
    main()
