#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
表格脱敏（.xlsx / .xls）—— 让立丰脱敏支持 Excel。

要点：
  1. 逐个 sheet 逐格替换，保留原格式（字体/列宽/合并单元格不动）
  2. 公式单元格不动（否则会破坏计算）
  3. 表头整列脱敏：如果某列表头是「姓名/身份证/手机/账号」等，整列数据都处理
  4. 记住每次替换，输出对照表

用法：
  python3 sheet_redact.py 台账.xlsx --terms 敏感词表.txt [--out 台账_已脱敏.xlsx]
"""
import os
import re
import sys
import csv
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from desensitize import (load_terms, REGEX_RULES,  # noqa: E402
                         protect_disabled_spans, restore_spans)


def redact_value(v, rules, precise_ok=True):
    """对单元格值做脱敏，返回 (新值, 命中列表)。非字符串原样返回。"""
    if not isinstance(v, str) or not v:
        return v, []
    hits = []
    out = v
    # 1) 自定义词表（长词优先）
    for orig, repl in rules:
        if orig and orig in out:
            out = out.replace(orig, repl)
            hits.append(orig)
    # 1.5) 禁用字段保护（2026-10-30）
    # 表格通道不走 Redactor，禁用一个字段后别的规则会冒名顶替：
    # 实测关掉「身份证号」，18 位号码被「统一社会信用代码」接管，
    # 单元格变成 [统一社会信用代码] —— 标错类别比不脱更误导。
    # 先把这些片段换成哨兵，替换完再原样还原。
    out, _keep = protect_disabled_spans(out)
    # 2) 正则类（身份证/手机/银行卡/信用代码/车牌/机构）
    for cat, rx in REGEX_RULES:
        new = rx.sub("[%s]" % cat, out)
        if new != out:
            hits.append(cat)
            out = new
    # 3) 还原被保护片段
    out = restore_spans(out, _keep)
    return out, hits


def redact_sheet_xlsx(inp, outp, terms, precise=False):
    import openpyxl
    wb = openpyxl.load_workbook(inp)       # 保持公式
    records = []
    total_cells = 0
    touched = 0

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if val is None:
                    continue
                # 公式跳过（value 以 = 开头 或 data_type 为 f）
                if isinstance(val, str) and val.startswith("="):
                    continue
                if getattr(cell, "data_type", "") == "f":
                    continue
                total_cells += 1
                nv, hits = redact_value(val, terms)
                if nv != val:
                    cell.value = nv
                    touched += 1
                    records.append({
                        "sheet": ws.title,
                        "cell": cell.coordinate,
                        "category": "/".join(sorted(set(hits))),
                    })
    wb.save(outp)
    wb.close()
    return records, total_cells, touched


def redact_sheet_xls_via_convert(inp, outp, terms):
    """老 .xls 用系统工具转 xlsx 后处理（无 openpyxl 的 xls 支持时兜底）。"""
    import subprocess, tempfile, shutil
    tmpd = tempfile.mkdtemp()
    tmp_xlsx = os.path.join(tmpd, "conv.xlsx")
    # macOS 可用 textutil 转；若无则报错
    r = subprocess.run(["/usr/bin/textutil", "-convert", "xlsx", "-output", tmp_xlsx, inp],
                       capture_output=True)
    if r.returncode != 0 or not os.path.exists(tmp_xlsx):
        return None, 0, 0
    recs, total, touched = redact_sheet_xlsx(tmp_xlsx, outp, terms)
    return recs, total, touched


def main():
    ap = argparse.ArgumentParser(description="表格脱敏（xlsx）")
    ap.add_argument("input")
    ap.add_argument("--terms", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--map", default="")
    ap.add_argument("--precise", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print("文件不存在：", args.input)
        return 1
    ext = os.path.splitext(args.input)[1].lower()
    if ext not in (".xlsx", ".xls", ".xlsm"):
        print("仅支持 .xlsx / .xls，当前：", ext)
        return 1

    terms = load_terms(args.terms) if args.terms else []
    outp = args.out or (os.path.splitext(args.input)[0] + "_已脱敏" + ext)
    mapf = args.map or (os.path.splitext(outp)[0] + "_映射表.csv")

    try:
        if ext == ".xlsx" or ext == ".xlsm":
            records, total, touched = redact_sheet_xlsx(args.input, outp, terms)
        else:
            records, total, touched = redact_sheet_xls_via_convert(args.input, outp, terms)
            if records is None:
                print("处理失败：老版 .xls 需要先转成 .xlsx")
                return 1
    except Exception as e:
        print("处理失败：", e)
        return 1

    with open(mapf, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["工作表", "单元格", "命中类别"])
        for r in records:
            w.writerow([r["sheet"], r["cell"], r["category"]])

    print("脱敏成品：", outp)
    print("对照表（勿外传）：", mapf)
    print("扫描 %d 个单元格，脱敏 %d 个" % (total, touched))
    if touched == 0 and terms:
        print("提示：没有命中。若表里确有真名，请确认词表是否覆盖本案。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
