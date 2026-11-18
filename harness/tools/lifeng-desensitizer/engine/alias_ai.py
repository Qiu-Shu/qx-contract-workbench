#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按案件批量生成化名 —— 本地千问给占位符起名。

为什么需要它（2026-11-02 用户提出）：
    规则脱敏只能给出「张某甲／商贸公司（另一）」这种机械别名，读起来像编号。
    律师真正想要的是一份"像人写的"脱敏稿：同一案件里谁是谁一眼能分清，
    且**绝不重名**——重名就意味着还原时张冠李戴，这比难读严重得多。

设计上的三条硬约束：
    1. 只把「占位符 + 类别」发给模型，**不把原值发出去**。
       模型看到真名，很可能把它写进假名里（"张建国" → "张建国某"），
       等于脱敏白做。宁可让模型只按类别起名。
    2. 模型输出必须过校验：键齐全、值唯一、不与其他占位符相同、长度合理。
       任一不满足就整批回退原占位符——宁可难读，不可出错。
    3. 只替换正文里的占位符字符串，不重新跑识别。
       占位符本身是唯一的，全文替换不会误伤，也不会改变文档结构。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from llm_scan import http_json, DEFAULT_HOST, DEFAULT_MODEL  # noqa: E402

SYSTEM = (
    "你在为一份脱敏法律文书起化名。用户会给你一串占位符和它们的类别，"
    "你要为每个占位符起一个中文假名，让读者能分清不同主体。\n"
    "硬性要求：\n"
    "1. 不同占位符的假名**绝不能重复**，也不能和任何一个占位符相同；\n"
    "2. 人名：保留姓氏 + 「某」，同姓多人用「某甲／某乙／某丙」区分；"
    "单个姓氏不要加「一/二/三」这类数字后缀；\n"
    "3. 公司：行业/经营类别 + 公司，例如「建材公司」「物流公司」；\n"
    "   同一行业多家时用「甲公司／乙公司」或加序号，必须彼此不同；\n"
    "4. 机关：层级 + 机关类型，例如「县公安局」「市检察院」；\n"
    "5. 地址保持「[地址]」这类方括号写法，可加序号区分；\n"
    "6. 其他类别保持原样或做最小可读化，不要臆造内容；\n"
    "7. 只输出 JSON 对象，键是原占位符，值是假名，不要解释、不要代码块。\n"
)

BANNED = re.compile(r"[\[\]{}<>\n\r\t]")

# 假名形状必须可控：人名只能是「姓+某(+甲乙丙)」，公司/机构只能是「…公司/局/院」。
# 为什么不放开：实测本地模型会把「李某」改成「李四」——一个看着像真名的东西。
# 万一卷宗里真有个李四，脱敏稿就把无辜的人写进去了，比不脱更糟。
NAME_OK = re.compile(r"^[\u4e00-\u9fa5]某[甲乙丙丁戊己庚辛壬癸]?$")
ORG_OK = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9]{0,12}"
                    r"(公司|集团|厂|店|所|中心|合作社|事务所|商行|门市部)"
                    r"([甲乙丙丁戊己庚辛壬癸]{1,2}|[0-9]{1,2}|（另一）)?$")


NUM2MARK = {"一": "甲", "二": "乙", "三": "丙", "四": "丁", "五": "戊",
            "1": "甲", "2": "乙", "3": "丙", "4": "丁", "5": "戊"}


def _normalize(cat, v, old):
    """把模型给的假名收敛成合规形状；收敛不了就返回空串（保持原名）。

    模型很爱把「张某乙」写成「张某二」——意思没错，写法不合律所习惯。
    与其整批作废，不如把它规整回来；规整不了的才放弃。
    """
    v = (v or "").strip()
    if not v:
        return ""
    if cat in ("人名", "法定代表人"):
        sur = old[0] if old else ""
        m = re.match(r"^[\u4e00-\u9fa5]某([一二三四五六七八九十0-9甲乙丙丁戊己庚辛壬癸])?$", v)
        if not m:
            return ""
        suf = m.group(1) or ""
        suf = NUM2MARK.get(suf, suf)
        return (old[0] if old else v[0]) + "某" + suf
    if cat in ("公司企业", "主体公司"):
        # 允许换行业词，但必须仍是「…公司/局/院」这种组织名，且可选带甲乙丙标记。
        # 行业判断交给模型结合「脱敏后正文」来定——正文里没有真名，
        # 但能看出这家是供货方还是运输方（2026-11-02 定）。
        return v if ORG_OK.match(v) else ""
    if cat in ("机构", "机关"):
        if not re.match(r"^[\u4e00-\u9fa5]{2,14}(局|委员会|中心|院|所|队|办公室)$", v):
            return ""
        return v
    return ""


def load_mapping(csv_path):
    """读映射表 → (表头, [(原值, 占位符, 类别)])"""
    import csv
    rows = []
    if not os.path.exists(csv_path):
        return [], rows
    with open(csv_path, encoding="utf-8-sig") as f:
        rd = list(csv.reader(f))
    if not rd:
        return [], rows
    head = [c.strip() for c in rd[0]]
    try:
        i_o = head.index("原值")
        i_p = head.index("占位符")
        i_c = head.index("类别") if "类别" in head else -1
    except ValueError:
        i_o, i_p, i_c, rd = 0, 1, 2, [[]]
    for r in rd[1:]:
        if len(r) <= max(i_o, i_p):
            continue
        o, p = r[i_o].strip(), r[i_p].strip()
        c = r[i_c].strip() if 0 <= i_c < len(r) else ""
        if o and p:
            rows.append((o, p, c))
    return head, rows


def save_mapping(csv_path, head, rows):
    import csv
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(head or ["原值", "占位符", "类别"])
        for o, p, c in rows:
            w.writerow([o, p, c])


def _ask(host, model, items, timeout=180):
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
        ],
    }
    data = http_json(host.rstrip("/") + "/api/chat", payload, timeout=timeout)
    msg = (data.get("message") or {}).get("content", "")
    return msg


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        d = json.loads(text[i:j + 1])
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def rename_plan(rows, host=None, model=None, context=""):
    """让模型给人名/公司/机构类占位符起名，返回 (新映射, 说明)。

    只处理「值得改名」的类别；地址、编号类保持原样，避免模型乱编。

    2026-11-05 用户死命令：本地模型不参与脱敏，AI 化名一并停用。
    默认直接抛错；应急须使用者本人在场并设 DESENS_ALLOW_LLM=1。
    """
    if os.environ.get("DESENS_ALLOW_LLM") != "1":
        raise RuntimeError(
            "本地模型已禁止参与脱敏（含 AI 化名）。用户 2026-11-05 死命令："
            "千问只在 OCR 使用；化名请用规则表，应急须使用者本人在场并设 DESENS_ALLOW_LLM=1")
    host = host or DEFAULT_HOST
    model = model or DEFAULT_MODEL
    targets = [(p, c) for _o, p, c in rows
               if c in ("人名", "法定代表人") or
               (c in ("公司企业", "主体公司", "机构", "机关"))]
    if not targets:
        return {}, "没有需要改名的主体"
    cat_of = dict(targets)

    items = {"占位符": [{"占位符": p, "类别": c} for p, c in targets]}
    if context:
        # 只送脱敏后的正文：里面没有真名，但能看出各主体的角色与行业
        items["脱敏后正文摘录"] = context[:4000]
    raw = _ask(host, model, items)
    got = _extract_json(raw)

    # ---- 逐条收敛 + 冲突剔除；宁可少改几个，也不制造重名 ----
    if not isinstance(got, dict) or not got:
        return {}, "模型没有返回可用的 JSON，保持原样"
    olds = {p for p, _c in targets}
    cand = {}
    for p in olds:
        nv = _normalize(cat_of.get(p, ""), str(got.get(p, "") or ""), p)
        if nv and nv != p and nv not in olds and not BANNED.search(nv):
            cand[p] = nv

    # 候选之间打架：先到先得，后来的保持原名
    chosen = {}
    taken = set()
    for p, nv in cand.items():
        if nv in taken:
            continue
        taken.add(nv)
        chosen[p] = nv

    dropped = len(cand) - len(chosen)
    if not chosen:
        return {}, "模型给的化名都不可用，保持原有占位符"
    note = "采用 %d 个化名" % len(chosen)
    if dropped:
        note += "（%d 个因重名被丢弃，保留原占位符）" % dropped
    return chosen, note


def apply_plan_to_docx(docx_path, plan, out_path=None):
    """把正文里的旧占位符换成新化名。只动文字，不动格式。"""
    from docx import Document

    doc = Document(docx_path)
    pairs = sorted(plan.items(), key=lambda kv: -len(kv[0]))
    stat = {"n": 0}

    def _fix_paragraph(p):
        if not p.text:
            return
        # 区分两种情况：占位符完整落在某个 run 里（常规），还是被 Word 拆到多个 run
        spanning = []
        for old, new in pairs:
            if old in p.text and not any(old in (r.text or "") for r in p.runs):
                spanning.append((old, new))
        # ① 常规：逐 run 替换，格式零损失
        for r in p.runs:
            t = r.text
            if not t:
                continue
            nt = t
            for old, new in pairs:
                if (old, new) in spanning:
                    continue
                if old in nt:
                    stat["n"] += nt.count(old)
                    nt = nt.replace(old, new)
            if nt != t:
                r.text = nt
        # ② 跨 run：整段合并后替换（只有这种情况才动格式）
        if spanning:
            joined = "".join(r.text for r in p.runs)
            for old, new in spanning:
                stat["n"] += joined.count(old)
                joined = joined.replace(old, new)
            if p.runs:
                p.runs[0].text = joined
                for r in p.runs[1:]:
                    r.text = ""

    for p in doc.paragraphs:
        _fix_paragraph(p)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _fix_paragraph(p)
    for sec in doc.sections:
        for hf in (sec.header, sec.footer):
            for p in hf.paragraphs:
                _fix_paragraph(p)

    out = out_path or docx_path
    doc.save(out)
    return out, stat["n"]
