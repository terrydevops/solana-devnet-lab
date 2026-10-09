#!/usr/bin/env python3
"""Vote credits exporter for Prometheus.

The community solana-exporter reports whether a validator votes (last vote, delinquent) but not
how well: vote credits are missing. Credits are what rewards are paid on. A validator that votes
late on every slot is never delinquent and never alerts, and still earns less than its peers.

Polls getVoteAccounts and serves, for every vote account:

  solana_vote_credits_total          credits since the account was created (a counter)
  solana_vote_credits_epoch          credits earned so far in the current epoch
  solana_vote_credits_current_epoch  the epoch the two values above belong to

Standard library only, so it runs on a host with nothing but python3.
"""
import argparse
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

state = {"body": "", "ok": 0, "last_success": 0.0}
lock = threading.Lock()


def rpc(url, method, params):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.load(resp)
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload["result"]


def render(accounts):
    lines = [
        "# HELP solana_vote_credits_total Vote credits earned since the vote account was created.",
        "# TYPE solana_vote_credits_total counter",
        "# HELP solana_vote_credits_epoch Vote credits earned so far in the current epoch.",
        "# TYPE solana_vote_credits_epoch gauge",
        "# HELP solana_vote_credits_current_epoch Epoch the credit values belong to.",
        "# TYPE solana_vote_credits_current_epoch gauge",
    ]
    for acc in accounts:
        history = acc.get("epochCredits") or []
        if not history:
            continue
        epoch, credits, previous = history[-1]
        labels = f'votekey="{acc["votePubkey"]}",nodekey="{acc["nodePubkey"]}"'
        lines.append(f"solana_vote_credits_total{{{labels}}} {credits}")
        lines.append(f"solana_vote_credits_epoch{{{labels}}} {credits - previous}")
        lines.append(f"solana_vote_credits_current_epoch{{{labels}}} {epoch}")
    return "\n".join(lines) + "\n"


def poll(url, interval):
    while True:
        try:
            result = rpc(url, "getVoteAccounts", [{"keepUnstakedDelinquents": True}])
            body = render(result["current"] + result["delinquent"])
            with lock:
                state.update(body=body, ok=1, last_success=time.time())
        except Exception as err:  # keep serving; the scrape shows the failure
            print(f"poll failed: {err}", flush=True)
            with lock:
                state["ok"] = 0
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        with lock:
            body = (
                state["body"]
                + "# HELP solana_vote_credits_exporter_up 1 if the last RPC poll succeeded.\n"
                + "# TYPE solana_vote_credits_exporter_up gauge\n"
                + f"solana_vote_credits_exporter_up {state['ok']}\n"
                + "# HELP solana_vote_credits_exporter_last_success_seconds Unix time of the last good poll.\n"
                + "# TYPE solana_vote_credits_exporter_last_success_seconds gauge\n"
                + f"solana_vote_credits_exporter_last_success_seconds {state['last_success']}\n"
            )
        data = body.encode()
        self.send_response(200)
        self.send_header("content-type", "text/plain; version=0.0.4")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # one line per scrape is noise
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8899")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9102)
    parser.add_argument("--interval", type=float, default=10.0, help="seconds between polls")
    args = parser.parse_args()

    threading.Thread(target=poll, args=(args.rpc_url, args.interval), daemon=True).start()
    print(f"listening on {args.listen}:{args.port}, polling {args.rpc_url}", flush=True)
    HTTPServer((args.listen, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
