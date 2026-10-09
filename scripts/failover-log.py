#!/usr/bin/env python3
"""Turn the output of `ansible-playbook failover.yml` into a step-by-step log.

Reads the playbook output on stdin, prints one line per step as it starts and finishes, with the
wall-clock time and how long the step took, and the messages of the result at the end. The raw
output is kept by the caller (scripts/failover.sh).
"""
import re
import sys
import time

RANK = {"skipped": 0, "ok": 1, "changed": 2, "rescued": 3, "FAILED": 4}
task, status, started, retries, messages, errors = None, None, 0.0, 0, [], []
in_msg = False


def now():
    return time.strftime("%H:%M:%S")


def finish():
    global task
    if task is None:
        return
    took = time.time() - started
    extra = f", {retries} checks" if retries else ""
    print(f"  {status or 'ok'} ({took:.1f}s{extra})", flush=True)
    for e in errors:
        print(f"            ! {e}", flush=True)
    task = None


for raw in sys.stdin:
    line = raw.rstrip("\n")
    m = re.match(r"TASK \[(.+?)\] \*+", line)
    if m:
        finish()
        task, status, started, retries, in_msg = m.group(1), None, time.time(), 0, False
        errors.clear()
        print(f"{now()}  {task} ...", end="", flush=True)
        continue
    if line.startswith(("PLAY RECAP", "PLAY [")):
        finish()
        in_msg = False
        continue
    if task is None:
        continue
    if line.startswith("FAILED - RETRYING"):
        retries += 1
        continue
    m = re.match(r"(ok|changed|skipping|fatal|failed)\b", line)
    if m:
        word = {"skipping": "skipped", "fatal": "FAILED", "failed": "FAILED"}.get(m.group(1), m.group(1))
        if status is None or RANK[word] > RANK[status]:
            status = word
        if word == "FAILED":
            body = re.sub(r"^.*?=> ", "", line)
            hit = (re.search(r"(timeout: [^\\\"]+|refused: [^\\\"]+)", body)
                   or re.search(r'"msg": "((?:[^"\\\\]|\\\\.)*)"', body)
                   or re.search(r'"stderr": "((?:[^"\\\\]|\\\\.)+)"', body))
            errors.append((hit.group(1) if hit else body)[:300])
        in_msg = line.rstrip().endswith("=> {") or line.rstrip().endswith("=>")
        continue
    if in_msg:
        text = line.strip().strip(",").strip()
        if text in ("{", "}", "[", "]", '"msg": [', "msg:", ""):
            continue
        text = re.sub(r'^"?msg"?:\s*', "", text).lstrip("- ").strip('"')
        if text:
            messages.append(text)

finish()
if messages:
    print()
    for t in messages:
        print(f"  {t}")
