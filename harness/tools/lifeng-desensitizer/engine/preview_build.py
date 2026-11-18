# -*- coding: utf-8 -*-
"""
预览数据构建 —— 把脱敏后的文档拆成「可高亮浏览」的结构。

为什么不在脱敏引擎里记位置：
    引擎内部是「整段文本 replace」，没有位置概念，硬加位置要动核心替换逻辑，
    而核心刚在 v2.1 验收完，不值得为预览去碰。

改用的办法：脱敏完拿到映射表（原值→占位符→类别），再在**脱敏后的文本**里
反查占位符出现位置。占位符本身是唯一的（`[甲方公司]`、`周某`、`[地址]`），
反查足够准，且完全不侵入引擎。

两条底线：
    1. 原值不写进 preview.json —— 单独存 origs.json，前端点击某一处才按需取。
       一次把整篇原值灌进页面，等于脱敏白做。
    2. 只展示脱敏后的内容。原文不提供给预览页。
"""
import os
import json
import re
import time


def _load_mapping(map_csv):
    """读映射表，返回 [(原值, 占位符, 类别), ...]。容忍列序差异。"""
    import csv
    rows = []
    if not map_csv or not os.path.exists(map_csv):
        return rows
    try:
        with open(map_csv, encoding="utf-8-sig") as f:
            rd = list(csv.reader(f))
    except Exception:
        return rows
    if not rd:
        return rows
    head = [c.strip() for c in rd[0]]
    try:
        i_o, i_p = head.index("原值"), head.index("占位符")
        i_c = head.index("类别") if "类别" in head else -1
        body = rd[1:]
    except ValueError:
        i_o, i_p, i_c, body = 0, 1, 2, []
    for r in body:
        if len(r) <= max(i_o, i_p):
            continue
        o, ph = r[i_o].strip(), r[i_p].strip()
        cat = r[i_c].strip() if 0 <= i_c < len(r) else ""
        if o and ph:
            rows.append((o, ph, cat))
    return rows


def _find_all(text, sub):
    """返回 sub 在 text 中所有出现位置 [(起, 止), ...]。"""
    out, st = [], 0
    if not sub:
        return out
    while True:
        i = text.find(sub, st)
        if i < 0:
            break
        out.append((i, i + len(sub)))
        st = i + len(sub)
    return out


def _dedup(spans):
    """去重叠，保留先出现与更长的。"""
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out, last = [], -1
    for t in spans:
        if t[0] >= last:
            out.append(t)
            last = t[1]
    return out


def _align_runs(orig, red, mapping, id_alloc, origs):
    """把一段原文与脱敏文对齐，返回脱敏侧的 runs（被替换区间标 mark）。

    为什么不用字符级 diff：脱敏是「整词换成占位符」，difflib 会在替换段内部
    找到巧合相同的字——`某某建材有限公司` → `[甲方公司]` 时，
    `公司` 两个字被判为"未变"，于是占位符被切成 `[甲方` + `公司` + `]` 三段；
    `周立国` → `周某` 时 `周` 被判未变，原值只剩 `立国`。都是错的。

    正确做法：原文里找每个原值的位置（A），脱敏文里找每个占位符的位置（B），
    **按出现顺序一一配对**。替换是顺序执行的，两侧顺序天然一致。
    数量对不上时（占位符被子串误命中）退化为只标位置、不给原值。
    """
    if orig == red:
        return [{"text": red, "mark": False}] if red else []

    # A：原文中被替换的片段
    A = []
    for o, ph, cat in mapping:
        if not o:
            continue
        for (i, j) in _find_all(orig, o):
            A.append((i, j, o, ph, cat))
    A = _dedup(A)

    # B：脱敏文中的占位符位置（长占位符优先，避免 `[地址]` 被 `[地]` 截断）
    phs = sorted({t[3] for t in A if t[3]}, key=len, reverse=True)
    B = []
    for ph in phs:
        for (i, j) in _find_all(red, ph):
            B.append((i, j, ph))
    B = _dedup(B)

    if not B:
        return [{"text": red, "mark": False}] if red else []

    paired = len(A) == len(B)
    runs, pos = [], 0
    for k, (s, e, ph) in enumerate(B):
        if s > pos:
            runs.append({"text": red[pos:s], "mark": False})
        rid = id_alloc()
        if paired:
            o = A[k][2]
            cat = A[k][4] or "敏感项"
            origs[str(rid)] = o
        else:
            # 占位符现在会带序号（[地址2]），类别要去掉序号才算干净
            cat = re.sub(r"\d+$", "", ph.strip("[]")) or "敏感项"
            origs[str(rid)] = ""
        runs.append({"text": red[s:e], "mark": True, "id": rid, "cat": cat})
        pos = e
    if pos < len(red):
        runs.append({"text": red[pos:], "mark": False})
    return runs


def build_preview(orig_docx, red_docx, map_csv, task_dir, source_name=""):
    """生成 preview.json / origs.json / meta.json，返回 meta。

    orig_docx: 原始文件（只在本机读取，不向前端下发）
    red_docx:  脱敏后的文件
    map_csv:   本次映射表（只用来判定类别）
    """
    from docx import Document

    mapping = _load_mapping(map_csv)
    counter = {"n": 0}
    origs = {}

    def alloc():
        counter["n"] += 1
        return counter["n"]

    d_orig = Document(orig_docx)
    d_red = Document(red_docx)

    blocks = []
    hit_count = 0
    by_cat = {}

    def _tap(runs):
        nonlocal hit_count
        for r in runs:
            if r.get("mark"):
                hit_count += 1
                by_cat[r["cat"]] = by_cat.get(r["cat"], 0) + 1

    # 按文档原始顺序输出：段落与表格是穿插的。
    # 原来是「先排完所有段落、再把所有表格追加到末尾」，
    # 结果合同里的表格在预览中要么跑到文末、要么整块不见（2026-10-30 实测）。
    def _body_order(doc):
        out, pi, ti = [], 0, 0
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                out.append(("p", pi))
                pi += 1
            elif tag == "tbl":
                out.append(("table", ti))
                ti += 1
        return out

    o_paras = [p.text for p in d_orig.paragraphs]
    r_paras = [p.text for p in d_red.paragraphs]
    o_tables = list(d_orig.tables)
    r_tables = list(d_red.tables)

    for kind, idx in _body_order(d_red):
        if kind == "p":
            rt = r_paras[idx] if idx < len(r_paras) else ""
            ot = o_paras[idx] if idx < len(o_paras) else ""
            if not rt.strip():
                continue
            runs = _align_runs(ot, rt, mapping, alloc, origs)
            _tap(runs)
            blocks.append({"type": "p", "runs": runs})
            continue

        t_red = r_tables[idx]
        t_orig = o_tables[idx] if idx < len(o_tables) else None
        rows = []
        for ri, row in enumerate(t_red.rows):
            cells = []
            for ci, cell in enumerate(row.cells):
                o_cell = None
                try:
                    if t_orig is not None:
                        o_cell = t_orig.rows[ri].cells[ci]
                except Exception:
                    o_cell = None
                o_cell_text = "\n".join(p.text for p in o_cell.paragraphs) if o_cell else ""
                cell_text = "\n".join(p.text for p in cell.paragraphs)
                runs = _align_runs(o_cell_text, cell_text, mapping, alloc, origs)
                _tap(runs)
                cells.append(runs)
            rows.append(cells)
        if rows:
            blocks.append({"type": "table", "index": idx + 1, "rows": rows})

    os.makedirs(task_dir, exist_ok=True)
    preview = {
        "file": source_name or os.path.basename(red_docx),
        "count": hit_count,
        "by_category": by_cat,
        "blocks": blocks,
    }
    with open(os.path.join(task_dir, "preview.json"), "w", encoding="utf-8") as f:
        json.dump(preview, f, ensure_ascii=False)

    with open(os.path.join(task_dir, "origs.json"), "w", encoding="utf-8") as f:
        json.dump(origs, f, ensure_ascii=False)

    meta = {
        "task_id": os.path.basename(os.path.normpath(task_dir)),
        "source": source_name,
        "output": os.path.basename(red_docx),
        "count": hit_count,
        "by_category": by_cat,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "preview",
    }
    with open(os.path.join(task_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta
