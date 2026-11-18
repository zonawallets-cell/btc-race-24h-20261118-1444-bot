"""BTC dip-buy bot for make.fun btc-race-24h-20261118-1444.

One asset (CBBTC, Coinbase Wrapped BTC vs USDC), one-minute bars, long only,
starting cash 1,000 USDC. The bot waits for a sharp pullback, buys it with
everything it has, and lets a trailing stop carry the recovery.

Rules, all in integer basis points (10,000 bps = 100%):

- BUY when a bar's close sits at least DIP_BPS below the highest high of
  the WINDOW bars before it. One position at a time, full size (all cash).
- SELL the whole position when its value drops TRAIL_BPS below the highest
  value it reached since the buy (trailing stop), or STOP_BPS below what
  the position cost (hard stop-loss, for a dip that keeps falling).
- Orders decided on the batch of the bar closing at minute t fill at the
  next bar's open, so every decision is made from closes already seen.
  max_slippage_bps bounds the move from the latest close, impact and
  modelled slippage included.

Why this shape: a full-size round trip costs roughly 26 bps (4 bps fee +
2 bps modelled slippage + constant-product impact on each leg at the
pool's depth), so a trade must catch a move far larger than that to pay.
On one-minute bars the ordinary wiggle is only a few bps, so fast
trend-following systems churn dozens of times a day and drown in those
costs. The one repeatable event is the sharp V: a ~2% drop inside an hour
followed by a bounce. This bot does nothing until that drop appears.

Tuning (local exact-fill replay of the official harness model, on this
competition's 24h dev window and the two previous instances' dev windows):

- WINDOW 60, DIP 230, TRAIL 150, STOP 150: dev +$3.47 (1 round trip:
  buy bar 65 near $63,737, sell bar 678 near $64,009), max drawdown 1.85%.
  Same parameters: +$7.52 on the 2026-11-15 window (3 round trips),
  +$2.40 on the 2026-11-17 window (1 round trip) -- positive on all three,
  and the best worst-of-three of the sweep. Neighbours are noisy because
  this window holds a single qualifying dip, so the number is a gate pass,
  not a promise about the race window: if the race window holds no
  ~230 bps / 60-minute dip, the bot makes no trade.
- Rejected by the same sweep: smaller dips (150 bps) churn and lose
  heavily on the older windows (-$42 on 2026-11-15); tighter trailing
  stops (60-120 bps) flip this window's one trade negative; breakout
  entries lost money on the older windows and were not re-added.

Determinism: pure integer arithmetic on bar closes and highs (bps tests
as cross-multiplied integers), no floats, no randomness, no wall clock,
no network, no files. The bar history and the peak value are the only
state, both functions of the bars seen, so two runs on the same bars
produce byte-identical replies (verified: action-log sha256
e7a0ce34f4076a30f714e2961254a5d6ac976d9d1219a123ad894335bff6f8a5, 56,685 bytes).

Protocol: agent-fun/bars-replay/v1, spoken through the vendored SDK shim
(vendor/makefun_bars.py, a byte-identical copy of the kit's
sdk/makefun_bars.py).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

ASSET = "CBBTC"

# Strategy parameters (bps).
WINDOW = 60         # bars of highs the dip is measured against
DIP_BPS = 230       # buy when the close is this far below the window high
TRAIL_BPS = 150     # sell when value falls this far below its peak since entry
STOP_BPS = 150      # sell when value falls this far below cost
SLIP_BPS = 200      # max slippage allowed from the latest close


class DipBot:
    """Dip-buy mean reversion: one full-size position, trailing-stop exit."""

    def __init__(self):
        self.closes = []   # closes seen, oldest first
        self.highs = []    # highs seen, oldest first, same order as closes
        self.peak = 0      # highest position value (quote units) since entry

    def decide(self, state, batch):
        if state.warming_up:
            return []
        bar = None
        for candidate in batch.get("bars", []):
            if candidate.get("symbol") == ASSET:
                bar = candidate
                break
        if bar is None:
            return []
        close = state.close(ASSET)
        if close is None:
            return []
        self.closes.append(close)
        self.highs.append(int(bar["h"]))
        if len(self.closes) <= WINDOW:
            return []

        held = state.positions.get(ASSET)
        if held is not None:
            value = state.value(ASSET, held.qty)
            if value > self.peak:
                self.peak = value
            # Trailing stop first: it normally fires before the hard stop.
            if value * 10000 <= self.peak * (10000 - TRAIL_BPS):
                self.peak = 0
                return [self._sell_all(held.qty)]
            if value * 10000 <= held.cost * (10000 - STOP_BPS):
                self.peak = 0
                return [self._sell_all(held.qty)]
            return []

        # Flat: is the close far enough below the high of the WINDOW bars
        # before this one to buy the dip?
        self.peak = 0
        reference = max(self.highs[-WINDOW - 1:-1])
        if close * 10000 > reference * (10000 - DIP_BPS):
            return []
        floor = int(state.hello["fees"]["min_notional_quote_units"])
        if state.cash < floor:
            return []
        return [{"side": "buy", "symbol": ASSET,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": SLIP_BPS}]

    @staticmethod
    def _sell_all(qty):
        return {"side": "sell", "symbol": ASSET, "qty": qty,
                "max_slippage_bps": SLIP_BPS}


_BOT = DipBot()
makefun_bars.run(_BOT.decide)
