#!/usr/bin/env python3
"""Pick this run's Job 2 batch off the scan-queue ring. Deterministic, no judgment.

    python3 scripts/next_batch.py          # next 50, as CSV on stdout
    python3 scripts/next_batch.py 25       # next 25
    python3 scripts/next_batch.py --status # just the cursor report, no batch

The queue (data/scan_queue.csv) is a RING of RepVue companies at score >= 76,
sorted best-score-first. A cycle marker (data/queue_cycle.txt) is the cursor:

  eligible = queue rows never evaluated, OR whose `Last Checked` in
             claude_universe.csv is EARLIER than the cycle start date

Each run takes the top `n` eligible rows in score order. When nothing is
eligible the ring has been fully walked, so this starts a new cycle (writes
today's date to the marker) and hands back the top of the ring again. The queue
NEVER goes dry: exhausting it means rotating back to the highest-scored
companies, which is the whole point.

Runs in the cloud clone: both inputs are committed. RepVue's raw library is not
needed here (the Score column is carried in the queue file itself).

Date granularity note: rows checked earlier on the same day a new cycle opens
are skipped for that cycle and picked up on the next one. That is at most one
run's worth of companies, and it is the price of `Last Checked` being date-only.
"""
import csv, datetime, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(REPO, "data", "scan_queue.csv")
UNIVERSE = os.path.join(REPO, "data", "claude_universe.csv")
CYCLE = os.path.join(REPO, "data", "queue_cycle.txt")


def base(name):
    return name.split(" (")[0].strip().lower()


def load_cycle():
    if os.path.exists(CYCLE):
        text = open(CYCLE).read().strip()
        if text:
            return text
    return start_cycle()


def start_cycle():
    today = datetime.date.today().isoformat()
    with open(CYCLE, "w") as f:
        f.write(today + "\n")
    return today


def eligible_rows(queue, checked, cycle_start):
    """Queue rows not yet visited in this cycle, in queue (score) order."""
    out = []
    for row in queue:
        last = checked.get(base(row["Company"]), "")
        if not last or last < cycle_start:
            out.append(row)
    return out


def main():
    args = sys.argv[1:]
    status_only = "--status" in args
    args = [a for a in args if not a.startswith("--")]
    n = int(args[0]) if args else 50

    queue = list(csv.DictReader(open(QUEUE, newline="")))
    checked = {}
    for r in csv.DictReader(open(UNIVERSE, newline="")):
        key = base(r["Company"])
        last = (r.get("Last Checked") or "").strip()
        if last > checked.get(key, ""):
            checked[key] = last

    cycle_start = load_cycle()
    pending = eligible_rows(queue, checked, cycle_start)

    wrapped = False
    if not pending:
        cycle_start = start_cycle()
        pending = eligible_rows(queue, checked, cycle_start)
        wrapped = True

    done = len(queue) - len(pending)
    sys.stderr.write(
        f"ring {len(queue)} | cycle started {cycle_start} | walked {done} | "
        f"remaining this cycle {len(pending)}"
        + ("  <- WRAPPED: new cycle, restarting from the highest scores\n" if wrapped else "\n")
    )
    if status_only:
        return

    batch = pending[:n]
    w = csv.writer(sys.stdout)
    w.writerow(["Company", "Slug", "Score"])
    for row in batch:
        w.writerow([row["Company"], row["Slug"], row.get("Score", "")])


if __name__ == "__main__":
    main()
