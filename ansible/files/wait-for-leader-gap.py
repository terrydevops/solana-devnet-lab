#!/usr/bin/env python3
"""Wait until a validator identity has no leader slot for the next N slots.

The leader schedule of an epoch is public, so the wait is a lookup, not a guess. This is the
slot-level version of `agave-validator wait-for-restart-window`, whose smallest window is one
minute: too long for a validator that is leader every few seconds, as in this lab.

    wait-for-leader-gap.py --url http://rpc:8899 --identity <pubkey> --min-idle-slots 20

Exit 0 as soon as the gap is there (the caller must act at once), 1 on timeout or when too
much stake is delinquent. Prints one line with the slot numbers it decided on.
"""
import argparse
import json
import subprocess
import sys
import time


def solana(url, *args):
    out = subprocess.check_output(["solana", "-u", url, *args, "--output", "json"], text=True)
    return json.loads(out)


def leader_slots(url, identity):
    """Leader slots of the identity in the current epoch, and the epoch's last slot."""
    info = solana(url, "epoch-info")
    last = info["absoluteSlot"] - info["slotIndex"] + info["slotsInEpoch"] - 1
    entries = solana(url, "leader-schedule")["leaderScheduleEntries"]
    return sorted(e["slot"] for e in entries if e["leader"] == identity), last


def delinquent_percent(url):
    v = solana(url, "validators")
    total = v["totalActiveStake"]
    return 100.0 * v["totalDelinquentStake"] / total if total else 0.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--identity", required=True)
    p.add_argument("--min-idle-slots", type=int, default=20)
    p.add_argument("--max-delinquent-stake", type=float, default=5.0, help="percent")
    p.add_argument("--timeout", type=float, default=300.0, help="seconds")
    a = p.parse_args()

    bad = delinquent_percent(a.url)
    if bad > a.max_delinquent_stake:
        print(f"refused: {bad:.1f}% of stake is delinquent, limit {a.max_delinquent_stake}%")
        return 1

    deadline = time.time() + a.timeout
    mine, last = leader_slots(a.url, a.identity)
    waited_from = None
    while time.time() < deadline:
        slot = int(subprocess.check_output(["solana", "-u", a.url, "slot"], text=True))
        if waited_from is None:
            waited_from = slot
        if slot > last:                      # epoch boundary: the schedule is a new one
            mine, last = leader_slots(a.url, a.identity)
            continue
        upcoming = [s for s in mine if s >= slot]
        # Past the last leader slot of the epoch, the next epoch's schedule decides; only the
        # slots left in this epoch are known to be free.
        next_leader = upcoming[0] if upcoming else last + 1
        gap = next_leader - slot
        if gap >= a.min_idle_slots:
            what = f"next leader slot {next_leader}" if upcoming else f"no leader slot left before the epoch ends at {last}"
            print(f"window: slot {slot}, {what}, {gap} slots idle "
                  f"(wanted {a.min_idle_slots}, waited {slot - waited_from} slots)")
            return 0
        time.sleep(0.1)
    print(f"timeout: no gap of {a.min_idle_slots} slots within {a.timeout:.0f} s")
    return 1


if __name__ == "__main__":
    sys.exit(main())
