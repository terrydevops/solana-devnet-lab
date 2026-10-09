# Lab notes

A dated record of what was run on this cluster, what broke, and what was changed because of it.
Newest material is at the end of each part. Numbers are from a development cluster on one machine
and say nothing about mainnet.

## Bringing the cluster up, 2026-10-08

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

## Incidents and drills

### Incident 2026-10-08: the disk filled and the cluster stopped

- Cause: the start script had no ledger limit. Each node's `rocksdb` grew to 13–15 GB and the
  Docker VM disk (148 GB, shared with other projects) reached 100%.
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

Two faults found, both in the playbook:

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

## Monitoring: tests and findings

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

State on 2026-10-08, late evening: 16 scrape targets up, 27 rules, a dashboard of 31 panels whose
queries all return data. On 2026-10-09: 18 targets, 32 rules.

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

## Why Agave is built from source here

Checked 2026-10-08 on this machine (Apple M4 Max, Docker Desktop, linuxkit 6.12 arm64 kernel):

- `anzaxyz/agave` is published for x86_64 only. Under emulation the validator panics at start:
  `io_uring NOT supported: Function not implemented (os error 38)` then
  `assertion failed: io_uring_supported()` (`fs/src/dirs.rs`). Same result with seccomp unconfined, so
  it is the emulation layer, not Docker's security profile.
- The Docker VM's own kernel has io_uring. A native arm64 build can use it.
- The official macOS release contains the CLI and `solana-test-validator` only. No `agave-validator`,
  `solana-genesis` or `solana-gossip`, so no multi-node cluster from it.

So track B builds Agave from the v4.3.0 tag: `image/Dockerfile`.

## Compared with an Ethereum devnet

| Ethereum devnet | Here |
|---|---|
| Genesis ceremony | `solana-genesis`, also one-time |
| Validating set: execution client, consensus client, validator client | One `agave-validator` process |
| Archive pair: archive execution client and a consensus client | Non-voting RPC node with full transaction history. Different meaning: Solana RPC keeps block and transaction history; it cannot answer "account state at an old height" |
| Remote signing (web3signer) | No equivalent. Hot spare and `set-identity` instead |
| Pause a node, then resume | Stop a validator, restart it, watch it fetch a snapshot and catch up |
| docker compose | systemd and Ansible |

## Single-node track

`solana-test-validator` from the official macOS release, for first contact with the CLI.

```bash
export PATH=$PWD/.release/solana-release/bin:$PATH
solana -u http://127.0.0.1:8899 slot
solana -u http://127.0.0.1:8899 epoch-info
solana -u http://127.0.0.1:8899 gossip
solana -u http://127.0.0.1:8899 validators
kill "$(cat run/tv.pid)"      # stop it
```
