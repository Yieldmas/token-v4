## Components

- MEME Token (ERC-20)
  - mints on buy
  - mints rewards

---

- Hook
  - uses bonding curve
  - forwards USDC inflows to vault
  - withdraws USDC from vault on sells/exits
  - handles add/remove liquidity in same settlement model
  - requests rewards minting on liquidity removal
