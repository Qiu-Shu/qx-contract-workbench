# -*- coding: utf-8 -*-
"""手动标记的应用层 —— 把用户在预览里划选的词，落到导出文件上。

为什么不重跑整条流水线（2026-10-30 用户决定）：
    标记只是浏览阶段的"待办"，导出时才统一应用。
    重跑整条流水线会把所有占位符重新编号（[地址] 可能变成 [地址3]），
    预览和成品就对不上了；而且每次标记都跑一遍，慢且吵。

所以做法是：在已经脱敏好的成品上，只替换用户点名的那些词。
    原文本 → 占位符，其余一个字不动；替换同时补进映射表，还原才不会漏。

边界（都在 apply_marks 里挡掉）：
    · 已经脱敏的占位符（[地址]）不参与匹配，避免把占位符内部拆坏
    · 跨 run 的词：先按 run 替换，替换不到再合并该段（保留首个 run 的格式）
"""
import csv
import os
import re

PLACEHOLDER_RX = re.compile(r"\[[^\[\]]{1,20}\]")

# 排版分隔符：文档里的字被 Word/PDF 提取塞进空格的情况太常见。
# 实测（2026-11-18）用户在预览里选「张某某」点「姓名」，
# 预览数据里那一行是 `列席人员：…、张 绪`（字间有空格），
# 精确匹配数不到 → 弹「这份预览里找不到「张某某」」，人明明就在眼前。
_GAP_RX = r"[ \t\u00a0\u3000\u200b-\u200d\ufeff]*"


def _fuzzy_rx(src):
    """把「张某某」编译成 `张[空格]*绪`。实义字不足 2 个则不做容错。"""
    core = [c for c in (src or "") if not c.isspace()]
    if len(core) < 2:
        return None
    try:
        return re.compile(_GAP_RX.join(re.escape(c) for c in core))
    except Exception:
        return None


def _count_in(text, src, rx=None):
    """数 src 在 text 里出现几次：先精确，再容错（含中间被空格断开）。"""
    if not text or not src:
        return 0
    n = text.count(src)
    if n:
        return n
    rx = rx or _fuzzy_rx(src)
    if not rx:
        return 0
    try:
        return len(rx.findall(text))
    except Exception:
        return 0


def _sub_in(text, src, repl, rx=None):
    """替换：精确优先，未命中再按容错正则。返回 (新文本, 处数)。"""
    if not text or not src:
        return text, 0
    if src in text:
        return text.replace(src, repl), text.count(src)
    rx = rx or _fuzzy_rx(src)
    if not rx:
        return text, 0
    try:
        new, k = rx.subn(repl, text)
        return new, k
    except Exception:
        return text, 0


def iter_paragraphs(doc):
    """正文段落 + 表格单元格 + 页眉页脚。"""
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
    try:
        for sec in doc.sections:
            for hf in (sec.header, sec.footer, sec.first_page_header,
                       sec.first_page_footer, sec.even_page_header, sec.even_page_footer):
                for p in hf.paragraphs:
                    yield p
    except Exception:
        pass


def strip_placeholders(text):
    """去掉 [xxx] 占位符，剩下的才是可被标记的原文。"""
    return PLACEHOLDER_RX.sub("", text or "")


def count_hits(text, needle):
    """在非占位符文本里数命中次数。"""
    if not needle:
        return 0
    return strip_placeholders(text).count(needle)


def default_repl(text, category):
    """按类别生成默认替换词，和自动脱敏的口径保持一致。"""
    cat = (category or "").strip() or "敏感项"
    if cat in ("人名", "法定代表人"):
        try:
            import chinese_names as _CN
            sur, _given = _CN.split_surname(text)
            if sur:
                return sur + "某"
        except Exception:
            pass
        return (text[0] + "某") if text else "[人名]"
    if cat in ("企业名", "主体公司", "公司企业"):
        return "[企业名]"
    if cat == "地址":
        return "[地址]"
    return "[%s]" % cat


# 纯通名：标了会把全文所有同类词一起换掉，必须挡在门外。
# gen_terms.is_legal_common 覆盖了「项目/合同/地址/单位/甲方/工程」这类，
# 但没覆盖「公司/企业/银行」——实测漏了，所以这里补一张表。
GENERIC = {
    "公司", "企业", "集团", "单位", "部门", "银行", "学校", "医院", "法院",
    "检察院", "政府", "委员会", "事务所", "中心", "工厂", "酒店", "超市",
    "合作社", "分公司", "子公司", "项目部", "工程部", "财务部", "办公室",
}


def check_mark(text, category):
    """能不能标记。返回 (ok, 原因)。"""
    t = (text or "").strip()
    if len(t) < 2:
        return False, "至少选两个字"
    if "\n" in t or "\r" in t:
        return False, "不能跨段落选择"
    if "[" in t or "]" in t:
        return False, "不要选中已脱敏的方括号内容"
    if not category:
        return False, "请先选择类别"
    if t in GENERIC:
        return False, "「%s」是通名，标了会把全文所有同类词一并替换，请选完整的名称" % t
    # 标「公司」「项目」这种通用词，会把全文同类词全部替换掉
    try:
        import gen_terms as _GT
        if _GT.is_legal_common(t):
            return False, "「%s」是通用词，标记它会把全文同类词一并替换" % t
    except Exception:
        pass
    return True, ""


def _replace_in_paragraph(p, src, repl):
    """在段落里替换。返回替换次数。

    先按 run 替换（保住加粗/字号等格式）；整段仍含 src 说明它跨了 run，
    再退化为合并整段——这种情况罕见，合并后该段格式以首个 run 为准。

    2026-11-18：三层都要容错。用户选「张某某」而原文是「张 绪」时，
    精确匹配在第一层就全灭，必须让正则兜住，否则「找不到」「替换不上去」一起出现。
    """
    rx = _fuzzy_rx(src)
    n = 0
    # 第一层：run 内精确
    for r in p.runs:
        if r.text and src in r.text:
            n += r.text.count(src)
            r.text = r.text.replace(src, repl)
    if n:
        return n
    # 第二层：run 内容错（同一个 run 里被塞了空格）
    if rx:
        for r in p.runs:
            if not r.text:
                continue
            try:
                new, k = rx.subn(repl, r.text)
            except Exception:
                continue
            if k:
                r.text = new
                n += k
        if n:
            return n

    full = p.text or ""
    if _count_in(strip_placeholders(full), src, rx) <= 0:
        return 0
    if _count_in(full, src, rx) <= 0:
        return 0
    runs = [r for r in p.runs if r.text]
    if not runs:
        return 0

    # 第三层：整段（按占位符切开，占位符原样保留）
    parts = []
    pos = 0
    for m in PLACEHOLDER_RX.finditer(full):
        seg = full[pos:m.start()]
        new, k = _sub_in(seg, src, repl, rx)
        n += k
        parts.append(new)
        parts.append(m.group(0))
        pos = m.end()
    tail = full[pos:]
    new, k = _sub_in(tail, src, repl, rx)
    n += k
    parts.append(new)
    if not n:
        return 0

    runs[0].text = "".join(parts)
    for r in runs[1:]:
        r.text = ""
    return n


def apply_marks(src_docx, out_docx, marks):
    """把标记落到文件上。返回 (ok, 总数, 明细)。"""
    try:
        from docx import Document
    except Exception as e:
        return False, 0, "缺少 python-docx：%s" % e

    doc = Document(src_docx)
    total = 0
    detail = []
    for m in marks or []:
        src = (m.get("text") or "").strip()
        repl = m.get("repl") or default_repl(src, m.get("category"))
        if not src:
            continue
        rx = _fuzzy_rx(src)
        n = 0
        for p in iter_paragraphs(doc):
            # 2026-11-18：判断也要容错，否则原文「张 绪」的段落进不来
            if _count_in(p.text or "", src, rx) > 0:
                n += _replace_in_paragraph(p, src, repl)
        if n:
            detail.append("%s → %s（%d 处）" % (src, repl, n))
            total += n
    try:
        doc.save(out_docx)
    except Exception as e:
        return False, total, "保存失败：%s" % e
    return True, total, "；".join(detail)


def merge_mapping(map_csv, marks):
    """把标记补进映射表。还原时要靠它把占位符换回真名。"""
    if not map_csv or not os.path.exists(map_csv):
        return 0
    try:
        with open(map_csv, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except Exception:
        return 0
    if not rows:
        rows = [["原值", "占位符", "类别"]]
    head = rows[0]
    try:
        i_orig, i_ph, i_cat = head.index("原值"), head.index("占位符"), head.index("类别")
    except ValueError:
        head = ["原值", "占位符", "类别"]
        i_orig, i_ph, i_cat = 0, 1, 2
        rows = [head] + rows

    seen = {(r[i_orig].strip(), r[i_ph].strip()) for r in rows[1:] if len(r) > i_cat}
    added = 0
    for m in marks or []:
        src = (m.get("text") or "").strip()
        repl = m.get("repl") or default_repl(src, m.get("category"))
        if not src or (src, repl) in seen:
            continue
        rows.append([src, repl, m.get("category") or "手动标记"])
        seen.add((src, repl))
        added += 1
    if not added:
        return 0
    try:
        with open(map_csv, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)
    except Exception:
        return 0
    return added
