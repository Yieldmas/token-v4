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
        Reaches 0 at 100K USDC.
        """
        base = CAP / EXPOSURE_FACTOR  # 10,000
        effective = min(self.buy_usdc, VIRTUAL_LIMIT)
        liquidity = base * (D(1) - effective / VIRTUAL_LIMIT)
        return max(D(0), liquidity)

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

    def _get_out_amount(self, sold_amount: D, selling_token: bool) -> D:
        """
        Calculate output using constant product with virtual reserves:
        (token_reserve) * (buy_usdc + virtual_liquidity) = k
        Uses dynamic exposure that decreases as more tokens are minted.
        Only buy_usdc affects bonding curve.
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
        usd_amount = usd_deposit + usd_yield

        # LP token inflation (5% APY)
        token_yield = token_deposit * (delta - D(1))
        token_amount = token_deposit + token_yield

        # Buy USDC yield (5% APY)
        buy_usdc_yield = buy_usdc_principal * (delta - D(1))
        total_usdc = usd_amount + buy_usdc_yield

        # mint inflation yield on tokens
        self.mint(token_yield)

        # remove LP USDC + buy USDC yield from vault
        self.dehypo(total_usdc)

        # reduce lp_usdc by the original LP principal
        self.lp_usdc -= usd_deposit

        # reduce buy_usdc by the yield (principal stays for bonding curve)
        self.buy_usdc -= buy_usdc_yield

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

def single_user_scenario(
    user_initial_usd: D = 1 * K,
    user_buy_token_usd: D = D(500),
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

    # add liquidity symmetrically: match token value at current price
    user_add_liquidity_token = user.balance_token
    user_add_liquidity_usd = user_add_liquidity_token * lp.price
    lp.add_liquidity(user, user_add_liquidity_token, user_add_liquidity_usd)
    assert lp.balance_token == user_add_liquidity_token
    assert lp.balance_usd == D(0)
    assert vault.balance_usd == user_add_liquidity_usd + user_buy_token_usd
    assert vault.balance_of() == user_add_liquidity_usd + user_buy_token_usd
    print(f"[Liquidity add] User USDC: {user_add_liquidity_usd}")
    print(f"[Liquidity add] User tokens: {user_add_liquidity_token}")
    print(f"[Liquidity add] User liquidity tokens: {lp.liquidity_token[user.name]}")
    print(f"[Liquidity add] User liquidity USDC: {lp.liquidity_usd[user.name]}")

    # snapshot price after adding liquidity
    price_after_add_liquidity = lp.price
    print(f"[Liquidity add] Token price: {lp.price}")
    print(f"[Liquidity add] Pool invariant k: {lp.k}")

    # compound for 100 days
    vault.compound(compound_days)
    print(f"[{compound_days} days] Vault balance: {vault.balance_of()}")

    # price changes as vault balance grows (more USDC per token)
    assert lp.price > price_after_add_liquidity, f"Price should increase as vault compounds, got {lp.price} vs {price_after_add_liquidity}"
    print(f"[After compound] Token price: {lp.price}")
    print(f"[After compound] Pool invariant k: {lp.k}")

    # remove liquidity
    lp.remove_liquidity(user)
    print(f"[Liquidity removal] User USDC: {user.balance_usd}")
    print(f"[Liquidity removal] User tokens: {user.balance_token}")
    print(f"[Liquidity removal] LP tokens: {lp.balance_token}")
    print(f"[Liquidity removal] LP USDC: {lp.balance_usd}")
    print(f"[Liquidity removal] Vault balance of: {vault.balance_of()}")
    print(f"[Liquidity removal] Vault USDC: {vault.balance_usd}")
    print(f"[Liquidity removal] Token price: {lp.price}")
    print(f"[Liquidity removal] Pool invariant k: {lp.k}")

    # sell all tokens
    user_tokens = user.balance_token
    lp.sell(user, user_tokens)
    print(f"[Sell] User sold tokens: {user_tokens}")
    print(f"[Sell] User USDC: {user.balance_usd}")
    print(f"[Sell] User tokens: {user.balance_token}")
    print(f"[Sell] LP tokens: {lp.balance_token}")
    print(f"[Sell] LP USDC: {lp.balance_usd}")
    print(f"[Sell] Vault balance of: {vault.balance_of()}")
    print(f"[Sell] Vault USDC: {vault.balance_usd}")
    print(f"[Sell] Token price: {lp.price}")
    print(f"[Sell] Pool invariant k: {lp.k}")

def multi_user_scenario(
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
    print(f"\n=== MULTI-USER SCENARIO ===")
    
    print(f"[Initial] Aaron USDC: {aaron.balance_usd}")
    print(f"[Initial] Bob USDC: {bob.balance_usd}")
    print(f"[Initial] Carl USDC: {carl.balance_usd}")
    print(f"[Initial] Dennis USDC: {dennis.balance_usd}")

    # aaron buys tokens for 500 usd
    lp.buy(aaron, aaron_buy_usd)
    assert vault.balance_of() == aaron_buy_usd
    print(f"[Aaron Buy] Aaron tokens: {aaron.balance_token}")
    print(f"[Aaron Buy] Token price: {lp.price}")
    print(f"[Aaron Buy] Vault balance: {vault.balance_of()}")

    # aaron adds liquidity symmetrically
    aaron_add_liquidity_token = aaron.balance_token
    aaron_add_liquidity_usd = aaron_add_liquidity_token * lp.price
    lp.add_liquidity(aaron, aaron_add_liquidity_token, aaron_add_liquidity_usd)
    assert lp.liquidity_token[aaron.name] == aaron_add_liquidity_token
    print(f"[Aaron LP] Aaron liquidity tokens: {lp.liquidity_token[aaron.name]}")
    print(f"[Aaron LP] Aaron liquidity USDC: {lp.liquidity_usd[aaron.name]}")
    print(f"[Aaron LP] Vault balance: {vault.balance_of()}")

    # bob buys tokens for 400 usd
    lp.buy(bob, bob_buy_usd)
    print(f"[Bob Buy] Bob tokens: {bob.balance_token}")
    print(f"[Bob Buy] Token price: {lp.price}")
    print(f"[Bob Buy] Vault balance: {vault.balance_of()}")

    # bob adds liquidity symmetrically
    bob_add_liquidity_token = bob.balance_token
    bob_add_liquidity_usd = bob_add_liquidity_token * lp.price
    lp.add_liquidity(bob, bob_add_liquidity_token, bob_add_liquidity_usd)
    assert lp.liquidity_token[bob.name] == bob_add_liquidity_token
    print(f"[Bob LP] Bob liquidity tokens: {lp.liquidity_token[bob.name]}")
    print(f"[Bob LP] Bob liquidity USDC: {lp.liquidity_usd[bob.name]}")
    print(f"[Bob LP] Vault balance: {vault.balance_of()}")

    # carl buys tokens for 300 usd
    lp.buy(carl, carl_buy_usd)
    print(f"[Carl Buy] Carl tokens: {carl.balance_token}")
    print(f"[Carl Buy] Token price: {lp.price}")
    print(f"[Carl Buy] Vault balance: {vault.balance_of()}")

    # carl adds liquidity symmetrically
    carl_add_liquidity_token = carl.balance_token
    carl_add_liquidity_usd = carl_add_liquidity_token * lp.price
    lp.add_liquidity(carl, carl_add_liquidity_token, carl_add_liquidity_usd)
    assert lp.liquidity_token[carl.name] == carl_add_liquidity_token
    print(f"[Carl LP] Carl liquidity tokens: {lp.liquidity_token[carl.name]}")
    print(f"[Carl LP] Carl liquidity USDC: {lp.liquidity_usd[carl.name]}")
    print(f"[Carl LP] Vault balance: {vault.balance_of()}")

    # dennis buys tokens for 600 usd
    lp.buy(dennis, dennis_buy_usd)
    print(f"[Dennis Buy] Dennis tokens: {dennis.balance_token}")
    print(f"[Dennis Buy] Token price: {lp.price}")
    print(f"[Dennis Buy] Vault balance: {vault.balance_of()}")

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

    # compound for 50 days
    vault.compound(compound_interval)
    print(f"[{compound_interval} days] Vault balance: {vault.balance_of()}")
    print(f"[{compound_interval} days] Token price: {lp.price}")

    # aaron removes liquidity (staked 50 days)
    aaron_usdc_before = aaron.balance_usd
    lp.remove_liquidity(aaron)
    print(f"[Aaron removal] Aaron USDC: {aaron.balance_usd}")
    print(f"[Aaron removal] Aaron USDC gain: {aaron.balance_usd - aaron_usdc_before}")
    print(f"[Aaron removal] Aaron tokens: {aaron.balance_token}")
    print(f"[Aaron removal] Vault balance: {vault.balance_of()}")
    print(f"[Aaron removal] Token price: {lp.price}")

    # compound for another 50 days
    vault.compound(compound_interval)
    print(f"[{compound_interval*2} days] Vault balance: {vault.balance_of()}")
    print(f"[{compound_interval*2} days] Token price: {lp.price}")

    # bob removes liquidity (staked 100 days)
    bob_usdc_before = bob.balance_usd
    lp.remove_liquidity(bob)
    print(f"[Bob removal] Bob USDC: {bob.balance_usd}")
    print(f"[Bob removal] Bob USDC gain: {bob.balance_usd - bob_usdc_before}")
    print(f"[Bob removal] Bob tokens: {bob.balance_token}")
    print(f"[Bob removal] Vault balance: {vault.balance_of()}")
    print(f"[Bob removal] Token price: {lp.price}")

    # compound for another 50 days
    vault.compound(compound_interval)
    print(f"[{compound_interval*3} days] Vault balance: {vault.balance_of()}")
    print(f"[{compound_interval*3} days] Token price: {lp.price}")

    # carl removes liquidity (staked 150 days)
    carl_usdc_before = carl.balance_usd
    lp.remove_liquidity(carl)
    print(f"[Carl removal] Carl USDC: {carl.balance_usd}")
    print(f"[Carl removal] Carl USDC gain: {carl.balance_usd - carl_usdc_before}")
    print(f"[Carl removal] Carl tokens: {carl.balance_token}")
    print(f"[Carl removal] Vault balance: {vault.balance_of()}")
    print(f"[Carl removal] Token price: {lp.price}")

    # compound for another 50 days
    vault.compound(compound_interval)
    print(f"[{compound_interval*4} days] Vault balance: {vault.balance_of()}")
    print(f"[{compound_interval*4} days] Token price: {lp.price}")

    # dennis removes liquidity (staked 200 days - longest)
    dennis_usdc_before = dennis.balance_usd
    lp.remove_liquidity(dennis)
    print(f"[Dennis removal] Dennis USDC: {dennis.balance_usd}")
    print(f"[Dennis removal] Dennis USDC gain: {dennis.balance_usd - dennis_usdc_before}")
    print(f"[Dennis removal] Dennis tokens: {dennis.balance_token}")
    print(f"[Dennis removal] Vault balance: {vault.balance_of()}")
    print(f"[Dennis removal] Token price: {lp.price}")

single_user_scenario()
multi_user_scenario()
