"""Strategy docstring metadata parsing (Phase P4).

策略文件模块 docstring 首部为 YAML 风格元数据块，``---`` 分隔行之后的自由文档
不参与解析。仅用 ``ast.parse`` + ``ast.get_docstring`` 提取，绝不执行代码。
"""
import ast
import re

# 支持的元数据键（factor_keys 特殊处理为 list）
_META_KEYS = ("name", "description", "rebalance_freq", "version_note")


def _parse_factor_keys(raw: str) -> list[str]:
    """把 factor_keys 的 ``[a, b]`` 或 ``a,b`` 两种写法解析成 list[str]。"""
    if not raw:
        return []
    s = raw.strip()
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    keys = []
    for part in re.split(r"[,，]", s):
        part = part.strip().strip("\"'`")
        if part:
            keys.append(part)
    return keys


def parse_strategy_docstring(code: str) -> dict:
    """提取模块 docstring 首部元数据块。

    返回 dict：name / description / rebalance_freq / factor_keys / version_note。
    字段缺失时对应值为 None（factor_keys 缺失为 None，解析成功为 list[str]）。
    """
    meta = {
        "name": None,
        "description": None,
        "rebalance_freq": None,
        "factor_keys": None,
        "version_note": None,
    }
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return meta
    doc = ast.get_docstring(tree, clean=False)
    if not doc:
        return meta

    # 只取第一个 --- 分隔行之前的内容作为元数据头
    header_lines = []
    for line in doc.splitlines():
        if line.strip().startswith("---"):
            break
        header_lines.append(line)

    for line in header_lines:
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key == "factor_keys":
            meta["factor_keys"] = _parse_factor_keys(value)
        elif key in _META_KEYS and value:
            meta[key] = value
    return meta
