# Keys, and what someone with host access can reach

A validator is run by one party and paid for by another. This page is about who holds which key,
what each key can do, and what an operator with root on the validator hosts can and cannot do
with them. Addresses are the ones of this lab, shortened.

Sources: the Agave v4.3 vote program (`programs/vote/src/vote_state/mod.rs`), the Firedancer source
tree and CLI reference, and the Anza failover guide. Where something is my reading and not from a
source, it says so.

## Two parties

| | Operator | Delegator |
|---|---|---|
| Who | Runs the validator | Owns the SOL |
| On-chain record | Vote account | Stake account |
| Key that does the work | Identity (also the vote authority) | Stake authority |
| Key that moves money | Withdraw authority of the vote account | Withdraw authority of the stake account |

An account is controlled either by its own private key or by an address written inside it, an
*authority*. Only the identity and a wallet are controlled by their own key. The vote account and
the stake account each have a keypair that is used once, to create them, and controls nothing
afterwards.

The only link between the two parties is the delegation: a stake account names a vote account.
The SOL never leaves the stake account.

## Operator side

```
Vote account  FoBb…        votes, vote credits, commission settings, commission income
├── Vote authority     = 6vj8…   (the identity)     may sign votes
└── Withdraw authority = DRVH…                      may withdraw commission, change the commission,
                                                    change where rewards are paid, move the vote
                                                    account to another identity, replace both authorities
```

| Key | Where it is kept | What it does |
|---|---|---|
| Identity | On the validator host, online. On the hot spare too, at rest | Signs votes and blocks. Its account pays the vote fees and receives block revenue |
| Withdraw authority of the vote account | Offline; never on a host | Everything in the second branch above |

## Delegator side

```
Stake account  DFiP…       the delegator's SOL, and the vote account it is delegated to
├── Stake authority    = F5zR…   (the wallet)       may delegate and deactivate
└── Withdraw authority = F5zR…   (same by default)  may withdraw the SOL, replace both authorities
```

Rewards are paid into the stake account every epoch and compound there. Leaving is the delegator's
call alone: deactivate, wait for the epoch boundary, withdraw.

## What an operator with host access can do

| Action | Possible? |
|---|---|
| Make the validator miss votes or leader slots | Yes. The usual case, by mistake rather than intent |
| Cause double voting, by running the identity on two hosts | Yes |
| Move the SOL in the identity account (fee balance and accumulated block revenue) | Yes |
| Hand the vote authority to another key | Yes: the current vote authority may sign that change. It takes effect in a later epoch and the withdraw authority can undo it |
| Choose the binary, its flags, and the block-building connection | Yes |
| Set the MEV commission | Yes on Firedancer, where it is a line in the config file (`[tiles.bundle] commission_bps`) |
| Change the inflation rewards commission, or withdraw commission from the vote account | No: needs the withdraw authority |
| Redirect where rewards are paid | No: `update_commission_collector` requires the withdraw authority |
| Move the vote account to a different identity | No: needs the withdraw authority and the new identity's signature |
| Touch a delegator's SOL, or stop a delegator from leaving | No |

In one line: host access can hurt income and reputation. It cannot reach the delegators' principal.

What follows for operations:

- The identity account is a hot wallet. Block revenue lands there, so sweep it and keep the balance
  near what voting needs.
- A hot spare is a second place where the staked identity key lies. The switch procedure and the
  identity alerts are the control for that.
- Topping up the identity must not use the withdraw authority. A small funding wallet does it.
- The withdraw authority belongs on a hardware wallet or a multisig, with people who do not hold
  root. This lab does not model that: the file sits on the control machine, next to the playbooks.
- If the identity key is lost, the withdraw authority can give the vote account a new one and the
  delegations stay where they are. If the withdraw authority is lost, nothing can be changed any
  more. That makes it the key that must not be lost and must not leak.

## Never two machines voting with one identity

No single safeguard is enough, so they are stacked.

| Safeguard | Works when | Weak point | Agave | Firedancer |
|---|---|---|---|---|
| The order of the switch: the old host lets go, then the new host takes over | Planned switch, both hosts healthy | Cannot be completed when the old host is unreachable | `set-identity <unstaked>` on the old host, then `set-identity --require-tower <staked>` on the new one; `wait-for-restart-window` first | `fdctl set-identity --config <the toml the validator runs with>`. Without `--config` the key may not change on every tile. Waits for a leader slot in progress. A cancelled run needs `--force` |
| Fencing from outside the host: power off through the BMC, or shut the switch port | The old host cannot be reached | Needs an out-of-band path that still works | Not a client feature. The Anza guide: shut the primary down, "powering off the machine if necessary". Here: `scripts/fence.sh` disconnects the container's network, and `takeover.yml` refuses to run without it | The same |
| What the host is after a restart: the identity path points at the unstaked key | The old host reboots | Still points at the staked key if the switch never finished | `--identity` is a symlink, rewritten after each `set-identity` (Anza guide) | `identity_path` in the config; the same link would work there (my inference) |
| No staked key on the old host | Always | Switching back means moving the key again | Operator's choice | The same |
| The vote record moves with the identity, and a takeover without it is refused | The new host takes over | Protects the new host only; a stale copy passes the check | `tower-1_9-<identity>.bin`, rewritten on every vote; `--require-tower`. Without the file and the flag, the tower is rebuilt from the vote account on chain | `tower.bin`; `--require-tower` on `set-identity`, `require_tower` in the config |
| Duplicate-instance check in gossip: the older instance exits when it sees a newer one with its identity | Both instances see each other | Slow to propagate; useless while the old host is cut off; an automatic restart brings the host back | "duplicate running instances of the same validator node" (`gossip/src/cluster_info.rs`) | The same check and message (`src/discof/gossip/fd_gossvf_tile.c`) |
| Monitoring from outside: how many hosts run each voting identity | Seconds later, after the fact | Sees only the hosts it scrapes | Here: alerts for "on two hosts" and "on none" | Not built here |
| The key inside the validator | A component is compromised | Does not protect against root on the host | One process holds it | Only the sandboxed sign tile holds it |

Slashing is not live on Solana at the time of writing: public write-ups and the Firedancer CLI
reference speak of "(future) slashing". Double voting costs reputation today and may cost stake
later.
