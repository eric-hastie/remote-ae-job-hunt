#!/usr/bin/env python3
"""Refuse to publish a run that silently drops most of data/latest.csv.

Why this exists: on 2026-08-25 and 2026-08-26 two refresh runs rewrote
data/latest.csv from a partial read of it, losing the tail of the file. The
runs reported "-1" in their commit subjects while actually removing 358 and
366 rows (291 and 313 whole companies). Nothing compared the file about to be
published against the file published last time, so both runs committed, built
and pushed with no complaint. 658 verified roles are still missing, and the
first anyone noticed was Eric reading a hole in the list five days later.

The loss is silent by construction: a truncated CSV is a valid CSV, and
build.py renders it happily.

Run this BEFORE the snapshot copy and BEFORE the commit, as its own step. A
check inside the same command block as the write it guards cannot stop that
write.

  python3 scripts/check_no_silent_loss.py
  python3 scripts/check_no_silent_loss.py --dropped 3

Thresholds are set from the repo's own history, not guessed. Across the 289
legitimate transitions in the log, the worst single run removed 34 rows and
made 24 companies disappear. The two bad runs removed 358 and 366 rows and
291 and 313 companies. The defaults below sit in that gap, so every run this
project has ever legitimately made passes and both real incidents are refused
by a wide margin.

--dropped is advisory. It prints a WARN when more rows vanish than the run
meant to remove, but it does not refuse, because the routine's own drop count
is approximate and a gate that cries wolf gets switched off.

Exit codes:
  0  within thresholds (a WARN may still be printed)
  1  refused: bulk loss
  2  refused: the gate could not scan a real baseline. Never a pass.
"""
import argparse
import csv
import io
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = os.path.join(REPO, "data", "latest.csv")
REL = "data/latest.csv"


def company(row):
    return (row.get("Company") or "").strip()


def rowkey(row):
    return (company(row), (row.get("Job Posting URL") or "").strip())


def parse(text, label):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        print(f"REFUSED: {label} parsed to 0 rows. An empty scope is not a pass.",
              file=sys.stderr)
        sys.exit(2)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dropped", type=int, default=None,
                    help="rows this run meant to remove; prints a WARN if exceeded")
    ap.add_argument("--max-companies", type=int, default=40,
                    help="refuse if more companies than this vanish (legit max: 24)")
    ap.add_argument("--max-rows", type=int, default=60,
                    help="refuse if more rows than this vanish (legit max: 34)")
    ap.add_argument("--baseline", help="compare against this file instead of HEAD")
    ap.add_argument("--candidate", default=LATEST)
    args = ap.parse_args()

    if args.baseline:
        if not os.path.exists(args.baseline):
            print(f"REFUSED: baseline {args.baseline} does not exist.", file=sys.stderr)
            sys.exit(2)
        base_text = open(args.baseline, encoding="utf-8").read()
        base_label = args.baseline
    else:
        proc = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{REL}"],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"REFUSED: no committed {REL} to compare against.", file=sys.stderr)
            sys.exit(2)
        base_text, base_label = proc.stdout, f"HEAD:{REL}"

    if not os.path.exists(args.candidate):
        print(f"REFUSED: candidate {args.candidate} does not exist.", file=sys.stderr)
        sys.exit(2)

    before = parse(base_text, base_label)
    after = parse(open(args.candidate, encoding="utf-8").read(), args.candidate)

    after_rows = set(map(rowkey, after))
    after_cos = {company(r) for r in after}
    lost_rows = [r for r in before if rowkey(r) not in after_rows]
    lost_cos = sorted({company(r) for r in before} - after_cos)

    # State the scope every run, passing or failing. A gate that says nothing
    # about what it read cannot be trusted when it says nothing about what it
    # found.
    print(f"baseline  {base_label}: {len(before)} rows, "
          f"{len({company(r) for r in before})} companies")
    print(f"candidate {args.candidate}: {len(after)} rows, {len(after_cos)} companies")
    print(f"rows gone: {len(lost_rows)} (ceiling {args.max_rows}) | "
          f"companies gone: {len(lost_cos)} (ceiling {args.max_companies})")

    if lost_rows:
        print("removed:")
        for r in lost_rows[:30]:
            print(f"  - {company(r)} | {r.get('Title','')} | "
                  f"added {r.get('Date Added','')} | {r.get('Status','')}")
        if len(lost_rows) > 30:
            print(f"  ... and {len(lost_rows) - 30} more")

    failed = False
    if len(lost_cos) > args.max_companies:
        print(f"REFUSED: {len(lost_cos)} companies vanished, above the ceiling of "
              f"{args.max_companies}.", file=sys.stderr)
        failed = True
    if len(lost_rows) > args.max_rows:
        print(f"REFUSED: {len(lost_rows)} rows vanished, above the ceiling of "
              f"{args.max_rows}.", file=sys.stderr)
        failed = True
    if failed:
        print(f"Do NOT snapshot, build, commit or push. Recover with "
              f"`git show HEAD:{REL} > {REL}` and redo the run's edits on top.",
              file=sys.stderr)
        return 1

    if args.dropped is not None and len(lost_rows) > args.dropped:
        print(f"WARN: {len(lost_rows)} rows gone but {args.dropped} declared. "
              f"Within ceilings, so not refused, but check the list above.")

    print("OK: no bulk loss.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
