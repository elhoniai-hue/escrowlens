# EscrowLens

**Check that the escrow actually exists — before you do the work.**

🔗 **Live MVP:** http://102.203.200.157

---

## The problem

I am a freelancer in Libya. When a client promises to pay in crypto, there is no bank, no dispute desk, and no chargeback to fall back on. The only question that matters before I start working is a simple one:

> **Is the money actually there, and is this client real?**

Today that question is answered by *reading a promise in a chat window* — a screenshots-of-balances culture that is trivially faked and impossible to verify. Freelancers in places without PayPal-grade payment rails have no tool that answers it with evidence.

EscrowLens answers it **from the chain itself**.

## What it does

Paste any Solana address — an escrow wallet, a client's payout address, or a token account. EscrowLens reads the chain and returns:

- **A 0–100 trust score** with the reasoning written out, not just a number
- **Stablecoin holdings** (USDC / USDG / USDT) found on the address — the actual money
- **SOL balances on both mainnet and devnet**
- **Recent transaction history**, with success/failure flags and timestamps
- **A verdict** in plain language: safe to proceed / needs manual verification / high risk
- **Explorer links** so every claim is independently checkable

The design principle: **never assert anything the user cannot verify themselves.** Every number has a link to the explorer behind it.

## How Solana is used

EscrowLens talks to the Solana JSON-RPC directly on every request. No caching layer, no indexer, no database — the chain is the source of truth.

| RPC method | Used for |
|---|---|
| `getBalance` | SOL balance, queried against **both** devnet and mainnet for the same address |
| `getTokenAccountsByOwner` | Enumerating SPL token accounts, parsed via the Token Program, to find stablecoin holdings |
| `getSignaturesForAddress` | Recent transaction history — the activity signal that separates a real payer from a freshly-minted address |

The Solana integration is not decorative: **the score is entirely a function of on-chain state.** An address with zero history and no stablecoins cannot score well, no matter what the client claims in chat.

**Token program:** `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA`
**Clusters used:** devnet + mainnet-beta (both queried live)

### Scoring model (v0)

| Signal | Weight |
|---|---|
| Stablecoin balance present on-chain | 45 |
| Real mainnet SOL balance | 20 |
| Recent transaction activity (≥5) | 20 |
| Transaction within the last 30 days | 15 |

Deliberately transparent and deliberately conservative. The roadmap (below) adds escrow-program state checks.

## Running it

No dependencies. Python 3.8+ standard library only.

```bash
git clone https://github.com/elhoniai-hue/escrowlens.git
cd escrowlens
sudo python3 app.py          # binds :80 — or PORT=8080 python3 app.py
```

Open `http://localhost/`.

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `80` | HTTP port |
| `SOLANA_RPC` | `https://api.devnet.solana.com` | Devnet RPC endpoint |

### API

```
GET /api/check?address=<solana-address>   → JSON report
GET /health                               → {"ok": true, "rpc": "..."}
```

## Deployment

- **Mainnet:** the app queries `https://api.mainnet-beta.solana.com` live for balances, token accounts and transaction history.
- **Devnet:** queried in parallel per address, so escrow built on devnet is also visible.
- **Live instance:** http://102.203.200.157 (systemd service, auto-restart)

## Why this, why me

I work on banking-systems development and I freelance for crypto payouts, so I live on both sides of this problem: the sender's compliance and the receiver's safety. EscrowLens is the tool I wanted and could not find.

## Roadmap

1. **Escrow-program awareness** — read the actual escrow state (PDA accounts, release conditions, dispute flags) for common Solana escrow programs, not just the wallet balances.
2. **Counterparty history** — has this address paid freelancers before? Build a public track record from signatures.
3. **Shareable proof pages** — a read-only link a freelancer can attach to a dispute.
4. **Watch mode** — alert me if an escrowed balance moves before the milestone is delivered.
5. **Multi-chain** — the same primitive applies anywhere there is a public ledger.

## License

MIT
