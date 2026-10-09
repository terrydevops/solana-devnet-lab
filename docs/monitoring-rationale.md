# What we monitor on the Solana cluster, and why

**A snapshot of 2026-10-08**, when the cluster had three nodes and two alert severities. The hot
spare, the identity rules, the three priorities, the SLOs and the runbooks came a day later and
are described in the README and in `runbooks.md`; the reasoning below still holds.

Each signal: what it measures,
which failure it is there to catch, what the operator does. Metric names are the ones this
deployment exports. Every number was read off the running stack on 2026-10-08, on a two-validator
lab cluster; none of them says anything about mainnet.

**Five layers, each one vouching for the layer above it.**

| Layer | Question | If it is wrong |
|---|---|---|
| 1. Cluster | Is the chain moving and agreeing? | Nothing else matters while the cluster is stalled |
| 2. Validators | Are we voting, and voting well? | Votes and leader slots are the product |
| 3. Funds | Can we still pay for votes? | An empty account looks like a dead validator |
| 4. Nodes | Is each node healthy and caught up? | The node view explains the validator view |
| 5. Foundation | Is any of this being measured? Is the host fine? | A dead collector looks like a quiet system |

Alerting runs top-down: page for the cause, stay quiet about the symptoms (inhibit rules).
Where the text below says "pages" read priority p1, and "tickets" p3; p2 sits between them:
the on-call is told at once and nobody is woken. The list per priority is in the README.
Diagnosis runs bottom-up: trust the foundation before believing the chain.

On an Ethereum validator stack this layer would be "signing" (the remote signer). Here it is "funds": a Solana validator
pays a fee for every vote, an Ethereum validator pays nothing to attest.

Where the numbers come from:

| Source | Runs | Gives |
|---|---|---|
| `solana-exporter` v3.1.0 (community) | On each host, polling the local RPC. Light mode on the validators, full mode on the RPC node | Votes, roots, delinquency, stake, balances, leader slots, node health |
| `vote-credits-exporter.py` (ours, 120 lines) | On the RPC node | Vote credits, which the community exporter does not report |
| `node_exporter` 1.12.1 | On each host | Disk, memory, state and restart count of `sol.service` |
| Alloy 1.20.1 → Loki | On each host | The validator log and the journal of `sol.service` |

Agave has no Prometheus endpoint, so everything about the chain is seen from outside, through RPC.
What is not visible this way: replay time, proof-of-history, gossip, turbine, repair. Agave pushes
those to InfluxDB; Firedancer serves them on a Prometheus endpoint. Neither is set up here.

---

## Layer 1: Is the chain moving and agreeing?

### `solana_cluster_root_slot`

The newest slot that can no longer be rolled back. **Look at this before slot height.** Slots keep
coming as long as some leader produces blocks; roots advance only while enough stake agrees. A
cluster with rising slots and a flat root is producing blocks nobody can rely on.

Ethereum equivalent: the finalized epoch against the head.

Current: the root trails the newest vote by 31 slots, steadily. `ClusterRootStalled` pages when the
root has not moved for 2 minutes.

### `solana_node_slot_height`, as a rate

3.8 slots per second on this cluster. Mainnet aims at 2.5 (400 ms); the lab runs faster because
its ticks sleep instead of hashing. The absolute number does not matter here. A node whose rate
goes to zero has stopped following the chain.

---

## Layer 2: Are we voting, and voting well?

### `solana_validator_last_vote` against `solana_cluster_last_vote`

How many slots a validator's last vote trails the newest vote in the cluster. Zero for both
validators when healthy. This is the early signal: it moves within seconds of a validator
stopping.

`ValidatorVoteLagging` pages above 50 slots.

### `solana_validator_delinquent`

The cluster's own verdict that a validator's votes are too far behind. Delegators see this mark,
and it is what makes them move their stake. It is late by design.

**Measured ordering.** validator2 was stopped at 10:11:34 UTC. `ValidatorVoteLagging` reached the
alert sink at 10:12:19 (45 seconds), `ValidatorDelinquent` at 10:12:49 (75 seconds). The first
version of the lag rule waited a full minute before firing and arrived *after* the delinquent
alert: an early warning that comes after the verdict is no warning. It now waits 15 seconds.

### `solana_node_identity`: which host runs which identity

Every other signal in this layer follows the vote account: it says whether somebody is voting, not
which machine. With a hot spare that is a blind spot in both directions. The staked identity on
two hosts is the one thing a failover must never produce, and nothing else here would show it
while both vote happily. The staked identity on no host looks, for the first minute, like any
other reason for a validator to fall behind.

Each host's exporter reports the identity its validator runs. Joined with the list of validator
identities from the RPC node, that gives the number of hosts per voting identity, which must be 1.

- `VotingIdentityOnTwoHosts` pages at once, with no waiting period.
- `VotingIdentityNotHeld` pages after 30 s: longer than a clean switch (under 2 s here, between two
  5 s scrapes) and than one missed scrape. Measured 2026-10-09: it fired about 35 s after the
  identity was taken off validator2, ahead of the delinquent and vote-lag rules, and inhibits them.

Limit: this sees only hosts that are scraped. A machine outside the inventory that starts with
the staked key is invisible to it; on a real network the gossip table is where that would show.

### `solana_vote_credits_total` (our exporter)

Credits are what rewards are paid on. A vote that lands late earns fewer credits than one that
lands at once. So a validator can vote on every slot, never be delinquent, trigger nothing in the
two rules above, and still earn less than its peers.

This is the degradation nobody notices, the same shape as late attestation inclusion on Ethereum.
The community exporter has no credits metric, which is why the small exporter exists.

We compare each validator's credit rate with the best one in the cluster
(`solana:validator_credits_ratio:10m`). Current: bootstrap 1.00, validator2 0.78. The 0.78 is real:
validator2 was stopped twice for tests in the ten minutes before, and the missed votes show up as
missing credits. `ValidatorCreditsBehind` tickets below 0.90 for 15 minutes.

A rate, not the per-epoch value: the per-epoch value resets at every epoch boundary and would make
the ratio jump.

### Skip rate (`solana_validator_leader_slots_total`, as `solana:validator_skip_rate:1h`)

The share of a validator's leader slots in which no block was produced. Leader slots are where
transaction fees come from, so a skipped slot is income nobody got.

Current: bootstrap 0%, validator2 11.7%. validator2's figure comes from two things: its first
leader windows after joining were skipped (seen on both chains built here; cause not confirmed),
and it was stopped for tests. `ValidatorSkipRateHigh` tickets above 20% over an hour.

The exporter counts slots as valid or skipped; the rate needs a window, so it is a recording rule.

### `solana_validator_active_stake`

Decides the share of leader slots. bootstrap 9999.998 SOL, validator2 1038.97 SOL. A drop is a
business signal, not a fault: a delegator left. `ValidatorStakeDropped` tickets on a fall of more
than 10% within an hour.

---

## Layer 3: Can we still pay for votes?

### `solana_account_balance`, filtered to identities (`solana:identity_balance:sol`)

Every vote is a transaction, paid from the validator's identity account. When the account is
empty the validator stops voting and goes delinquent, with nothing wrong on the machine. It is the
most predictable outage there is.

Current: bootstrap 499.99 SOL, validator2 99.95 SOL. Measured spend over ten minutes, as an hourly
rate: about 0.06 SOL per hour per validator. At that rate validator2's 100 SOL lasts roughly 70
days. (Lab slots are faster than mainnet, so the cost per hour here is not the mainnet cost.)

`IdentityBalanceRunningOut` is p2 (tell the on-call) when the projection reaches zero within 3 days.
`IdentityBalanceLow` is p1 under 1 SOL: at about 1 SOL a day that is the last day of voting.

> **Watch out:** the exporter reports identity accounts and vote accounts under the same metric.
> A vote account holds only its rent reserve (0.027 SOL here). A rule on the raw metric fires for
> it forever. The recording rule keeps only addresses that are a validator identity.

> **Gap:** a validator with no active stake is not in the per-validator metrics, so its identity
> is not in the recording rule either. A validator that has just joined is not covered until its
> stake activates.

---

## Layer 4: Is each node healthy and caught up?

### `solana_node_is_healthy`, `solana_node_num_slots_behind`

What the node says about itself. Zero slots behind on all three nodes. These explain the layer
above: "validator2 is lagging" together with "node validator2 is 400 slots behind" is a node that
is catching up; lagging with zero slots behind points somewhere else.

### `solana_node_version`

All three on 4.3.0. `NodeVersionMismatch` tickets when versions differ for more than an hour:
normal for the length of a rolling upgrade, a mistake after it.

---

## Layer 5: Is any of this being measured, and is the host fine?

### `node_filesystem_avail_bytes`, as a projection

**This is the alert that was missing on the day the cluster died.** The ledger had no size limit,
the disk filled, and the validators crashed for six hours.

The rule projects forward instead of waiting for a percentage: `HostDiskWillFillSoon` (p2 since the alert review) fires when
the last hour's trend reaches zero within 24 hours. A Solana ledger grows by the second, so the
window is hours, where the Ethereum archive node uses days.

It went pending by itself minutes after it was enabled. Current: 27.5 GB free, falling at a rate
that leaves about an hour.

`--limit-blockstore-size` is set, but its minimum (100 million shreds) is sized for mainnet. On
this cluster the disk fills long before the limit is reached. The flag is not the protection here;
this alert is.

### `node_systemd_service_restart_total{name="sol.service"}`

`Restart=on-failure` keeps a crashing validator looking alive: the unit is "active" most of the
time and the process is always young. During the incident the bootstrap validator was restarted
4102 times and nothing showed it.

Tested: the validator process on the rpc host was killed three times, 12 seconds apart.
`ValidatorServiceRestarting` reached the sink within about 40 seconds of the first kill.

### `up`

16 scrape targets, all up: three chain exporters, the credits exporter, four `node_exporter`, three
Alloy, and the monitoring stack itself (Prometheus, Alertmanager, the alert sink, Grafana, Loki).
A dead exporter looks exactly like a quiet system, so its absence is an alert of its own.

---

## Logs

Validator log files and the journal of `sol.service`, shipped by Alloy to Loki, with the level as
the only label parsed out of the line. The module name stays in the text: there are hundreds of
modules and every label value is its own stream.

**Sampling.** Measured across the three nodes before sampling: 588 INFO lines per second, 11 WARN,
0.02 ERROR. The lines that explain an incident are the rare ones. So WARN and ERROR are shipped in
full and INFO is sampled at 5%. After the change: 30 INFO per second, WARN unchanged at 11.

The journal is there for one case: a validator that fails before it opens its own log file. The
start script's output goes to the journal and nowhere else.

---

## What this does not cover

- The inside of the validator (replay, proof-of-history, turbine, repair). RPC cannot see it.
- Jito: no block engine in this lab, so no connection or tip income to watch.
- Upgrade deadlines and delegation-programme rules: they need a source outside the cluster.
- Alert rules on logs: the logs are searchable, nothing alerts on them yet.
- The leader schedule: the same fault costs more just before our leader slots, and no rule here
  takes that into account.
