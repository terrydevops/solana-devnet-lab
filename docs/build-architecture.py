#!/usr/bin/env python3
"""Build docs/architecture.svg, the diagram shown in the README.

    python3 docs/build-architecture.py
"""
import pathlib
from xml.sax.saxutils import escape as esc

OUT = pathlib.Path(__file__).resolve().parent / "architecture.svg"
W, H = 1200, 800
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
group(40, 232, 1120, 304, "Docker network 172.30.0.0/24: four systemd hosts, each with ledger / accounts / snapshots volumes")
HOSTS = [
    (70, GREEN, ["bootstrap  .11", "validator; started the chain", "stake from genesis",
                 "syncs, votes, produces blocks"]),
    (340, GREEN, ["validator2  .12", "validator; joined later", "stake delegated by delegators",
                  "syncs, votes, produces blocks"]),
    (610, YELLOW, ["spare  .14", "hot spare for validator2", "unstaked identity, no stake",
                   "syncs only"]),
    (880, BLUE, ["rpc  .13", "RPC node", "keeps transaction history",
                 "syncs only, answers queries"]),
]
for x, colours, lines in HOSTS:
    box(x, 296, 250, 108, colours, lines, emphasis=(3,))
label(330, 288, "blocks, votes")
arrow(320, 350, 340, 350, both=True)
label(600, 288, "identity switch")
arrow(590, 350, 610, 350, both=True, dashed=True)
label(600, 434, "All four run the same agave-validator binary as a systemd service, and all four sync the chain:", size=13)
label(600, 453, "they gossip with each other, receive every block, replay it and store it. Start-up flags decide the rest.", size=13)
label(600, 482, "Voting costs a fee per slot and needs a funded identity. The spare and the RPC node do not vote, so they cost nothing on chain.", size=13)
label(600, 511, "On every host: node_exporter, solana-exporter and Alloy, also as systemd services.", size=13)

# ---- control -> cluster -------------------------------------------------------------------
arrow(220, 146, 220, 232)
label(232, 196, "configures every host", anchor="start")
o.append('<line x1="600" y1="146" x2="600" y2="196" stroke="#444" stroke-width="1.8"/>')
o.append('<line x1="600" y1="196" x2="1005" y2="196" stroke="#444" stroke-width="1.8"/>')
arrow(1005, 196, 1005, 296)
label(800, 188, "RPC on 127.0.0.1:8999")

# ---- monitoring ---------------------------------------------------------------------------
group(40, 606, 1120, 170, "Monitoring stack")
box(70, 652, 180, 100, GREY, ["Loki", "validator logs and", "the service journal"])
box(300, 652, 200, 100, GREY, ["Prometheus", "32 rules in five layers,", "unit-tested identity alerts"])
box(550, 652, 200, 100, GREY, ["Alertmanager", "page / ticket,", "inhibition by cause"])
box(800, 652, 140, 100, GREY, ["Alert sink", "counts what", "was delivered"])
box(990, 652, 140, 100, GREY, ["Grafana", "dashboards from", "Prometheus and Loki"])
arrow(500, 702, 550, 702)
arrow(750, 702, 800, 702)
arrow(160, 536, 160, 606)
label(172, 576, "logs (Alloy)", anchor="start")
arrow(400, 536, 400, 606)
label(412, 576, "metrics: node, chain, vote credits", anchor="start")

o.append("</svg>")
OUT.write_text("\n".join(o) + "\n")
print(f"wrote {OUT}")
