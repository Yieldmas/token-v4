# Yieldmas – Rehypo LP Memecoin (Draft Spec)

---

## Concept

Users buy the meme token with USDC, then provide liquidity into a **V4 Token : USDC** pool.  
The protocol rehypothecates USDC into a yield vault (e.g., **Spark / Sky**) and redistributes yield (+ fees) back to liquidity providers (and optionally lockers).

---

## User Journey

1. Buy token using USDC  
2. USDC is counted as "common wealth" in Pool (it is deposited into yield bearing vault)  
3. Add liquidity (token + USDC) to activate participation in common wealth  
4. USDC is deposited again into yield bearing vault  
5. Token is locked for some time in contract
6. When you sell USDC it is added to vault each time  
7. When you sell token then USDC is taken out from vault for liquidity  
8. Vault fees are tracked & automatically collected when you want to remove liquidity  
9. Locked token has inflation APY (example: 1 year deposit → same % as USDT APY)  
10. Custom AMM → computes amounts based on balances in PoolManager & Vault

---

## Core Economic Loop (diagram)

```mermaid
flowchart LR
  U[User] -->|swap USDC -> token| T[V4 Token]
  U -->|deposit token + USDC| P[V4:USDC Pool]
  P -->|sweep / stake USDC| V[Spark / Sky Vault]
  V -->|yield accrues| V
  P <-->|withdraw USDC to settle exits| V
  P -->|LP fees + vault yield| R[Rewards accounting]
  R -->|claim / auto-collect on remove liquidity| U
```

---

## “Common Wealth” / Accounting Intuition

The protocol tracks **two** categories of value:

- **On-hand pool balances**: what the user wallet holds *right now*
- **Deferred / vault-backed balances**: funds in the "common wealth" (pool & vaults)

A practical phrasing:

- The pool keeps just enough USDC for immediate swap/exit needs
- Excess USDC is deposited into the vault
- LPs (and/or lockers) earn a pro-rata share of vault yield + pool fees
- On exits/sells, the system pulls USDC out of the vault to settle

---

## Example Math

**Scenario**
1. 100 USDC → swap → 100 V4 tokens  
2. 100 USDC → stake → vault  
3. 100 V4 tokens + 101 USDC → add liquidity  
4. 101 USDC → stake → vault  
5. 100 V4 tokens → lock → pool  
6. User receives rewards:
   - 5% APY on 100 USDC (initial swap leg)
   - 5% APY on 101 USDC (liquidity leg)
   - 5% APY on V4 tokens (inflation)
7. Protocol effectively generates ~7.5% APY from whole user capital

After ~1 year (illustration from your note):
- user portfolio: **111.15 USDC + 105 V4 tokens**

> Exact outcomes depend on vault APY, fee model, how you attribute “swap-leg” yield, and how you price exits.

---

## Implementation Sketch (Facet / Hook Awareness)

1) **Initial deployment**: “V4 token facet” + base asset functionality  
2) **Pool creation with hook**  
3) **Attach facet aware of Pool, Hook & Vault**

```mermaid
flowchart TB
  subgraph Deploy
    F[V4 token facet] --> BA[Base asset functionality]
  end

  subgraph Pool
    P[V4:USDC Pool] <--> H[Liquidity control hook]
  end

  subgraph Yield
    V[Spark / Sky Vault]
  end

  F -->|swap tracking / deferred balances| P
  F -->|vault integration / rehypothecation| V
  P -->|stake USDC| V
  V -->|withdraw USDC to settle exits| P
```
