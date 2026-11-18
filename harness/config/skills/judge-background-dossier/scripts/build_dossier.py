# -*- coding: utf-8 -*-
"""
法官背调与开庭提纲生成器

用法：
    python build_dossier.py 内容稿.json 输出文件.docx

依赖：python-docx（pip install python-docx）

内容稿为 JSON，结构见 references/format.md。
生成后自动做三项检查：半角符号、表格列宽、段落数量。
"""

import collections
import json
import os
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

SONG = "宋体"
HEI = "黑体"
GRAY = RGBColor(0x59, 0x59, 0x59)
BLACK = RGBColor(0x1A, 0x1A, 0x1A)
PAGE_W = 15.8  # 版心宽度，单位厘米


def run_font(run, font=SONG, size=12, bold=False, color=BLACK):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), font)
    rFonts.set(qn("w:ascii"), font)
    rFonts.set(qn("w:hAnsi"), font)


class Builder(object):
    def __init__(self):
        self.doc = Document()
        sec = self.doc.sections[0]
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.top_margin = Cm(2.6)
        sec.bottom_margin = Cm(2.4)
        sec.left_margin = Cm(2.6)
        sec.right_margin = Cm(2.6)
        self.sec = sec

        st = self.doc.styles["Normal"]
        st.font.name = SONG
        st.font.size = Pt(12)
        st.font.color.rgb = BLACK
        st.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)
        st.paragraph_format.line_spacing = 1.5
        st.paragraph_format.space_before = Pt(0)
        st.paragraph_format.space_after = Pt(0)

        self._footer_page_number()

    # ---------- 页脚 ----------
    def _footer_page_number(self):
        p = self.sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run_font(run, SONG, 9, False, GRAY)
        f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
        it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = " PAGE "
        f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "end")
        run._r.append(f1); run._r.append(it); run._r.append(f2)

    # ---------- 区块 ----------
    def title(self, text):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.2
        run_font(p.add_run(text), SONG, 24, True)

    def subtitle(self, text):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.2
        run_font(p.add_run(text), SONG, 10.5, False, GRAY)
        pPr = p._element.get_or_add_pPr()
        pbdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "6")
        bottom.set(qn("w:color"), "BFBFBF")
        pbdr.append(bottom)
        pPr.append(pbdr)

    def h1(self, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(15)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.line_spacing = 1.3
        p.paragraph_format.keep_with_next = True
        run_font(p.add_run(text), HEI, 14.5, True)

    def h2(self, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.4
        p.paragraph_format.keep_with_next = True
        run_font(p.add_run(text), SONG, 12.5, True)

    def body(self, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.first_line_indent = Cm(0.6)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run_font(p.add_run(text), SONG, 12)

    def item(self, num, head, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.left_indent = Cm(1.5)
        p.paragraph_format.first_line_indent = Cm(-1.5)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(1.5))
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run_font(p.add_run("%s\t" % num), SONG, 12, True)
        run_font(p.add_run(head), SONG, 12, True)
        run_font(p.add_run(text), SONG, 12)

    def tip(self, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.45
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Cm(0.6)
        p.paragraph_format.right_indent = Cm(0.4)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run_font(p.add_run(text), SONG, 11, False, RGBColor(0x33, 0x33, 0x33))

    def caption(self, text):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run_font(p.add_run(text), SONG, 11, True, GRAY)

    def pagebreak(self):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.add_run().add_break(WD_BREAK.PAGE)

    def table(self, headers, widths, rows, font_size=9.5, center_cols=None, row_height=None):
        if center_cols is None:
            center_cols = [0]
        total = sum(widths)
        if total > PAGE_W + 0.01:
            print("[警告] 表格列宽合计 %.1f 厘米，超过版心 %.1f 厘米" % (total, PAGE_W))
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        t._tbl.tblPr.append(layout)
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)

        hdr = t.rows[0]
        trPr = hdr._tr.get_or_add_trPr()
        el = OxmlElement("w:tblHeader")
        el.set(qn("w:val"), "true")
        trPr.append(el)
        for i, h in enumerate(headers):
            c = hdr.cells[i]
            c.width = Cm(widths[i])
            c.text = ""
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.line_spacing = 1.2
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run_font(p.add_run(h), SONG, font_size, True)
            tcPr = c._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F2F2F2")
            tcPr.append(shd)

        for row in rows:
            cells = t.add_row().cells
            for ci, val in enumerate(row):
                c = cells[ci]
                c.width = Cm(widths[ci])
                c.text = ""
                p = c.paragraphs[0]
                p.paragraph_format.line_spacing = 1.2
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci in center_cols else WD_ALIGN_PARAGRAPH.LEFT
                run_font(p.add_run(val), SONG, font_size)
            if row_height:
                t.rows[-1].height = Pt(row_height)
        return t

    def save(self, path):
        self.doc.save(path)


def build(spec, out_path):
    b = Builder()
    if spec.get("title"):
        b.title(spec["title"])
    if spec.get("subtitle"):
        b.subtitle(spec["subtitle"])

    for blk in spec.get("blocks", []):
        kind = blk.get("type")
        if kind == "h1":
            b.h1(blk["text"])
        elif kind == "h2":
            b.h2(blk["text"])
        elif kind == "body":
            b.body(blk["text"])
        elif kind == "item":
            b.item(blk.get("num", ""), blk.get("head", ""), blk.get("text", ""))
        elif kind == "tip":
            b.tip(blk["text"])
        elif kind == "caption":
            b.caption(blk["text"])
        elif kind == "pagebreak":
            b.pagebreak()
        elif kind == "table":
            b.table(
                blk["headers"],
                blk["widths"],
                blk.get("rows", []),
                font_size=blk.get("font", 9.5),
                center_cols=blk.get("center_cols", [0]),
                row_height=blk.get("row_height"),
            )
        else:
            raise ValueError("未知区块类型：%s" % kind)

    b.save(out_path)


def check(path):
    doc = Document(path)
    texts = [p.text for p in doc.paragraphs]
    for tb in doc.tables:
        for r in tb.rows:
            for c in r.cells:
                texts.append(c.text)
    joined = "\n".join(texts)

    bad = collections.Counter(
        ch for ch in joined if ord(ch) < 128 and not ch.isalnum() and ch not in " \t\n"
    )
    chars = len("".join(joined.split()))

    print("")
    print("==== 自检 ====")
    print("输出文件：%s" % path)
    print("正文字数：%d" % chars)
    print("段落数：%d　表格数：%d" % (len(doc.paragraphs), len(doc.tables)))
    if bad:
        print("半角符号：不合格，共 %d 处" % sum(bad.values()))
        for ch, n in bad.most_common():
            print("    0x%02X %r 出现 %d 次" % (ord(ch), ch, n))
        print("处理办法：回到内容稿改字符后重新生成，不要在 Word 里手工替换。")
    else:
        print("半角符号：合格，全文仅用中文标点。")
    keywords = ["上一篇", "如上文", "承前", "前一份", "上一篇提到"]
    hits = [k for k in keywords if k in joined]
    if hits:
        print("跨篇引用：发现 %s，按规范应删除，每篇独立成稿。" % "、".join(hits))
    return 0 if not bad else 1


def main():
    if len(sys.argv) < 3:
        print("用法：python build_dossier.py 内容稿.json 输出文件.docx")
        return 2
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    build(spec, out_path)
    return check(out_path)


if __name__ == "__main__":
    sys.exit(main())
