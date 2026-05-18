"""
Fixed Strategy Backtesting for Hummingbot Research Project
==========================================================
B 同学任务：固定策略测试

Performs grid search on 2-year training data, then backtests the best
parameters on 6-month test data for 4 strategy types across 3 trading pairs.

Strategies:
  1. Bollinger Bands  — mean reversion
  2. MA Cross         — trend following
  3. RSI              — overbought/oversold reversal
  4. MACD             — trend momentum

Output metrics: cumulative return, max drawdown, Sharpe ratio, win rate,
                total trades, strategy switches (always 0 for fixed strategies)
"""
import itertools
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ─── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TRADING_PAIRS = ["BTC", "ETH", "SOL"]
TRAIN_START = "2023-07-01"
TRAIN_END = "2025-06-30"
TEST_START = "2025-07-01"
TEST_END = "2025-12-31"

# ─── Strategy Parameter Grids ─────────────────────────────────────────────────

BOLLINGER_GRID = {
    "bb_length": [20, 50, 100],
    "bb_std": [1.5, 2.0, 2.5],
    "bb_long_threshold": [0.0, 0.15],
    "bb_short_threshold": [0.85, 1.0],
    "take_profit": [0.02, 0.04, 0.06],
    "stop_loss": [0.02, 0.04, 0.06],
    "time_limit_hours": [12, 24, 48],
}

MA_CROSS_GRID = {
    "ma_fast": [5, 10, 20],
    "ma_slow": [50, 100, 200],
    "take_profit": [0.03, 0.06, 0.09],
    "stop_loss": [0.03, 0.06, 0.09],
    "time_limit_hours": [12, 24, 48],
}

RSI_GRID = {
    "rsi_period": [7, 14, 21],
    "rsi_oversold": [20, 25, 30],
    "rsi_overbought": [70, 75, 80],
    "take_profit": [0.02, 0.04, 0.06],
    "stop_loss": [0.02, 0.04, 0.06],
    "time_limit_hours": [12, 24, 48],
}

MACD_GRID = {
    "macd_fast": [8, 12, 21],
    "macd_slow": [21, 26, 42],
    "macd_signal": [5, 9, 14],
    "take_profit": [0.02, 0.04, 0.06],
    "stop_loss": [0.02, 0.04, 0.06],
    "time_limit_hours": [12, 24, 48],
}


# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_candles(symbol: str, period: str = "train") -> pd.DataFrame:
    """Load 1h K-line CSV and return a DataFrame with parsed timestamps."""
    filename = f"{symbol}_{period}_1h.csv"
    path = os.path.join(DATA_DIR, filename)
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df.columns = [c.lower() for c in df.columns]
    return df


# ─── Indicator & Signal Functions ─────────────────────────────────────────────

def compute_bollinger_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """Bollinger Bands signal: BBP below threshold → long, above threshold → short."""
    import pandas_ta as ta
    length = params["bb_length"]
    std = params["bb_std"]

    # ta.bbands requires explicit lower_std/upper_std, not the 'std' alias
    bb_df = ta.bbands(df["close"], length=length, lower_std=std, upper_std=std)
    lower = bb_df[f"BBL_{length}_{std}_{std}"]
    upper = bb_df[f"BBU_{length}_{std}_{std}"]
    bbp = bb_df[f"BBP_{length}_{std}_{std}"]

    signal = pd.Series(0, index=df.index)
    signal[bbp < params["bb_long_threshold"]] = 1
    signal[bbp > params["bb_short_threshold"]] = -1
    return signal


def compute_ma_cross_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """Dual MA Cross signal: fast MA crosses above slow → long, crosses below → short."""
    fast_ma = df["close"].rolling(params["ma_fast"]).mean()
    slow_ma = df["close"].rolling(params["ma_slow"]).mean()

    signal = pd.Series(0, index=df.index)
    # Crossover: fast was below, now above
    crossover_up = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    crossover_down = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))
    signal[crossover_up] = 1
    signal[crossover_down] = -1
    return signal


def compute_rsi_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """RSI signal: oversold → long, overbought → short."""
    import pandas_ta as ta
    rsi = ta.rsi(df["close"], length=params["rsi_period"])

    signal = pd.Series(0, index=df.index)
    signal[rsi < params["rsi_oversold"]] = 1
    signal[rsi > params["rsi_overbought"]] = -1
    return signal


def compute_macd_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """MACD signal: MACD line crosses above signal line → long, crosses below → short."""
    import pandas_ta as ta
    f = params["macd_fast"]
    s = params["macd_slow"]
    sig = params["macd_signal"]
    macd_df = ta.macd(df["close"], fast=f, slow=s, signal=sig)
    macd_line = macd_df[f"MACD_{f}_{s}_{sig}"]
    signal_line = macd_df[f"MACDs_{f}_{s}_{sig}"]

    signal = pd.Series(0, index=df.index)
    crossover_up = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
    crossover_down = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))
    signal[crossover_up] = 1
    signal[crossover_down] = -1
    return signal


# ─── Backtesting Engine ───────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int  # 1=long, -1=short
    entry_price: float
    exit_price: float
    exit_reason: str  # "tp", "sl", "tl"
    pnl: float
    pnl_pct: float


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    params: dict
    trades: List[Trade] = field(default_factory=list)
    total_return: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    avg_trade_pnl_pct: float = 0.0


def vectorized_backtest(df: pd.DataFrame, signal_series: pd.Series, params: dict,
                        trade_cost: float = 0.0006) -> List[Trade]:
    """
    Vectorized backtest with triple-barrier exit (TP, SL, time limit).

    Entry: next candle's open after signal
    Exit: first of TP, SL, or time_limit (in hours)

    For each candle, checks within-bar whether TP/SL was hit using high/low.
    If both hit in the same candle, uses (open-low)/(high-low) ratio to
    determine which was hit first.
    """
    tp = params["take_profit"]
    sl_frac = params["stop_loss"]
    tl_hours = params["time_limit_hours"]

    open_arr = df["open"].values
    high_arr = df["high"].values
    low_arr = df["low"].values
    close_arr = df["close"].values
    signals = signal_series.values
    timestamps = df.index

    trades = []
    i = 0
    n = len(df)

    while i < n - 1:
        sig = signals[i]
        if sig == 0:
            i += 1
            continue

        # Enter at next candle's open
        entry_idx = i + 1
        if entry_idx >= n:
            break

        entry_price = open_arr[entry_idx]
        side = sig  # 1=long, -1=short

        # Determine exit levels
        if side == 1:
            tp_price = entry_price * (1 + tp)
            sl_price = entry_price * (1 - sl_frac)
        else:
            tp_price = entry_price * (1 - tp)
            sl_price = entry_price * (1 + sl_frac)

        exit_idx = None
        exit_price = 0.0
        exit_reason = "tl"

        # Time limit in candles
        tl_idx = min(entry_idx + tl_hours, n - 1)

        for j in range(entry_idx, tl_idx + 1):
            h = high_arr[j]
            l = low_arr[j]
            o = open_arr[j]
            c = close_arr[j]

            tp_hit = False
            sl_hit = False

            if side == 1:
                if h >= tp_price:
                    tp_hit = True
                if l <= sl_price:
                    sl_hit = True
            else:
                if l <= tp_price:
                    tp_hit = True
                if h >= sl_price:
                    sl_hit = True

            if tp_hit and sl_hit:
                # Both hit in the same candle — determine which first by ratio
                if h == l:
                    # No range, can't distinguish; use close as exit
                    exit_price = c
                    exit_reason = "tp" if (side == 1 and c >= tp_price) or (side == -1 and c <= tp_price) else "sl"
                else:
                    # For long: (o - l) / (h - l) → if high fraction, low (SL) came first
                    # For short: (h - o) / (h - l) → if high fraction, high (SL) came first
                    low_first_ratio = (o - l) / (h - l) if side == 1 else (h - o) / (h - l)
                    if low_first_ratio > 0.5:
                        sl_hit = True
                        tp_hit = False
                    else:
                        tp_hit = True
                        sl_hit = False

            if tp_hit:
                exit_price = tp_price
                exit_reason = "tp"
                exit_idx = j
                break
            elif sl_hit:
                exit_price = sl_price
                exit_reason = "sl"
                exit_idx = j
                break

            # Last candle in time limit → exit at close
            if j == tl_idx:
                exit_price = c
                exit_reason = "tl"
                exit_idx = j

        if exit_idx is None:
            # Shouldn't happen, but safety fallback
            i = entry_idx + 1
            continue

        # Calculate PnL
        if side == 1:
            pnl_pct = (exit_price - entry_price) / entry_price - trade_cost
        else:
            pnl_pct = (entry_price - exit_price) / entry_price - trade_cost

        trades.append(Trade(
            entry_time=timestamps[entry_idx],
            exit_time=timestamps[exit_idx],
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            exit_reason=exit_reason,
            pnl=pnl_pct,
            pnl_pct=pnl_pct,
        ))

        # Skip to after exit to avoid overlapping positions
        i = exit_idx + 1

    return trades


def compute_metrics(trades: List[Trade], initial_capital: float = 1.0) -> dict:
    """Compute aggregate performance metrics from a list of trades."""
    if not trades:
        return {
            "total_return": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "profit_factor": 0.0,
            "avg_trade_pnl_pct": 0.0,
        }

    pnl_pcts = [t.pnl_pct for t in trades]

    # Cumulative return (compounded)
    cumulative = 1.0
    equity_curve = [1.0]
    for p in pnl_pcts:
        cumulative *= (1 + p)
        equity_curve.append(cumulative)
    total_return = cumulative - 1.0

    # Max drawdown
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (np.array(equity_curve) - peak) / peak
    max_dd = float(np.min(drawdowns))

    # Sharpe (from per-trade returns, not annualized for comparison purposes)
    returns_arr = np.array(pnl_pcts)
    sharpe = float(returns_arr.mean() / returns_arr.std()) if returns_arr.std() > 0 else 0.0

    # Win rate
    wins = sum(1 for p in pnl_pcts if p > 0)
    win_rate = wins / len(pnl_pcts)

    # Profit factor
    total_wins = sum(p for p in pnl_pcts if p > 0)
    total_losses = abs(sum(p for p in pnl_pcts if p < 0))
    profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

    return {
        "total_return": total_return,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "win_rate": win_rate,
        "total_trades": len(trades),
        "profit_factor": profit_factor,
        "avg_trade_pnl_pct": float(returns_arr.mean()),
        "total_long": sum(1 for t in trades if t.side == 1),
        "total_short": sum(1 for t in trades if t.side == -1),
        "tp_exits": sum(1 for t in trades if t.exit_reason == "tp"),
        "sl_exits": sum(1 for t in trades if t.exit_reason == "sl"),
        "tl_exits": sum(1 for t in trades if t.exit_reason == "tl"),
    }


def run_single_backtest(df: pd.DataFrame, signal_fn: Callable, params: dict,
                        trade_cost: float = 0.0006) -> dict:
    """Run a single backtest given a DataFrame, signal function, and parameters."""
    signal = signal_fn(df, params)
    trades = vectorized_backtest(df, signal, params, trade_cost)
    metrics = compute_metrics(trades)
    metrics["params"] = params
    metrics["trades"] = trades
    return metrics


# ─── Grid Search ──────────────────────────────────────────────────────────────

def grid_search(df_train: pd.DataFrame, signal_fn: Callable, param_grid: dict,
                trade_cost: float = 0.0006, max_combos: int = 300,
                df_val: pd.DataFrame = None) -> List[dict]:
    """Grid search over parameter combinations.

    If df_val is provided, uses validation Sharpe for ranking (reduces overfitting).
    Otherwise, ranks by training Sharpe.
    """
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combos = list(itertools.product(*values))

    # If too many combos, randomly sample
    if len(all_combos) > max_combos:
        rng = np.random.RandomState(42)
        indices = rng.choice(len(all_combos), max_combos, replace=False)
        all_combos = [all_combos[i] for i in indices]

    results = []
    total = len(all_combos)

    print(f"  Grid search: {total} combinations{' (with validation split)' if df_val is not None else ''}")
    t0 = time.perf_counter()

    for combo in all_combos:
        params = dict(zip(keys, combo))
        try:
            train_metrics = run_single_backtest(df_train, signal_fn, params, trade_cost)
            train_metrics["params"] = params

            if df_val is not None:
                val_metrics = run_single_backtest(df_val, signal_fn, params, trade_cost)
                train_metrics["val_sharpe"] = val_metrics["sharpe_ratio"]
                train_metrics["val_return"] = val_metrics["total_return"]
                train_metrics["val_trades"] = val_metrics["total_trades"]
                # Rank by validation Sharpe
                train_metrics["_rank_score"] = val_metrics["sharpe_ratio"]
            else:
                train_metrics["_rank_score"] = train_metrics["sharpe_ratio"]

            results.append(train_metrics)
        except Exception as e:
            print(f"    Error with {params}: {e}")
            continue

    elapsed = time.perf_counter() - t0
    if elapsed > 0:
        print(f"  Completed in {elapsed:.1f}s ({total/elapsed:.0f} combos/s)")
    else:
        print(f"  Completed in <0.1s")

    # Sort by rank score (descending)
    results.sort(key=lambda x: x["_rank_score"], reverse=True)
    return results


# ─── Display Helpers ──────────────────────────────────────────────────────────

def print_metrics_table(results: List[dict], title: str, top_n: int = 5):
    """Print a formatted table of top results."""
    print(f"\n{'=' * 120}")
    print(f"  {title}")
    print(f"{'=' * 120}")
    header = f"{'Rank':<5} {'Sharpe':>8} {'Return':>9} {'MaxDD':>8} {'WinRate':>8} {'Trades':>7} {'PF':>7} {'AvgPnL':>8}   Params"
    print(header)
    print("-" * 120)

    for rank, r in enumerate(results[:top_n]):
        params_str = ", ".join(f"{k}={v}" for k, v in r["params"].items())
        print(f"{rank+1:<5} {r['sharpe_ratio']:>8.4f} {r['total_return']:>9.4f} "
              f"{r['max_drawdown_pct']:>8.4f} {r['win_rate']:>8.4f} {r['total_trades']:>7d} "
              f"{r['profit_factor']:>7.2f} {r['avg_trade_pnl_pct']:>8.4f}   {params_str}")


def print_final_result(result: dict, symbol: str, strategy: str, bold: bool = False):
    """Print a single final result line."""
    prefix = "**" if bold else ""
    suffix = "**" if bold else ""
    print(f"{prefix}{strategy:<14}{'':>2} "
          f"{result['total_return']:>10.4f}{'':>2} "
          f"{result['max_drawdown_pct']:>8.4f}{'':>2} "
          f"{result['sharpe_ratio']:>8.4f}{'':>2} "
          f"{result['win_rate']:>8.4f}{'':>2} "
          f"{result['total_trades']:>7d}{'':>2} "
          f"{result['profit_factor']:>7.2f}{suffix}")


# ─── Strategy Registry ────────────────────────────────────────────────────────

STRATEGIES = {
    "Bollinger": (compute_bollinger_signal, BOLLINGER_GRID),
    "MA_Cross": (compute_ma_cross_signal, MA_CROSS_GRID),
    "RSI": (compute_rsi_signal, RSI_GRID),
    "MACD": (compute_macd_signal, MACD_GRID),
}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    trade_cost = 0.0006  # 0.06% round-trip (conservative for spot)
    top_n_params = 3     # Number of top parameter sets to test on test data

    all_final_results = {}  # {(symbol, strategy): best_result}
    bh_returns = {}         # {symbol: buy_and_hold_return}

    for symbol in TRADING_PAIRS:
        print(f"\n{'#' * 120}")
        print(f"#  Symbol: {symbol}/USDT")
        print(f"{'#' * 120}")

        # Load data
        df_train = load_candles(symbol, "train")
        df_test = load_candles(symbol, "test")
        test_first = df_test["close"].iloc[0]
        test_last = df_test["close"].iloc[-1]
        bh_return = (test_last - test_first) / test_first
        bh_returns[symbol] = bh_return

        print(f"  Train: {len(df_train)} candles ({df_train.index[0].date()} to {df_train.index[-1].date()})")
        print(f"  Test: {len(df_test)} candles ({df_test.index[0].date()} to {df_test.index[-1].date()})")
        print(f"  B&H Return (Train): {(df_train['close'].iloc[-1] / df_train['close'].iloc[0] - 1):.4%}")
        print(f"  B&H Return (Test): {bh_return:.4%}")

        for strategy_name, (signal_fn, param_grid) in STRATEGIES.items():
            print(f"\n{'─' * 80}")
            print(f"  Strategy: {strategy_name}")
            print(f"{'─' * 80}")

            # ── Phase 1: Grid Search on Full 2-Year Training Data ──
            print("  [Phase 1] Grid search on full 2-year training data...")
            search_results = grid_search(df_train, signal_fn, param_grid,
                                         trade_cost=trade_cost, max_combos=250)
            print_metrics_table(search_results, f"Top {top_n_params} — {strategy_name} (Train)")

            if not search_results:
                print("  WARNING: No valid results from grid search, skipping...")
                continue

            # ── Phase 2: Test Top-N on Test Data ──
            print(f"\n  [Phase 2] Testing top {top_n_params} parameter sets on test data...")
            test_results = []
            for rank, tr in enumerate(search_results[:top_n_params]):
                best_params = tr["params"]
                test_metrics = run_single_backtest(df_test, signal_fn, best_params, trade_cost)
                test_metrics["train_sharpe"] = tr["sharpe_ratio"]
                test_metrics["val_sharpe"] = tr.get("val_sharpe", tr["sharpe_ratio"])
                test_metrics["train_return"] = tr["total_return"]
                test_results.append(test_metrics)
                print(f"    Rank {rank+1}: Test Sharpe={test_metrics['sharpe_ratio']:.4f}, "
                      f"Return={test_metrics['total_return']:.4%}, "
                      f"Trades={test_metrics['total_trades']}, "
                      f"TP/SL/TL={test_metrics.get('tp_exits',0)}/{test_metrics.get('sl_exits',0)}/{test_metrics.get('tl_exits',0)}")

            # Pick best on test (by Sharpe)
            best_test = max(test_results, key=lambda x: x["sharpe_ratio"])
            all_final_results[(symbol, strategy_name)] = best_test

            # Print details
            print(f"\n  Best {strategy_name} params for {symbol}/USDT: "
                  f"{best_test['params']}")
            print(f"    Test: Return={best_test['total_return']:.4%}, "
                  f"MaxDD={best_test['max_drawdown_pct']:.4%}, "
                  f"Sharpe={best_test['sharpe_ratio']:.4f}, "
                  f"WinRate={best_test['win_rate']:.4%}, "
                  f"Trades={best_test['total_trades']}, "
                  f"PF={best_test['profit_factor']:.2f}")
            print(f"    Exit distribution: TP={best_test.get('tp_exits',0)}, "
                  f"SL={best_test.get('sl_exits',0)}, TL={best_test.get('tl_exits',0)}")

            # Save trades to CSV
            trades_df = pd.DataFrame([{
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "side": "LONG" if t.side == 1 else "SHORT",
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason.upper(),
                "pnl_pct": t.pnl_pct,
            } for t in best_test["trades"]])
            csv_path = os.path.join(OUTPUT_DIR, f"trades_{symbol}_{strategy_name}.csv")
            trades_df.to_csv(csv_path, index=False)

    # ── Final Summary Table ──
    print(f"\n\n{'#' * 120}")
    print(f"#  FINAL SUMMARY TABLE")
    print(f"#  Test Period: {TEST_START} to {TEST_END}")
    print(f"{'#' * 120}")

    for symbol in TRADING_PAIRS:
        bh = bh_returns[symbol]
        print(f"\n{'=' * 120}")
        print(f"  {symbol}/USDT  |  Buy & Hold Return: {bh:+.4%}")
        print(f"{'=' * 120}")
        header = (f"{'Strategy':<16} {'Return':>10} {'MaxDD%':>9} {'Sharpe':>8} "
                  f"{'WinRate':>8} {'Trades':>7} {'PF':>7} {'vs B&H':>8}   Best Params")
        print(header)
        print("-" * 120)

        # Find best strategy for this symbol
        symbol_results = {k: v for k, v in all_final_results.items() if k[0] == symbol}
        if not symbol_results:
            continue

        best_sharpe = max(r["sharpe_ratio"] for r in symbol_results.values())
        best_return = max(r["total_return"] for r in symbol_results.values())

        for (_, sname), r in symbol_results.items():
            is_best_sharpe = (r["sharpe_ratio"] == best_sharpe)
            is_best_return = (r["total_return"] == best_return)
            marker = ""
            if is_best_sharpe and is_best_return:
                marker = " ★ BEST"
            elif is_best_sharpe:
                marker = " ★ Sharpe"
            elif is_best_return:
                marker = " ★ Return"

            vs_bh = r["total_return"] - bh
            params_short = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            b1, b2 = ("**", "**") if is_best_sharpe else ("", "")
            print(f"{b1}{sname:<16}{b2} {b1}{r['total_return']:>+10.4%}{b2} "
                  f"{b1}{r['max_drawdown_pct']:>9.4%}{b2} {b1}{r['sharpe_ratio']:>+8.4f}{b2} "
                  f"{b1}{r['win_rate']:>8.4%}{b2} {b1}{r['total_trades']:>7d}{b2} "
                  f"{b1}{r['profit_factor']:>7.2f}{b2} {b1}{vs_bh:>+8.4%}{b2}   {params_short}{marker}")

    # ── Cross-Symbol Summary ──
    print(f"\n\n{'=' * 120}")
    print(f"  CROSS-SYMBOL SUMMARY — Average Performance by Strategy")
    print(f"{'=' * 120}")
    print(f"{'Strategy':<16} {'Avg Return':>10} {'Avg MaxDD':>9} {'Avg Sharpe':>9} "
          f"{'Avg WinRate':>10} {'Avg Trades':>9} {'Avg PF':>7}   Notes")
    print("-" * 120)

    for strategy_name in STRATEGIES:
        str_results = [all_final_results[(s, strategy_name)] for s in TRADING_PAIRS
                       if (s, strategy_name) in all_final_results]
        if not str_results:
            continue
        avg_return = np.mean([r["total_return"] for r in str_results])
        avg_dd = np.mean([r["max_drawdown_pct"] for r in str_results])
        avg_sharpe = np.mean([r["sharpe_ratio"] for r in str_results])
        avg_wr = np.mean([r["win_rate"] for r in str_results])
        avg_trades = np.mean([r["total_trades"] for r in str_results])
        avg_pf = np.mean([r["profit_factor"] for r in str_results])
        # Count positive symbols
        pos_count = sum(1 for r in str_results if r["total_return"] > 0)
        print(f"{strategy_name:<16} {avg_return:>+10.4%} {avg_dd:>9.4%} {avg_sharpe:>+9.4f} "
              f"{avg_wr:>10.4%} {avg_trades:>9.0f} {avg_pf:>7.2f}   profitable on {pos_count}/3 pairs")

    # ── Save Combined CSV ──
    csv_path = os.path.join(OUTPUT_DIR, "final_summary.csv")
    print(f"\nSaving combined results to {csv_path}")
    rows = []
    for (symbol, strategy_name), r in all_final_results.items():
        row = {
            "交易对": symbol,
            "策略": strategy_name,
            "累计收益率": f"{r['total_return']:.4%}",
            "最大回撤": f"{r['max_drawdown_pct']:.4%}",
            "夏普比率": f"{r['sharpe_ratio']:.4f}",
            "胜率": f"{r['win_rate']:.4%}",
            "交易次数": r["total_trades"],
            "盈亏比": f"{r['profit_factor']:.2f}",
            "平均单笔收益": f"{r['avg_trade_pnl_pct']:.4%}",
            "做多次数": r.get("total_long", 0),
            "做空次数": r.get("total_short", 0),
            "止盈出场": r.get("tp_exits", 0),
            "止损出场": r.get("sl_exits", 0),
            "时间出场": r.get("tl_exits", 0),
            "买入持有收益": f"{bh_returns.get(symbol, 0):.4%}",
            "vs买入持有": f"{r['total_return'] - bh_returns.get(symbol, 0):.4%}",
            "策略切换次数": 0,
        }
        row.update({f"参数_{k}": v for k, v in r["params"].items()})
        rows.append(row)
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding='utf-8-sig')
    print("Done!")


if __name__ == "__main__":
    main()
