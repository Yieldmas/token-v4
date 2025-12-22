# Yield-Bearing Liquidity Pool with Bonding Curve

## Overview

This is a liquidity pool (LP) system that combines:
- **Bonding curve pricing** (constant product AMM: x*y=k)
- **Yield generation** through vault rehypothecation (5% APY on USDC)
- **Token inflation** for liquidity providers (5% APY on tokens)
- **Dynamic price discovery** that increases with both buys and vault yield

Users can buy tokens, provide liquidity, earn yield, and exit at any time.

---

## Core Mechanics

### 1. Buy Tokens

Users buy tokens with USDC using a bonding curve:

```
(token_reserve - token_out) * (usdc_reserve + usdc_in) = k
```

**What happens:**
- User sends USDC to pool
- Pool mints new tokens based on bonding curve formula
- USDC is deposited into yield vault (rehypothecation)
- `buy_usdc` tracker increases (affects price)
- Price increases due to bonding curve dynamics

**Example:**
- User buys with 500 USDC
- Gets ~476 tokens (slippage from bonding curve)
- Price after: 500 / 476 ≈ 1.05
- All 500 USDC goes to vault earning 5% APY

---

### 2. Add Liquidity

Users provide tokens + USDC to become liquidity providers (LPs):

**What happens:**
- User deposits tokens + USDC symmetrically (equal value at current price)
- USDC is deposited into vault for yield generation
- `lp_usdc` tracker increases (does NOT affect price)
- User receives LP position entitling them to:
  - Their principal back
  - 5% APY on their USDC
  - 5% APY on their tokens (inflation)
- Price remains stable (LP USDC doesn't affect bonding curve)

**Key insight:** Only `buy_usdc` affects price, not `lp_usdc`. This prevents price jumps when adding liquidity.

**Example:**
- User has 476 tokens from buy
- Price is 1.05
- User adds: 476 tokens + 500 USDC
- Total in vault: 1000 USDC (500 from buy + 500 from LP)
- Price stays 1.05 (no jump)

---

### 3. Vault Compounding

Vault earns 5% APY (compounded daily):

```
vault_balance = principal * (1 + apy/365) ^ days
```

**What happens:**
- Vault balance grows over time
- `buy_usdc` portion of vault grows with yield
- Price increases as `buy_usdc` grows (more USDC backing same tokens)
- LP yield accrues separately

**Example after 100 days:**
- Vault grows from 1000 → ~1068 USDC
- `buy_usdc` share: 500 → ~534 USDC (with yield)
- `lp_usdc` share: 500 → ~534 USDC (with yield)
- Price: 534 / 476 ≈ 1.12 (increased from yield)

---

### 4. Remove Liquidity

LPs can remove their liquidity position:

**What happens:**
- Calculate yield based on time staked: `delta = current_index / entry_index`
- LP gets:
  - Original LP USDC + 5% APY yield
  - Original tokens + 5% APY inflation (new tokens minted)
  - Share of buy USDC yield (proportional to their stake)
- **Fair share scaling** applied to prevent bank runs
- User receives USDC + inflated tokens

**Fair share scaling:**
```
scaling_factor = min(1, fair_share / requested, vault_available / requested)
```

This ensures no user can drain vault beyond their fair share.

**Example:**
- User staked 500 USDC + 476 tokens for 100 days
- Delta: 1.0682 (68.2% yield over 100 days)
- LP USDC yield: 500 * 0.0682 ≈ 34 USDC
- Token inflation: 476 * 0.0682 ≈ 32 tokens
- Buy USDC yield: proportion of ~34 USDC
- Total USDC out: ~568 USDC
- Total tokens out: ~508 tokens

---

### 5. Sell Tokens

Users can sell tokens back to the pool:

**What happens:**
- User sends tokens to pool
- Pool burns tokens (reduces `minted`)
- Pool calculates USDC out using bonding curve:

```
(token_reserve + token_in) * (usdc_reserve - usdc_out) = k
```

- **Fair share cap** applied: `min(curve_amount, user_fraction * vault)`
- USDC withdrawn from vault (dehypo)
- User receives USDC
- Price decreases (fewer tokens, less USDC)

**Fair share cap:**
```
user_fraction = tokens_sold / total_minted
max_usdc = user_fraction * vault.balance_of()
```

This prevents late sellers from getting more than their fair share.

**Example:**
- User sells 508 tokens
- Bonding curve says: ~540 USDC
- Fair share: (508 / 508) * 1068 ≈ 1068 USDC
- User gets: min(540, 1068) = 540 USDC (bonding curve wins)

---

## Bonding Curve Deep Dive

### Virtual Reserves

The bonding curve uses **virtual reserves** for flexibility:

```python
token_reserve = (CAP - minted) / exposure_factor
usdc_reserve = buy_usdc_with_yield + virtual_liquidity
k = token_reserve * usdc_reserve
```

**CAP:** 1 billion tokens (max supply)
**minted:** Current minted tokens
**exposure_factor:** Dynamic factor that decreases as more tokens are minted
**virtual_liquidity:** Bootstrap liquidity that decreases as USDC is added

---

### Dynamic Exposure Factor

```python
exposure = EXPOSURE_FACTOR * (1 - min(minted * 1000, CAP) / CAP)
exposure_factor = 100,000 initially
```

**Purpose:** Amplifies price movement for small test amounts

- At 0 minted: exposure = 100,000
- At 1M tokens minted: exposure → 0
- Creates a steeper bonding curve initially
- Flattens as more tokens are minted

**Example:**
- CAP = 1B tokens
- EXPOSURE_FACTOR = 100K
- Effective cap for curve = 1B / 100K = 10,000
- Much smaller reserve makes price more sensitive

---

### Dynamic Virtual Liquidity

```python
virtual_liquidity = base * (1 - min(buy_usdc, VIRTUAL_LIMIT) / VIRTUAL_LIMIT)
base = CAP / EXPOSURE_FACTOR = 10,000
VIRTUAL_LIMIT = 100,000 USDC
```

**Purpose:** Bootstrap initial liquidity, vanishes as real USDC accumulates

- At 0 USDC: virtual liquidity = 10,000
- At 100K USDC: virtual liquidity → 0
- Creates smooth price discovery from launch
- Prevents division by zero

**Floor constraint:**
```python
floor = token_reserve - buy_usdc  # Ensures usdc_reserve >= token_reserve
virtual_liquidity = max(virtual_liquidity, floor, 0)
```

---

## Price Calculation

### Current Price (Marginal)

The price is the **marginal price** from the bonding curve:

```python
price = usdc_reserve / token_reserve
```

Where:
- `usdc_reserve = buy_usdc_with_yield + virtual_liquidity`
- `token_reserve = (CAP - minted) / exposure`

**Why this formula?**
- This is the instantaneous price for the next infinitesimal token
- Derived from constant product formula: d(USDC) / d(Token) = USDC / Token
- Represents the current market price

**Price increases when:**
1. Users buy tokens (`buy_usdc` increases, `minted` increases via curve)
2. Vault compounds (buy_usdc grows with yield)
3. Virtual liquidity decreases (denominator shrinks)

**Price does NOT increase when:**
- Users add liquidity (only `lp_usdc` increases, not `buy_usdc`)

---

### Buy USDC with Yield

```python
compound_ratio = vault.balance_of() / (buy_usdc + lp_usdc)
buy_usdc_with_yield = buy_usdc * compound_ratio
```

**Purpose:** Track how buy_usdc portion grows with vault yield

- Vault holds total USDC (buy + lp)
- Vault compounds everything together
- But we need to know buy_usdc portion for price calculation
- This proportionally allocates vault growth to buy_usdc

**Example:**
- buy_usdc = 500, lp_usdc = 500 (total principal = 1000)
- Vault compounds to 1068
- compound_ratio = 1068 / 1000 = 1.068
- buy_usdc_with_yield = 500 * 1.068 = 534
- Price uses 534 (not 500) for calculation

---

## USDC Tracking: buy_usdc vs lp_usdc

### Why Two Trackers?

**buy_usdc:**
- USDC from buy operations
- Affects bonding curve price
- Represents "backing" for minted tokens
- Used in price calculation
- Grows with vault yield

**lp_usdc:**
- USDC from add_liquidity operations
- Does NOT affect bonding curve price
- Represents LP yield pool
- Used for fair share calculations
- Grows with vault yield

### Why Separate?

If we mixed them, price would jump when users add liquidity:

**Bad (mixed):**
- User buys 500 USDC → price 1.05
- User adds LP 500 USDC → price jumps to ~2.1 (1000 / 476)
- **Problem:** Price doubled just from LP, not real demand!

**Good (separated):**
- User buys 500 USDC → price 1.05 (buy_usdc = 500)
- User adds LP 500 USDC → price stays 1.05 (buy_usdc still 500)
- **Result:** Price only changes from buys/sells/yield, not LP operations

---

## Fair Share Scaling

### Purpose

Prevent bank runs where early exiters drain vault, leaving nothing for late exiters.

### How It Works

When removing liquidity or selling:

```python
user_principal = lp_usdc_deposited + buy_usdc_deposited
total_principal = sum(all users' principals)
user_fraction = user_principal / total_principal

vault_available = vault.balance_of()
fair_share = user_fraction * vault_available

scaling_factor = min(1, fair_share / requested, vault_available / requested)
```

**Scaling is applied to BOTH:**
- USDC withdrawal (including yield)
- Token inflation

This maintains proportionality - if you get 80% of USDC yield, you get 80% of token inflation.

### Example

**Scenario:**
- Total vault: 1000 USDC
- User A deposited: 500 USDC (50% of total)
- User A requests: 600 USDC (with yield)

**Calculation:**
- Fair share: 0.5 * 1000 = 500 USDC
- Scaling: min(1, 500/600, 1000/600) = min(1, 0.833, 1.667) = 0.833

**Result:**
- User A gets: 600 * 0.833 = 500 USDC ✓
- If they had 50 tokens inflation, they get: 50 * 0.833 = 41.67 tokens

---

## Constants

```python
CAP = 1_000_000_000  # 1 billion max token supply
EXPOSURE_FACTOR = 100_000  # Price movement amplification
VIRTUAL_LIMIT = 100_000  # Max USDC before virtual liquidity vanishes
VAULT_APY = 5%  # Annual percentage yield (compounded daily)
```

---

## Complete Example Walkthrough

### Single User Journey

**Initial state:**
- User has 1000 USDC
- Pool: 0 tokens minted, 0 USDC in vault
- Price: 1.0 (default)

**Step 1: Buy 500 USDC of tokens**
- Bonding curve: ~476.2 tokens out
- buy_usdc: 500
- Vault: 500
- Price: 500 / 476.2 ≈ 1.05
- User: 500 USDC, 476.2 tokens

**Step 2: Add liquidity (476 tokens + 500 USDC)**
- lp_usdc: 500
- Vault: 1000 (500 buy + 500 lp)
- Price: 1.05 (unchanged)
- User: 0 USDC, 0 tokens, LP position

**Step 3: Compound 100 days**
- Vault: 1000 → 1068.2 USDC
- buy_usdc with yield: 500 → 534.1
- Price: 534.1 / 476.2 ≈ 1.12 (+6.7% from yield)

**Step 4: Remove liquidity**
- Delta: 1.0682
- LP USDC yield: 500 * 0.0682 = 34.1
- Token inflation: 476.2 * 0.0682 = 32.5 tokens
- Buy USDC yield: ~34.1 (user's share)
- Total out: ~568 USDC, ~508.7 tokens
- User balance: 568 USDC, 508.7 tokens

**Step 5: Sell 508.7 tokens**
- Bonding curve: ~540 USDC out
- Fair share: (508.7 / 508.7) * 500 = 500 USDC
- User gets: min(540, 500) = 500 USDC (bonding curve)
- Final: ~1068 USDC

**Total profit:** ~68 USDC on 1000 initial ≈ 6.8% over 100 days ✓

---

## Key Design Principles

1. **Separation of concerns:** buy_usdc (price) vs lp_usdc (yield)
2. **Bonding curve for price discovery:** Market-driven pricing
3. **Virtual reserves for flexibility:** Bootstrap liquidity, dynamic exposure
4. **Fair share scaling:** Prevent bank runs, ensure fairness
5. **Yield compounding:** Both USDC and tokens earn 5% APY
6. **Proportional scaling:** USDC and token yields scaled together

---

## Known Issues & Trade-offs

### Issue 1: Vault Residual

After all users exit, small amount of USDC may remain in vault due to:
- Bonding curve slippage on entry/exit
- Fair share caps preventing full withdrawal
- Rounding errors in yield calculations

**Current behavior:** Vault may have ~20-50 USDC residual in test scenarios

**Potential fixes:**
- Give residual to last exiting user
- Distribute residual proportionally on sells
- Adjust bonding curve to eliminate slippage

### Issue 2: Late Buyer Disadvantage

Users who buy tokens late (at higher price due to appreciation) may lose money if:
- They exit early (less time to earn yield)
- Fair share caps prevent full bonding curve payout
- Price decreased significantly between entry and exit

**Current behavior:** In bank run scenarios, last users may lose capital

**Potential fixes:**
- Flatten bonding curve (reduce EXPOSURE_FACTOR)
- Use linear pricing instead of bonding curve
- Separate buy/sell mechanics from yield distribution

### Issue 3: Price Slippage

Bonding curve creates slippage on large buys/sells:
- Large buy: Average price paid > marginal price shown
- Large sell: Average price received < marginal price shown

**Current behavior:** 500 USDC buy has ~5% slippage (476 tokens instead of 500)

**Trade-off:** This is intended behavior for bonding curves (prevents manipulation), but may confuse users expecting 1:1 swap

---

## Testing

Run simulations with:

```bash
python test_yield_model.py
```

**Scenarios:**
1. **Single user full cycle:** Buy → Add LP → Compound → Remove LP → Sell
2. **Multi-user spreaded exits:** 4 users, staggered exits over 200 days
3. **10-user bank run:** All users exit simultaneously after 365 days

**Assertions:**
- Price increases after buys ✓
- Price increases after compounding ✓
- Vault balance never goes negative ✓
- Users can always exit (no deadlock) ✓

---

## Next Steps / Future Improvements

1. **Vault residual cleanup:** Ensure vault → 0 when all users exit
2. **Slippage reduction:** Consider flattening bonding curve or using linear pricing
3. **Dynamic fees:** Add swap fees that go to LPs
4. **Time-weighted rewards:** Bonus APY for longer staking periods
5. **Token locking:** Optional lock periods for higher yields
6. **Multiple vaults:** Different risk/reward profiles (Spark, Sky, Aave)
7. **Exit queue:** Orderly exits during high volatility
8. **Insurance fund:** Reserve pool to cover negative scenarios

---

## References

- **Constant Product AMM:** Uniswap v2 (x*y=k)
- **Bonding Curves:** Bancor protocol
- **Rehypothecation:** Using deposited assets to generate yield
- **Compounding snapshots:** Efficient on-chain yield tracking