"""Agent-friendly backtest CLI — same engine as the FinKit UI, JSON on stdout.

Runs a strategy from a ``.py`` file through the real backtest engine
(``run_backtest_in_subprocess``) with live prices + fees from the SQLite DB.

Usage
-----
python scripts/run_backtest_cli.py \\
    --strategy-file my_strategy.py \\
    --universe 000217,000667,002910,006432,378546 \\
    --start 2021-09-01 --end 2026-08-25 \\
    --params '{"lookback_days":180,"top_k":2}'

Output
------
* stdout: one JSON object with {status, metrics, nav_series, weight_history,
  rebalance_records, rebalance_freq, params}.
* stderr: a short human-readable summary.

Exit code 0 on success, 1 on failure (error message on stderr).
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import sys

# Make `import app` work when run from anywhere (repo root / scripts / cwd).
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.backtest_engine import run_backtest_in_subprocess  # noqa: E402


def _read_strategy_code(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_metadata(code: str) -> dict:
    """Best-effort pull of name/params_schema from the Strategy subclass."""
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name):
                            try:
                                val = ast.literal_eval(item.value)
                            except (ValueError, SyntaxError):
                                continue
                            if t.id in ("name", "description", "rebalance_freq"):
                                if isinstance(val, (str, type(None))):
                                    return {t.id: val}
                            if t.id == "params_schema" and isinstance(val, dict):
                                return {t.id: val}
    return {}


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run a FinKit strategy backtest (JSON out).")
    p.add_argument("--strategy-file", required=True, help="Path to the Strategy .py file")
    p.add_argument("--universe", required=True, help="Comma-separated asset symbols")
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    p.add_argument("--params", default="{}", help='JSON string of strategy params, e.g. \'{"top_k":2}\'')
    p.add_argument("--freq", default="monthly", choices=["monthly", "weekly"])
    p.add_argument("--db", default="finkit.db", help="Path to SQLite DB (default finkit.db)")
    p.add_argument("--timeout", type=int, default=120, help="Subprocess timeout seconds")
    args = p.parse_args(argv)

    try:
        code = _read_strategy_code(args.strategy_file)
        params = json.loads(args.params) if args.params else {}
        universe = [s.strip() for s in args.universe.split(",") if s.strip()]
        meta = _extract_metadata(code)
        if meta.get("rebalance_freq") and args.freq == "monthly":
            # let the strategy's own default win unless the user explicitly passed --freq
            args.freq = meta["rebalance_freq"]

        result = asyncio.run(
            run_backtest_in_subprocess(
                strategy_code=code,
                params=params,
                universe=universe,
                start_date=args.start,
                end_date=args.end,
                rebalance_freq=args.freq,
                db_path=args.db,
                timeout=args.timeout,
            )
        )
    except Exception as e:
        sys.stderr.write(f"ERROR: {type(e).__name__}: {e}\n")
        return 1

    if result.get("status") != "ok":
        sys.stderr.write(f"ERROR: {result.get('error', 'unknown')}\n")
        return 1

    # Human summary on stderr; machine JSON on stdout.
    m = result.get("metrics", {})
    navs = result.get("nav_series") or []
    sys.stderr.write(
        f"status=ok  ann_return={(m.get('ann_return') or 0)*100:.2f}%  "
        f"ann_vol={(m.get('ann_volatility') or 0)*100:.2f}%  "
        f"sharpe={m.get('sharpe') or 0:.3f}  "
        f"max_drawdown={(m.get('max_drawdown') or 0)*100:.2f}%  "
        f"cost={(m.get('total_cost') or 0):.0f}  "
        f"nav={navs[-1]['nav'] if navs else 0:.4f}\n"
    )
    sa = result.get("stagnant_analysis") or {}
    if sa.get("merged_periods"):
        thr = (sa.get("threshold_ann") or 0) * 100
        sys.stderr.write(f"stagnant windows (window-ann < {thr:.1f}%):\n")
        for p in sa["merged_periods"]:
            sys.stderr.write(f"  {p['start']} -> {p['end']}\n")
    cfa = result.get("custom_factor_analysis") or {}
    if cfa:
        sys.stderr.write("custom factors:\n")
        for fname, st in cfa.items():
            sys.stderr.write(
                f"  {fname}: ic={st['ic_mean']:+.4f} rank_ic={st['rank_ic']:+.4f} "
                f"win={(st['win_rate'])*100:.0f}% n={st['n_periods']}\n"
            )
    out = {
        "status": "ok",
        "metrics": m,
        "nav_series": navs,
        "weight_history": result.get("weight_history", []),
        "rebalance_records": result.get("rebalance_records", []),
        "stagnant_analysis": result.get("stagnant_analysis"),
        "custom_factor_analysis": result.get("custom_factor_analysis"),
        "rebalance_freq": args.freq,
        "params": params,
        "universe": universe,
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())