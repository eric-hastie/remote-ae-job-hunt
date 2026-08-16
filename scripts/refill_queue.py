#!/usr/bin/env python3
"""Rebuild data/scan_queue.csv from the local RepVue universe.

The queue is a RING, not a well. It holds every RepVue company at or above the
score floor, best-score-first. Job 2 walks it 50 at a time; when it reaches the
bottom it starts a new cycle from the TOP, so the highest-scored sales orgs get
re-checked first. Roles churn, so a second pass is real discovery, not waste.

    python3 scripts/refill_queue.py            # the floor: score >= 76
    python3 scripts/refill_queue.py --dry-run  # report counts, don't write

THE SCORE FLOOR IS 76 AND THIS SCRIPT CANNOT GO BELOW IT. `--floor` can only
raise the bar; anything under 76 exits non-zero. A lower floor buys volume by
buying Enterprise-heavy, weak-sales-org companies: MM density concentrates in
the top ranks. On 2026-08-15 the floor was dropped to 70 to refill a dry queue
without asking Eric, and 1,686 sub-76 companies entered the queue. Eric's call,
2026-08-16: pull them back out and rotate instead. Going below 76 takes a
deliberate edit to the FLOOR constant, and that is Eric's decision to make.

Reads (both local; repvue_universe.csv is gitignored, so this is a LOCAL step,
the cloud clone cannot run it):
    data/repvue_universe.csv  cols: name,slug,industry,repvue_score,...
    data/claude_universe.csv  the dedup memory (every company ever evaluated)
Writes:
    data/scan_queue.csv       cols: Company,Slug,Score  (best-score-first)
    data/queue_cycle.txt      resets the rotation cursor to a fresh cycle

Never-checked companies are flagged in the printout but NOT sorted to the front:
scan order is score order, always. scripts/next_batch.py picks each run's 50.
"""
import csv, datetime, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPVUE = os.path.join(REPO, "data", "repvue_universe.csv")
UNIVERSE = os.path.join(REPO, "data", "claude_universe.csv")
QUEUE = os.path.join(REPO, "data", "scan_queue.csv")
CYCLE = os.path.join(REPO, "data", "queue_cycle.txt")

FLOOR = 76.0


def base(name):
    """Dedup key: lowercase, strip a ' (...)' suffix, trim."""
    return name.split(" (")[0].strip().lower()


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    floor = FLOOR
    if "--floor" in args:
        floor = float(args[args.index("--floor") + 1])
    if floor < FLOOR:
        sys.exit(f"REFUSED: floor {floor:g} is below {FLOOR:g}. Lowering the score floor is Eric's "
                 "call, not the script's. Ask him. If he says yes, edit the FLOOR constant; "
                 "--floor can only raise the bar. A dry queue is not a reason (the ring wraps).")

    if not os.path.exists(REPVUE):
        sys.exit(f"ERROR: {REPVUE} not found. RepVue data is local-only (gitignored). "
                 "run this on the machine that has it, not in a cloud clone.")

    evaluated = {base(r["Company"]) for r in csv.DictReader(open(UNIVERSE, newline=""))}

    rows, seen = [], set()
    for r in csv.DictReader(open(REPVUE, newline="")):
        try:
            score = float(r["repvue_score"])
        except (ValueError, KeyError):
            continue
        key = base(r["name"])
        if score >= floor and key not in seen:
            seen.add(key)
            rows.append((score, r["name"], r["slug"]))
    rows.sort(key=lambda x: x[0], reverse=True)

    fresh = sum(1 for _, n, _ in rows if base(n) not in evaluated)
    print(f"floor >= {floor:g}  |  ring size: {len(rows)}  |  never checked: {fresh}  "
          f"|  re-check on this pass: {len(rows) - fresh}")
    if rows:
        print(f"  score range: {rows[0][0]:.1f} -> {rows[-1][0]:.1f}")
        print(f"  top of ring: {rows[0][1]}   bottom: {rows[-1][1]}")
        print(f"  at 250 companies/day, one full cycle = {len(rows) / 250:.1f} days")
    if dry_run:
        print("(--dry-run: nothing written)")
        return

    with open(QUEUE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Company", "Slug", "Score"])
        for score, name, slug in rows:
            w.writerow([name, slug, f"{score:.2f}"])
    today = datetime.date.today().isoformat()
    with open(CYCLE, "w") as f:
        f.write(today + "\n")
    print(f"wrote {QUEUE}: {len(rows)} companies")
    print(f"wrote {CYCLE}: cycle starts {today} (everything in the ring is eligible again)")


if __name__ == "__main__":
    main()
