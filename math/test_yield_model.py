from decimal import Decimal as D
from typing import Dict, List
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

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
    compounding_index: D
    compounds: int
    total_shares: D
    shares: Dict[str, D]

    def __init__(self):
        self.apy = D(5) / D(100)
        self.compounding_index = D(1)
        self.compounds = 0
        self.total_shares = D(0)
        self.shares: Dict[str, D] = {}  # depositor -> shares

    def total_assets(self) -> D:
        return self.total_shares * self.compounding_index

    def balance_of(self, owner: str) -> D:
        return self.shares.get(owner, D(0)) * self.compounding_index

    def deposit(self, owner: str, amount: D):
        minted = amount / self.compounding_index
        self.shares[owner] = self.shares.get(owner, D(0)) + minted
        self.total_shares += minted

    def withdraw(self, owner: str, amount: D):
        burn = amount / self.compounding_index
        cur = self.shares.get(owner, D(0))
        if burn > cur:
            raise Exception("Insufficient shares")
        self.shares[owner] = cur - burn
        self.total_shares -= burn

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


class HistorySnapshot:
    timestamp: datetime
    price: D
    virtual_reserve_usd: D
    virtual_reserve_token: D
    vault_total_assets: D
    vault_deposits: D
    vault_yield: D
    user_balance_usd: D
    user_balance_token: D
    user_liquidity: D
    minted_total: D
    minted_from_buys: D
    minted_from_yield: D
    event: str

    def __init__(
        self,
        timestamp: datetime,
        price: D,
        virtual_reserve_usd: D,
        virtual_reserve_token: D,
        vault_total_assets: D,
        vault_deposits: D,
        vault_yield: D,
        user_balance_usd: D,
        user_balance_token: D,
        user_liquidity: D,
        minted_total: D,
        minted_from_buys: D,
        minted_from_yield: D,
        event: str = "",
    ):
        self.timestamp = timestamp
        self.price = price
        self.virtual_reserve_usd = virtual_reserve_usd
        self.virtual_reserve_token = virtual_reserve_token
        self.vault_total_assets = vault_total_assets
        self.vault_deposits = vault_deposits
        self.vault_yield = vault_yield
        self.user_balance_usd = user_balance_usd
        self.user_balance_token = user_balance_token
        self.user_liquidity = user_liquidity
        self.minted_total = minted_total
        self.minted_from_buys = minted_from_buys
        self.minted_from_yield = minted_from_yield
        self.event = event


class LP:
    balance_usd: D
    balance_token: D
    price: D
    minted: D
    minted_from_buys: D
    minted_from_yield: D
    vault_total_deposits: D
    liquidity: Dict[str, D]
    total_liquidity: D
    user_snapshot: Dict[str, UserSnapshot]
    vault: Vault
    history: List[HistorySnapshot]
    current_time: datetime
    # Virtual reserves for bonding curve (k = virtual_usd * virtual_token)
    virtual_reserve_usd: D
    virtual_reserve_token: D

    def __init__(self, vault: Vault, initial_virtual_usd: D = 10 * K, initial_virtual_token: D = 10 * K):
        self.balance_usd = D(0)
        self.balance_token = D(0)
        self.price = D(1)
        self.minted = D(0)
        self.minted_from_buys = D(0)
        self.minted_from_yield = D(0)
        self.vault_total_deposits = D(0)
        self.liquidity = {}
        self.total_liquidity = D(0)
        self.user_snapshot = {}
        self.vault = vault
        self.history = []
        self.current_time = datetime.now()
        # Initialize virtual reserves for bonding curve
        # Price = virtual_reserve_usd / virtual_reserve_token
        self.virtual_reserve_usd = initial_virtual_usd
        self.virtual_reserve_token = initial_virtual_token

    def snapshot(self, user: User, event: str = ""):
        """Take a snapshot of current state for history tracking"""
        vault_assets = self.vault.total_assets()
        vault_yield = vault_assets - self.vault_total_deposits
        
        self.history.append(
            HistorySnapshot(
                timestamp=self.current_time,
                price=self.price,
                virtual_reserve_usd=self.virtual_reserve_usd,
                virtual_reserve_token=self.virtual_reserve_token,
                vault_total_assets=vault_assets,
                vault_deposits=self.vault_total_deposits,
                vault_yield=vault_yield,
                user_balance_usd=user.balance_usd,
                user_balance_token=user.balance_token,
                user_liquidity=self.liquidity.get(user.name, D(0)),
                minted_total=self.minted,
                minted_from_buys=self.minted_from_buys,
                minted_from_yield=self.minted_from_yield,
                event=event,
            )
        )

    def advance_time(self, days: int):
        """Advance current time by specified days"""
        self.current_time += timedelta(days=days)

    def get_current_price(self) -> D:
        """Calculate current price from bonding curve: price = reserve_usd / reserve_token"""
        if self.virtual_reserve_token == D(0):
            return D(1)
        return self.virtual_reserve_usd / self.virtual_reserve_token

    # use token to perform mint (in case of buy or inflation)
    def mint(self, amount: D, from_yield: bool = False):
        if self.minted + amount > CAP:
            raise Exception("Cannot mint over cap")
        self.balance_token += amount
        self.minted += amount
        
        if from_yield:
            self.minted_from_yield += amount
        else:
            self.minted_from_buys += amount

    def add_liquidity(self, user: User, token_amount: D, usd_amount: D):
        # take tokens from user
        user.balance_token -= token_amount
        user.balance_usd -= usd_amount

        # push tokens to pool
        self.balance_token += token_amount
        self.balance_usd += usd_amount

        # Track deposit
        self.vault_total_deposits += usd_amount
        
        # put usdc on vault for yield generation
        self.rehypo(user)

        # store compound day on user
        self.user_snapshot[user.name] = UserSnapshot(
            self.vault.compounds, self.vault.compounding_index
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
        compound_delta = (
            self.vault.compounding_index
            / self.user_snapshot[user.name].snapshot_of_compounding_index
        )

        usd_deposit = liquidity_amount / 2
        usd_yield = usd_deposit * (compound_delta - D(1)) * 2
        usd_amount = usd_deposit + usd_yield

        token_deposit = liquidity_amount / 2
        token_yield = token_deposit * (compound_delta - D(1))
        token_amount = token_deposit + token_yield

        # mint inflation yield on tokens (from yield rewards!)
        self.mint(token_yield, from_yield=True)
        
        # Track withdrawal of deposits
        self.vault_total_deposits -= usd_deposit

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

        # Bonding curve: constant product formula (x * y = k)
        # k = virtual_reserve_usd * virtual_reserve_token
        k = self.virtual_reserve_usd * self.virtual_reserve_token
        
        # New USD reserve after adding user's USD
        new_virtual_reserve_usd = self.virtual_reserve_usd + amount
        
        # Calculate new token reserve to maintain k
        new_virtual_reserve_token = k / new_virtual_reserve_usd
        
        # Tokens to give to user
        out_amount = self.virtual_reserve_token - new_virtual_reserve_token

        # Update virtual reserves
        self.virtual_reserve_usd = new_virtual_reserve_usd
        self.virtual_reserve_token = new_virtual_reserve_token
        
        # Update price
        self.price = self.get_current_price()

        # mint as much token as needed (from buys, not yield)
        if out_amount > self.balance_token:
            self.mint(out_amount - self.balance_token, from_yield=False)

        # give token
        self.balance_token -= out_amount
        user.balance_token += out_amount

        # Track deposit before rehypo
        self.vault_total_deposits += amount
        
        # rehypo
        self.rehypo(user)

    def sell(self, user: User, amount: D):
        # take token
        user.balance_token -= amount
        self.balance_token += amount

        # Bonding curve: constant product formula (x * y = k)
        k = self.virtual_reserve_usd * self.virtual_reserve_token
        
        # New token reserve after adding user's tokens
        new_virtual_reserve_token = self.virtual_reserve_token + amount
        
        # Calculate new USD reserve to maintain k
        new_virtual_reserve_usd = k / new_virtual_reserve_token
        
        # USD to give to user
        in_amount = self.virtual_reserve_usd - new_virtual_reserve_usd
        
        # Update virtual reserves
        self.virtual_reserve_usd = new_virtual_reserve_usd
        self.virtual_reserve_token = new_virtual_reserve_token
        
        # Update price
        self.price = self.get_current_price()

        # dehypo
        self.dehypo(user, in_amount)

        self.balance_usd -= in_amount
        user.balance_usd += in_amount

    def rehypo(self, user: User):
        # add funds to vault
        self.vault.deposit(user.name, self.balance_usd)

        # remove funds from lp
        self.balance_usd = D(0)

        # save user information

    def dehypo(self, user: User, amount: D):
        # remove from vault
        self.vault.withdraw(user.name, amount)

        # add to lp
        self.balance_usd += D(amount)

        # update user information

    def plot_metrics(self, title: str = "Protocol Metrics Over Time", filename: str = "protocol_metrics.png"):
        """Create comprehensive charts for protocol metrics"""
        if not self.history:
            print("No history data to plot")
            return

        # Extract data from history
        timestamps = [h.timestamp for h in self.history]
        prices = [float(h.price) for h in self.history]
        virtual_reserve_usd = [float(h.virtual_reserve_usd) for h in self.history]
        virtual_reserve_token = [float(h.virtual_reserve_token) for h in self.history]
        vault_assets = [float(h.vault_total_assets) for h in self.history]
        vault_deposits = [float(h.vault_deposits) for h in self.history]
        vault_yield = [float(h.vault_yield) for h in self.history]
        user_usd = [float(h.user_balance_usd) for h in self.history]
        user_token = [float(h.user_balance_token) for h in self.history]
        user_liquidity = [float(h.user_liquidity) for h in self.history]
        minted_total = [float(h.minted_total) for h in self.history]
        minted_from_buys = [float(h.minted_from_buys) for h in self.history]
        minted_from_yield = [float(h.minted_from_yield) for h in self.history]
        events = [h.event for h in self.history]

        # Calculate user rewards (yield earned)
        user_total_value = [
            user_usd[i] + user_token[i] * prices[i] + user_liquidity[i]
            for i in range(len(timestamps))
        ]

        # Calculate potential MEME mintable from yield (at current price)
        mintable_from_yield = [
            vault_yield[i] / prices[i] if prices[i] > 0 else 0
            for i in range(len(timestamps))
        ]

        # Create subplots - now 4x2
        fig, axes = plt.subplots(4, 2, figsize=(16, 16))
        fig.suptitle(title, fontsize=16, fontweight="bold")

        # 1. MEME Price over time
        ax1 = axes[0, 0]
        ax1.plot(timestamps, prices, "b-", linewidth=2, label="MEME Price")
        ax1.set_xlabel("Time")
        ax1.set_ylabel("Price (USDC)")
        ax1.set_title("MEME Token Price (Bonding Curve)")
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # Mark events
        for i, event in enumerate(events):
            if event and i % 2 == 0:  # Show every other event to avoid clutter
                ax1.axvline(x=timestamps[i], color="gray", linestyle="--", alpha=0.3)

        # 2. Virtual Reserves (Bonding Curve) - simple view
        ax2 = axes[0, 1]
        
        ax2.plot(timestamps, virtual_reserve_usd, "g-", linewidth=3, label="Virtual USDC Reserve", marker='o', markersize=4)
        ax2.plot(timestamps, virtual_reserve_token, "r-", linewidth=3, label="Virtual MEME Reserve", marker='s', markersize=4)
        ax2.set_xlabel("Time")
        ax2.set_ylabel("Reserve Amount")
        ax2.grid(True, alpha=0.3)
        
        ax2.set_title("Bonding Curve: Virtual Reserves\n(USDC↑ + MEME↓ = Price increases)")
        ax2.legend(loc='best')
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 3. Vault: Deposits vs Yield (clearer stacked visualization)
        ax3 = axes[1, 0]
        
        # Plot deposits as bottom layer
        ax3.fill_between(timestamps, 0, vault_deposits, alpha=0.6, color="steelblue", label="User Deposits")
        # Plot yield on top of deposits
        ax3.fill_between(timestamps, vault_deposits, vault_assets, alpha=0.6, color="gold", label="Yield Generated")
        # Total line
        ax3.plot(timestamps, vault_assets, "darkviolet", linewidth=2.5, label="Total Assets", marker='o', markersize=3)
        # Deposits line for clarity
        ax3.plot(timestamps, vault_deposits, "navy", linewidth=1.5, linestyle="--", label="Deposits Only", alpha=0.7)
        
        ax3.set_xlabel("Time")
        ax3.set_ylabel("USDC")
        ax3.set_title("Vault: Deposits (Blue) + Yield (Gold) = Total Assets")
        ax3.grid(True, alpha=0.3)
        ax3.legend(loc='upper left')
        
        # Add text annotations showing actual amounts
        if len(vault_yield) > 0:
            final_yield = vault_yield[-1]
            final_deposits = vault_deposits[-1]
            final_total = vault_assets[-1]
            
            # Annotation for deposits
            mid_point = len(timestamps) // 2
            ax3.annotate(f'Deposits:\n{final_deposits:.2f} USDC', 
                       xy=(timestamps[mid_point], vault_deposits[mid_point]/2), 
                       xytext=(0, 0), textcoords='offset points',
                       bbox=dict(boxstyle='round,pad=0.5', facecolor='steelblue', alpha=0.8, edgecolor='navy'),
                       fontsize=10, ha='center', fontweight='bold', color='white')
            
            # Annotation for yield
            if final_yield > 0:
                ax3.annotate(f'Yield:\n{final_yield:.2f} USDC', 
                           xy=(timestamps[-1], final_deposits + final_yield/2), 
                           xytext=(-10, 0), textcoords='offset points',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='gold', alpha=0.9, edgecolor='orange'),
                           arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='orange', lw=2),
                           fontsize=10, ha='right', fontweight='bold')
            
            # Annotation for total
            ax3.annotate(f'Total: {final_total:.2f}', 
                       xy=(timestamps[-1], final_total), 
                       xytext=(10, 10), textcoords='offset points',
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='darkviolet', alpha=0.8),
                       fontsize=9, color='white', fontweight='bold')
        
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 4. Yield → MEME Rewards Mechanism (clearer visualization)
        ax4 = axes[1, 1]
        ax4_twin = ax4.twinx()
        
        # Plot USDC yield as bars for clarity
        ax4.bar(timestamps, vault_yield, alpha=0.5, color="gold", label="USDC Yield Generated", width=2)
        ax4.set_xlabel("Time")
        ax4.set_ylabel("USDC Yield", color="goldenrod", fontweight='bold')
        ax4.tick_params(axis='y', labelcolor="goldenrod")
        ax4.grid(True, alpha=0.3, axis='y')
        
        # Only plot MEME minted where it's non-zero
        minted_nonzero_idx = [i for i, v in enumerate(minted_from_yield) if v > 0 or (i > 0 and minted_from_yield[i-1] != v)]
        if minted_nonzero_idx:
            minted_times = [timestamps[i] for i in minted_nonzero_idx]
            minted_values = [minted_from_yield[i] for i in minted_nonzero_idx]
            ax4_twin.plot(minted_times, minted_values, "purple", linewidth=3, label="MEME Minted from Yield", 
                         marker='o', markersize=8, markerfacecolor='purple', markeredgecolor='white', markeredgewidth=2)
        
        # Max mintable as area
        ax4_twin.fill_between(timestamps, mintable_from_yield, alpha=0.2, color="orange", label="Mintable MEME (unused)")
        ax4_twin.plot(timestamps, mintable_from_yield, "darkorange", linewidth=2, linestyle="--", alpha=0.7)
        ax4_twin.set_ylabel("MEME Tokens", color="purple", fontweight='bold')
        ax4_twin.tick_params(axis='y', labelcolor="purple")
        
        ax4.set_title("Yield → MEME Rewards\n(How USDC yield becomes MEME rewards when users claim)")
        
        # Add annotation showing the buffer
        if len(vault_yield) > 0 and vault_yield[-1] > 0:
            final_mintable = mintable_from_yield[-1]
            final_minted = minted_from_yield[-1]
            buffer = final_mintable - final_minted
            if buffer > 0:
                ax4_twin.annotate(f'Buffer: {buffer:.2f} MEME\n({buffer/final_mintable*100:.1f}% unused)', 
                               xy=(timestamps[-1], final_mintable/2), 
                               xytext=(-80, 20), textcoords='offset points',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='orange', alpha=0.7),
                               fontsize=9, ha='center')
        
        # Combine legends
        lines1, labels1 = ax4.get_legend_handles_labels()
        lines2, labels2 = ax4_twin.get_legend_handles_labels()
        ax4.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9)
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 5. User Token Balances with event annotations
        ax5 = axes[2, 0]
        ax5.plot(timestamps, user_usd, "g-", linewidth=2, label="User USDC", marker='o', markersize=3)
        ax5.plot(timestamps, user_token, "r-", linewidth=2, label="User MEME", marker='s', markersize=3)
        ax5.set_xlabel("Time")
        ax5.set_ylabel("Amount")
        ax5.set_title("User Token Balances (with Events)")
        ax5.grid(True, alpha=0.3)
        ax5.legend(loc='upper right')
        
        # Add event annotations with vertical lines
        event_colors = {
            'Buy': 'blue',
            'Sell': 'red',
            'Add Liquidity': 'green',
            'Remove Liquidity': 'orange',
            'Initial': 'gray'
        }
        
        for i, event in enumerate(events):
            if event and event != 'Initial':
                # Determine event type
                event_type = None
                for key in event_colors.keys():
                    if key in event:
                        event_type = key
                        break
                
                if event_type:
                    color = event_colors.get(event_type, 'gray')
                    ax5.axvline(x=timestamps[i], color=color, linestyle=':', alpha=0.6, linewidth=1.5)
                    
                    # Add text label (rotated 45 degrees to prevent overlap)
                    y_pos = ax5.get_ylim()[1] * (0.95 if i % 2 == 0 else 0.85)
                    ax5.text(timestamps[i], y_pos, event, rotation=45, 
                           verticalalignment='bottom', horizontalalignment='left',
                           fontsize=7, color=color, alpha=0.9, fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor=color))
        
        plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 6. User Total Value & Rewards with annotations
        ax6 = axes[2, 1]
        initial_value = user_total_value[0] if user_total_value else 0
        rewards = [v - initial_value for v in user_total_value]
        
        ax6.plot(timestamps, user_total_value, "c-", linewidth=3, label="Total Value", marker='o', markersize=4)
        ax6.fill_between(timestamps, [initial_value]*len(timestamps), user_total_value, 
                        alpha=0.3, color="cyan", label="Rewards Earned")
        ax6.axhline(y=initial_value, color="gray", linestyle="--", alpha=0.5, linewidth=2, label="Initial Value")
        
        ax6.set_xlabel("Time")
        ax6.set_ylabel("USDC Value")
        ax6.set_title("User Portfolio Value Over Time\n(Cyan area = rewards earned | Drops = withdrawals)")
        ax6.grid(True, alpha=0.3)
        
        # Add event markers
        for i, event in enumerate(events):
            if event and event != 'Initial':
                event_type = None
                for key in ['Buy', 'Sell', 'Add Liquidity', 'Remove Liquidity']:
                    if key in event:
                        event_type = key
                        break
                
                if event_type:
                    color = event_colors.get(event_type, 'gray')
                    ax6.axvline(x=timestamps[i], color=color, linestyle=':', alpha=0.6, linewidth=1.5)
                    
                    # Add marker on the value line
                    ax6.plot(timestamps[i], user_total_value[i], 'o', markersize=8, 
                           color=color, markeredgecolor='white', markeredgewidth=2, alpha=0.8)
        
        # Add final rewards annotation
        if len(rewards) > 0 and rewards[-1] > 0:
            ax6.annotate(f'Total Rewards:\n+{rewards[-1]:.2f} USDC\n({rewards[-1]/initial_value*100:.1f}% gain)', 
                       xy=(timestamps[-1], user_total_value[-1]), 
                       xytext=(-100, -40), textcoords='offset points',
                       bbox=dict(boxstyle='round,pad=0.7', facecolor='cyan', alpha=0.8, edgecolor='darkblue'),
                       arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0.3', color='darkblue', linewidth=2),
                       fontsize=10, fontweight='bold')
        
        ax6.legend(loc='upper left')
        plt.setp(ax6.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 7. MEME Supply Breakdown
        ax7 = axes[3, 0]
        ax7.fill_between(timestamps, minted_from_buys, alpha=0.5, color="blue", label="Minted from Buys")
        ax7.fill_between(timestamps, minted_from_buys, minted_total, alpha=0.5, color="green", label="Minted from Yield")
        ax7.plot(timestamps, minted_total, "purple", linewidth=2, label="Total Minted")
        ax7.set_xlabel("Time")
        ax7.set_ylabel("MEME Tokens")
        ax7.set_title("Total MEME Supply Breakdown\n(Blue = bought with USDC | Green = minted as yield rewards)")
        ax7.grid(True, alpha=0.3)
        ax7.legend()
        plt.setp(ax7.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 8. Protocol Health Metrics
        ax8 = axes[3, 1]
        # Calculate backing ratio: vault assets / (minted * price)
        backing_ratio = [
            (vault_assets[i] / (minted_total[i] * prices[i]) * 100) if minted_total[i] > 0 else 100
            for i in range(len(timestamps))
        ]
        ax8.plot(timestamps, backing_ratio, "darkgreen", linewidth=2, label="Backing Ratio")
        ax8.axhline(y=100, color="red", linestyle="--", alpha=0.5, label="100% Backed")
        ax8.fill_between(timestamps, 100, backing_ratio, where=[b >= 100 for b in backing_ratio], 
                        alpha=0.3, color="green", label="Over-collateralized")
        ax8.set_xlabel("Time")
        ax8.set_ylabel("Backing %")
        ax8.set_title("Protocol Health: Backing Ratio\n(>100% = GOOD! Protocol has more USDC than token value)")
        ax8.grid(True, alpha=0.3)
        ax8.legend()
        plt.setp(ax8.xaxis.get_majorticklabels(), rotation=45, ha='right')

        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        print(f"\nCharts saved to {filename}")
        plt.close()  # Close the figure to free memory


def multi_user_scenario():
    """Comprehensive scenario with multiple users demonstrating bonding curve and yield mechanics"""
    vault = Vault()
    lp = LP(vault, initial_virtual_usd=10 * K, initial_virtual_token=10 * K)
    
    # Create multiple users
    alice = User("alice", 5 * K)
    bob = User("bob", 3 * K)
    charlie = User("charlie", 2 * K)
    
    print(f"\n{'='*70}")
    print(f"MULTI-USER SCENARIO - BONDING CURVE & YIELD REWARDS")
    print(f"{'='*70}\n")
    
    print(f"Initial Setup:")
    print(f"  Alice: {alice.balance_usd} USDC")
    print(f"  Bob: {bob.balance_usd} USDC")
    print(f"  Charlie: {charlie.balance_usd} USDC")
    print(f"  Initial MEME Price: {lp.get_current_price()} USDC/MEME")
    
    lp.snapshot(alice, "Initial")
    
    # === Phase 1: Alice makes first buy ===
    print(f"\n--- Phase 1: Alice buys MEME tokens ---")
    buy_amount = D(1000)
    price_before = lp.get_current_price()
    lp.buy(alice, buy_amount)
    lp.advance_time(1)
    price_after = lp.get_current_price()
    
    print(f"  Alice bought with {buy_amount} USDC")
    print(f"  Received: {alice.balance_token:.2f} MEME")
    print(f"  Price: {price_before:.4f} → {price_after:.4f} USDC/MEME ({((price_after-price_before)/price_before*100):.2f}% impact)")
    print(f"  Vault deposits: {lp.vault_total_deposits} USDC")
    
    lp.snapshot(alice, "Alice Buy")
    
    # === Phase 2: Bob buys at higher price ===
    print(f"\n--- Phase 2: Bob buys MEME tokens (higher price) ---")
    buy_amount = D(500)
    price_before = lp.get_current_price()
    lp.buy(bob, buy_amount)
    lp.advance_time(1)
    price_after = lp.get_current_price()
    
    print(f"  Bob bought with {buy_amount} USDC")
    print(f"  Received: {bob.balance_token:.2f} MEME")
    print(f"  Price: {price_before:.4f} → {price_after:.4f} USDC/MEME ({((price_after-price_before)/price_before*100):.2f}% impact)")
    print(f"  Vault deposits: {lp.vault_total_deposits} USDC")
    
    lp.snapshot(bob, "Bob Buy")
    
    # === Phase 3: Charlie buys MEME first, then adds liquidity ===
    print(f"\n--- Phase 3: Charlie buys MEME tokens ---")
    charlie_buy_amount = D(300)
    price_before = lp.get_current_price()
    lp.buy(charlie, charlie_buy_amount)
    lp.advance_time(1)
    price_after = lp.get_current_price()
    
    print(f"  Charlie bought with {charlie_buy_amount} USDC")
    print(f"  Received: {charlie.balance_token:.2f} MEME")
    print(f"  Price: {price_before:.4f} → {price_after:.4f} USDC/MEME")
    
    lp.snapshot(charlie, "Charlie Buy")
    
    print(f"\n--- Phase 4: Charlie adds liquidity ---")
    charlie_meme = D(100)
    charlie_usdc = D(100)
    
    lp.add_liquidity(charlie, charlie_meme, charlie_usdc)
    lp.advance_time(1)
    
    print(f"  Charlie added: {charlie_usdc} USDC + {charlie_meme} MEME")
    print(f"  Charlie's liquidity position: {lp.liquidity[charlie.name]}")
    print(f"  Total vault deposits: {lp.vault_total_deposits} USDC")
    
    lp.snapshot(charlie, "Charlie Add Liquidity")
    
    # === Phase 5: Time passes, yield accrues ===
    print(f"\n--- Phase 5: Yield generation (30 days) ---")
    vault_before = vault.total_assets()
    vault.compound(30)
    lp.advance_time(30)
    vault_after = vault.total_assets()
    yield_generated = vault_after - vault_before
    
    print(f"  Vault before: {vault_before:.2f} USDC")
    print(f"  Vault after: {vault_after:.2f} USDC")
    print(f"  Yield generated: {yield_generated:.2f} USDC")
    print(f"  Potential MEME mintable: {yield_generated / lp.price:.2f} MEME")
    
    lp.snapshot(alice, "Day 30")
    
    # === Phase 6: More yield ===
    print(f"\n--- Phase 6: More yield (another 30 days) ---")
    vault_before = vault.total_assets()
    vault.compound(30)
    lp.advance_time(30)
    vault_after = vault.total_assets()
    yield_generated = vault_after - vault_before
    
    print(f"  Additional yield: {yield_generated:.2f} USDC")
    print(f"  Total vault: {vault_after:.2f} USDC")
    print(f"  Total deposits: {lp.vault_total_deposits} USDC")
    print(f"  Total yield: {vault_after - lp.vault_total_deposits:.2f} USDC")
    
    lp.snapshot(alice, "Day 60")
    
    # === Phase 7: Another user buys ===
    print(f"\n--- Phase 7: Bob buys more ---")
    price_before = lp.get_current_price()
    lp.buy(bob, D(300))
    lp.advance_time(1)
    price_after = lp.get_current_price()
    
    print(f"  Bob bought more with 300 USDC")
    print(f"  Bob's total MEME: {bob.balance_token:.2f}")
    print(f"  Price impact: {((price_after-price_before)/price_before*100):.2f}%")
    
    lp.snapshot(bob, "Bob Buy 2")
    
    # === Phase 8: More compounding ===
    print(f"\n--- Phase 8: More yield (40 days) ---")
    vault_before = vault.total_assets()
    vault.compound(40)
    lp.advance_time(40)
    vault_after = vault.total_assets()
    
    print(f"  Total vault: {vault_after:.2f} USDC")
    print(f"  Total yield: {vault_after - lp.vault_total_deposits:.2f} USDC")
    
    lp.snapshot(alice, "Day 100")
    
    # === Phase 9: Charlie removes liquidity (claims yield rewards) ===
    print(f"\n--- Phase 9: Charlie removes liquidity (claiming rewards) ---")
    charlie_liquidity = lp.liquidity[charlie.name]
    minted_before = lp.minted_from_yield
    
    lp.remove_liquidity(charlie, charlie_liquidity)
    lp.advance_time(1)
    
    minted_after = lp.minted_from_yield
    meme_minted_as_reward = minted_after - minted_before
    
    print(f"  Charlie removed all liquidity")
    print(f"  Charlie USDC: {charlie.balance_usd:.2f}")
    print(f"  Charlie MEME: {charlie.balance_token:.2f}")
    print(f"  MEME minted as yield reward: {meme_minted_as_reward:.2f}")
    print(f"  Total MEME from yield: {lp.minted_from_yield:.2f}")
    print(f"  Total MEME from buys: {lp.minted_from_buys:.2f}")
    
    lp.snapshot(charlie, "Charlie Remove Liquidity")
    
    # === Final state ===
    print(f"\n{'='*70}")
    print(f"FINAL STATE")
    print(f"{'='*70}")
    print(f"\nUsers:")
    print(f"  Alice - USDC: {alice.balance_usd:.2f}, MEME: {alice.balance_token:.2f}, Value: {alice.balance_usd + alice.balance_token * lp.price:.2f} USDC")
    print(f"  Bob   - USDC: {bob.balance_usd:.2f}, MEME: {bob.balance_token:.2f}, Value: {bob.balance_usd + bob.balance_token * lp.price:.2f} USDC")
    print(f"  Charlie - USDC: {charlie.balance_usd:.2f}, MEME: {charlie.balance_token:.2f}, Value: {charlie.balance_usd + charlie.balance_token * lp.price:.2f} USDC")
    
    print(f"\nProtocol:")
    print(f"  MEME Price: {lp.price:.4f} USDC/MEME")
    print(f"  Total MEME minted: {lp.minted:.2f}")
    print(f"    - From buys: {lp.minted_from_buys:.2f}")
    print(f"    - From yield rewards: {lp.minted_from_yield:.2f}")
    print(f"  Vault total assets: {vault.total_assets():.2f} USDC")
    print(f"  Vault deposits: {lp.vault_total_deposits:.2f} USDC")
    print(f"  Vault yield: {vault.total_assets() - lp.vault_total_deposits:.2f} USDC")
    
    backing_ratio = vault.total_assets() / (lp.minted * lp.price) * 100 if lp.minted > 0 else 0
    print(f"  Backing ratio: {backing_ratio:.2f}%")
    
    # Generate charts
    print(f"\n{'='*70}")
    print(f"Generating comprehensive visualizations...")
    print(f"{'='*70}")
    lp.plot_metrics("Multi-User Scenario - Complete Protocol Metrics", "protocol_metrics.png")
    
    return lp


# Run scenarios
if __name__ == "__main__":
    multi_user_scenario()
