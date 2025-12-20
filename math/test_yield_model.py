from decimal import Decimal as D
from typing import Dict, Optional

# const
K = D(1_000)
M = D(1_000_000)
B = D(1_000_000_000)

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
    snapshot_of_compounding_index: D

    def __init__(self, value: D, snapshot: D):
        self.value = value
        self.snapshot_of_compounding_index = snapshot

class Vault:
    apy: D
    balance_usd: D
    compounding_index: D
    lp_compounding_snapshot: Optional[CompoundingSnapshot]
    compounds: int

    def __init__(self, ):
        self.apy = D(5) / D(100)
        self.balance_usd = D(0)
        self.compounding_index = D(1.0)
        self.lp_compounding_snapshot = None
        self.compounds = 0

    def balance_of(self) -> D:
        if self.lp_compounding_snapshot is None:
            return self.balance_usd
        else:
            return self.lp_compounding_snapshot.value * (
                self.compounding_index / self.lp_compounding_snapshot.snapshot_of_compounding_index
            )

    def add(self, value: D):
        if self.lp_compounding_snapshot is None:
            # store value as snapshot
            self.lp_compounding_snapshot = CompoundingSnapshot(
                value,
                self.compounding_index
            )
        else:
            # we assume that compound has been already run
            # store deposit + last deposit with rewards as snapshot
            self.lp_compounding_snapshot = CompoundingSnapshot(
                value + self.balance_of(),
                self.compounding_index
            )

        # set balance in usd as deposit + last deposit with rewards
        self.balance_usd = self.balance_of()

    def remove(self, value: D):
        if self.lp_compounding_snapshot is None:
            raise Exception("Nothing staked!")
        else:
            # store last deposit with rewards - withdrawal as snapshot
            self.lp_compounding_snapshot = CompoundingSnapshot(
                self.balance_of() - value,
                self.compounding_index
            )
        
        # set balance in usd as last deposit with rewards - withdrawal
        self.balance_usd = self.balance_of()

    def compound(self, days: int):
        # run compounding daily
        for _ in range(0, days):
            self.compounding_index *= D(1) + (self.apy / D(365))
        
        # track compounds number
        self.compounds += days

class UserSnapshot:
    compounds: int
    snapshot_of_compounding_index: D

    def __init__(self, compounds: int, snapshot: D):
        self.compounds = compounds
        self.snapshot_of_compounding_index = snapshot

class LP:
    balance_usd: D
    balance_token: D
    price: D
    minted: D
    liquidity: Dict[str, D]
    total_liquidity: D
    user_snapshot: Dict[str, UserSnapshot]
    vault: Vault

    def __init__(self, vault: Vault):
        self.balance_usd = D(0)
        self.balance_token = D(0)
        self.price = D(1)
        self.minted = D(0)
        self.liquidity = {}
        self.total_liquidity = D(0)
        self.user_snapshot = {}
        self.vault = vault

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

        # put usdc on vault for yield generation
        self.rehypo(user)

        # store compound day on user
        self.user_snapshot[user.name] = UserSnapshot(
            self.vault.compounds,
            self.vault.compounding_index
        )

        # compute liquidity
        user_liquidity = self.liquidity.get(user.name)
        if user_liquidity is None:
            self.liquidity[user.name] = token_amount + usd_amount
        else:
            self.liquidity[user.name] += token_amount + usd_amount
        self.total_liquidity += token_amount + usd_amount

    def remove_liquidity(self, user: User, liquidity_amount: D):
        # translate liquidity to token & usdc
        compound_delta = self.vault.compounding_index / self.user_snapshot[user.name].snapshot_of_compounding_index
        
        usd_deposit = liquidity_amount / 2
        usd_yield = usd_deposit * (compound_delta - D(1)) * 2
        usd_amount = usd_deposit + usd_yield

        token_deposit = liquidity_amount / 2
        token_yield = token_deposit * (compound_delta - D(1))
        token_amount = token_deposit + token_yield

        # mint inflation yield on tokens
        self.mint(token_yield)

        # remove user usdc deposit & rewards from vault
        self.dehypo(user, usd_amount)

        # remove funds from lp
        self.balance_token -= token_amount
        self.balance_usd -= usd_amount

        # send funds to user
        user.balance_token += token_amount
        user.balance_usd += usd_amount

        # update liquidity
        self.liquidity[user.name] -= liquidity_amount
        self.total_liquidity -= liquidity_amount

    def buy(self, user: User, amount: D):
        # take usd
        user.balance_usd -= amount
        self.balance_usd += amount

        # compute out amount (token)
        # 1_000 USD / 1 USD price -> 1_000 tokens
        # 2_000 USD / 1 USD price -> 2_000 tokens
        # 1_500 USD / 1.5 USD price -> 1_000 tokens
        out_amount = amount / self.price

        # mint as much token as needed
        self.mint(out_amount - self.balance_token)
        
        # give token
        self.balance_token -= out_amount
        user.balance_token += out_amount

        # bump price
        # in pool: 0 USD ; amount: 10_000 USD -> 0.1 UP (higher amount > pool)
        # in pool: 100 USD ; amount: 100 USD -> 0.01 UP (equal amount to pool)
        # in pool: 1000 USD ; amount: 100 USD -> 0.001 UP (smaller amount < pool)
        # TODO: convert to price discovery (bonding curve)
        self.price += D(0.1)

        # rehypo
        self.rehypo(user)

    def rehypo(self, user: User):
        # add funds to vault
        self.vault.add(self.balance_usd)

        # remove funds from lp
        self.balance_usd = D(0)

        # save user information

    def sell(self, user: User, amount: D):
        # take token
        user.balance_token -= amount
        self.balance_token += amount

        # compute amount in (usd)
        in_amount = amount * self.price

        # dehypo
        self.dehypo(user, in_amount)

        self.balance_usd -= in_amount
        user.balance_usd += in_amount

        # deflate price
        # TODO: convert to price discovery (bonding curve)
        self.price -= D(0.1)

    def dehypo(self, user: User, amount: D):
        # remove from vault
        self.vault.remove(amount)

        # add to lp
        self.balance_usd += D(amount)

        # update user information

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

    lp.add_liquidity(user, user_add_liquidity_token, user_add_liquidity_usd)
    assert lp.balance_token == user_add_liquidity_token
    assert lp.balance_usd == D(0)
    assert vault.balance_usd == user_add_liquidity_usd + user_buy_token_usd
    assert vault.balance_of() == user_add_liquidity_usd + user_buy_token_usd
    print(f"[Liquidity add] User USDC: {user_add_liquidity_usd}")
    print(f"[Liquidity add] User tokens: {user_add_liquidity_token}")
    print(f"[Liquidity add] User liquidity: {lp.liquidity[user.name]}")

    # compound for 100 days
    vault.compound(compound_days)
    print(f"[{compound_days} days] Vault balance: {vault.balance_of()}")

    # remove liquidity
    lp.remove_liquidity(user, lp.liquidity[user.name])
    print(f"[Liquidity removal] User USDC: {user.balance_usd}")
    print(f"[Liquidity removal] User tokens: {user.balance_token}")
    print(f"[Liquidity removal] LP tokens: {lp.balance_token}")
    print(f"[Liquidity removal] LP USDC: {lp.balance_usd}")
    print(f"[Liquidity removal] Vault balance of: {vault.balance_of()}")
    print(f"[Liquidity removal] Vault USDC: {vault.balance_usd}")

single_user_scenario()
