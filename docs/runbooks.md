# Runbooks

One entry per alert: what it means, what to look at first, what to do, and what not to do.
Every alert rule links here. Commands are written for this lab (`docker exec sol-<host> ...` stands
for "on that host"); `solana` talks to the RPC node at `http://127.0.0.1:8999`.

Each entry says whether it has been exercised on this cluster. Several have not.

Two commands answer most first questions:

```bash
scripts/failover.sh --check        # which host runs the staked identity; is the other one ready
solana -u http://127.0.0.1:8999 validators
```

## Identity

### VotingIdentityOnTwoHosts

**p1.** Two hosts report the same voting identity. Both can sign votes: this is double voting.

1. Do not wait and do not investigate first. Decide which host keeps the identity: the one that
   holds the newer tower file, normally the one that took over last.
2. On the other host: `agave-validator --ledger /mnt/ledger set-identity /home/sol/keys/unstaked-identity.json`,
   then point `identity.json` at the unstaked key.
3. If that host does not answer, fence it: power it off or cut its network.
4. Afterwards find out how it happened. The usual causes are a host that restarted with its link
   still on the staked key, or a switch started by hand on the wrong host.

Do not restart either validator to "clear" it. Exercised: unit test only.

### VotingIdentityNotHeld

**p1.** A validator identity that is known to the cluster runs on no monitored host. Nobody votes.

1. `scripts/failover.sh --check`. If it shows an active host, the exporter is the problem, not the
   validator: see NodeDown.
2. If neither host is active and both answer, pick the one that holds the newest tower file and is
   caught up, and give it the identity: `set-identity --require-tower /home/sol/keys/staked-identity.json`,
   then fix its `identity.json` link.
3. If the host that held it does not answer, this is a takeover, not a switch. Fence that host from
   outside first (`scripts/fence.sh <host>`; on real hardware power or the switch port), then
   `ansible-playbook takeover.yml -e from=<old> -e to=<new> -e fenced=yes`. It waits until the old
   host's last vote stands still and the cluster has finalized past it. Do not shorten that wait.
4. Before the old host is allowed back, put it on its unstaked key through its console.
   `scripts/fence.sh --lift <host>` refuses otherwise.

Exercised: yes. Fired after about 35 seconds when the identity was taken off the primary, and in
the takeover drill of 2026-10-10.

## Voting

### ValidatorVoteLagging, ValidatorDelinquent, ValidatorRootStalled

**p1.** The validator's votes are behind the cluster, the cluster has marked it delinquent, or its
root no longer moves. The same failure at three stages. Every minute costs vote credits.

1. Is the whole cluster stalled? If `ClusterRootStalled` fires too, start there.
2. `scripts/failover.sh --check`: is the active host running and caught up?
3. On the active host: `systemctl status sol`, then the last errors in `/var/log/solana/validator.log`.
   "Unable to vote" with "authorized keypair ... not available" means the vote-signing key is not
   loaded: `agave-validator --ledger /mnt/ledger authorized-voter add /home/sol/keys/staked-identity.json`.
4. Identity balance: `solana balance <identity>`. An empty account cannot pay for votes.
5. If the host is sick and the spare is ready: `scripts/failover.sh`.

Do not switch while the standby is behind. Exercised: yes (stop tests, failover drills).

### ValidatorCreditsBehind, CreditsBudgetFastBurn, CreditsBudgetSlowBurn

**p3, p1, p3.** The validator votes but earns fewer credits than the best one: its votes land late.

1. Vote lag panel and the credits ratio over time: a step (something changed) or a slope?
2. A step: what changed then: a switch, a restart, a version.
3. A slope: host load, disk latency, network path to the leaders.

The fast burn pages because a day's budget would be gone in under two hours; by then one of the
alerts above is usually firing as well. Exercised: the fast burn fired after the takeover drill
(about 77 seconds without votes); the slow burn has not fired.

## Block production

### ValidatorSkipRateHigh, ClusterSkipRateHigh, LeaderSlotBudgetBurn

**p3.** Leader slots without a block: ours, or everybody's.

1. Ours only, or the cluster's? If the cluster's, it is not this validator.
2. Do the skips line up with a switch or a restart? Then it is the cost of that change.
3. Otherwise look at the leader slots themselves: was the validator caught up when its turn came?

Exercised: seen after every identity switch on a validator with a large share of the stake.

### LeaderSlotCountersStalled

**p2.** Roots advance but no leader slots are being counted: the skip-rate rules are blind.

1. On the RPC host: `journalctl -u solana-exporter -n 20`. A line like "finalized slot number has
   not advanced from N" with N above the current slot means the exporter remembers another chain.
2. `systemctl restart solana-exporter`.

Exercised: happened for real after a chain reset and went unnoticed for hours; the rule was written
afterwards and has not fired since.

## Funds

### IdentityBalanceLow, IdentityBalanceRunningOut

**p1** under 1 SOL, **p2** when the projection reaches zero within three days.

1. `solana balance <identity>` and the "Days left" column on the dashboard.
2. Top up from the funding wallet: `solana transfer <identity> <amount>`. Voting resumes by itself.

Do not use the withdraw authority for this, and do not put it on a host to automate it.
Exercised: no.

### ValidatorStakeDropped, ValidatorStakeShareDropped

**p3.** A business signal: stake left, or others gained. `solana stakes <vote account>` lists the
stake accounts. Nothing to fix on the host. Exercised: the first fired after a reset (comparison with the
previous chain); the second was not checked when new delegators changed the shares.

## Cluster

### ClusterRootStalled

**p1.** No new root in the whole cluster. While this fires, the validator alerts below it are
inhibited: they are symptoms.

1. Are more than a third of the stake's validators not voting? `solana validators`.
2. In this lab that means: is the bootstrap validator up, and is the staked identity of validator2
   held and voting. Together they are the cluster.

On a real network this alert is information, not a task: nothing one operator does restarts
consensus. Exercised: finality paused for tens of seconds during switches of a validator with more
than a third of the stake.

## Nodes and hosts

Seven of these exist twice: **p1** on a host that runs a staked identity, **p2** on the spare or the
RPC node, where no stake is at risk.

### NodeDown, NodeUnhealthy, NodeFallingBehind, NodeSlotStalled

1. `docker exec sol-<host> systemctl status sol` and `systemctl status solana-exporter`. A dead
   exporter looks like a dead node.
2. Validator log: is it replaying, repairing, or stuck?
3. p1 and the spare is ready: `scripts/failover.sh`, then repair the old host as a standby.
4. After a restart, expect well under a minute here: the node reuses its local snapshot and gets
   the missing slots from its peers.

Exercised: yes. p2 on the standby (five-minute stop, caught up 46 seconds after the start); p1 for
a fenced host that had been running the staked identity (takeover drill).

### ValidatorServiceRestarting, ValidatorServiceNotActive

A crash loop, or a stopped service. `Restart=on-failure` keeps the unit "active" while it crashes.

1. `journalctl -u sol -n 50`: the reason is in the first lines after each start.
2. Disk full, a flag the binary rejects, a port conflict.

Exercised: yes (process killed three times; and the real disk-full incident).

### HostDiskWillFillSoon, HostDiskSpaceLow

**p2** when the trend reaches zero within 24 hours, **p1 / p2** under 15% free.

1. Which directory: `du -sh /mnt/ledger/* /mnt/accounts /mnt/snapshots`.
2. In this lab the ledger limit cannot go low enough, so: stop the validators that are not needed,
   or `ansible-playbook reset.yml -e confirm=yes` for a new chain.

Exercised: yes, the hard way.

### HostMemoryLow, NodeVersionMismatch

**p2, p3.** Memory under 10%: look for what grew. Versions differ for over an hour: an upgrade was
left half done, or is in progress; finish it or say so in the channel. Exercised: no.

## Monitoring

### MonitoringTargetDown, HostAgentDown

**p2.** Part of the monitoring is blind. `docker ps` for the stack, `systemctl status node_exporter
alloy` on the host. Fix this before trusting any quiet dashboard. Exercised: partly (exporter
restarts).
