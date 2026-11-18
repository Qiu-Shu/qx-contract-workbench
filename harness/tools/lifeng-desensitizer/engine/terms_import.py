#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""词条对照表读取与模板生成。

2026-11-06 用户反馈原话：
    「词条对照表里面，我导入对照表需要基础格式啊，你要支持表格的对照表读取，
      还有就是，你要给我一个一键清空的功能，我导进去以后还得自己手动一个个删」

原来的「从词表库导入」只认 txt，而且是把选中的文件**原样 copy** 成
`敏感词表.txt` —— 选了 xlsx 就等于把一堆 zip 二进制塞进文本词表，
词表当场报废，用户还看不出为什么。

这里把「读表格」独立成一个模块，职责三件事：
1. 认格式：xlsx / xlsm / csv / tsv / txt / docx 表格，逐个解析成 [(原词, 替换为)]；
2. 认列：有表头按表头认，没表头按列位置推（含「序号 | 原词 | 替换为」这种三列排法）；
3. 出模板：给用户一份能直接填的基础格式，省得他猜。

刻意不做的：不猜语义、不调模型、不改原词。读进来什么就是什么，
清洗只做「去掉包裹引号 / 压掉换行 / 掐掉首尾空白」这种无损处理。
"""

import csv
import io
import os
import re

# 表头关键词。顺序有讲究：长的放前面，避免「原」先匹配到「原词」以外的东西。
ORIG_KEYS = (
    "原词", "原文", "原名", "原内容", "原值", "原字符串",
    "敏感词", "敏感信息", "敏感内容", "待脱敏", "需脱敏",
    "真名", "真实姓名", "真实名称", "实际名称",
)
REPL_KEYS = (
    "替换为", "替换词", "替换成", "替换", "改成", "改为",
    "脱敏为", "脱敏后", "脱敏词", "脱敏",
    "占位符", "化名", "代号", "匿名",
)
IDX_KEYS = ("序号", "编号", "行号", "no.", "no", "idx", "id", "#")

MAX_ORIG = 200      # 单条原词上限，防止把整段正文当词条贴进来
MAX_ITEMS = 20000   # 兜底，别让一个几万行的表把界面撑死


def _cell_text(v):
    """单元格 → 干净字符串。Excel 里 1 读出来是 1.0，这里要还原成 1。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    if isinstance(v, int):
        return str(v)
    if hasattr(v, "strftime"):          # datetime / date
        try:
            return v.strftime("%Y-%m-%d")
        except Exception:
            return str(v)
    s = str(v)
    # 零宽字符、不换行空格：从网页或 PDF 复制过来的表经常夹带，
    # 肉眼看不见却会让「原词」永远匹配不上正文。
    s = s.replace("\u200b", "").replace("\ufeff", "").replace("\xa0", " ")
    return s.strip()


def _clean_term(s):
    """清洗单个词条值：去首尾空白、去包裹引号、多行压成一行。"""
    s = _cell_text(s)
    if not s:
        return ""
    # 中文引号、英文引号、书名号样式的包裹，成对才去，避免误删词内引号
    for a, b in (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」")):
        if len(s) > 1 and s.startswith(a) and s.endswith(b):
            s = s[1:-1].strip()
    s = re.sub(r"\s*[\r\n]+\s*", " ", s)
    return s.strip()


def _norm_key(s):
    """表头比对用：去空格、去标点、转小写。"""
    return re.sub(r"[\s:：()（）\[\]【】.。、,，]", "", (s or "")).lower()


def _match_col(header, keys):
    """在一行表头里找匹配某一类关键词的列号，找不到返回 None。"""
    norm = [_norm_key(h) for h in header]
    # 先精确相等，再包含。精确优先是为了「原词」不被「原词说明」抢走。
    for i, h in enumerate(norm):
        if h and h in keys:
            return i
    for i, h in enumerate(norm):
        if not h:
            continue
        for k in keys:
            if k in h:
                return i
    return None


def _is_header_row(row):
    """判断某一行是不是表头：至少命中一个原词类或替换类关键词。"""
    keys = set(ORIG_KEYS) | set(REPL_KEYS) | set(IDX_KEYS)
    hits = 0
    for c in row:
        n = _norm_key(c)
        if not n:
            continue
        if n in keys or any(k in n for k in keys):
            hits += 1
    return hits >= 1


def _looks_like_index_col(rows, ci):
    """判断某一列是否全是序号（1,2,3…），用来推三列表的偏移。"""
    seen = 0
    for r in rows:
        if ci >= len(r):
            continue
        t = _cell_text(r[ci])
        if not t:
            continue
        if not re.fullmatch(r"\d{1,6}", t):
            return False
        seen += 1
        if seen >= 8:      # 看前 8 个就够，不必全表
            break
    return seen >= 2


def _pick_columns(rows):
    """返回 (数据起始行, 原词列, 替换列, 说明文字)。

    rows 是 list[list[str]]，已去掉全空行。
    """
    if not rows:
        return 0, 0, None, "空表"

    # ---- 1) 有表头 ----
    head = rows[0]
    if _is_header_row(head):
        co = _match_col(head, ORIG_KEYS)
        cr = _match_col(head, REPL_KEYS)
        ci = _match_col(head, IDX_KEYS)
        if co is None and cr is not None:
            # 只有「替换为」没有「原词」：认为紧挨着它的前一列是原词
            co = max(0, cr - 1)
        if co is None:
            # 表头没认出来原词列，退回第一列
            co = 1 if (ci == 0 and len(head) > 1) else 0
        note = "按表头识别：第 %d 列 = 原词，%s" % (
            co + 1, ("第 %d 列 = 替换为" % (cr + 1)) if cr is not None else "未指定替换列（自动生成占位符）")
        return 1, co, cr, note

    # ---- 2) 没表头：三列表且首列是序号 ----
    width = max(len(r) for r in rows)
    if width >= 3 and _looks_like_index_col(rows, 0):
        return 0, 1, 2, "无表头，首列是序号 → 第 2 列 = 原词，第 3 列 = 替换为"

    # ---- 3) 没表头：一列或两列 ----
    if width >= 2:
        return 0, 0, 1, "无表头 → 第 1 列 = 原词，第 2 列 = 替换为"
    return 0, 0, None, "无表头，单列 → 整列都是原词，替换词自动生成"


def normalize_items(raw, source=""):
    """把 [(原词, 替换为, 行号)] 清洗去重成标准条目。

    去重规则：同一原词只留最后一条 —— 与手工新增时「同名覆盖」的行为一致，
    用户改表后再导一遍，不该出现两条同名词条互相打架。
    """
    order = []
    bucket = {}
    skipped = []
    for orig, repl, row in raw:
        o = _clean_term(orig)
        r = _clean_term(repl)
        if not o:
            continue
        if "=" in o:
            skipped.append({"row": row, "why": "原词里含等号（词表用等号分列）", "text": o[:60]})
            continue
        if len(o) > MAX_ORIG:
            skipped.append({"row": row, "why": "原词超过 %d 字，像是整段正文" % MAX_ORIG, "text": o[:40] + "…"})
            continue
        if r and r == o:
            skipped.append({"row": row, "why": "原词与替换词相同，改了等于没改", "text": o[:60]})
            continue
        if o not in bucket:
            order.append(o)
        bucket[o] = {"orig": o, "repl": r, "row": row, "src": source}
        if len(bucket) > MAX_ITEMS:
            skipped.append({"row": row, "why": "超过 %d 条上限，后面不再读" % MAX_ITEMS, "text": ""})
            break
    return [bucket[o] for o in order], skipped


# ============================ 各格式读取 ============================

def _read_xlsx(path):
    """读 xlsx/xlsm。多个 sheet 时选「最像对照表」的那个。

    ⚠️ 2026-11-06 踩过的坑：最初按「行数最多」挑 sheet，
    结果自己生成的模板里「填写说明」有几行说明文字、比主表还多，
    于是把说明当词条读了一堆「1. 第一列『原词』填要盖掉的原话…」。
    正确判据是「第一行像不像表头」——主表第一行是 原词/替换为，
    说明页第一行是「词条对照表 · 填写说明」，一眼可分。行数只作次要参考。
    """
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    cands = []
    try:
        for i, ws in enumerate(wb.worksheets):
            rows = []
            for row in ws.iter_rows(values_only=True):
                vals = [_cell_text(v) for v in row]
                if any(v for v in vals):
                    rows.append(vals)
            if not rows:
                continue
            cands.append((1 if _is_header_row(rows[0]) else 0, len(rows), i, rows,
                          ws.title or ("Sheet%d" % (i + 1))))
    finally:
        try:
            wb.close()
        except Exception:
            pass
    if not cands:
        return [], ""
    # 有表头的优先 → 行多的优先 → 靠前的优先
    cands.sort(key=lambda c: (-c[0], -c[1], c[2]))
    win = cands[0]
    return win[3], win[4]


def _read_docx(path):
    """读 docx 里的表格。正文段落不读 —— 对照表一定是表格形式。"""
    from docx import Document
    doc = Document(path)
    rows = []
    for tb in doc.tables:
        for row in tb.rows:
            vals = [_cell_text(c.text) for c in row.cells]
            if any(v for v in vals):
                rows.append(vals)
    return rows, "docx 表格"


def _split_lines(text):
    """把纯文本拆成二维表：自己判分隔符，不依赖 csv.Sniffer（它对中文逗号不灵）。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    # 看前 20 行里各候选分隔符的出现次数，取最稳的那个
    cands = ["\t", ",", "，", ";", "；", "|"]
    best_sep, best_score = None, 0
    for sep in cands:
        cnt = sum(1 for ln in lines[:20] if sep in ln)
        if cnt > best_score:
            best_sep, best_score = sep, cnt
    if not best_sep:
        return [[ln.strip()] for ln in lines]
    rows = []
    for ln in lines:
        if best_sep == "，" or best_sep == "；":
            vals = ln.split(best_sep)
        else:
            vals = next(csv.reader([ln], delimiter=best_sep))
        rows.append([_cell_text(v) for v in vals])
    return rows


def _read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(enc)
            return _split_lines(text), "文本（%s）" % enc
        except UnicodeDecodeError:
            continue
    return _split_lines(raw.decode("utf-8", "ignore")), "文本（有损）"


def parse_terms_file(path):
    """解析对照表文件，返回统一结构。任何异常都转成 ok=False + 人话提示。"""
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)

    # xls 是 Excel 97-2003 的二进制格式，openpyxl 读不了，
    # 硬读只会抛一句用户看不懂的 BadZipFile。直接告诉他怎么办。
    if ext == ".xls":
        return {"ok": False, "msg": "这是 Excel 97-2003 老格式（.xls），程序读不了。\n"
                                    "请用 Excel 打开 → 另存为 → 选「Excel 工作簿 (*.xlsx)」再导入。",
                "file": name}

    try:
        if ext in (".xlsx", ".xlsm"):
            rows, sheet = _read_xlsx(path)
            kind = "Excel"
        elif ext == ".docx":
            rows, sheet = _read_docx(path)
            kind = "Word 表格"
        elif ext in (".csv", ".tsv", ".txt", ".text", ""):
            rows, sheet = _read_text(path)
            kind = "CSV/文本"
        else:
            return {"ok": False,
                    "msg": "不支持的文件类型 %s。\n认这几种：.xlsx / .xlsm / .csv / .tsv / .txt / .docx" % (ext or "（无扩展名）"),
                    "file": name}
    except Exception as e:
        return {"ok": False, "msg": "读取失败：%s" % str(e)[:200], "file": name}

    if not rows:
        return {"ok": False, "msg": "这个文件里没读到任何内容（空表或全是图片）。", "file": name}

    start, co, cr, note = _pick_columns(rows)
    raw = []
    for i in range(start, len(rows)):
        r = rows[i]
        o = r[co] if co < len(r) else ""
        v = r[cr] if (cr is not None and cr < len(r)) else ""
        raw.append((o, v, i + 1))

    items, skipped = normalize_items(raw, source=name)
    if not items:
        return {"ok": False, "file": name, "kind": kind,
                "msg": "表读出来了（%d 行），但一条有效词条都没解析到。\n%s" % (len(rows), note),
                "layout": note, "skipped": skipped[:20]}

    return {
        "ok": True,
        "file": name,
        "kind": kind,
        "sheet": sheet,
        "layout": note,
        "rows": len(rows),
        "total": len(items),
        "items": items,
        "skipped": skipped,
        "sample": items[:8],
    }


# ============================ 模板生成 ============================

_TPL_HEAD = ["原词", "替换为"]
# 示例只放进「填写说明」页，主表里一条示例都不留 ——
# 用户填完直接导入，不会混进三个根本没用的示例词条。
_TPL_SAMPLE = [
    ("湖北某某建材有限公司", "建材公司"),
    ("李某某", "李某"),
    ("某某花园项目", "花园项目"),
]
_TPL_NOTE = [
    "词条对照表 · 填写说明",
    "",
    "一、怎么填",
    "1. 到左边「词条对照表」那一页填，第一列「原词」写要盖掉的原话，第二列「替换为」写替换成什么。",
    "2. 第二列留空 = 由程序自动生成占位符（如 [人名1]、[公司2]），一般不用自己起。",
    "3. 一行一条，不要合并单元格，不要在单元格里换行。",
    "4. 原词里不要出现等号（=），程序用等号分隔两列。",
    "",
    "二、格式要求",
    "5. 表头可以保留，程序会自动识别；删掉表头也能认，按列位置读。",
    "6. 支持 .xlsx / .xlsm / .csv / .tsv / .txt / .docx（Word 表格）。",
    "7. .xls 老格式不支持，请在 Excel 里另存为 .xlsx。",
    "8. 表格可以带「序号」列，放在最左边即可，程序会自动跳过。",
    "",
    "三、示例（照着这个填）",
    "原词：湖北某某建材有限公司        替换为：建材公司",
    "原词：李某某                      替换为：李某",
    "原词：某某花园项目                替换为：（留空，自动生成）",
    "",
    "四、生效方式",
    "词条优先于正则：登记过的名称一定按你写的替换，不再走自动识别。",
]


def build_template(fmt="xlsx"):
    """生成基础格式模板，返回 (bytes, 文件名, mime)。

    主表刻意**不放示例行**：示例会被当成真词条导进去，
    用户还得回头删掉那三条假公司名。示例统一放「填写说明」页。
    """
    fmt = (fmt or "xlsx").lower()
    if fmt in ("csv", "txt"):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(_TPL_HEAD)
        # 只留表头 + 若干空行，让用户直接在 Excel 里接着填
        for _ in range(30):
            w.writerow(["", ""])
        # 带 BOM，Excel 双击打开中文才不乱码
        data = ("\ufeff" + buf.getvalue()).encode("utf-8")
        return data, "词条对照表-模板.csv", "text/csv; charset=utf-8"

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "词条对照表"

    head_fill = PatternFill("solid", fgColor="D9E7F5")
    for i, h in enumerate(_TPL_HEAD, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")

    # 预留 200 行空行（Excel 里空单元格不算数据，解析时会跳过）
    for r in range(2, 202):
        ws.cell(row=r, column=1, value="")
        ws.cell(row=r, column=2, value="")

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 26
    ws.freeze_panes = "A2"

    nt = wb.create_sheet("填写说明")
    r = 1
    for line in _TPL_NOTE:
        c = nt.cell(row=r, column=1, value=line)
        if r == 1:
            c.font = Font(bold=True, size=13)
        elif line.startswith(("一、", "二、", "三、", "四、")):
            c.font = Font(bold=True)
        r += 1
    nt.column_dimensions["A"].width = 96

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue(), "词条对照表-模板.xlsx", \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def terms_to_lines(items):
    """标准条目 → 词表文件的若干行（`原词=替换为`）。"""
    out = []
    for it in items:
        o = _clean_term(it.get("orig"))
        r = _clean_term(it.get("repl"))
        if not o:
            continue
        out.append("%s=%s" % (o, r))
    return out


def parse_lines(lines):
    """反向：词表文件的行 → 标准条目，用于「合并导入」时读旧词表。"""
    out = []
    for i, t in enumerate(lines, start=1):
        s = (t or "").strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            a, b = s.split("=", 1)
            out.append({"orig": a.strip(), "repl": b.strip(), "row": i})
        else:
            out.append({"orig": s, "repl": "", "row": i})
    return out


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        r = parse_terms_file(p)
        print(json.dumps(r, ensure_ascii=False, indent=1)[:2000] if r.get("ok")
              else r.get("msg"))
