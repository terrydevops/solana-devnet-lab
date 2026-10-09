#!/usr/bin/env python3
"""Build grafana/dashboards/solana-overview.json.

The dashboard is generated so the panel list stays readable and reviewable here instead of in a
thousand lines of JSON. Rows follow the same five layers as the alert rules, top-down.

    python3 scripts/build-dashboard.py            # write the JSON
    python3 scripts/build-dashboard.py --exprs    # print datasource and query, one per line
"""
import json
import pathlib
import sys

DS = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
OUT = pathlib.Path(__file__).resolve().parent.parent / "grafana/dashboards/solana-overview.json"

# (title, type, width, unit, [(expr, legend)], description[, datasource])
# Panels read Prometheus unless a datasource is given.
LAYERS = [
    ("Layer 1: cluster. Is the chain moving and agreeing?", [
        ("Cluster root slot", "stat", 4, "none",
         [("max(solana_cluster_root_slot)", "root")],
         "Newest slot that can no longer be rolled back."),
        ("Epoch", "stat", 3, "none", [("max(solana_node_epoch_number)", "epoch")], ""),
        ("Validators", "stat", 4, "none",
         [('solana_cluster_validator_count{state="current"}', "current"),
          ('solana_cluster_validator_count{state="delinquent"}', "delinquent")], ""),
        ("Firing alerts", "stat", 3, "none",
         [('count(ALERTS{alertstate="firing"}) or vector(0)', "firing")], ""),
        ("Slots per second", "timeseries", 10, "none",
         [("rate(solana_node_slot_height[1m])", "{{node}}")],
         "Flat at zero means the node stopped following the chain."),
        ("Root and last vote of the cluster", "timeseries", 12, "none",
         [("max(solana_cluster_last_vote)", "last vote"),
          ("max(solana_cluster_root_slot)", "root")],
         "The gap between the two is how far finality trails the tip."),
        ("Cluster skip rate, last hour", "timeseries", 12, "percentunit",
         [("solana:cluster_skip_rate:1h", "cluster")], ""),
    ]),
    ("Layer 2: validators. Are we voting and producing our leader slots?", [
        ("Which host runs a voting identity", "state-timeline", 16, "none",
         [("max by (node) (solana_node_identity and on (identity) label_replace("
           "group by (nodekey) (solana_validator_last_vote), \"identity\", \"$1\", \"nodekey\", \"(.+)\"))"
           " or max by (node) (solana_node_identity) * 0", "{{node}}")],
         "One row per host. A failover shows as two rows changing colour at the same moment."),
        ("Hosts per voting identity", "stat", 8, "none",
         [("solana:voting_identity_hosts:count", "{{identity}}")],
         "Must be 1. 2 pages at once (VotingIdentityOnTwoHosts); missing pages after 30 s."),
        ("Identity each host runs", "table", 24, "none",
         [("count by (node, role, identity) (solana_node_identity)", "")], ""),
        ("Vote lag behind the cluster (slots)", "timeseries", 12, "none",
         [("solana:validator_vote_lag:slots", "{{nodekey}}")],
         "ValidatorVoteLagging pages above 50."),
        ("Delinquent", "timeseries", 12, "none",
         [("solana_validator_delinquent", "{{nodekey}}")],
         "1 = the cluster marks this validator as delinquent."),
        ("Skip rate per validator, last hour", "timeseries", 12, "percentunit",
         [("solana:validator_skip_rate:1h", "{{nodekey}}")], ""),
        ("Leader slots per minute", "timeseries", 12, "none",
         [("sum by (nodekey, status) (rate(solana_validator_leader_slots_total[5m])) * 60",
           "{{nodekey}} {{status}}")], ""),
        ("Vote credits, share of the best validator", "timeseries", 12, "percentunit",
         [("solana:validator_credits_ratio:10m", "{{nodekey}}")],
         "Voting late earns fewer credits without ever being delinquent."),
        ("Vote credits earned this epoch", "timeseries", 12, "none",
         [("solana_vote_credits_epoch", "{{nodekey}}")], "Resets at every epoch boundary."),
        ("Active stake (SOL)", "timeseries", 12, "none",
         [("solana_validator_active_stake", "{{nodekey}}")],
         "Decides the share of leader slots."),
        ("Stake share of the cluster", "timeseries", 12, "percentunit",
         [("solana:validator_stake_share:ratio", "{{nodekey}}")],
         "The share decides the leader slots. ValidatorStakeShareDropped opens a ticket."),
        ("Root slot per validator", "timeseries", 12, "none",
         [("solana_validator_root_slot", "{{nodekey}}")], ""),
    ]),
    ("Layer 3: funds. Can we still pay for votes?", [
        ("Identity balance (SOL)", "timeseries", 12, "none",
         [("solana:identity_balance:sol", "{{address}}")],
         "Every vote is paid from this account."),
        ("SOL spent per hour", "timeseries", 12, "none",
         [("-delta(solana:identity_balance:sol[1h])", "{{address}}")],
         "Positive = the balance is falling. Balance divided by this is the hours left."),
    ]),
    ("Layer 4: nodes. Is each node healthy and caught up?", [
        ("Healthy", "stat", 8, "none", [("solana_node_is_healthy", "{{node}}")],
         "getHealth as seen from the node itself."),
        ("Slots behind", "timeseries", 8, "none",
         [("solana_node_num_slots_behind", "{{node}}")], ""),
        ("Version", "table", 8, "none",
         [("count by (node, version) (solana_node_version)", "")], ""),
    ]),
    ("Layer 5: foundation. Hosts, services and the monitoring itself", [
        ("Free space on the ledger volume", "timeseries", 12, "bytes",
         [('node_filesystem_avail_bytes{mountpoint="/mnt/ledger"}', "{{node}}")],
         "All hosts share one disk in this lab, so the lines overlap."),
        ("Hours until the disk is full, at the rate of the last hour", "timeseries", 12, "h",
         [('node_filesystem_avail_bytes{mountpoint="/mnt/ledger"}'
           ' / clamp_min(-deriv(node_filesystem_avail_bytes{mountpoint="/mnt/ledger"}[1h]), 1)'
           ' / 3600', "{{node}}")],
         "The same idea as HostDiskWillFillSoon, shown as a number."),
        ("sol.service restarts in the last 15 minutes", "timeseries", 8, "none",
         [('increase(node_systemd_service_restart_total{name="sol.service"}[15m])', "{{node}}")],
         "Restart=on-failure hides a crash loop; this shows it."),
        ("sol.service active", "stat", 8, "none",
         [('node_systemd_unit_state{name="sol.service",state="active"}', "{{node}}")],
         "The spare host is expected to show 0."),
        ("Memory available", "timeseries", 8, "percentunit",
         [("node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes", "{{node}}")], ""),
        ("Scrape targets up", "timeseries", 12, "none",
         [("up", "{{job}} {{node}}")], "A dead exporter looks exactly like a quiet system."),
        ("Notifications delivered to the sink", "timeseries", 12, "none",
         [("increase(alert_sink_alerts_total[15m])", "{{status}}")], ""),
    ]),
    ("Logs. What the validators say about it", [
        ("Warnings and errors per minute", "timeseries", 12, "none",
         [('sum by (node, level) (count_over_time({job="solana-validator", level=~"WARN|ERROR"}[1m]))',
           "{{node}} {{level}}")],
         "From the validator log files, shipped by Alloy.", LOKI),
        ("Log lines per second", "timeseries", 12, "none",
         [('sum by (node) (rate({job="solana-validator"}[1m]))', "{{node}}")],
         "A validator that stops logging has stopped.", LOKI),
        ("Errors", "logs", 24, "none",
         [('{job="solana-validator", level="ERROR"}', "")], "", LOKI),
        ("systemd journal of sol.service", "logs", 24, "none",
         [('{job="systemd"}', "")],
         "What the start script printed before the validator opened its own log.", LOKI),
    ]),
]

HEIGHT = {"stat": 4, "timeseries": 8, "table": 8, "logs": 8, "state-timeline": 4}


def build():
    panels, pid, y = [], 1, 0
    for title, items in LAYERS:
        panels.append({"id": pid, "type": "row", "title": title, "collapsed": False,
                       "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}})
        pid += 1
        y += 1
        x, row_h = 0, 0
        for name, kind, width, unit, targets, desc, *rest in items:
            ds = rest[0] if rest else DS
            h = HEIGHT[kind]
            if x + width > 24:
                x, y, row_h = 0, y + row_h, 0
            panel = {
                "id": pid, "type": kind, "title": name, "description": desc, "datasource": ds,
                "gridPos": {"x": x, "y": y, "w": width, "h": h},
                "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
                "targets": [
                    {"refId": chr(65 + i), "expr": expr, "legendFormat": legend, "datasource": ds,
                     **({"instant": True, "format": "table"} if kind == "table" else {})}
                    for i, (expr, legend) in enumerate(targets)
                ],
            }
            if kind == "state-timeline":
                panel["fieldConfig"]["defaults"]["mappings"] = [{"type": "value", "options": {
                    "1": {"text": "voting identity", "color": "green", "index": 0},
                    "0": {"text": "unstaked identity", "color": "gray", "index": 1}}}]
                panel["fieldConfig"]["defaults"]["color"] = {"mode": "fixed", "fixedColor": "gray"}
                panel["options"] = {"showValue": "always", "mergeValues": True, "rowHeight": 0.8,
                                    "legend": {"showLegend": False}}
            if kind == "stat":
                panel["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]},
                                    "textMode": "value_and_name", "colorMode": "none"}
            panels.append(panel)
            pid += 1
            x += width
            row_h = max(row_h, h)
        y += row_h
    return {
        "uid": "solana-overview", "title": "Solana cluster overview", "tags": ["solana"],
        "schemaVersion": 39, "version": 1, "editable": False, "refresh": "10s",
        "time": {"from": "now-30m", "to": "now"}, "timezone": "utc", "panels": panels,
    }


if __name__ == "__main__":
    if "--exprs" in sys.argv:
        for _, items in LAYERS:
            for item in items:
                source = "loki" if len(item) > 6 else "prometheus"
                for expr, _ in item[4]:
                    print(f"{source}\t{expr}")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(build(), indent=2) + "\n")
        print(f"wrote {OUT}")
