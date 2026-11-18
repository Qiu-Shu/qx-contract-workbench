# -*- coding: utf-8 -*-
"""
文件还原服务 —— 把已脱敏文件换回真名。

底层复用 ~/.workbuddy/scripts/restore_origin.py（已实现"脱敏件+映射表→真名"），
这里只做三件事：找映射表、判格式、把结果说清楚。

匹配映射表的三步（按可靠性排序）：
    ① 文件名：`XX_已脱敏.docx` → 去掉 `_已脱敏` → 找 `XX_映射表.csv`
    ② 内容反查：扫成品里的占位符，在全部映射表里算命中率，取最高
    ③ 手动：把候选列表交给用户选

**任何一步都不自动执行**。选错映射表会把真名换成别人的名字，比不还原更危险，
所以必须让用户在界面上看清楚"用了哪份映射表、会替换多少处"再点头。
"""
import os
import re
import csv
import json
import subprocess


def _read_docx_text(path):
    try:
        from docx import Document
        d = Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                for c in row.cells:
                    parts.append(c.text)
        return "\n".join(parts)
    except Exception:
        return ""


def _map_placeholders(csv_path):
    """读映射表里的占位符集合。"""
    out = set()
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception:
        return out
    if not rows:
        return out
    head = [c.strip() for c in rows[0]]
    try:
        i_p = head.index("占位符")
        body = rows[1:]
    except ValueError:
        i_p, body = 1, rows
    for r in body:
        if len(r) > i_p and r[i_p].strip():
            out.add(r[i_p].strip())
    return out


def list_maps(keys_dir):
    """列出全部映射表（供手动选择）。"""
    items = []
    if not os.path.isdir(keys_dir):
        return items
    for n in sorted(os.listdir(keys_dir)):
        if not n.endswith("_映射表.csv"):
            continue
        p = os.path.join(keys_dir, n)
        try:
            n_rows = sum(1 for _ in open(p, encoding="utf-8-sig")) - 1
        except Exception:
            n_rows = 0
        items.append({
            "file": n,
            "path": p,
            "rows": max(0, n_rows),
            "mtime": os.path.getmtime(p),
            "name": n[:-len("_映射表.csv")],
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def match_map(red_path, keys_dir):
    """为一份已脱敏文件找最合适的映射表。

    返回 {"by": "name|content|none", "best": {...}|None, "candidates": [...]}
    """
    stem = os.path.splitext(os.path.basename(red_path))[0]
    plain = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem

    # ① 按文件名
    exact = os.path.join(keys_dir, "%s_映射表.csv" % plain)
    all_maps = list_maps(keys_dir)
    if os.path.exists(exact):
        for it in all_maps:
            if it["path"] == exact:
                return {"by": "name", "best": it, "candidates": all_maps}
        return {"by": "name", "best": {"file": os.path.basename(exact), "path": exact,
                                       "rows": 0, "name": plain}, "candidates": all_maps}

    # ② 内容反查：文档里出现的占位符，哪个映射表覆盖得最多
    text = _read_docx_text(red_path)
    scored = []
    if text:
        for it in all_maps[:200]:      # 映射表上百份时限制扫描量
            phs = _map_placeholders(it["path"])
            if not phs:
                continue
            hit = sum(1 for ph in phs if ph in text)
            if hit:
                scored.append(dict(it, hit=hit, ratio=hit / max(1, len(phs))))
        scored.sort(key=lambda x: (-x["ratio"], -x["hit"]))
    # 命中门槛不能只看条数（2026-10-30 实测）：
    # 一份无关文件里只出现了一个 [地址]，却因为某张映射表凑够 2 条命中，
    # 就被当成「按内容匹配」推荐给用户 —— 点下去就是把别人的真名换进来。
    # 改成必须同时满足：覆盖率 ≥ 60%、命中 ≥ 3 条。
    # 真正被改过名的脱敏件，占位符几乎全在，覆盖率接近 1，照样能认出来。
    if scored and scored[0]["hit"] >= 3 and scored[0]["ratio"] >= 0.6:
        best = scored[0]
        return {"by": "content", "best": best, "candidates": scored + all_maps}

    # ③ 交给用户选
    return {"by": "none", "best": None, "candidates": all_maps}


def can_restore(path):
    """能不能还原。PDF/图片涂黑是真删像素，原样恢复不了。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return True, ""
    if ext in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp"):
        return False, "扫描件与图片的脱敏是抹除像素，原内容已不存在，无法还原"
    if ext == ".xlsx":
        return False, "表格还原尚未支持（占位符是逐单元格替换，需单独适配）"
    return False, "暂不支持该格式"


def _python_with_docx():
    """挑一个装了 python-docx 的解释器。

    不能用 /usr/bin/python3 硬跑：系统自带的 Python 没有 python-docx，
    restore_origin.py 一 import 就报 No module named 'docx'，
    用户看到的只有一句"还原失败"，完全不知道是解释器的问题。

    2026-11-05 打包分发：优先用「环境变量 DESENSITIZE_PYTHON」与「当前解释器」，
    再找包内 runtime，最后才是 WorkBuddy venv。对方机器上只有包内那份。
    """
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.environ.get("DESENSITIZE_PYTHON", ""),
        sys.executable,
        os.path.abspath(os.path.join(_here, "..", "runtime", "bin", "python3")),
        os.path.abspath(os.path.join(_here, "runtime", "bin", "python3")),
        os.path.expanduser("~/.workbuddy/binaries/python/envs/default/bin/python3"),
        "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3",
    ]
    for p in cands:
        if not p or not os.path.exists(p):
            continue
        try:
            r = subprocess.run([p, "-c", "import docx"], capture_output=True, timeout=10)
            if r.returncode == 0:
                return p
        except Exception:
            continue
    return sys.executable


PH_SCAN = re.compile(r"\[[^\[\]]{1,20}\]")


def check_conflicts(map_csv):
    """一个占位符对应多个原值 → 还原时无法确定该填哪个。

    这是最危险的一类错：全部填成其中一家，成品读起来依然通顺，
    但名字悄悄换了人（实测尽调报告里 16 家公司共用一个 [乙方公司]）。
    宁可拒绝还原，也不能给出一个看着对的错答案。
    """
    if not map_csv or not os.path.exists(map_csv):
        return []
    try:
        with open(map_csv, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception:
        return []
    if not rows:
        return []
    head = [c.strip() for c in rows[0]]
    try:
        i_orig, i_ph = head.index("原值"), head.index("占位符")
        body = rows[1:]
    except ValueError:
        i_orig, i_ph = 0, 1
        body = rows
    rev = {}
    for r in body:
        if len(r) <= max(i_orig, i_ph):
            continue
        o, p = r[i_orig].strip(), r[i_ph].strip()
        if o and p:
            rev.setdefault(p, set()).add(o)
    return [{"placeholder": k, "values": sorted(v)}
            for k, v in rev.items() if len(v) > 1]


def scan_residual(path):
    """还原后还剩哪些占位符。用来判断「全还原」还是「部分还原」。"""
    txt = _read_docx_text(path)
    if not txt:
        return []
    return sorted({m.group(0) for m in PH_SCAN.finditer(txt)})


def _find_restore_script():
    """定位 restore_origin.py。

    2026-11-05 打包分发：原来写死 ~/.workbuddy/scripts/restore_origin.py，
    分发包里对方机器没有该路径，还原功能会直接报「还原脚本缺失」。
    改为按「环境变量 → 本目录 → 上一级 → WorkBuddy 老路径」顺序找，
    restore_origin.py 会随引擎一起打进 App。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.environ.get("LF_RESTORE_SCRIPT", ""),
        os.path.join(here, "restore_origin.py"),
        os.path.join(os.path.dirname(here), "restore_origin.py"),
        os.path.join(os.path.dirname(os.path.dirname(here)), "restore_origin.py"),
        os.path.expanduser("~/.workbuddy/scripts/restore_origin.py"),
    ]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return ""


def run_restore(red_path, map_csv, out_dir):
    """调用 restore_origin.py 执行还原，返回 (ok, 输出路径或错误)。"""
    script = _find_restore_script()
    if not script:
        return False, "还原脚本缺失：restore_origin.py 未随程序一起安装"
    stem = os.path.splitext(os.path.basename(red_path))[0]
    plain = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
    out = os.path.join(out_dir, "%s_已还原.docx" % plain)
    os.makedirs(out_dir, exist_ok=True)
    try:
        p = subprocess.run([_python_with_docx(), script, red_path,
                            "--map", map_csv, "--out", out],
                           capture_output=True, text=True, timeout=300)
    except Exception as e:
        return False, "执行失败：%s" % e
    log = (p.stdout or "") + (p.stderr or "")
    info = {"path": out, "residual": [], "log": log[-600:]}
    if p.returncode == 0 and os.path.exists(out):
        info["residual"] = scan_residual(out)
        return True, out, info
    if p.returncode == 1:
        # 有未还原占位符：文件通常会产出，但要告诉用户到底剩几处
        if os.path.exists(out):
            info["residual"] = scan_residual(out)
            return True, out, info
        return False, "存在未还原的占位符，未生成文件。\n" + log[-400:], info
    return False, "还原失败：\n" + log[-400:], info
