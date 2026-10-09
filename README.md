# solana-devnet-lab: a local Solana cluster run the way an operator would run it

A lab notebook as much as a repository: what was run, what broke, and what was changed because of
it. Started 2026-10-08.
Status: **in progress**. Only what is marked "works" below has been run.

## Two tracks

| Track | What | State |
|---|---|---|
| A. Single node, macOS native | `solana-test-validator` v4.3.0 from the official macOS release, in `.release/`. For first hands-on with the CLI | works (`run/`, RPC on 127.0.0.1:8899) |
| B. Production-like cluster | Linux hosts with systemd, configured by Ansible, running `agave-validator` v4.3.0 built from source for arm64 | three nodes running (bootstrap, second validator, RPC); see "what works" below |

## Track B: what works (run on 2026-10-08)

| Step | Command (from `ansible/`) | Result |
|---|---|---|
| Hosts | `docker compose up -d` in `hosts/` | 4 systemd hosts, fixed IPs, 3 data volumes each |
| Host preparation + binaries | `ansible-playbook site.yml --tags host,binaries` | user `sol`, directories, sysctls checked against the live kernel, io_uring check, Agave 4.3.0 installed. Second run: 0 changes |
| Genesis | `ansible-playbook genesis.yml` | genesis hash recorded in `group_vars/solana.yml` (first chain `3tfV…xUS5`, second `4trY…Mpm3`) |
| Bootstrap validator | `ansible-playbook site.yml --tags service --limit bootstrap -e solana_start=true` | produces blocks, votes, skip rate 0% |
| Second validator | `ansible-playbook join.yml --limit validator2`, then the service command with `--limit validator2` | fetched snapshot 800 from the bootstrap node, caught up, votes. Withdrawer key stayed on the Mac |
| RPC node | `ansible-playbook join-nonvoting.yml --limit rpc`, then the service command with `--limit rpc` | non-voting, transaction history on, reachable from the Mac at `http://127.0.0.1:8999` |
| Stake | `ansible-playbook stake.yml --limit validator2` | 1000 SOL delegated from an operator wallet on the Mac; activating from epoch 5 |

Not done yet: a timed stop / restart catch-up drill, a `status` target.

### Found on the way (each cost a failed start)

1. Flags from the v3.1 run script are hidden in v4.3 help but still exist: `--allow-private-addr`
   (needs `--no-xdp`), `--no-poh-speed-test`, `--no-os-network-limits-test`,
   `--no-wait-for-vote-to-start-leader`. `--gossip-host` is gone. The advertised address is taken
   from `--bind-address` when that is a real address (`validator/src/commands/run/execute.rs`).
2. `--rpc-bind-address 0.0.0.0` together with `--bind-address <ip>` panics on a joining node:
   "All sockets should be bound to the same IP" (`net-utils/src/ip_echo_client.rs`). The node asks
   the entrypoint to test its ports and asserts that every listener has the same address. The
   bootstrap node did not hit it because it has no entrypoint. systemd restarted the crashing
   service 64 times before the fix: `Restart=on-failure` hides a crash loop unless something
   watches `NRestarts`.
3. Ansible 2.20 rejects a string from `-e var=true` in `when:`. Conditions use `| bool`.
4. The stake program is a Core BPF program now. Genesis must include it
   (`fetch-core-bpf.sh`), or there is no staking.

### Observed after the stake was delegated

- **Stake warms up slowly.** 1000 SOL was delegated at epoch 4; after two epoch boundaries only
  0.0936 SOL was active (0.0448, then 0.0936). New stake activates at a limited rate relative to
  the stake already active, and the bootstrap validator has only about 0.5 SOL. Even so, validator2
  reached 15.8% of active stake and entered the leader schedule in epoch 7 (344 of 4096 slots).
  To activate the full amount quickly the genesis would have to give the bootstrap validator far
  more stake (`--bootstrap-validator-stake-lamports`); that means a new chain.
- **First leader slots were skipped.** validator2's first three leader windows (12 slots) were all
  skipped; every window after that was produced (12 of 12 at the time of writing, bootstrap 209 of
  209). Likely cause, not yet confirmed: by default a validator does not produce blocks until one
  of its own votes has landed in a rooted slot (the bootstrap node runs with
  `--no-wait-for-vote-to-start-leader`, validator2 does not). `solana validators` showed it with a
  warning mark and no last vote at the epoch boundary.
- **The Mac sleeps.** `pmset -g log` shows maintenance sleep from about 04:56 local time; the
  validator logs have a gap from 17:36 to 18:10 UTC. All nodes froze and resumed together and the
  cluster carried on. Commands issued during sleep hang. Keep the Mac awake (`caffeinate`) for any
  timed drill.

### Incident 2026-10-08: the disk filled and the cluster stopped

- Cause: the start script had no ledger limit. Each node's `rocksdb` grew to 13–15 GB and the
  Docker VM disk (148 GB, shared with the Ethereum devnet and a kind cluster) reached 100%.
- First error in the bootstrap log, 02:20 UTC: `RocksDB error: IO error: No space left on device`.
- Found more than six hours later, by chance. systemd had restarted the services 4102 (bootstrap),
  703 (validator2) and 701 (rpc) times.
- Missing: a disk trend alert, an alert on `NRestarts`, and "root not advancing".

What was done the same day:

- `ansible-playbook reset.yml -e confirm=yes` (new): wipes ledger, accounts, snapshots and logs,
  keeps the keys. Then a second genesis, hash `4trYJQm9anUjR77EBfD6Xtn2f9m2XEZfR4KwUSyuMpm3`.
- The start script now has `--limit-blockstore-size 100000000`. **This does not protect the lab.**
  100 million shreds is the smallest value v4.3.0 accepts and it is sized for mainnet; here the
  disk fills long before. Measured after the rebuild, at slot 2200: about 500 MB of table files
  (roughly 230 KB per slot) plus about 1 GB of write-ahead log per node, at roughly 2.4 slots per
  second. With 35 GB free the three nodes have a few hours.
- So the real protection is `scripts/disk-guard.sh` (stops the validators under 15 GB free; pid in
  `run/disk-guard.pid`) until the host disk alert exists, and stopping the cluster when not in use.
- Genesis now gives the bootstrap validator 10,000 SOL of stake. The 1000 SOL delegated to
  validator2 was fully active by epoch 6 (on the first chain: 0.09 SOL after two epochs), and the
  bootstrap validator keeps more than two thirds, so the cluster finalizes while validator2 is
  stopped.

### Restart of all hosts, 2026-10-08 (unplanned)

Docker Desktop was restarted at 11:10 UTC (its disk was enlarged from 148 GB to 307 GB). Twenty
minutes earlier the disk guard had already stopped the validators at 14 GB free. After the restart
the dashboards were empty. Nothing was lost; three things had not come back:

1. The four hosts. Their restart policy is `no`, so they stayed down. `docker start` brought them
   back, systemd started every enabled unit, and the chain continued from slot 14057: the bootstrap
   validator alone holds more than two thirds of the stake.
2. Prometheus and Alertmanager, although their policy is `unless-stopped`. They had been reloaded
   earlier with `docker kill -s HUP`, which marks a container as stopped by hand. Prometheus is now
   reloaded over HTTP.
3. The agents on two hosts: `Failed to adjust resource limit RLIMIT_NOFILE`, status 205/LIMITS.
   The role had set `fs.nr_open` to 1000000, below the kernel default of 1048576. A host that
   booted before the sysctl was applied gave its units a limit above `fs.nr_open`, and they could
   not start. The validator itself was not affected because its unit sets its own limit. Fixed in
   the role defaults.

Do not recreate the host containers (`docker compose up` after a change to `hosts/`): keys and
installed binaries live in the container's own filesystem, only `/mnt/*` is on volumes.

### Identity failover drill, 2026-10-08

`ansible/spare.yml` prepares the pair (validator2 and spare); `ansible/failover.yml` moves the
staked identity between them with no restart:
`ansible-playbook failover.yml -e from=validator2 -e to=spare`, and back with the two swapped.

The rule: never two machines voting with one identity. So the old host lets go first
(`set-identity` to its unstaked key), then the tower file moves, then the new host takes over
(`set-identity --require-tower`), then the `identity.json` symlinks are switched so a reboot keeps
the new roles.

| Run | Result |
|---|---|
| validator2 → spare, first attempt | Identity moved, 1.92 s with no holder, playbook reported success. **The spare did not vote for 88 seconds.** Log: `The authorized keypair … for vote account … is not available. Unable to vote`. 16 leader slots skipped; `ValidatorVoteLagging` and `ValidatorDelinquent` paged |
| Fix at runtime | `agave-validator authorized-voter add` on the spare: voting at the tip 10 s later |
| Restart of the old primary | Came back with its unstaked identity (the symlink), not the staked one. One gossip entry for the staked identity |
| spare → validator2, corrected playbook | 2.01 s with no holder, voted on the next slots, 4 leader slots skipped (one window), no alert |

Two faults found, both in my own playbook:

1. `set-identity` gives a host the identity but not the key that signs votes. The vote account
   names the staked identity as authorized voter, and a host started with an unstaked identity has
   only that unstaked key loaded. Fix: both hosts start with `--authorized-voter
   keys/staked-identity.json` (hosts with `solana_failover: true`), and the playbook loads the key
   before anything moves.
2. The success check was wrong. It waited for a vote newer than the last one seen before the
   switch, and the old host's final votes satisfy that. It now waits for a vote on a slot more
   than 32 past the cluster tip at the switch. The monitoring caught what the playbook missed.

Not done: `wait-for-restart-window` before the switch (validator2 has a tenth of the stake here and
is leader every few seconds, so an idle minute never comes); a switch with the old host
unreachable, which is the real emergency; the spare has no monitoring agents yet.

The new start script is on both hosts but the running processes were started before it: a
template change does not restart a validator here unless `-e solana_restart_on_change=true` is
given. Until the next restart the playbook's step 0 is what loads the key.

### Disk enlarged again and where the space goes, 2026-10-09

The Mac restarted at about 10:30 local time; Docker Desktop did not come back by itself and the
disk guard was gone with it. The Docker disk had 38 GB free. It was enlarged from 307 GB to 646 GB
in Docker Desktop (enlarging keeps the data; shrinking wipes the whole disk). The four hosts were
started with `docker start`, the chain continued from slot 99847, and the guard was restarted with
`MIN_FREE_GB=30`.

Measured on the bootstrap node at about slot 98850 (39 GB of `rocksdb`):

| Column family | Size |
|---|---|
| `data_shred` | 18.1 GB |
| `code_shred` | 18.5 GB |
| `index`, `meta` and the rest | about 1.2 GB |
| accounts and snapshots directories | under 1 MB each |

- The ledger is almost only shreds, and half of them are erasure coding: a FEC set is 32 data and
  32 coding shreds (`ledger/src/shred.rs`). About 370 KB per slot with nothing but votes in it.
- `--limit-blockstore-size 100000000` is about 120 GB per node at roughly 1.2 KB per shred. A node
  here holds about a third of that, so cleanup has not started yet. Four nodes at the limit need
  about 480 GB, which now fits; whether the size really settles there has not been observed.
- Growth measured after the restart: 29 GB per hour over 160 seconds, all of it in the four
  `rocksdb` directories (write-ahead log and table files), and 34 and 54 GB per hour in the first
  minutes after two starts. The cluster ran at about 3.9 slots per second during these samples.
  The higher early figures are not explained.
- Open: the solana exporter on the bootstrap node was reported down once before the Docker
  restart; cause not looked at.

### Third genesis, 2026-10-09 15:16 local

Done to free the disk before an evening of drills: the identity was moved back to validator2
(`failover.yml -e from=spare -e to=validator2`, 1.74 s with no holder; the earlier run the same day
in the other direction took 1.72 s), then `reset.yml -e confirm=yes`. Free space went from 307 GB
to 508 GB. New genesis hash `DSaqBftvKidyUoc2gU8Q8Hn4kZRMCjBhanG8Yik41Uqb`, recorded in
`group_vars/solana.yml`. All keys were kept, so identities, vote account and withdrawer are the
same as before. Rebuild in order: `genesis.yml`, bootstrap service, `join.yml --limit validator2`,
service on validator2, rpc and spare, `stake.yml --limit validator2`. About five minutes.

Seen on the way:

- `stake.yml` failed on its first run: the operator wallet was funded through the bootstrap node
  and the next task spent from it through the rpc node, which did not have the balance yet
  ("insufficient funds for spend"). The second run passed. The playbook should wait for the
  balance on the endpoint it spends through.
- validator2 caught up at once and its log said `voting:` on every slot, but `solana validators`
  showed no last vote, no root and 0 credits through epoch 4, with 900 of 1000 SOL already active.
  Votes landed from epoch 5 on. `ValidatorDelinquent` and `ValidatorCreditsBehind` went pending in
  that window. Same pattern as on the first chain; cause not established.
- Its first leader slots were skipped again (skip rate 26.67% shortly after it started voting).
- The previous chain had 4,847 SOL delegated to validator2 at the end, from the 1,000 that
  `stake.yml` delegates. The difference is staking rewards: half an hour into this chain the
  same account already held 1,047 SOL. Rewards compound into the stake account every epoch, and
  the bootstrap validator's stake stands still because its commission is 100%. So validator2's
  share climbs by itself (9.09% at the start).

### More than one delegator, 2026-10-09

Two more wallets ("alice", "bob"; keys in `ansible/secrets/delegators/`, on the Mac) each created
a stake account and delegated it to validator2's vote account in epoch 7: 500 and 2,000 SOL, next
to the operator's 1,047. Three stake accounts, three different stake authorities, one vote
account. The validator did nothing and holds none of those keys.

- Commands per delegator, from its own wallet: `solana create-stake-account <stake keypair>
  <amount>`, then `solana delegate-stake <stake account> <vote account>`. `solana stakes <vote
  account>` lists every stake account delegated to it.
- Consequence for drills: validator2's share goes from about 9% to about 26% once this is active,
  and it keeps rising with rewards. Above one third, stopping validator2 stops finality for the
  whole cluster, because the bootstrap validator alone no longer has two thirds.
- `ValidatorStakeShareDropped` is expected to open a ticket for the bootstrap validator: its
  share falls by more than a tenth without it losing any stake.

## Monitoring and alerting (`monitoring/`)

The design: layers that vouch for each other, two severities,
inhibition so the cause pages and the symptoms stay quiet, and a stack that watches itself.
State: **running since 2026-10-08**. Prometheus http://127.0.0.1:9190, Alertmanager
http://127.0.0.1:9193, Grafana http://127.0.0.1:3100.

| Layer | Question | Rules |
|---|---|---|
| 1. Cluster | Is the chain moving and agreeing? | `ClusterRootStalled`, `ClusterSkipRateHigh` |
| 2. Validators | Are we voting, voting well, and producing our leader slots? | `ValidatorDelinquent`, `ValidatorVoteLagging`, `ValidatorRootStalled`, `ValidatorCreditsBehind`, `ValidatorSkipRateHigh`, `ValidatorStakeDropped`, `ValidatorStakeShareDropped`, `VotingIdentityOnTwoHosts`, `VotingIdentityNotHeld` |
| 3. Funds | Can we still pay for votes? | `IdentityBalanceRunningOut`, `IdentityBalanceLow` |
| 4. Node | Is each node healthy and caught up? | `NodeUnhealthy`, `NodeFallingBehind`, `NodeSlotStalled`, `NodeVersionMismatch` |
| 5. Foundation | Is any of this being measured, and is the host fine? | `NodeDown`, `MonitoringTargetDown`, `HostAgentDown`, `HostDiskWillFillSoon`, `HostDiskSpaceLow`, `HostMemoryLow`, `ValidatorServiceRestarting`, `ValidatorServiceNotActive` |

Compared with the Ethereum stack: layer 3 was "signing" there (web3signer) and is "funds" here,
because a Solana validator pays for every vote and an Ethereum validator does not.

Why each signal is there, with the numbers read off the stack: `docs/monitoring-rationale.md`.

Added 2026-10-09: which host runs which identity. Every host's exporter reports the identity it
runs, so a failover is visible as a state change on two hosts, and two rules watch the one rule of
failover from outside. `VotingIdentityNotHeld` was tested live twice by putting validator2 on its
unstaked key: it fired about 35 s later, before `ValidatorDelinquent` and `ValidatorVoteLagging`,
and while it fired Alertmanager showed those two as suppressed. `VotingIdentityOnTwoHosts` is
tested only with synthetic series (`monitoring/metrics/prometheus/tests/identity_test.yml`); it
has not been triggered on the cluster, because that means two hosts really signing with one key.
After the third genesis `ValidatorStakeDropped` fired for an hour: the rule compares with the
value an hour ago, which belonged to the previous chain.

Checked 2026-10-09 against the categories a production Solana alert set usually has: stuck node,
identity balance and skip rate are covered; stake share was covered only as an absolute amount and
now has its own rule; "vote success rate" is covered indirectly by vote lag and the credits ratio,
not as a metric of that name; the compliance checks of the foundation delegation programme have no
counterpart here.

Parts:

| Part | Where it runs | Installed by |
|---|---|---|
| `solana-exporter` v3.1.0 (community; no release binaries, built by `monitoring/exporter/build.sh`) | On each host, polling the local RPC. Light mode on the validators, full mode on the RPC node | `ansible/monitoring.yml`, role `solana_exporter` |
| `vote-credits-exporter.py` (ours) | On the RPC node | same role |
| `node_exporter` 1.12.1 with the systemd collector | On every host | role `node_exporter` |
| Alloy 1.20.1: validator log and `sol.service` journal | On each host that runs a validator | role `alloy` |
| Prometheus (7 days or 2 GB), Alertmanager, alert sink, Grafana, Loki (48 hours) | `monitoring/docker-compose.yml`, ports on localhost only | `docker compose up -d` |

All agents are systemd services with their own users, downloaded with the published checksum where
a release archive exists. `ansible-playbook monitoring.yml` twice in a row: 0 changes.

State on 2026-10-08, late evening: 16 scrape targets up, 27 rules, a dashboard of 31 panels
("Solana cluster overview", folder Solana) whose queries all return data. The dashboard is
generated: `python3 monitoring/scripts/build-dashboard.py`.

Tests run:

| Test | Result |
|---|---|
| Stop validator2 | `ValidatorVoteLagging` at the sink after 45 s, `ValidatorDelinquent` after 75 s, then `NodeDown`. Cleared after restart |
| Kill the validator process three times on the rpc host | `ValidatorServiceRestarting` at the sink within about 40 s of the first kill |
| Disk trend | `HostDiskWillFillSoon` went pending by itself minutes after it was enabled |
| Credits | validator2's credit ratio fell to 0.78 after the two stop tests; `ValidatorCreditsBehind` pending |
| Log sampling | INFO 588 lines/s before, 30 after; WARN unchanged at 11 |

Found while bringing it up:

1. The exporter exits if a `-nodekey` has no active stake. A validator that has just joined is
   given by `-votekey` instead.
2. The exporter reports identity accounts and vote accounts under one balance metric. A vote
   account holds only its rent reserve (0.027 SOL here), so "balance under 1 SOL" on the raw metric
   would fire forever. The rules use a recording rule that keeps identity accounts only.
3. `ValidatorVoteLagging` is meant as the early warning before `ValidatorDelinquent`. With
   `for: 1m` the delinquent alert came first. With `for: 15s` it comes 30 seconds earlier.
4. A validator with no active stake is missing from the per-validator metrics, so its identity
   balance is not covered by the rules until its stake activates.
5. The first exporters ran as containers next to Prometheus and reached the nodes over the
   network. Moved to the hosts: a voting validator does not open RPC to the network in production.
6. The community exporter has no vote credits. Without them the rules see "stopped voting" but not
   "voting late and earning less". Hence the small exporter of our own.

Not covered: the inside of the validator (RPC cannot see it), Jito, upgrade deadlines, alert rules
on logs, the leader schedule.

Start the monitoring stack:

```bash
cd ansible && ansible-playbook monitoring.yml      # agents on the hosts
cd ../monitoring && docker compose up -d           # Prometheus, Alertmanager, Grafana, Loki
```

Stop the validators when done (the ledger grows by the hour):

```bash
for h in bootstrap validator2 rpc; do docker exec sol-$h systemctl stop sol; done
```

## Why not the official image

Checked 2026-10-08 on this machine (Apple M4 Max, Docker Desktop, linuxkit 6.12 arm64 kernel):

- `anzaxyz/agave` is published for x86_64 only. Under emulation the validator panics at start:
  `io_uring NOT supported: Function not implemented (os error 38)` then
  `assertion failed: io_uring_supported()` (`fs/src/dirs.rs`). Same result with seccomp unconfined, so
  it is the emulation layer, not Docker's security profile.
- The Docker VM's own kernel has io_uring. A native arm64 build can use it.
- The official macOS release contains the CLI and `solana-test-validator` only. No `agave-validator`,
  `solana-genesis` or `solana-gossip`, so no multi-node cluster from it.

So track B builds Agave from the v4.3.0 tag: `image/Dockerfile`.

## Track B design: what "production-like" means here

| Production practice | Here |
|---|---|
| A Linux host per validator | One systemd container per node (Ubuntu 24.04, `--privileged`, cgroup v2). Verified: systemd runs, `vm.max_map_count` = 1048576, io_uring enabled |
| Validator as a systemd service under its own user | Unit file and `sol` user installed by an Ansible role |
| Start-up flags kept in a start script | Templated `validator.sh`: identity, vote account, entrypoint, known validators, expected genesis hash, separate ledger / accounts / snapshots paths, port range, log path |
| Host tuning | The role sets sysctls and file limits and checks them |
| Key separation | identity (on the host), vote account, authorized withdrawer (never copied to the host) |
| Trust anchors on join | `--known-validator`, `--expected-genesis-hash`, `--only-known-rpc` |
| Voting validators and non-voting RPC nodes are separate | `rpc` host runs `--no-voting` with transaction history |
| Upgrades by identity switch to a hot spare | `spare` host, `set-identity` and tower-file drill |
| Monitoring and alerting | RPC-based exporter into the existing Prometheus / Grafana of the Ethereum devnet; `agave-watchtower` |

Nodes: `bootstrap` (genesis validator), `validator2` (joins with delegated stake), `rpc` (non-voting,
full transaction history), `spare` (hot spare for the identity-switch drill).

## Mapping to the Ethereum devnet

| Ethereum devnet | Here |
|---|---|
| Genesis ceremony (`make genesis`) | `solana-genesis`, also one-time |
| Validating pair: besu + teku + validator client | One `agave-validator` process |
| Archive pair: geth archive + lighthouse | Non-voting RPC node with full transaction history. Different meaning: Solana RPC keeps block and transaction history; it cannot answer "account state at an old height" |
| web3signer remote signing | No equivalent. Hot spare + `set-identity` instead |
| `pause.sh`, then resume | Stop a validator, restart it, watch it fetch a snapshot and catch up |
| docker compose | systemd + Ansible |

## Limits

- Firedancer cannot run here: it needs XDP, huge pages and bare-metal Linux.
- Containers as hosts share one kernel. Sysctls are global to the Docker VM, NUMA and NIC tuning do not
  apply, and timing is not representative.
- A development cluster uses `--hashes-per-tick sleep`, so proof of history does not load the CPU.
  Nothing measured here says anything about mainnet performance.

## Track A commands

```bash
cd solana-devnet
export PATH=$PWD/.release/solana-release/bin:$PATH
solana -u http://127.0.0.1:8899 slot
solana -u http://127.0.0.1:8899 epoch-info
solana -u http://127.0.0.1:8899 gossip
solana -u http://127.0.0.1:8899 validators
kill "$(cat run/tv.pid)"      # stop it
```
