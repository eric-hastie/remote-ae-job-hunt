#!/usr/bin/env python3
"""One-time repair: put back the rows the 2026-08-25/26 truncations dropped.

Recovers from git rather than from anything held in context, appends to the file
on disk, and counts at both ends. Rows come back marked "Needs check" so Job 1
re-verifies them on the next run; their original Date Added is preserved so the
history page shows when they really entered the list.

Held back: rows whose company the routine has re-checked and marked
Currently Open = N on or after 2026-08-25, i.e. after the loss. Those are the
pipeline's current knowledge and re-adding them would republish known-dead roles.
"""
import csv, io, os, subprocess, sys
sys.path.insert(0, "scripts")
from bar import base

CUTOFF = "2026-08-25"
EVENTS = [("769c4c5", "d35350b"), ("abd339b", "437f3fc")]
LATEST = "data/latest.csv"


def load(rev):
    t = subprocess.run(["git", "show", f"{rev}:{LATEST}"], capture_output=True, text=True).stdout
    return list(csv.DictReader(io.StringIO(t)))


def main():
    cur = list(csv.DictReader(open(LATEST, newline="", encoding="utf-8")))
    cols = list(cur[0].keys())
    have_url = {(r["Company"].strip(), (r["Job Posting URL"] or "").strip()) for r in cur}
    have_role = {(r["Company"].strip(), (r.get("Title") or "").strip()) for r in cur}

    lost = {}
    for rev, par in EVENTS:
        after = {(r["Company"].strip(), (r["Job Posting URL"] or "").strip()) for r in load(rev)}
        for r in load(par):
            k = (r["Company"].strip(), (r["Job Posting URL"] or "").strip())
            if k not in after and k not in have_url:
                lost[k] = r
    print(f"recoverable from git: {len(lost)}")

    uni = {}
    for r in csv.DictReader(open("data/claude_universe.csv", newline="", encoding="utf-8")):
        uni.setdefault(base(r["Company"]), r)

    restore, held, dup = [], [], 0
    for k, r in lost.items():
        u = uni.get(base(r["Company"]))
        # A closure recorded only as "speedrun board: not flagged remote" rests on
        # the a16z board's own location label, which ROUTINE.md's URL-capture rule 4
        # says never to trust ("verify remote from the JD text, not the board's
        # location label"), and which merge_speedrun.py's own docstring says is not a
        # complete mirror of the company's board. Those rows come back and let
        # verify_links.py test the real posting. Substantive closures stay held.
        board_label_only = "speedrun board" in (u or {}).get("Notes", "")
        if (u and u["Currently Open"] == "N" and u["Last Checked"][:10] >= CUTOFF
                and not board_label_only):
            held.append((r, u))
            continue
        rk = (r["Company"].strip(), (r.get("Title") or "").strip())
        if rk in have_role:          # same role already listed under a sibling URL
            dup += 1
            continue
        have_role.add(rk)
        row = {c: r.get(c, "") for c in cols}
        row["Status"] = "Needs check"
        restore.append(row)

    print(f"held back (closed after the loss): {len(held)}")
    print(f"skipped as same company+title already listed: {dup}")
    print(f"to restore: {len(restore)}")

    before_rows = len(cur)
    before_bytes = os.path.getsize(LATEST)
    with open(LATEST, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=cols).writerows(restore)

    after = list(csv.DictReader(open(LATEST, newline="", encoding="utf-8")))
    print(f"\nCOUNT AT BOTH ENDS")
    print(f"  before: {before_rows} rows, {before_bytes:,} bytes")
    print(f"  after:  {len(after)} rows, {os.path.getsize(LATEST):,} bytes")
    print(f"  expected {before_rows + len(restore)} -> "
          f"{'MATCH' if len(after) == before_rows + len(restore) else 'MISMATCH'}")
    if len(after) != before_rows + len(restore):
        sys.exit("REFUSED: row count does not match. Inspect before committing.")
    for r, u in held:
        print(f"  held: {r['Company'][:30]:32} {u['Last Checked'][:10]}  {u['Notes'][:46]}")


if __name__ == "__main__":
    main()
