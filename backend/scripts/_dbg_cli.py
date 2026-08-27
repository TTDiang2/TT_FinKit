import json
import os
import subprocess
import sys
import tempfile
import importlib.util

spec = importlib.util.spec_from_file_location("tbc", "tests/test_backtest_cli.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

p = os.path.join(tempfile.gettempdir(), "cli_strategy_dbg.py")
with open(p, "w", encoding="utf-8") as f:
    f.write(m.STRATEGY_PY)

cmd = [
    sys.executable, os.path.join("scripts", "run_backtest_cli.py"),
    "--strategy-file", p,
    "--universe", "000217,000667,002910,006432,378546",
    "--start", "2021-09-01", "--end", "2026-08-25",
    "--db", "finkit.db",
    "--params", json.dumps({"lookback_days": 180, "top_k": 2}),
]
print("RUNNING...")
r = subprocess.run(cmd, capture_output=True, timeout=170)
out = r.stdout.decode("utf-8", errors="replace")
print("rc:", r.returncode)
print("stdout bytes:", len(r.stdout), "| stderr bytes:", len(r.stderr))
try:
    d = json.loads(out)
    print("JSON OK | status:", d.get("status"), "| nav:", len(d.get("nav_series") or []), "| sharpe:", (d.get("metrics") or {}).get("sharpe"))
except Exception as e:
    print("JSON FAIL:", e)
    bad = out.encode("utf-8", errors="replace")
    print("head:", out[:400].replace("\n", " | "))
    print("tail:", out[-400:].replace("\n", " | "))
