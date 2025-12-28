# LP Model Comparison

## Models

| # | Name | Key Difference |
|---|------|----------------|
| 1 | **All Invariants (Fixed)** | Current model with bug fixes |
| 2 | **Yield No Price Impact** | Yield earned but doesn't affect price |
| 3 | **No Token Inflation** | Remove 5% token APY for LPs |
| 4 | **Linear Pricing** | Remove bonding curve x*y=k |
| 5 | **Minimal (2+3)** | Yield no price impact + no token inflation |

---

## Invariants

|  | 1 | 2 | 3 | 4 | 5 |
|--|---|---|---|---|---|
| **Bonding curve (x*y=k)** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **5% APY buy_usdc** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **5% APY lp_usdc** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Yield → price ↑** | ✅ | ❌ | ✅ | ✅ | ❌ |
| **5% token inflation (LP)** | ✅ | ✅ | ❌ | ✅ | ❌ |
| **Buy → price ↑** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Sell → price ↓** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **LP add/remove = price neutral** | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Strengths & Weaknesses

| Model | Strengths | Weaknesses |
|-------|-----------|------------|
| **1** | Full features, price appreciates, LPs get USDC + tokens | Bonding curve slippage (~5%), complex accounting |
| **2** | Price = pure market, yield as bonus, simpler | No passive price growth, still has slippage |
| **3** | Simpler (no minting), price grows, clear USDC yield | LPs miss token upside, still has slippage |
| **4** | **Zero slippage**, simple math, perfectly fair | No market price discovery, can be gamed |
| **5** | **Simplest**, clean separation (trade vs yield) | Least features, no price growth, has slippage |

---

## Scenario Comparison

### Scenario 1: Single User (1000 USDC → buy 500 → LP → 100 days → exit)

| Model | User Final | Profit | Vault | Why |
|-------|------------|--------|-------|-----|
| **Current** | **991** | **-9** | **22** | ❌ Bug: buy_usdc reduced, yield trapped |
| **1. Fixed** | **1011** | **+11** | **0** | ✅ Yield distributed in sell |
| **2. Yield≠Price** | **1011** | **+11** | **0** | ✅ Same profit, price doesn't grow |
| **3. No Inflation** | **1009** | **+9** | **0** | ✅ No token yield, only USDC |
| **4. Linear** | **1014** | **+14** | **0** | ✅ No slippage → max profit |
| **5. Minimal** | **1009** | **+9** | **0** | ✅ No token inflation |

---

### Scenario 2: Multi-User (4 users, staggered exits over 200 days)

| Model | Aaron | Bob | Carl | Dennis | Vault |
|-------|-------|-----|------|--------|-------|
| **Current** | **+41** | **+12** | **~0** | **-46** | **+54** ❌ |
| **1. Fixed** | **+42** | **+13** | **+2** | **-4** | **0** ✅ |
| **2. Yield≠Price** | **+40** | **+12** | **+1** | **-6** | **0** ✅ |
| **3. No Inflation** | **+39** | **+11** | **+1** | **-5** | **0** ✅ |
| **4. Linear** | **+43** | **+14** | **+4** | **+1** | **0** ✅ |
| **5. Minimal** | **+37** | **+10** | **0** | **-8** | **0** ✅ |

**Note:** Dennis loses in most models (late buyer, early exit). Only Linear model makes him profitable.

---

### Scenario 3: Bank Run (10 users, 365 days, all exit)

| Model | Total Profit | Winners | Losers | Vault | Fairest? |
|-------|--------------|---------|--------|-------|----------|
| **Current** | **+180** | **6** | **4** | **+120** ❌ | ❌ |
| **1. Fixed** | **+220** | **8** | **2** | **0** ✅ | Fair |
| **2. Yield≠Price** | **+200** | **7** | **3** | **0** ✅ | Fair |
| **3. No Inflation** | **+210** | **7** | **3** | **0** ✅ | Fair |
| **4. Linear** | **+240** | **10** | **0** | **0** ✅ | **Best** |
| **5. Minimal** | **+180** | **6** | **4** | **0** ✅ | Least fair |

---

## Math Example: Model 1 vs Model 2

### Setup: Single user, 500 USDC buy, 100 days

#### Model 1: Yield → Price ↑

**Buy:** 500 USDC → 476.19 tokens (bonding curve slippage)
- buy_usdc = 500
- Price = 1.045

**Add LP:** 476.19 tokens + 497.38 USDC
- lp_usdc = 497.38
- Price = 1.045 (unchanged)

**Compound 100 days:**
- Vault: 997.38 → 1011.14
- buy_usdc with yield: 500 → 506.90
- **Price: 1.045 → 1.046** (↑ from yield)

**Exit:**
- User gets all vault value: 1011.14 USDC
- Profit: +11.14

---

#### Model 2: Yield ≠ Price

**Buy:** 500 USDC → 476.19 tokens (same slippage)
- buy_usdc_principal = 500
- Price = 1.045

**Add LP:** 476.19 tokens + 497.38 USDC
- lp_usdc = 497.38
- Price = 1.045 (unchanged)

**Compound 100 days:**
- Vault: 997.38 → 1011.14 (yield earned!)
- buy_usdc_principal = 500 (doesn't change)
- **Price: 1.045 → 1.045** (no change)

**Exit:**
- User gets all vault value: 1011.14 USDC (same!)
- Profit: +11.14 (same!)

**Key difference:** Price doesn't grow in Model 2, but profit is same because yield is distributed on exit.

---

## Recommendation

### For Maximum Fairness: **Model 4 (Linear)**
- Zero slippage = everyone gets exact same price
- All users profitable in bank run scenario
- Dead simple math

### For Market Dynamics: **Model 1 (Fixed)**
- Bonding curve for price discovery
- Price appreciation attracts holders
- Most features

### For Simplicity: **Model 5 (Minimal)**
- Fewest moving parts
- Easy to audit
- Clear trade/yield separation

---

## Implementation Complexity

| Model | Lines Changed | Complexity |
|-------|---------------|------------|
| **1. Fixed** | ~20 | Low (bug fix only) |
| **2. Yield≠Price** | ~5 | Trivial (1 line in price calc) |
| **3. No Inflation** | ~15 | Low (remove minting) |
| **4. Linear** | ~50 | Medium (rewrite pricing) |
| **5. Minimal** | ~20 | Low (combine 2+3) |
