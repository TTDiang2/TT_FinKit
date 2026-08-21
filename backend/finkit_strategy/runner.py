"""Run strategy in isolated subprocess. Strategy code receives JSON input,
returns JSON output via tempfile."""
import subprocess, json, tempfile, os, sys, time

def run_strategy_in_subprocess(input_json_path: str, timeout: int = 30) -> dict:
    """Run strategy from JSON input file in subprocess.
    
    input_json: {
        "strategy_code": str,  # Python source for the Strategy subclass
        "params": dict,
        "pool": list[dict],
        "prices": dict,
        "returns": dict,
        "factor_values": dict,
        "factor_exposures": dict,
        "current_weights": dict,
        "rebalance_dates": list[str],
    }
    
    Returns: {"status": "ok"|"error"|"timeout", "weights": {date: {asset: weight}}, "error": str|None}
    """
    runner_code = '''
import sys, json, traceback
from finkit_strategy.base import Strategy, StrategyContext

input_path = sys.argv[1]
output_path = sys.argv[2]

with open(input_path, "r", encoding="utf-8") as f:
    data = json.load(f)

try:
    namespace = {}
    exec(data["strategy_code"], namespace)
    strat_classes = [v for v in namespace.values() if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy]
    if not strat_classes:
        raise ValueError("No Strategy subclass found in code")
    StratClass = strat_classes[0]
    strategy = StratClass(**data.get("params", {}))

    ctx = StrategyContext(
        pool=data.get("pool", []),
        prices=data.get("prices", {}),
        returns=data.get("returns", {}),
        factor_values=data.get("factor_values", {}),
        factor_exposures=data.get("factor_exposures", {}),
        current_weights=data.get("current_weights", {}),
        params=data.get("params", {}),
        now=data.get("rebalance_dates", [""])[0] if data.get("rebalance_dates") else "",
    )

    weights = {}
    for date in data.get("rebalance_dates", []):
        ctx.now = date
        w = strategy.target_weights(ctx, date)
        if w is not None:
            weights[date] = w

    result = {"status": "ok", "weights": weights, "error": None}

except Exception as e:
    result = {"status": "error", "weights": {}, "error": f"{type(e).__name__}: {e}"}
    try:
        result["traceback"] = traceback.format_exc()
    except:
        pass

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False)
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(runner_code)
        runner_script = f.name

    output_path = tempfile.mktemp(suffix='.json')

    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = pkg_parent + (os.pathsep + existing if existing else "")

    try:
        proc = subprocess.Popen(
            [sys.executable, runner_script, input_json_path, output_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return {"status": "timeout", "weights": {}, "error": f"Strategy execution timed out after {timeout}s"}

        with open(output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        return result
    except Exception as e:
        return {"status": "error", "weights": {}, "error": str(e)}
    finally:
        try:
            os.unlink(runner_script)
        except:
            pass
        try:
            os.unlink(output_path)
        except:
            pass
