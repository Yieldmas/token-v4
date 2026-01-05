from decimal import Decimal as D
from typing import Dict, Optional

# const
K = D(1_000)
B = D(1_000_000_000)

# price movement amplification
EXPOSURE_FACTOR = 100 * K

# cap
CAP = 1 * B

# max USDC before virtual liquidity vanishes
VIRTUAL_LIMIT = 100 * K

# ANSI color codes
class Color:
    HEADER = '\033[95m'      # Magenta
    BLUE = '\033[94m'        # Blue
    CYAN = '\033[96m'        # Cyan
    GREEN = '\033[92m'       # Green
    YELLOW = '\033[93m'      # Yellow
    RED = '\033[91m'         # Red
    BOLD = '\033[1m'         # Bold
    UNDERLINE = '\033[4m'    # Underline
    DIM = '\033[2m'          # Dim/faint
    STATS = '\033[90m'       # Gray (for technical stats)
    END = '\033[0m'          # Reset

class User:
    name: str
    balance_usd: D
    balance_token: D

    def __init__(self, name: str, usd: D = D(0), token: D = D(0)):
        self.name = name
        self.balance_usd = usd
        self.balance_token = token

class CompoundingSnapshot:
    value: D
    index: D

    def __init__(self, value: D, index: D):
        self.value = value
        self.index = index

class Vault:
    apy: D
    balance_usd: D
    compounding_index: D
    snapshot: Optional[CompoundingSnapshot]
    compounds: int

    def __init__(self):
        self.apy = D(5) / D(100)
        self.balance_usd = D(0)
        self.compounding_index = D(1.0)
        self.snapshot = None
        self.compounds = 0

    def balance_of(self) -> D:
        if self.snapshot is None:
            return self.balance_usd
        return self.snapshot.value * (self.compounding_index / self.snapshot.index)

    def add(self, value: D):
        self.snapshot = CompoundingSnapshot(
            value + self.balance_of(),
            self.compounding_index
        )
        self.balance_usd = self.balance_of()

    def remove(self, value: D):
        if self.snapshot is None:
            raise Exception("Nothing staked!")
        self.snapshot = CompoundingSnapshot(
            self.balance_of() - value,
            self.compounding_index
        )
        self.balance_usd = self.balance_of()

    def compound(self, days: int):
        # run compounding daily
        for _ in range(days):
            self.compounding_index *= D(1) + (self.apy / D(365))

        # track compounds number
        self.compounds += days

class UserSnapshot:
    index: D

    def __init__(self, index: D):
        self.index = index

class LP:
    balance_usd: D
    balance_token: D
    minted: D
    liquidity_token: Dict[str, D]
    liquidity_usd: Dict[str, D]
    user_buy_usdc: Dict[str, D]
    user_snapshot: Dict[str, UserSnapshot]
    vault: Vault
    k: Optional[D]
    buy_usdc: D  # USDC from buy operations (affects bonding curve)
    lp_usdc: D   # USDC from LP operations (yield only)
    virtual_liquidity: D  # Bootstrap virtual USDC for bonding curve

    def __init__(self, vault: Vault):
        self.balance_usd = D(0)
        self.balance_token = D(0)
        self.minted = D(0)
        self.liquidity_token = {}
        self.liquidity_usd = {}
        self.user_buy_usdc = {}
        self.user_snapshot = {}
        self.vault = vault
        self.k = None
        self.buy_usdc = D(0)
        self.lp_usdc = D(0)
        self.virtual_liquidity = CAP / EXPOSURE_FACTOR  # Bootstrap virtual liquidity

    def get_buy_usdc_with_yield(self) -> D:
        """
        Get current buy_usdc value including compounded yield.
        Buy USDC grows proportionally with total vault balance.
        """
        if self.buy_usdc == 0 and self.lp_usdc == 0:
            return D(0)

        total_principal = self.buy_usdc + self.lp_usdc
        if total_principal == 0:
            return D(0)

        # Buy USDC gets its share of vault yield
        compound_ratio = self.vault.balance_of() / total_principal
        return self.buy_usdc * compound_ratio

    @property
    def price(self) -> D:
        """Current token price calculated from bonding curve marginal price.
        price = usdc_reserve / token_reserve
        This is the instantaneous price for the next token based on x*y=k curve.
        Only buy USDC affects price, not LP USDC."""
        token_reserve = self._get_token_reserve()
        usdc_reserve = self._get_usdc_reserve()
        if token_reserve == 0:
            return D(1)  # fallback if no reserves
        return usdc_reserve / token_reserve

    def get_exposure(self) -> D:
        """
        Dynamic exposure that decreases as more tokens are minted.
        Reaches 0 at 1M tokens minted.
        """
        # Amplify minting effect by 1000x to hit 0 at 1M tokens
        effective = min(self.minted * D(1000), CAP)
        exposure = EXPOSURE_FACTOR * (D(1) - effective / CAP)
        return max(D(0), exposure)

    def get_virtual_liquidity(self) -> D:
        """
        Dynamic virtual liquidity that decreases as more USDC is added.
        Floor at 0 USDC, ceiling at 100K USDC.
        """
        base = CAP / EXPOSURE_FACTOR  # 10,000
        effective = min(self.buy_usdc, VIRTUAL_LIMIT)
        liquidity = base * (D(1) - effective / VIRTUAL_LIMIT)

        # Floor >= 1: buy_usdc + virtual_liquidity >= token_reserve
        token_reserve = self._get_token_reserve()
        floor_liquidity = token_reserve - self.buy_usdc

        # Use the higher of liquidity or floor requirement
        return max(D(0), liquidity, floor_liquidity)

    def _get_token_reserve(self) -> D:
        """Virtual token reserve = (CAP - minted) / exposure"""
        exposure = self.get_exposure()
        return (CAP - self.minted) / exposure if exposure > 0 else CAP - self.minted

    def _get_usdc_reserve(self) -> D:
        """Virtual USDC reserve = buy_usdc_with_yield + dynamic virtual_liquidity
        Includes compounded yield so price increases as vault compounds."""
        return self.get_buy_usdc_with_yield() + self.get_virtual_liquidity()

    def _update_k(self):
        """
        Update constant product invariant using virtual reserves with dynamic exposure:
        k = (token_reserve) * (buy_usdc + virtual_liquidity)
        Only buy_usdc affects bonding curve, not lp_usdc.
        """
        self.k = self._get_token_reserve() * self._get_usdc_reserve()

    def _apply_fair_share_cap(self, requested_amount: D, user_fraction: D) -> D:
        """
        Apply fair share cap to prevent bank runs.
        Returns capped amount based on user's fraction of vault.

        Args:
            requested_amount: Amount user would get from bonding curve
            user_fraction: User's fraction of total pool (0 to 1)

        Returns:
            Capped amount: min(requested_amount, fair_share, vault_available)
        """
        vault_available = self.vault.balance_of()
        fair_share = user_fraction * vault_available
        return min(requested_amount, fair_share, vault_available)

    def _get_fair_share_scaling(self, requested_total_usdc: D, user_principal: D, total_principal: D) -> D:
        """
        Calculate fair share scaling factor for withdrawals.
        Returns a scaling factor between 0 and 1 to apply proportionally to USDC and tokens.

        Args:
            requested_total_usdc: Total USDC user would get with full yield
            user_principal: User's principal (LP USDC + buy USDC)
            total_principal: Total principal in pool (all users' LP USDC + buy USDC)

        Returns:
            Scaling factor (0 to 1) to apply to both USDC and token withdrawals
        """
        vault_available = self.vault.balance_of()

        if total_principal > 0 and requested_total_usdc > 0:
            fraction = user_principal / total_principal
            fair_share = fraction * vault_available
            # scale down if either fair_share or vault_available is insufficient
            scaling_factor = min(D(1), fair_share / requested_total_usdc, vault_available / requested_total_usdc)
        elif requested_total_usdc > 0:
            # no principal tracked, just cap at vault available
            scaling_factor = min(D(1), vault_available / requested_total_usdc)
        else:
            # no USDC requested, no scaling needed
            scaling_factor = D(1)

        return scaling_factor

    def _get_out_amount(self, sold_amount: D, selling_token: bool) -> D:
        """
        Calculate output using constant product with virtual reserves:
        (token_reserve) * (buy_usdc + virtual_liquidity) = k
        Uses dynamic exposure that decreases as more tokens are minted.
        Only buy_usdc affects bonding curve, not lp_usdc.
        Applies quadratic vault scaling on sells to prevent depletion.
        """
        if self.k is None:
            # First buy: initialize k with dynamic virtual liquidity
            self.k = self._get_token_reserve() * self.get_virtual_liquidity()

        token_reserve = self._get_token_reserve()
        usdc_reserve = self._get_usdc_reserve()

        if selling_token:
            # Selling tokens, getting USDC (sell operation)
            # User adds tokens back, removes USDC from buy pool
            # (token_reserve + token_in) * (usdc_reserve - usdc_out) = k
            new_token_reserve = token_reserve + sold_amount
            new_usdc_reserve = self.k / new_token_reserve
            usdc_out_curve = usdc_reserve - new_usdc_reserve

            if self.minted == 0:
                # All tokens sold - use bonding curve with virtual reserves, no fair share scaling
                vault_available = self.vault.balance_of()
                return min(usdc_out_curve, vault_available)

            # apply fair share cap to prevent bank run
            user_fraction = sold_amount / self.minted
            return self._apply_fair_share_cap(usdc_out_curve, user_fraction)
        else:
            # Buying tokens with USDC
            # User adds USDC to buy pool, mints tokens
            # (token_reserve - token_out) * (usdc_reserve + usdc_in) = k
            new_usdc_reserve = usdc_reserve + sold_amount
            new_token_reserve = self.k / new_usdc_reserve
            token_out = token_reserve - new_token_reserve
            return token_out

    def mint(self, amount: D):
        if self.minted + amount > CAP:
            raise Exception("Cannot mint over cap")
        self.balance_token += amount
        self.minted += amount

    def add_liquidity(self, user: User, token_amount: D, usd_amount: D):
        # take tokens from user
        user.balance_token -= token_amount
        user.balance_usd -= usd_amount

        # push tokens to pool
        self.balance_token += token_amount
        self.balance_usd += usd_amount

        # track LP USDC (does NOT affect bonding curve)
        self.lp_usdc += usd_amount

        # put usdc on vault for yield generation
        self.rehypo()

        # initialize or update k on first liquidity add
        if self.k is None:
            self._update_k()

        # snapshot compounding index
        self.user_snapshot[user.name] = UserSnapshot(
            self.vault.compounding_index
        )

        # compute liquidity
        self.liquidity_token[user.name] = self.liquidity_token.get(user.name, D(0)) + token_amount
        self.liquidity_usd[user.name] = self.liquidity_usd.get(user.name, D(0)) + usd_amount

    def remove_liquidity(self, user: User):
        # get user's deposited amounts
        token_deposit = self.liquidity_token[user.name]
        usd_deposit = self.liquidity_usd[user.name]
        buy_usdc_principal = self.user_buy_usdc.get(user.name, D(0))

        # calculate yield based on compounding
        delta = self.vault.compounding_index / self.user_snapshot[user.name].index

        # LP USDC yield (5% APY)
        usd_yield = usd_deposit * (delta - D(1))
        usd_amount_full = usd_deposit + usd_yield

        # LP token inflation (5% APY)
        token_yield_full = token_deposit * (delta - D(1))

        # Buy USDC yield (5% APY)
        buy_usdc_yield_full = buy_usdc_principal * (delta - D(1))
        total_usdc_full = usd_amount_full + buy_usdc_yield_full

        # calculate fair share scaling factor
        principal = usd_deposit + buy_usdc_principal
        total_principal = self.lp_usdc + self.buy_usdc
        scaling_factor = self._get_fair_share_scaling(total_usdc_full, principal, total_principal)

        # apply scaling to both USDC and tokens proportionally
        total_usdc = total_usdc_full * scaling_factor
        token_yield = token_yield_full * scaling_factor
        token_amount = token_deposit + token_yield

        # mint scaled inflation yield on tokens
        self.mint(token_yield)

        # remove scaled USDC from vault
        self.dehypo(total_usdc)

        # reduce lp_usdc by the original LP principal
        self.lp_usdc -= usd_deposit

        # reduce buy_usdc by scaled buy yield
        buy_usdc_yield_actual = buy_usdc_yield_full * scaling_factor
        self.buy_usdc -= buy_usdc_yield_actual

        # remove funds from lp
        self.balance_token -= token_amount
        self.balance_usd -= total_usdc

        # send funds to user
        user.balance_token += token_amount
        user.balance_usd += total_usdc

        # clear user liquidity
        del self.liquidity_token[user.name]
        del self.liquidity_usd[user.name]
        if user.name in self.user_buy_usdc:
            del self.user_buy_usdc[user.name]

    def buy(self, user: User, amount: D):
        # take usd
        user.balance_usd -= amount
        self.balance_usd += amount

        # compute out amount (token) using x*y=k
        out_amount = self._get_out_amount(amount, selling_token=False)

        # always mint new tokens for buy operations (don't use LP tokens)
        self.mint(out_amount)

        # give token
        self.balance_token -= out_amount
        user.balance_token += out_amount

        # track buy USDC (affects bonding curve)
        self.buy_usdc += amount

        # track USDC used to buy tokens
        self.user_buy_usdc[user.name] = self.user_buy_usdc.get(user.name, D(0)) + amount

        # rehypo (deposits all USDC to vault)
        self.rehypo()

        # update invariant
        self._update_k()

    def rehypo(self):
        # add funds to vault
        self.vault.add(self.balance_usd)

        # remove funds from lp
        self.balance_usd = D(0)

    def sell(self, user: User, amount: D):
        # take token
        user.balance_token -= amount

        # burn tokens
        self.minted -= amount

        # compute amount out (usd) using x*y=k
        out_amount = self._get_out_amount(amount, selling_token=True)

        # update buy_usdc (reduces bonding curve reserve)
        self.buy_usdc -= out_amount

        # dehypo
        self.dehypo(out_amount)

        # give usd
        self.balance_usd -= out_amount
        user.balance_usd += out_amount

        # update invariant after swap
        self._update_k()

    def dehypo(self, amount: D):
        # remove from vault
        self.vault.remove(amount)

        # add to lp
        self.balance_usd += amount

    def print_stats(self, label: str = "Stats"):
        """Print detailed mathematical statistics for nerds"""
        # Use CYAN which is visible on both light and dark backgrounds
        print(f"\n{Color.CYAN}  ┌─ 📊 {label} (Math Under the Hood) ─────────────────────────{Color.END}")

        # Virtual reserves
        token_reserve = self._get_token_reserve()
        usdc_reserve = self._get_usdc_reserve()
        print(f"{Color.CYAN}  │ Virtual Reserves: {Color.END}token={Color.YELLOW}{token_reserve:.2f}{Color.END}, usdc={Color.YELLOW}{usdc_reserve:.2f}{Color.END}")

        # Bonding curve constant
        k_value = f"{self.k:.2f}" if self.k else "None"
        print(f"{Color.CYAN}  │ Bonding Curve k: {Color.YELLOW}{k_value}{Color.END}")

        # Dynamic factors
        exposure = self.get_exposure()
        virtual_liq = self.get_virtual_liquidity()
        buy_usdc_with_yield = self.get_buy_usdc_with_yield()
        print(f"{Color.CYAN}  │ Exposure Factor: {Color.YELLOW}{exposure:.2f}{Color.END} (decreases as tokens mint)")
        print(f"{Color.CYAN}  │ Virtual Liquidity: {Color.YELLOW}{virtual_liq:.2f}{Color.END} (decreases as USDC added)")

        # USDC tracking
        total_principal = self.buy_usdc + self.lp_usdc
        buy_ratio = (self.buy_usdc / total_principal * 100) if total_principal > 0 else D(0)
        lp_ratio = (self.lp_usdc / total_principal * 100) if total_principal > 0 else D(0)
        print(f"{Color.CYAN}  │ USDC Split: {Color.END}buy={Color.YELLOW}{self.buy_usdc:.2f}{Color.END} ({buy_ratio:.1f}%), lp={Color.YELLOW}{self.lp_usdc:.2f}{Color.END} ({lp_ratio:.1f}%)")
        print(f"{Color.CYAN}  │ Buy USDC (w/yield): {Color.YELLOW}{buy_usdc_with_yield:.2f}{Color.END}")

        # Vault & compounding
        print(f"{Color.CYAN}  │ Vault Balance: {Color.YELLOW}{self.vault.balance_of():.2f}{Color.END}")
        print(f"{Color.CYAN}  │ Vault Index: {Color.YELLOW}{self.vault.compounding_index:.6f}{Color.END} ({self.vault.compounds} days)")

        # Price calculation breakdown
        if token_reserve > 0:
            print(f"{Color.CYAN}  │ Price: {Color.END}usdc_reserve/token_reserve = {Color.YELLOW}{usdc_reserve:.2f}{Color.END}/{Color.YELLOW}{token_reserve:.2f}{Color.END} = {Color.GREEN}{self.price:.6f}{Color.END}")

        # Minted vs Cap
        mint_pct = (self.minted / CAP * 100) if CAP > 0 else D(0)
        print(f"{Color.CYAN}  │ Minted: {Color.YELLOW}{self.minted:.2f}{Color.END} / {CAP} ({mint_pct:.4f}%)")

        print(f"{Color.CYAN}  └────────────────────────────────────────────────────────────{Color.END}\n")

def single_user_scenario(
    user_initial_usd: D = 1 * K,
    user_buy_token_usd: D = D(500),
    compound_days: int = 100,
):
    vault = Vault()
    lp = LP(vault)
    user = User("aaron", user_initial_usd)

    # Scenario header
    print(f"\n{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'  SCENARIO 1: SINGLE USER FULL CYCLE':^70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}\n")

    print(f"{Color.CYAN}[Initial]{Color.END} User USDC: {Color.YELLOW}{user.balance_usd}{Color.END}")
    lp.print_stats("Initial State")

    # buy tokens for 500 usd
    print(f"\n{Color.BLUE}--- Phase 1: Buy Tokens ---{Color.END}")
    lp.buy(user, user_buy_token_usd)
    assert lp.balance_usd == D(0)
    assert vault.balance_usd == user_buy_token_usd
    assert vault.balance_of() == user_buy_token_usd
    print(f"[Buy] Spent: {Color.YELLOW}{user_buy_token_usd}{Color.END} USDC")
    print(f"[Buy] Got tokens: {Color.YELLOW}{user.balance_token}{Color.END}")

    # assert price after buy
    assert lp.price > D(1), f"Price should be > 1, got {lp.price}"
    print(f"[Buy] Token price: {Color.GREEN}{lp.price}{Color.END}")
    print(f"[Buy] Vault balance: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    lp.print_stats("After Buy")

    # add liquidity symmetrically: match token value at current price
    print(f"\n{Color.BLUE}--- Phase 2: Add Liquidity ---{Color.END}")
    user_add_liquidity_token = user.balance_token
    user_add_liquidity_usd = user_add_liquidity_token * lp.price
    lp.add_liquidity(user, user_add_liquidity_token, user_add_liquidity_usd)
    assert lp.balance_token == user_add_liquidity_token
    assert lp.balance_usd == D(0)
    assert vault.balance_usd == user_add_liquidity_usd + user_buy_token_usd
    assert vault.balance_of() == user_add_liquidity_usd + user_buy_token_usd
    print(f"[LP] Added USDC: {Color.YELLOW}{user_add_liquidity_usd}{Color.END}")
    print(f"[LP] Added tokens: {Color.YELLOW}{user_add_liquidity_token}{Color.END}")
    print(f"[LP] Token price: {Color.GREEN}{lp.price}{Color.END}")
    print(f"[LP] Vault balance: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    lp.print_stats("After Adding Liquidity")

    # compound for 100 days
    print(f"\n{Color.BLUE}--- Phase 3: Compound for {compound_days} days ---{Color.END}")
    price_after_add_liquidity = lp.price
    vault.compound(compound_days)
    price_after_compound = lp.price
    print(f"[{compound_days} days] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"[{compound_days} days] Price: {Color.GREEN}{price_after_add_liquidity}{Color.END} → {Color.GREEN}{price_after_compound}{Color.END}")
    price_increase = price_after_compound - price_after_add_liquidity
    print(f"[{compound_days} days] Price increase: {Color.GREEN}+{price_increase}{Color.END}")

    # price changes as vault balance grows (more USDC per token)
    assert lp.price > price_after_add_liquidity, f"Price should increase as vault compounds, got {lp.price} vs {price_after_add_liquidity}"
    lp.print_stats(f"After {compound_days} Days Compounding")

    # remove liquidity
    print(f"\n{Color.BLUE}--- Phase 4: Remove Liquidity & Sell ---{Color.END}")
    user_usdc_before_removal = user.balance_usd
    lp.remove_liquidity(user)
    user_usdc_after_removal = user.balance_usd
    gain = user_usdc_after_removal - user_usdc_before_removal
    gain_color = Color.GREEN if gain > 0 else Color.RED
    print(f"[Removal] USDC: {Color.YELLOW}{user_usdc_before_removal}{Color.END} → {Color.YELLOW}{user_usdc_after_removal}{Color.END} (gain: {gain_color}{gain}{Color.END})")
    print(f"[Removal] Tokens: {Color.YELLOW}{user.balance_token}{Color.END}")
    print(f"[Removal] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    lp.print_stats("After Removing Liquidity")

    # sell all tokens
    user_tokens = user.balance_token
    user_usdc_before_sell = user.balance_usd
    lp.sell(user, user_tokens)
    user_usdc_from_sell = user.balance_usd - user_usdc_before_sell
    print(f"[Sell] Sold {Color.YELLOW}{user_tokens}{Color.END} tokens → Got {Color.YELLOW}{user_usdc_from_sell}{Color.END} USDC")
    lp.print_stats("After Selling Tokens")

    # Final summary
    print(f"\n{Color.BOLD}Final USDC: {Color.GREEN}{user.balance_usd}{Color.END}")
    profit = user.balance_usd - user_initial_usd
    profit_color = Color.GREEN if profit > 0 else Color.RED
    print(f"{Color.BOLD}Total Profit: {profit_color}{profit}{Color.END}")
    print(f"Final vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"Final minted: {Color.YELLOW}{lp.minted}{Color.END}")

def multi_user_spreaded_scenario(
    aaron_buy_usd: D = D(500),
    bob_buy_usd: D = D(400),
    carl_buy_usd: D = D(300),
    dennis_buy_usd: D = D(600),
    compound_interval: int = 50,
):
    vault = Vault()
    lp = LP(vault)
    aaron = User("aaron", 2 * K)
    bob = User("bob", 2 * K)
    carl = User("carl", 2 * K)
    dennis = User("dennis", 2 * K)

    # Scenario header
    print(f"\n{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'  SCENARIO 2: MULTI-USER SPREADED EXITS':^70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}\n")

    print(f"{Color.CYAN}[Initial]{Color.END} Aaron USDC: {Color.YELLOW}{aaron.balance_usd}{Color.END}")
    print(f"{Color.CYAN}[Initial]{Color.END} Bob USDC: {Color.YELLOW}{bob.balance_usd}{Color.END}")
    print(f"{Color.CYAN}[Initial]{Color.END} Carl USDC: {Color.YELLOW}{carl.balance_usd}{Color.END}")
    print(f"{Color.CYAN}[Initial]{Color.END} Dennis USDC: {Color.YELLOW}{dennis.balance_usd}{Color.END}")
    lp.print_stats("Initial State")

    # aaron buys tokens for 500 usd
    lp.buy(aaron, aaron_buy_usd)
    assert vault.balance_of() == aaron_buy_usd
    print(f"[Aaron Buy] Aaron tokens: {aaron.balance_token}")
    print(f"[Aaron Buy] Token price: {lp.price}")
    print(f"[Aaron Buy] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Aaron Buy")

    # aaron adds liquidity symmetrically
    aaron_add_liquidity_token = aaron.balance_token
    aaron_add_liquidity_usd = aaron_add_liquidity_token * lp.price
    lp.add_liquidity(aaron, aaron_add_liquidity_token, aaron_add_liquidity_usd)
    assert lp.liquidity_token[aaron.name] == aaron_add_liquidity_token
    print(f"[Aaron LP] Aaron liquidity tokens: {lp.liquidity_token[aaron.name]}")
    print(f"[Aaron LP] Aaron liquidity USDC: {lp.liquidity_usd[aaron.name]}")
    print(f"[Aaron LP] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Aaron LP")

    # bob buys tokens for 400 usd
    lp.buy(bob, bob_buy_usd)
    print(f"[Bob Buy] Bob tokens: {bob.balance_token}")
    print(f"[Bob Buy] Token price: {lp.price}")
    print(f"[Bob Buy] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Bob Buy")

    # bob adds liquidity symmetrically
    bob_add_liquidity_token = bob.balance_token
    bob_add_liquidity_usd = bob_add_liquidity_token * lp.price
    lp.add_liquidity(bob, bob_add_liquidity_token, bob_add_liquidity_usd)
    assert lp.liquidity_token[bob.name] == bob_add_liquidity_token
    print(f"[Bob LP] Bob liquidity tokens: {lp.liquidity_token[bob.name]}")
    print(f"[Bob LP] Bob liquidity USDC: {lp.liquidity_usd[bob.name]}")
    print(f"[Bob LP] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Bob LP")

    # carl buys tokens for 300 usd
    lp.buy(carl, carl_buy_usd)
    print(f"[Carl Buy] Carl tokens: {carl.balance_token}")
    print(f"[Carl Buy] Token price: {lp.price}")
    print(f"[Carl Buy] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Carl Buy")

    # carl adds liquidity symmetrically
    carl_add_liquidity_token = carl.balance_token
    carl_add_liquidity_usd = carl_add_liquidity_token * lp.price
    lp.add_liquidity(carl, carl_add_liquidity_token, carl_add_liquidity_usd)
    assert lp.liquidity_token[carl.name] == carl_add_liquidity_token
    print(f"[Carl LP] Carl liquidity tokens: {lp.liquidity_token[carl.name]}")
    print(f"[Carl LP] Carl liquidity USDC: {lp.liquidity_usd[carl.name]}")
    print(f"[Carl LP] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Carl LP")

    # dennis buys tokens for 600 usd
    lp.buy(dennis, dennis_buy_usd)
    print(f"[Dennis Buy] Dennis tokens: {dennis.balance_token}")
    print(f"[Dennis Buy] Token price: {lp.price}")
    print(f"[Dennis Buy] Vault balance: {vault.balance_of()}")
    lp.print_stats("After Dennis Buy")

    # dennis adds liquidity symmetrically
    dennis_add_liquidity_token = dennis.balance_token
    dennis_add_liquidity_usd = dennis_add_liquidity_token * lp.price
    lp.add_liquidity(dennis, dennis_add_liquidity_token, dennis_add_liquidity_usd)
    assert lp.liquidity_token[dennis.name] == dennis_add_liquidity_token
    print(f"[Dennis LP] Dennis liquidity tokens: {lp.liquidity_token[dennis.name]}")
    print(f"[Dennis LP] Dennis liquidity USDC: {lp.liquidity_usd[dennis.name]}")
    print(f"[Dennis LP] Vault balance: {vault.balance_of()}")
    print(f"[Dennis LP] Pool tokens: {lp.balance_token}")
    print(f"[Dennis LP] Minted tokens: {lp.minted}")
    lp.print_stats("After Dennis LP")

    # compound for 50 days
    vault.compound(compound_interval)
    print(f"[{compound_interval} days] Vault balance: {vault.balance_of()}")
    print(f"[{compound_interval} days] Token price: {lp.price}")
    lp.print_stats(f"After {compound_interval} Days Compounding")

    # aaron removes liquidity (staked 50 days)
    print(f"\n{Color.CYAN}=== Aaron Exit (50 days) ==={Color.END}")
    aaron_usdc_before = aaron.balance_usd
    lp.remove_liquidity(aaron)
    aaron_gain = aaron.balance_usd - aaron_usdc_before
    gain_color = Color.GREEN if aaron_gain > 0 else Color.RED
    print(f"[Aaron removal] USDC: {Color.YELLOW}{aaron_usdc_before}{Color.END} → {Color.YELLOW}{aaron.balance_usd}{Color.END} (gain: {gain_color}{aaron_gain}{Color.END})")
    print(f"[Aaron removal] Tokens: {Color.YELLOW}{aaron.balance_token}{Color.END}")
    print(f"[Aaron removal] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"[Aaron removal] Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats("After Aaron Removal")

    # aaron sells all tokens
    aaron_tokens = aaron.balance_token
    aaron_usdc_before_sell = aaron.balance_usd
    lp.sell(aaron, aaron_tokens)
    aaron_usdc_from_sell = aaron.balance_usd - aaron_usdc_before_sell
    print(f"[Aaron sell] Sold {Color.YELLOW}{aaron_tokens}{Color.END} tokens → Got {Color.YELLOW}{aaron_usdc_from_sell}{Color.END} USDC")
    print(f"[Aaron sell] Final USDC: {Color.BOLD}{Color.YELLOW}{aaron.balance_usd}{Color.END}")
    lp.print_stats("After Aaron Sell")

    # compound for another 50 days
    vault.compound(compound_interval)
    print(f"\n{Color.BLUE}[{compound_interval*2} days] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}, Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats(f"After {compound_interval*2} Days Compounding")

    # bob removes liquidity (staked 100 days)
    print(f"\n{Color.CYAN}=== Bob Exit (100 days) ==={Color.END}")
    bob_usdc_before = bob.balance_usd
    lp.remove_liquidity(bob)
    bob_gain = bob.balance_usd - bob_usdc_before
    gain_color = Color.GREEN if bob_gain > 0 else Color.RED
    print(f"[Bob removal] USDC: {Color.YELLOW}{bob_usdc_before}{Color.END} → {Color.YELLOW}{bob.balance_usd}{Color.END} (gain: {gain_color}{bob_gain}{Color.END})")
    print(f"[Bob removal] Tokens: {Color.YELLOW}{bob.balance_token}{Color.END}")
    print(f"[Bob removal] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"[Bob removal] Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats("After Bob Removal")

    # bob sells all tokens
    bob_tokens = bob.balance_token
    bob_usdc_before_sell = bob.balance_usd
    lp.sell(bob, bob_tokens)
    bob_usdc_from_sell = bob.balance_usd - bob_usdc_before_sell
    print(f"[Bob sell] Sold {Color.YELLOW}{bob_tokens}{Color.END} tokens → Got {Color.YELLOW}{bob_usdc_from_sell}{Color.END} USDC")
    print(f"[Bob sell] Final USDC: {Color.BOLD}{Color.YELLOW}{bob.balance_usd}{Color.END}")
    lp.print_stats("After Bob Sell")

    # compound for another 50 days
    vault.compound(compound_interval)
    print(f"\n{Color.BLUE}[{compound_interval*3} days] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}, Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats(f"After {compound_interval*3} Days Compounding")

    # carl removes liquidity (staked 150 days)
    print(f"\n{Color.CYAN}=== Carl Exit (150 days) ==={Color.END}")
    carl_usdc_before = carl.balance_usd
    lp.remove_liquidity(carl)
    carl_gain = carl.balance_usd - carl_usdc_before
    gain_color = Color.GREEN if carl_gain > 0 else Color.RED
    print(f"[Carl removal] USDC: {Color.YELLOW}{carl_usdc_before}{Color.END} → {Color.YELLOW}{carl.balance_usd}{Color.END} (gain: {gain_color}{carl_gain}{Color.END})")
    print(f"[Carl removal] Tokens: {Color.YELLOW}{carl.balance_token}{Color.END}")
    print(f"[Carl removal] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"[Carl removal] Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats("After Carl Removal")

    # carl sells all tokens
    carl_tokens = carl.balance_token
    carl_usdc_before_sell = carl.balance_usd
    lp.sell(carl, carl_tokens)
    carl_usdc_from_sell = carl.balance_usd - carl_usdc_before_sell
    print(f"[Carl sell] Sold {Color.YELLOW}{carl_tokens}{Color.END} tokens → Got {Color.YELLOW}{carl_usdc_from_sell}{Color.END} USDC")
    print(f"[Carl sell] Final USDC: {Color.BOLD}{Color.YELLOW}{carl.balance_usd}{Color.END}")
    lp.print_stats("After Carl Sell")

    # compound for another 50 days
    vault.compound(compound_interval)
    print(f"\n{Color.BLUE}[{compound_interval*4} days] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}, Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats(f"After {compound_interval*4} Days Compounding")

    # dennis removes liquidity (staked 200 days - longest)
    print(f"\n{Color.CYAN}=== Dennis Exit (200 days) ==={Color.END}")
    dennis_usdc_before = dennis.balance_usd
    lp.remove_liquidity(dennis)
    dennis_gain = dennis.balance_usd - dennis_usdc_before
    gain_color = Color.GREEN if dennis_gain > 0 else Color.RED
    print(f"[Dennis removal] USDC: {Color.YELLOW}{dennis_usdc_before}{Color.END} → {Color.YELLOW}{dennis.balance_usd}{Color.END} (gain: {gain_color}{dennis_gain}{Color.END})")
    print(f"[Dennis removal] Tokens: {Color.YELLOW}{dennis.balance_token}{Color.END}")
    print(f"[Dennis removal] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"[Dennis removal] Price: {Color.YELLOW}{lp.price}{Color.END}")
    lp.print_stats("After Dennis Removal")

    # dennis sells all tokens
    dennis_tokens = dennis.balance_token
    dennis_usdc_before_sell = dennis.balance_usd
    lp.sell(dennis, dennis_tokens)
    dennis_usdc_from_sell = dennis.balance_usd - dennis_usdc_before_sell
    print(f"[Dennis sell] Sold {Color.YELLOW}{dennis_tokens}{Color.END} tokens → Got {Color.YELLOW}{dennis_usdc_from_sell}{Color.END} USDC")
    print(f"[Dennis sell] Final USDC: {Color.BOLD}{Color.YELLOW}{dennis.balance_usd}{Color.END}")
    lp.print_stats("After Dennis Sell")

    # summary
    print(f"\n{Color.BOLD}{Color.HEADER}=== FINAL SUMMARY ==={Color.END}")
    total_profit = D(0)
    for name, user in [("Aaron", aaron), ("Bob", bob), ("Carl", carl), ("Dennis", dennis)]:
        initial = 2 * K
        final = user.balance_usd
        profit = final - initial
        total_profit += profit
        profit_color = Color.GREEN if profit > 0 else Color.RED
        print(f"{name:7s}: Initial {Color.YELLOW}{initial}{Color.END}, Final {Color.YELLOW}{final}{Color.END}, Profit: {profit_color}{profit}{Color.END}")

    print(f"\n{Color.BOLD}Total profit (all users): {Color.GREEN if total_profit > 0 else Color.RED}{total_profit}{Color.END}")
    print(f"Final vault balance: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"Final minted tokens: {Color.YELLOW}{lp.minted}{Color.END}")

def multi_user_bank_run_scenario(
    compound_days: int = 365,
):
    vault = Vault()
    lp = LP(vault)

    # define 10 users with their buy amounts
    users_data = [
        ("aaron", D(500)),
        ("bob", D(400)),
        ("carl", D(300)),
        ("dennis", D(600)),
        ("eve", D(350)),
        ("frank", D(450)),
        ("grace", D(550)),
        ("henry", D(250)),
        ("iris", D(380)),
        ("jack", D(420)),
    ]

    users = {name: User(name, 3 * K) for name, _ in users_data}

    # Scenario header
    print(f"\n{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'  SCENARIO 3: 10-USER BANK RUN (365 DAYS)':^70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}\n")

    # print initial balances
    print(f"{Color.CYAN}[Initial Balances]{Color.END}")
    for name, buy_amount in users_data:
        print(f"  {name.capitalize():7s}: {Color.YELLOW}{users[name].balance_usd}{Color.END} USDC, Will buy: {Color.YELLOW}{buy_amount}{Color.END}")
    lp.print_stats("Initial State")

    # all users buy tokens
    print(f"\n{Color.BLUE}--- PHASE 1: ALL USERS BUY TOKENS ---{Color.END}")
    for name, buy_amount in users_data:
        price_before = lp.price
        lp.buy(users[name], buy_amount)
        price_after = lp.price
        print(f"[{name.capitalize()} buy] Spent {Color.YELLOW}{buy_amount}{Color.END} USDC → Got {Color.YELLOW}{users[name].balance_token}{Color.END} tokens")
        print(f"[{name.capitalize()} buy] Price: {Color.GREEN}{price_before}{Color.END} → {Color.GREEN}{price_after}{Color.END}")

    print(f"\n[All bought] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}, Minted: {Color.YELLOW}{lp.minted}{Color.END}, Price: {Color.GREEN}{lp.price}{Color.END}")
    lp.print_stats("After All Buys")

    # all users add liquidity symmetrically
    print(f"\n{Color.BLUE}--- PHASE 2: ALL USERS ADD LIQUIDITY ---{Color.END}")
    for name, _ in users_data:
        user = users[name]
        user_add_liquidity_token = user.balance_token
        user_add_liquidity_usd = user_add_liquidity_token * lp.price
        price_before = lp.price
        lp.add_liquidity(user, user_add_liquidity_token, user_add_liquidity_usd)
        price_after = lp.price
        print(f"[{name.capitalize()} LP] Added {user_add_liquidity_token} tokens + {lp.liquidity_usd[name]} USDC")
        print(f"[{name.capitalize()} LP] Price: {price_before} → {price_after}")

    print(f"\n[All added LP] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}, Pool tokens: {Color.YELLOW}{lp.balance_token}{Color.END}, Price: {Color.GREEN}{lp.price}{Color.END}")
    lp.print_stats("After All Added Liquidity")

    # compound for 365 days (1 year)
    price_before_compound = lp.price
    vault.compound(compound_days)
    price_after_compound = lp.price
    print(f"\n{Color.BLUE}--- PHASE 3: COMPOUND FOR {compound_days} DAYS ---{Color.END}")
    print(f"[{compound_days} days] Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"[{compound_days} days] Price: {Color.GREEN}{price_before_compound}{Color.END} → {Color.GREEN}{price_after_compound}{Color.END}")
    price_increase = price_after_compound - price_before_compound
    print(f"[{compound_days} days] Price increase: {Color.GREEN}+{price_increase}{Color.END}")
    lp.print_stats(f"After {compound_days} Days Compounding")

    # all users sequentially remove liquidity and sell
    print(f"\n{Color.BLUE}--- PHASE 4: ALL USERS REMOVE LIQUIDITY & SELL ---{Color.END}")
    for name, buy_amount in users_data:
        user = users[name]

        # remove liquidity
        user_usdc_before_removal = user.balance_usd
        lp.remove_liquidity(user)
        user_usdc_after_removal = user.balance_usd
        user_usdc_gain = user_usdc_after_removal - user_usdc_before_removal
        gain_color = Color.GREEN if user_usdc_gain > 0 else Color.RED
        print(f"\n{Color.CYAN}[{name.capitalize()} removal]{Color.END} USDC: {Color.YELLOW}{user_usdc_before_removal}{Color.END} → {Color.YELLOW}{user_usdc_after_removal}{Color.END} (gain: {gain_color}{user_usdc_gain}{Color.END})")
        print(f"  Tokens: {Color.YELLOW}{user.balance_token}{Color.END}, Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")

        # sell all tokens
        user_tokens = user.balance_token
        user_usdc_before_sell = user.balance_usd
        lp.sell(user, user_tokens)
        user_usdc_after_sell = user.balance_usd
        user_usdc_from_sell = user_usdc_after_sell - user_usdc_before_sell
        print(f"{Color.CYAN}[{name.capitalize()} sell]{Color.END} Sold {Color.YELLOW}{user_tokens}{Color.END} tokens → Got {Color.YELLOW}{user_usdc_from_sell}{Color.END} USDC")
        print(f"  Final USDC: {Color.BOLD}{Color.YELLOW}{user_usdc_after_sell}{Color.END}, Vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
        lp.print_stats(f"After {name.capitalize()} Exit")

    # summary
    print(f"\n{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'  FINAL SUMMARY':^70}{Color.END}")
    print(f"{Color.BOLD}{Color.HEADER}{'='*70}{Color.END}\n")
    total_profit = D(0)
    for name, buy_amount in users_data:
        initial = 3 * K
        final = users[name].balance_usd
        profit = final - initial
        total_profit += profit
        profit_color = Color.GREEN if profit > 0 else Color.RED
        print(f"{name.capitalize():7s}: Invested {Color.YELLOW}{buy_amount:4}{Color.END}, Profit: {profit_color}{profit:8.2f}{Color.END}, Final: {Color.YELLOW}{final}{Color.END}")

    total_profit_color = Color.GREEN if total_profit > 0 else Color.RED
    print(f"\n{Color.BOLD}Total invested: {Color.YELLOW}{sum(amount for _, amount in users_data)}{Color.END}")
    print(f"{Color.BOLD}Total profit: {total_profit_color}{total_profit}{Color.END}")
    print(f"Final vault: {Color.YELLOW}{vault.balance_of()}{Color.END}")
    print(f"Final minted: {Color.YELLOW}{lp.minted}{Color.END}")
    print(f"Final price: {Color.GREEN}{lp.price}{Color.END}")

single_user_scenario()
multi_user_spreaded_scenario()
multi_user_bank_run_scenario()
