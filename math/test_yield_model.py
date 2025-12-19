from decimal import Decimal as D
from typing import Dict

# const
K = D(1_000)
M = D(1_000_000)
B = D(1_000_000_000)

# cap
CAP = 1 * B

class LP:
    balance_usd: D = D(0)
    balance_token = CAP
    price: D = D(1)
    # TODO: track users liquidity

lp = LP()

class CompoundingSnapshot:
    value: D
    snapshot_of_compounding_index: D

    def __init__(self, value: D, snapshot: D):
        self.value = value
        self.snapshot_of_compounding_index = snapshot

class Vault:
    apy: D = D(5) / D(100)
    balance_usd: D = D(0)
    compounding_index: D = D(1.0)
    user_compounding_snapshots: Dict[str, CompoundingSnapshot] = {}
    compounds: int = 0

    # local compounding performed on user interaction
    # TODO: convert to single snapshot per LP
    def add(self, user_name: str, value: D):
        user_snapshot = self.user_compounding_snapshots.get(user_name, None)
        if user_snapshot is None:
            self.user_compounding_snapshots[user_name] = CompoundingSnapshot(
                value, self.compounding_index
            )
            self.balance_usd += value
        else:
            raise NotImplementedError("Handle case with local compound of user snapshot")
        
    # local compounding performed on user interaction
    def remove(self, user_name: str, value: D):
        pass

    # global compounding performed daily
    def compound(self, days: int):
        # run compounding daily
        for _ in range(0, days):
            self.compounding_index *= D(1) + (self.apy / D(365))
        
        # track compounds number
        self.compounds += days

vault = Vault()

class User:
    name: str
    balance_usd: D = D(0)
    balance_token: D = D(0)

    def __init__(self, name: str, usd: D, token: D = D(0)):
        self.name = name
        self.balance_usd = usd
        self.balance_token = token

user_a = User("aaron", 1 * K)

def buy(user: User, amount: D):
    # take usd
    user.balance_usd -= amount
    lp.balance_usd += amount

    # compute out amount (token)
    # 1_000 USD / 1 USD price -> 1_000 tokens
    # 2_000 USD / 1 USD price -> 2_000 tokens
    # 1_500 USD / 1.5 USD price -> 1_000 tokens
    out_amount = amount / lp.price

    # give token
    lp.balance_token -= out_amount
    user.balance_token += out_amount

    # bump price
    # in pool: 0 USD ; amount: 10_000 USD -> 0.1 UP (higher amount > pool)
    # in pool: 100 USD ; amount: 100 USD -> 0.01 UP (equal amount to pool)
    # in pool: 1000 USD ; amount: 100 USD -> 0.001 UP (smaller amount < pool)
    # TODO: convert to price discovery (bonding curve)
    lp.price += D(0.1)

    # rehypo
    rehypo(user)

def rehypo(user: User):
    vault.add(user.name, lp.balance_usd)
    lp.balance_usd = D(0)

def sell(user: User, amount: D):
    # take token
    user.balance_token -= amount
    lp.balance_token += amount

    # compute amount in (usd)
    in_amount = amount * lp.price

    # dehypo
    dehypo(user, in_amount)

    lp.balance_usd -= in_amount
    user.balance_usd += in_amount

    # deflate price
    # TODO: convert to price discovery (bonding curve)
    lp.price -= D(0.1)

def dehypo(user: User, amount: D):
    pass
