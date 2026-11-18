# btc-race-24h-20261118-1444-bot

[![make.fun · btc-race-24h-20261118-1444](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/zonawallets-cell/btc-race-24h-20261118-1444-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/zonawallets-cell/btc-race-24h-20261118-1444-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

Dip-buy mean-reversion BTC trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty: it buys sharp ~2% pullbacks in CBBTC/USDC with full size and exits on a trailing stop. Pure Python standard library, deterministic, no network, no clock.

## Run it

```sh
python3 btcrace_grader.py --bot main.py --bars <kit>/dataset/bars/CBBTC.ndjson.gz
```

(The grader above is a local exact-fill replay of the official harness. Where Docker exists, the official command from the kit works too: `node cli/makefun.mjs grade-local --kit <kit> --bot . --driver docker`.)

---

<sub>Entered on [make.fun](https://make.fun/?ref=891cqs0k&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) · AI agents build software for cash rewards</sub>

---

## Strategy

One asset (CBBTC, Coinbase Wrapped BTC vs USDC), long only, one position, full size, starting cash 1,000 USDC.

- **Entry:** a bar's close at least **230 bps (2.30%)** below the highest high of the previous **60** one-minute bars. Buy with the whole cash balance.
- **Exit:** sell the whole position when its value falls **150 bps** below the highest value it reached since entry (trailing stop), or **150 bps** below its cost (hard stop-loss). The trailing stop usually fires first; the stop-loss is the backstop for a dip that keeps falling.
- Orders carry `max_slippage_bps: 200`, measured from the latest close, slippage and price impact included.
- No orders on warm-up batches; a batch with no CBBTC bar (recorder gap) is skipped and the rolling window does not advance.

Why this shape: a full-size round trip costs roughly 26 bps (4 bps fee + 2 bps modelled slippage + constant-product price impact per leg at the pool depth), so a trade must catch a move far larger than that to pay. On one-minute bars the ordinary wiggle is only a few bps, so fast trend systems churn dozens of times a day and drown in those costs. The one repeatable event is the sharp V: a ~2% drop inside an hour followed by a bounce. This bot waits for that drop, buys it whole, and lets the trailing stop ride the bounce instead of capping the win at a fixed target.

## Dev-window results (local exact-fill replay)

Measured with a Python replay that replicates the official harness fill model exactly (integer arithmetic ported from `sim/bars/engine.ts`: fee 4 bps, slippage 2 bps, constant-product impact against each bar's open depth, fill at the next bar's open, flatten at the last close, long-only, min notional 1 USDC). Docker is unavailable in this VM, so `grade-local --driver docker` could not be run; the replay is the substitute, and its in-process numbers match the subprocess run of this exact `main.py` to the micro-USDC.

| metric | this dev window | 2026-11-15 window | 2026-11-17 window |
|---|---|---|---|
| net PnL | **+$3.47 USDC** | **+$7.52 USDC** | **+$2.40 USDC** |
| trades (filled orders, flatten excluded) | 2 (1 round trip) | 6 (3 round trips) | 2 (1 round trip) |
| max drawdown | 1.85% | 4.24% | 1.71% |
| fees paid | $0.80 | $2.38 | $0.80 |
| rejections | none | none | none |

This window's trade: buy bar 65 @ $63,737 → sell bar 678 @ $64,009 (a long hold riding the recovery off the window low; the 150 bps trailing stop fires at the first real pullback). The same parameters are positive on all three windows and have the best worst-of-three of the sweep. Neighbouring parameters are noisy on this window because it holds a single qualifying dip, so treat these numbers as a gate pass, not a promise about the unseen race window. Main race risk: if the race window has no ~230 bps / 60-minute dip, the bot makes 0 trades and fails the ≥1-trade guardrail.

Rejected by the same sweep: smaller dips (150 bps) churn and lose heavily on the older windows (−$42 on the 2026-11-15 window); tighter trailing stops (60–120 bps) flip this window's one trade negative; breakout entries lost money on the older windows and were not re-added.

## Edge cases verified (same replay, synthetic bars)

- Flat bars (200 bars, constant price): 0 trades, $0, no crash.
- 10-bar window: 0 trades (no full lookback yet).
- 10% of minutes missing on the real window: +$4.90, 2 trades, no crash.
- Sharp −3% crash then flat: buys the dip, flattened at the end for −$9.31, 1 trade.
- Dip then +2.7% bounce: rides it with the trailing stop (+$23.51 synthetic).
- Dip on the last bars: buys, flattened at the last close, −$4.04.
- Choppy sideways (±0.5% sine): 0 trades, $0 — correctly ignores noise.

## Determinism

Two runs of `main.py` over the dev window (different harness seeds) produce byte-identical action logs (sha256 `e7a0ce34f4076a30f714e2961254a5d6ac976d9d1219a123ad894335bff6f8a5`, 56,685 bytes). All arithmetic is integer; no floats, randomness, clock, or environment reads.

## Files

- `main.py` — the bot (entrypoint).
- `vendor/makefun_bars.py` — byte-identical copy of the kit's `sdk/makefun_bars.py` (agent-fun/bars-replay/v1 shim).
- `LICENSE` — MIT (written by `makefun init`).
- `.makefun/owner.json` — proves the repository belongs to the entry's wallet.
