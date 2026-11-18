#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**已脱敏的成品**转成 Markdown，供案件研判 agent 直接读取。

为什么单独做（2026-11-02）：
    脱敏 App 的成品是 docx / pdf / xlsx，agent 读这些要么装一堆解析库，
    要么拿到一堆无结构的字符流。研判要的是「标题层级 + 段落 + 表格」，
    Markdown 是唯一同时满足"人能看、模型能读、git 能存"的格式。

设计要点：
  1. **只吃脱敏件**：本脚本不做脱敏，输入必须是成品（含占位符），
     避免有人拿它去转原件、把真名带进知识库；
  2. 结构优先：docx 按 body 里的真实顺序输出（段落与表格是穿插的，
     不是"先所有段落再所有表格"）；标题按 style 映射 #/##/###；
  3. 表格转标准 md 表格；合并单元格用重复文字补齐，不丢信息；
  4. PDF 逐页提取；无文字层（扫描件）的页明确标注，别假装转成功；
  5. 图片走 macOS Vision OCR（可选），失败就写占位符；
  6. 输出 YAML front matter（来源、页数/段数、转换时间），便于检索与溯源。

用法：
    python3 to_markdown.py 成品.docx -o 输出.md
    python3 to_markdown.py 成品目录/            # 目录内批量，逐个转
    python3 to_markdown.py 成品.pdf --no-ocr    # 扫描件不跑 OCR，只标页码
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SUPPORTED = (".docx", ".docm", ".pdf", ".xlsx", ".xlsm", ".txt", ".md",
             ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


# ---------------- 通用 ----------------

def _clean(s):
    """清理不可见字符与多余空白，保留中文标点。"""
    if s is None:
        return ""
    s = str(s).replace("\u00a0", " ").replace("\r", "")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _cell(s):
    """表格单元格：竖线会破坏 md 表格，必须转义；换行压成空格。"""
    s = _clean(s)
    s = s.replace("|", "\\|")
    s = s.replace("\n", " ")
    return s or " "


def _md_table(rows, header=True):
    """二维数组 → md 表格。第一行作表头；空表返回空串。"""
    rows = [r for r in rows if any(_clean(c) for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [list(r) + [""] * (width - len(r)) for r in rows]
    out = []
    head = rows[0] if header else ["" for _ in range(width)]
    out.append("| " + " | ".join(_cell(c) for c in head) + " |")
    out.append("|" + "|".join([" --- "] * width) + "|")
    for r in (rows[1:] if header else rows):
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(out)


# ---------------- docx ----------------

_HEAD_STYLE = re.compile(r"(?:Heading|标题)\s*([1-6])", re.I)


def _docx_blocks(doc):
    """按 body 真实顺序产出 ('p', 段落) / ('t', 表格)。"""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield "p", Paragraph(child, doc)
        elif tag == "tbl":
            yield "t", Table(child, doc)


def _para_md(p):
    """段落 → md。标题按 style 出 #，列表项保留符号，其余按正文。"""
    text = _clean(p.text)
    if not text:
        return ""
    style = ""
    try:
        style = (p.style.name or "") if p.style is not None else ""
    except Exception:
        style = ""
    m = _HEAD_STYLE.search(style or "")
    if m:
        return "#" * min(6, int(m.group(1))) + " " + text
    if style and ("List" in style or "列表" in style):
        return "- " + text
    # 中文公文常见「一、」「（一）」「1.」这类编号段落：保留原样即可，
    # 不再自作主张加粗——加粗会破坏原文强调位置的语义。
    return text


def _table_md(t):
    rows = []
    seen = set()
    for row in t.rows:
        cells = []
        for c in row.cells:
            # 合并单元格在 python-docx 里会重复返回同一个 cell 对象，
            # 用 id 去重会让列数错位，所以这里直接取值并保留重复。
            cells.append(_clean(c.text))
        key = tuple(cells)
        if key in seen:          # 纵向合并的重复行，跳过
            continue
        seen.add(key)
        rows.append(cells)
    return _md_table(rows)


def docx_to_md(path):
    from docx import Document
    doc = Document(path)
    parts = []
    n_p = n_t = 0
    for kind, obj in _docx_blocks(doc):
        if kind == "p":
            s = _para_md(obj)
            if s:
                parts.append(s)
                n_p += 1
        else:
            s = _table_md(obj)
            if s:
                parts.append(s)
                n_t += 1
    # 页眉页脚里的内容（合同编号、页码说明）单独附在末尾，不塞正文
    hf = []
    try:
        for sec in doc.sections:
            for name, h in (("页眉", sec.header), ("页脚", sec.footer)):
                for p in h.paragraphs:
                    t = _clean(p.text)
                    if t and t not in hf:
                        hf.append(t)
    except Exception:
        pass
    if hf:
        parts.append("---\n\n**页眉页脚**：" + "　".join(hf))
    return "\n\n".join(parts), {"段落": n_p, "表格": n_t}


# ---------------- pdf ----------------

def pdf_to_md(path, ocr=True):
    import pymupdf
    doc = pymupdf.open(path)
    parts = []
    blank = 0
    for i, page in enumerate(doc, 1):
        txt = _clean(page.get_text("text"))
        if len(txt) < 10:
            blank += 1
            ocr_txt = ""
            if ocr:
                try:
                    ocr_txt = _ocr_pdf_page(page)
                except Exception:
                    ocr_txt = ""
            if ocr_txt:
                parts.append("## 第 %d 页（OCR）\n\n%s" % (i, ocr_txt))
            else:
                parts.append("## 第 %d 页\n\n> 本页无文字层（扫描图片），"
                             "未提取到内容，研判时需人工核对原页。" % i)
            continue
        # 单页内多段落：按空行切，保持可读
        paras = [x.strip() for x in re.split(r"\n\s*\n", txt) if x.strip()]
        body = "\n\n".join(paras) if paras else txt
        parts.append("## 第 %d 页\n\n%s" % (i, body))
    total = len(doc)
    doc.close()
    return "\n\n".join(parts), {"页数": total, "无文字层页": blank}


def _ocr_json_to_text(raw):
    """Vision 输出的是 [{text,x,y,w,h,conf}]，坐标原点在左下。

    直接把这串 JSON 塞进 md 等于没转换——研判 agent 读到一堆小数会疯。
    这里按 y 分行（自上而下）、行内按 x 排序，拼回自然段落。
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    arr = None
    try:
        i, j = raw.find("["), raw.rfind("]")
        arr = json.loads(raw[i:j + 1]) if i >= 0 and j > i else None
    except Exception:
        arr = None
    if not isinstance(arr, list):
        return _clean(raw)          # 不是 JSON 就按纯文本处理

    items = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        t = _clean(it.get("text", ""))
        if not t:
            continue
        try:
            items.append((float(it.get("y", 0)), float(it.get("x", 0)), t))
        except Exception:
            continue
    if not items:
        return ""
    items.sort(key=lambda z: (-z[0], z[1]))   # y 从大到小（页面自上而下）

    lines, cur = [], []
    last_y = None
    for y, x, t in items:
        if last_y is None or abs(y - last_y) < 0.012:
            cur.append(t)
        else:
            if cur:
                lines.append("".join(cur))
            cur = [t]
        last_y = y
    if cur:
        lines.append("".join(cur))
    return "\n\n".join(lines)


def _ocr_pdf_page(page):
    """把单页渲成图，走 macOS Vision OCR。没有工具就返回空串。"""
    exe = os.path.join(HERE, "ocr_vision", "ocr")
    if not os.path.exists(exe):
        alt = os.path.join(HERE, "ocr_vision.swift")
        if os.path.exists(alt):
            exe = alt
        else:
            return ""
    tmp = "/tmp/_tomd_%d.png" % int(time.time() * 1000)
    try:
        pix = page.get_pixmap(dpi=200)
        pix.save(tmp)
        if exe.endswith(".swift"):
            r = subprocess.run(["/usr/bin/swift", exe, tmp],
                               capture_output=True, timeout=120)
        else:
            r = subprocess.run([exe, tmp], capture_output=True, timeout=120)
        out = (r.stdout or b"").decode("utf-8", "ignore")
        return _ocr_json_to_text(out)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ---------------- xlsx ----------------

def xlsx_to_md(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    parts = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else str(v) for v in row])
        while rows and not any(_clean(c) for c in rows[-1]):
            rows.pop()
        if not rows:
            continue
        parts.append("## 工作表：%s\n\n%s" % (ws.title, _md_table(rows)))
    wb.close()
    return "\n\n".join(parts), {"工作表": len(parts)}


# ---------------- 图片 / 文本 ----------------

def image_to_md(path):
    txt = _ocr_pdf_page(type("P", (), {"get_pixmap": lambda self, dpi=0: _fake_pix(path)})())
    return (txt or "> 未提取到文字（OCR 不可用或图中无字）。"), {"类型": "图片"}


def _fake_pix(path):
    import pymupdf
    pix = pymupdf.Pixmap(path)
    return pix


def text_to_md(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    paras = [x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]
    return "\n\n".join(paras), {"段数": len(paras)}


# ---------------- 主流程 ----------------

def convert(path, out_path=None, ocr=True, title=None):
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        return {"ok": False, "msg": "不支持转 md 的格式：%s" % (ext or "无扩展名")}

    t0 = time.time()
    try:
        if ext in (".docx", ".docm"):
            body, stat = docx_to_md(path)
        elif ext == ".pdf":
            body, stat = pdf_to_md(path, ocr=ocr)
        elif ext in (".xlsx", ".xlsm"):
            body, stat = xlsx_to_md(path)
        elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
            body, stat = image_to_md(path)
        else:
            body, stat = text_to_md(path)
    except Exception as e:
        return {"ok": False, "msg": "转换失败：%s" % str(e)[:160]}

    name = os.path.splitext(os.path.basename(path))[0]
    # 文件名常带「_已脱敏」「（修订）」这类加工痕迹，塞进 H1 很难看；
    # 正文自身已有标题时不重复生成，没有才用干净文件名兜底。
    disp = name
    for suf in ("_已脱敏", "_已还原"):
        if disp.endswith(suf):
            disp = disp[:-len(suf)]
    disp = re.sub(r"^[（(](?:批注)?修订[）)]\s*", "", disp)
    disp = disp.strip(" _-—")
    disp = disp or name
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    stat_txt = "、".join("%s %s" % (k, v) for k, v in stat.items())
    body = body or "> 未提取到内容。"
    has_h1 = bool(re.search(r"(?m)^#\s+\S", body))
    fm = [
        "---",
        "source: %s" % name,
        "source_ext: %s" % ext.lstrip("."),
        "converted_at: %s" % stamp,
        "stats: %s" % (stat_txt or "-"),
        "note: 已脱敏成品转写，占位符（如 [甲方公司]、张某）保留原样，请勿据此推断真实身份",
        "---",
        "",
    ]
    head = "" if (has_h1 and not title) else ("# %s\n\n" % (title or disp))
    md = "\n".join(fm) + head + body + "\n"

    if not out_path:
        out_path = os.path.join(os.path.dirname(path), name + ".md")
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    # 同名不同格式（合同.docx 与 合同.xlsx）会写出同一个 md，互相覆盖。
    # 已有文件且来源不是同一个时，补上扩展名区分：合同__xlsx.md
    if os.path.exists(out_path):
        try:
            head = open(out_path, encoding="utf-8").read(600)
            m_src = re.search(r"(?m)^source: (.+)$", head)
            m_ext = re.search(r"(?m)^source_ext: (.+)$", head)
            same = (m_src and m_src.group(1).strip() == name and
                    m_ext and m_ext.group(1).strip() == ext.lstrip("."))
            if not same:
                stem2, ext2 = os.path.splitext(out_path)
                out_path = "%s__%s%s" % (stem2, ext.lstrip("."), ext2)
        except Exception:
            pass
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    return {"ok": True, "src": path, "md": out_path,
            "chars": len(md), "body_chars": len(body or ""),
            "stats": stat, "seconds": round(time.time() - t0, 2),
            "preview": (body or "")[:1200]}


def convert_dir(dirpath, ocr=True):
    out = []
    for n in sorted(os.listdir(dirpath)):
        p = os.path.join(dirpath, n)
        if not os.path.isfile(p) or n.startswith("."):
            continue
        if os.path.splitext(n)[1].lower() not in SUPPORTED:
            continue
        if n.lower().endswith(".md"):
            continue
        out.append(convert(p, ocr=ocr))
    return {"ok": True, "items": out, "count": len(out)}


def main():
    ap = argparse.ArgumentParser(description="已脱敏成品转 Markdown（供 agent 研判）")
    ap.add_argument("path", help="成品文件或目录")
    ap.add_argument("-o", "--out", default="", help="输出 md 路径（单文件时有效）")
    ap.add_argument("--no-ocr", action="store_true", help="扫描件不跑 OCR")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供程序调用）")
    a = ap.parse_args()

    if os.path.isdir(a.path):
        r = convert_dir(a.path, ocr=not a.no_ocr)
    else:
        r = convert(a.path, a.out or None, ocr=not a.no_ocr)

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") else 1

    if not r.get("ok"):
        print("失败：%s" % r.get("msg"))
        return 1
    if "items" in r:
        print("共 %d 份：" % r["count"])
        for it in r["items"]:
            if it.get("ok"):
                print("  ✓ %-46s %s 字  %.2fs" %
                      (os.path.basename(it["md"]), it["chars"], it["seconds"]))
            else:
                print("  × %s  %s" % (os.path.basename(it.get("src", "")), it.get("msg")))
    else:
        print("已生成：%s" % r["md"])
        print("字数：%d（正文 %d）　用时 %.2fs" % (r["chars"], r["body_chars"], r["seconds"]))
        if r.get("stats"):
            print("统计：" + "、".join("%s %s" % (k, v) for k, v in r["stats"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())