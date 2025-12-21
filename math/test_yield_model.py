from decimal import Decimal as D
from typing import Dict, Optional

# const
K = D(1_000)
B = D(1_000_000_000)

# price movement amplification
EXPOSURE_FACTOR = 100 * K

# cap
CAP = 1 * B

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
    liquidity: Dict[str, D]
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
        self.liquidity = {}
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
        """Current token price: price = buy_usdc_with_yield / minted_tokens
        Only buy USDC affects price, not LP USDC."""
        if self.minted == 0:
            return D(1)  # default price before any mints
        return self.get_buy_usdc_with_yield() / self.minted

    def get_exposure(self) -> D:
        """
        Dynamic exposure that decreases as more tokens are minted.
        Reaches 0 at 1M tokens minted.
        """
        # Amplify minting effect by 1000x to hit 0 at 1M tokens
        effective = min(self.minted * D(1000), CAP)
        exposure = EXPOSURE_FACTOR * (D(1) - effective / CAP)
        return max(D(0), exposure)

    def _get_token_reserve(self) -> D:
        """Virtual token reserve = (CAP - minted) / exposure"""
        exposure = self.get_exposure()
        return (CAP - self.minted) / exposure if exposure > 0 else CAP - self.minted

    def _get_usdc_reserve(self) -> D:
        """Virtual USDC reserve = buy_usdc + virtual_liquidity"""
        return self.buy_usdc + self.virtual_liquidity

    def _update_k(self):
        """
        Update constant product invariant using virtual reserves with dynamic exposure:
        k = (token_reserve) * (buy_usdc + virtual_liquidity)
        Only buy_usdc affects bonding curve, not lp_usdc.
        """
        self.k = self._get_token_reserve() * self._get_usdc_reserve()

    def _get_out_amount(self, sold_amount: D, selling_token: bool) -> D:
        """
        Calculate output using constant product with virtual reserves:
        (token_reserve) * (buy_usdc + virtual_liquidity) = k
        Uses dynamic exposure that decreases as more tokens are minted.
        Only buy_usdc affects bonding curve.
        """
        if self.k is None:
            # First buy: initialize k with virtual liquidity
            self.k = self._get_token_reserve() * self.virtual_liquidity

        token_reserve = self._get_token_reserve()
        usdc_reserve = self._get_usdc_reserve()

        if selling_token:
            # Selling tokens, getting USDC (sell operation)
            # User adds tokens back, removes USDC from buy pool
            # (token_reserve + token_in) * (usdc_reserve - usdc_out) = k
            new_token_reserve = token_reserve + sold_amount
            new_usdc_reserve = self.k / new_token_reserve
            usdc_out = usdc_reserve - new_usdc_reserve
            return usdc_out
        else:
            # Buying tokens with USDC
            # User adds USDC to buy pool, mints tokens
            # (token_reserve - token_out) * (usdc_reserve + usdc_in) = k
            new_usdc_reserve = usdc_reserve + sold_amount
            new_token_reserve = self.k / new_usdc_reserve
            token_out = token_reserve - new_token_reserve
            return token_out

    # use token to perform mint (in case of buy or inflation)
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
        user_liquidity = self.liquidity.get(user.name)
        if user_liquidity is None:
            self.liquidity[user.name] = token_amount + usd_amount
        else:
            self.liquidity[user.name] += token_amount + usd_amount

    def remove_liquidity(self, user: User, liquidity_amount: D):
        # translate liquidity to token & usdc
        delta = self.vault.compounding_index / self.user_snapshot[user.name].index

        usd_deposit = liquidity_amount / 2
        usd_yield = usd_deposit * (delta - D(1)) * 2
        usd_amount = usd_deposit + usd_yield

        token_deposit = liquidity_amount / 2
        token_yield = token_deposit * (delta - D(1))
        token_amount = token_deposit + token_yield

        # mint inflation yield on tokens
        self.mint(token_yield)

        # remove user usdc deposit & rewards from vault
        self.dehypo(usd_amount)

        # reduce lp_usdc by the original LP principal
        self.lp_usdc -= usd_deposit

        # remove funds from lp
        self.balance_token -= token_amount
        self.balance_usd -= usd_amount

        # send funds to user
        user.balance_token += token_amount
        user.balance_usd += usd_amount

        # update liquidity
        self.liquidity[user.name] -= liquidity_amount

    def buy(self, user: User, amount: D):
        # take usd
        user.balance_usd -= amount
        self.balance_usd += amount

        # compute out amount (token) using x*y=k
        out_amount = self._get_out_amount(amount, selling_token=False)

        # mint as much token as needed
        self.mint(max(D(0), out_amount - self.balance_token))

        # give token
        self.balance_token -= out_amount
        user.balance_token += out_amount

        # track buy USDC (affects bonding curve)
        self.buy_usdc += amount

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
        self.balance_token += amount

        # compute amount in (usd) using x*y=k
        in_amount = self._get_out_amount(amount, selling_token=True)

        # update buy_usdc (reduces bonding curve reserve)
        self.buy_usdc -= in_amount

        # dehypo
        self.dehypo(in_amount)

        # give usd
        self.balance_usd -= in_amount
        user.balance_usd += in_amount

        # update invariant after swap
        self._update_k()

    def dehypo(self, amount: D):
        # remove from vault
        self.vault.remove(amount)

        # add to lp
        self.balance_usd += amount

def single_user_scenario(
    user_initial_usd: D = 1 * K,
    user_buy_token_usd: D = D(500),
    user_add_liquidity_token: D = D(500),
    user_add_liquidity_usd: D = D(500),
    compound_days: int = 100,
):
    vault = Vault()
    lp = LP(vault)
    user = User("aaron", user_initial_usd)
    print(f"[Initial] User USDC: {user.balance_usd}")

    # buy tokens for 500 usd
    lp.buy(user, user_buy_token_usd)
    assert lp.balance_usd == D(0)
    assert vault.balance_usd == user_buy_token_usd
    assert vault.balance_of() == user_buy_token_usd
    print(f"[Buy] User USDC: {user_buy_token_usd}")
    print(f"[Buy] User tokens: {user.balance_token}")

    # assert price after buy
    assert lp.price > D(1), f"Price should be > 1, got {lp.price}"
    print(f"[Buy] Token price: {lp.price}")
    print(f"[Buy] Pool invariant k: {lp.k}")

    # add liquidity
    lp.add_liquidity(user, user_add_liquidity_token, user_add_liquidity_usd)
    assert lp.balance_token == user_add_liquidity_token
    assert lp.balance_usd == D(0)
    assert vault.balance_usd == user_add_liquidity_usd + user_buy_token_usd
    assert vault.balance_of() == user_add_liquidity_usd + user_buy_token_usd
    print(f"[Liquidity add] User USDC: {user_add_liquidity_usd}")
    print(f"[Liquidity add] User tokens: {user_add_liquidity_token}")
    print(f"[Liquidity add] User liquidity: {lp.liquidity[user.name]}")

    price_after_add_liquidity = lp.price
    print(f"[Liquidity add] Token price: {lp.price}")
    print(f"[Liquidity add] Pool invariant k: {lp.k}")

    # compound for 100 days
    vault.compound(compound_days)
    print(f"[{compound_days} days] Vault balance: {vault.balance_of()}")

    # Price changes as vault balance grows (more USDC per token)
    assert lp.price > price_after_add_liquidity, f"Price should increase as vault compounds, got {lp.price} vs {price_after_add_liquidity}"
    print(f"[After compound] Token price: {lp.price}")
    print(f"[After compound] Pool invariant k: {lp.k}")

    # remove liquidity
    lp.remove_liquidity(user, lp.liquidity[user.name])
    print(f"[Liquidity removal] User USDC: {user.balance_usd}")
    print(f"[Liquidity removal] User tokens: {user.balance_token}")
    print(f"[Liquidity removal] LP tokens: {lp.balance_token}")
    print(f"[Liquidity removal] LP USDC: {lp.balance_usd}")
    print(f"[Liquidity removal] Vault balance of: {vault.balance_of()}")
    print(f"[Liquidity removal] Vault USDC: {vault.balance_usd}")
    print(f"[Liquidity removal] Token price: {lp.price}")
    print(f"[Liquidity removal] Pool invariant k: {lp.k}")

single_user_scenario()
