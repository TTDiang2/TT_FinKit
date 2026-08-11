"""查 iFinDPy 4 个函数的真实签名 + docstring。"""
import sys, os, io, inspect
sys.stdout = io.open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
import iFinDPy

for name in ["THS_RQ", "THS_HQ", "THS_BD", "THS_DS", "THS_EDB", "THS_DateSerial", "THS_BasicData", "THS_HighFrequence", "THS_Realtime"]:
    fn = getattr(iFinDPy, name, None)
    if fn is None:
        print(f"{name}: (不存在)")
        continue
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        sig = "(签名不可获取)"
    doc = (inspect.getdoc(fn) or "").strip().split("\n")[0:3]
    print(f"=== {name}{sig} ===")
    for line in doc:
        print(f"    {line}")
    print()
