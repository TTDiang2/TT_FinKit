"""Run uvicorn for a quick 5s smoke test, then exit."""
import subprocess, time, sys, signal
p = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8100"],
    cwd=r"backend",
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
)
try:
    time.sleep(5)
    import urllib.request
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8100/api/health", timeout=2)
        print("HEALTH:", r.status, r.read().decode())
    except Exception as e:
        print("HEALTH_ERR:", e)
finally:
    p.terminate()
    try:
        out, _ = p.communicate(timeout=5)
        print("---- server output ----")
        print(out[-3000:])
    except Exception:
        p.kill()
