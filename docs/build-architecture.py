#!/usr/bin/env python3
"""Build docs/architecture.svg, the diagram shown in the README.

    python3 docs/build-architecture.py
"""
import pathlib
from xml.sax.saxutils import escape as esc

OUT = pathlib.Path(__file__).resolve().parent / "architecture.svg"
W, H = 1200, 908
GREEN, YELLOW, BLUE = ("#d5e8d4", "#82b366"), ("#fff2cc", "#d6b656"), ("#dae8fc", "#6c8ebf")
GREY, RED = ("#f0f0f0", "#888888"), ("#f8cecc", "#b85450")

o = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
    'font-family="Helvetica, Arial, sans-serif">',
    '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#444"/></marker></defs>',
    f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
]


def group(x, y, w, h, title):
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fafafa" stroke="#999" stroke-dasharray="6 4"/>')
    o.append(f'<text x="{x + 16}" y="{y + 26}" font-size="16" font-weight="bold" fill="#333">{esc(title)}</text>')


def box(x, y, w, h, colours, lines, emphasis=()):
    """First line is the title. Lines listed in `emphasis` (by index) are bold."""
    fill, stroke = colours
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    ty = y + 26
    for i, t in enumerate(lines):
        bold = ' font-weight="bold"' if i == 0 or i in emphasis else ''
        size, colour = (15, "#111") if i == 0 else (13, "#333")
        o.append(f'<text x="{x + w / 2}" y="{ty}" font-size="{size}" text-anchor="middle" fill="{colour}"{bold}>{esc(t)}</text>')
        ty += 20 if i == 0 else 18


def arrow(x1, y1, x2, y2, both=False, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ''
    start = ' marker-start="url(#a)"' if both else ''
    o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#444" stroke-width="1.8"{dash}{start} marker-end="url(#a)"/>')


def label(x, y, text, anchor="middle", size=12.5):
    o.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="#222">{esc(text)}</text>')


# ---- control machine ----------------------------------------------------------------------
group(40, 24, 1120, 138, "Control machine")
box(70, 62, 300, 84, GREY, ["Ansible playbooks", "host setup, genesis, join, stake,", "failover, reset, monitoring agents"])
box(450, 62, 300, 84, GREY, ["solana CLI", "stake, vote-account and", "status commands over RPC"])
box(830, 62, 300, 84, RED, ["Keys that never reach a host", "withdraw authority of the vote account,", "delegator wallets and stake accounts"])
arrow(830, 104, 750, 104, dashed=True)
label(790, 96, "signs", size=12)

# ---- cluster ------------------------------------------------------------------------------
group(40, 232, 1120, 350, "Docker network 172.30.0.0/24: four systemd hosts, each with ledger / accounts / snapshots volumes")
HOSTS = [
    (70, GREEN, ["bootstrap  .11", "genesis validator, no spare", "10,000 SOL of stake written into genesis",
                 "syncs, votes, produces blocks"]),
    (340, GREEN, ["validator2  .12", "joined later; primary", "stake delegated by three delegators",
                  "syncs, votes, produces blocks"]),
    (610, YELLOW, ["spare  .14", "hot spare for validator2", "unstaked identity until a switch",
                   "syncs only"]),
    (880, BLUE, ["rpc  .13", "RPC node", "keeps transaction history",
                 "syncs only, answers queries"]),
]
# the pair that is operated like a production validator
o.append('<rect x="330" y="290" width="540" height="120" rx="12" fill="none" stroke="#6c8ebf" stroke-width="2" stroke-dasharray="8 5"/>')
for x, colours, lines in HOSTS:
    box(x, 296, 250, 108, colours, lines, emphasis=(3,))
label(330, 284, "blocks, votes")
arrow(320, 350, 340, 350, both=True)
label(600, 284, "identity switch")
arrow(590, 350, 610, 350, both=True, dashed=True)
label(195, 428, "stands in for the rest of the network", size=12.5)
label(600, 428, "the validator we operate: withdraw authority offline, hot spare, scripts/failover.sh", size=12.5)
label(600, 462, "All four run the same agave-validator binary as a systemd service, and all four sync the chain:", size=13)
label(600, 481, "they gossip with each other, receive every block, replay it and store it. Start-up flags decide the rest.", size=13)
label(600, 510, "Voting costs a fee per slot and needs a funded identity. The spare and the RPC node do not vote, so they cost nothing on chain.", size=13)
label(600, 539, "A switch waits for a gap in the leader schedule, moves the tower file with a checksum, and rolls back a failed takeover.", size=13)
label(600, 564, "On every host: node_exporter, solana-exporter and Alloy, also as systemd services.", size=13)

# ---- control -> cluster -------------------------------------------------------------------
arrow(220, 146, 220, 232)
label(232, 196, "configures every host", anchor="start")
o.append('<line x1="600" y1="146" x2="600" y2="196" stroke="#444" stroke-width="1.8"/>')
o.append('<line x1="600" y1="196" x2="1005" y2="196" stroke="#444" stroke-width="1.8"/>')
arrow(1005, 196, 1005, 296)
label(800, 188, "RPC on 127.0.0.1:8999")

# ---- monitoring ---------------------------------------------------------------------------
MY = 652                                   # top of the monitoring group
group(40, MY, 1120, 232, "Monitoring stack")
label(56, MY + 48, "Alert rules in five layers: 1 cluster, 2 validators, 3 funds, 4 nodes, 5 foundation (hosts and the monitoring itself).",
      anchor="start", size=13)
label(56, MY + 67, "Three priorities: p1 page now, p2 tell the on-call, p3 ticket. The same fault is p1 on the staked host and p2 on the spare.", anchor="start", size=13)
box(70, MY + 86, 180, 92, GREY, ["Loki", "validator logs and", "the service journal"])
box(290, MY + 86, 210, 92, GREY, ["Prometheus", "29 alerts in three priorities,", "each with a runbook; unit tests"])
box(540, MY + 86, 190, 92, GREY, ["Alertmanager", "routes by severity,", "inhibits by cause"])
box(770, MY + 86, 140, 92, GREY, ["Alert sink", "stands in for a pager,", "counts deliveries"])
box(950, MY + 86, 180, 92, GREY, ["Grafana", "opens with one row per validator:", "host, stake, balance, days left"])
arrow(500, MY + 132, 540, MY + 132)
arrow(730, MY + 132, 770, MY + 132)
label(520, MY + 124, "fires", size=11.5)
label(750, MY + 124, "notifies", size=11.5)
# Grafana reads both stores: a bus under the row
for x in (160, 395):
    o.append(f'<line x1="{x}" y1="{MY + 178}" x2="{x}" y2="{MY + 206}" stroke="#444" stroke-width="1.8"/>')
o.append(f'<line x1="160" y1="{MY + 206}" x2="1040" y2="{MY + 206}" stroke="#444" stroke-width="1.8"/>')
arrow(1040, MY + 206, 1040, MY + 178)
label(700, MY + 223, "queried by Grafana", size=12)
arrow(160, 582, 160, MY)
label(172, 622, "logs: Alloy ships WARN and ERROR in full, INFO sampled", anchor="start")
arrow(700, 582, 700, MY)
label(712, 622, "metrics: node_exporter, solana-exporter, vote credits", anchor="start")

o.append("</svg>")
OUT.write_text("\n".join(o) + "\n")
print(f"wrote {OUT}")
