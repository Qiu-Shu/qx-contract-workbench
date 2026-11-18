# -*- coding: utf-8 -*-
"""
扫描件 / 照片 脱敏 —— 用 macOS Vision 做本地 OCR，把敏感文字所在区域真正涂黑。

要点：
  1. OCR 走 macOS 自带 Vision（本地、不联网、中文识别好），依赖 scripts/ocr_vision（由 ocr_vision.swift 编译）；
  2. PDF 用 PyMuPDF 做**真 redaction**：删除底层文字并把像素烧黑，
     不是画个黑方块盖住（后者底层文字仍可复制/检索，等于没脱敏）；
  3. 图片用 Pillow 直接覆写像素；
  4. 识别规则与文本版一致（复用 desensitize.py 的 REGEX_RULES + 词表）。

用法：
  python3 image_redact.py 扫描件.pdf
  python3 image_redact.py 照片.jpg --terms 敏感词表.txt --out 照片_已脱敏.jpg
  python3 image_redact.py 卷宗.pdf --dpi 300 --precise
"""
import os
import re
import sys
import json
import csv
import time
import argparse
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from desensitize import (REGEX_RULES, load_terms,  # noqa: E402
                         disabled_spans, in_disabled)

try:
    from gen_terms import COMPOUND_SURNAMES
except Exception:                      # 极端情况下退化为只用单字姓
    COMPOUND_SURNAMES = set()

OCR_BIN = os.path.join(HERE, "ocr_vision")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".heic", ".webp"}
PDF_EXT = {".pdf"}


def _nonspace_len(boxes):
    """OCR 结果的非空白字符总数——用来判断哪次识别「看得更清楚」。

    只统计长度，不看内容。强化前后各跑一次，取字符更多的那个，
    这样强化只会帮忙、不会帮倒忙（实测有些图强化后反而丢字）。
    """
    if not boxes:
        return 0
    return sum(len(re.sub(r"\s+", "", b.get("text") or "")) for b in boxes)


def _need_enhance(boxes):
    """判断这张图是否值得再强化重认一次。

    只在「识别明显偏少或置信度偏低」时才重试，正常图不折腾：
      · 识别出的非空字符少于 40 个 → 可能大量漏识别
      · 平均置信度低于 0.6        → 字糊了，看不清
    """
    if not boxes:
        return True
    n = _nonspace_len(boxes)
    if n < 40:
        return True
    confs = [float(b.get("conf", 0) or 0) for b in boxes]
    if confs and (sum(confs) / len(confs)) < 0.6:
        return True
    return False


def ocr(image_path, enhance=None):
    """调用 Vision OCR，返回 [{text,x,y,w,h,conf}]，坐标归一化且原点左下。

    enhance：可选的强化策略名（"auto"/"scan"/"photo"/"copy"/"lite"）。
    传了就先把图强化一遍再识别。**注意**：强化若含纠偏旋转，坐标将与原图不符，
    所以涂黑流程不要用这个参数（见 redact_image_file 里的几何安全强化）。
    这里只用于「单纯取文字」的场景（词表匹配、补漏扫描）。
    """
    if not os.path.exists(OCR_BIN):
        raise RuntimeError("OCR 组件缺失：%s（需先编译 ocr_vision.swift）" % OCR_BIN)
    if enhance:
        try:
            import scan_enhance
            from PIL import Image
            import tempfile
            with Image.open(image_path) as im:
                out, prof, _lg = scan_enhance.enhance(im.convert("RGB"), enhance)
            tmp = os.path.join(tempfile.mkdtemp(), "enh.png")
            out.save(tmp)
            p = subprocess.run([OCR_BIN, tmp], capture_output=True, text=True,
                               timeout=300)
            if p.returncode != 0:
                raise RuntimeError("OCR 失败：%s" % (p.stderr or "").strip()[:200])
            return json.loads(p.stdout or "[]")
        except Exception:
            pass        # 强化失败就退回原图识别，不能让主流程崩
    p = subprocess.run([OCR_BIN, image_path], capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError("OCR 失败：%s" % (p.stderr or "").strip()[:200])
    try:
        return json.loads(p.stdout or "[]")
    except Exception as e:
        raise RuntimeError("OCR 输出解析失败：%s" % e)


def is_person_alias(repl):
    """替换词是否为化名（「赵某」「欧阳某2」）——据此判断该词条是人名。"""
    return bool(repl and re.fullmatch(r"[\u4e00-\u9fa5]{1,2}某\d*", repl.strip()))


def surname_len(name):
    """姓氏占几个字：复姓 2 字，其余 1 字。"""
    if not name:
        return 0
    if len(name) >= 3 and name[:2] in COMPOUND_SURNAMES:
        return 2
    return 1


def find_sensitive(text, terms, precise=False):
    """在一条 OCR 文本里找敏感内容，返回 [(命中文本, 类别, 起, 止, 替换词)]。

    **起点终点一律换算回原始 text 的下标**。
    之前直接在去空格版（norm）上匹配并返回 norm 下标，而下游按带空格的 text
    推算字符宽度，索引错位 → 涂黑位置整体偏移，实测把相邻的姓氏一起糊掉。
    OCR 的行文本里空格很多（栏目对齐靠空格），错位量能到两三个字。
    """
    hits = []
    norm = text.replace(" ", "")
    # norm 下标 → text 下标 的映射表
    norm_to_src = [i for i, ch in enumerate(text) if ch != " "]

    def add(val, cat, s, e, repl, in_norm):
        if in_norm:
            if not norm_to_src:
                return
            s = norm_to_src[max(0, min(s, len(norm_to_src) - 1))]
            e = norm_to_src[max(0, min(e - 1, len(norm_to_src) - 1))] + 1
        hits.append((val, cat, s, e, repl))

    for orig, repl in terms:
        if not orig:
            continue
        idx = text.find(orig)
        if idx >= 0:
            add(orig, "词表", idx, idx + len(orig), repl, False)
            continue
        idx = norm.find(orig)
        if idx >= 0:
            add(orig, "词表", idx, idx + len(orig), repl, True)
    # 禁用字段保护（2026-10-30）：落在被禁用字段区段内的正则命中一律跳过，
    # 否则关掉「身份证号」后，18 位号码会被「统一社会信用代码」规则接走、
    # 在图上涂出一个标注错误的黑块。
    _dis = disabled_spans(text)
    for cat, rx in REGEX_RULES:
        for m in rx.finditer(text):
            if _dis and in_disabled(m.start(), m.end(), _dis):
                continue
            add(m.group(0), cat, m.start(), m.end(), None, False)
        if norm != text:
            for m in rx.finditer(norm):
                if _dis and in_disabled(m.start(), m.end(), _dis):
                    continue
                add(m.group(0), cat, m.start(), m.end(), None, True)
    # 人名结构识别：图片/PDF 这条路径原来只认词表 + 正则，
    # 「被告人翟勇」这种叙述句里的真名从来没人管，涂黑后名字还明晃晃在纸上。
    # 直接复用文本侧的 person_spans（角色词后 / 顿号连排 / 姓名栏）。
    try:
        import desensitize as _D
        _spans, _ = _D.person_spans(text)
        for (s, e, _nm) in _spans:
            hits.append((text[s:e], "人名", s, e, None))
        # 企业全称与街道门牌/村组也要补进来（2026-10-27 实测）。
        # 这两类是**结构识别**出来的，不走词表也不走 REGEX_RULES：
        # 原来图片/PDF 这条路径只接了 person_spans，结果「住…珞南街道民院路128号」
        # 和「颍上县青城房地产有限公司」在 PDF 成品里原样明晃晃留着——
        # 文本通道脱干净了、图片通道却漏，等于白脱。
        for _fn, _cat in ((_D._company_spans, "公司企业"), (_D._addr_spans, "地址")):
            try:
                for (s, e, _nm) in _fn(text):
                    hits.append((text[s:e], _cat, s, e, None))
            except Exception:
                pass
    except Exception:
        pass
    if not hits:
        return []
    # 合并同一类别重复命中
    seen = set()
    uniq = []
    for h in hits:
        key = (h[0], h[1], h[2])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq


def vision_box_to_rect(b, W, H):
    """Vision 归一化框（原点左下）→ 图像坐标系矩形（原点左上）。"""
    x0 = b["x"] * W
    x1 = (b["x"] + b["w"]) * W
    y0 = (1.0 - b["y"] - b["h"]) * H
    y1 = (1.0 - b["y"]) * H
    return x0, y0, x1, y1


def _char_weight(ch):
    """估算字符相对宽度：CJK/全角按 1.0，ASCII 数字字母按 0.5，空格 0.3。"""
    if ch == " ":
        return 0.3
    return 0.5 if ord(ch) < 128 else 1.0


def narrow_box(b, W, H, line, start, end, margin_chars=0.6, margin_left=None):
    """把整行框横向收窄到命中片段（--precise）。

    Vision 只给整行框，字符位置只能推算。这里**不能按等宽假设**：
    中文与数字混排时（如「当事人：张三，身份证号 4201...」），数字比汉字窄，
    等宽推算会让后面的字符整体错位，导致「涂一半、露出半个字」。
    改为按字符实际宽度加权累计定位，再留 margin_chars 的安全边距。

    margin_left：左边界单独控制。人名要保留姓氏时左边界必须收紧，
    否则 0.6 字宽的安全边距会盖住前面那个姓的右半边。
    """
    if not line:
        return vision_box_to_rect(b, W, H)
    weights = [_char_weight(c) for c in line]
    total = sum(weights)
    if total <= 0:
        return vision_box_to_rect(b, W, H)
    ml = margin_chars if margin_left is None else margin_left
    w0 = sum(weights[:max(0, start)])
    w1 = sum(weights[:max(0, min(end, len(line)))])
    r0 = max(0.0, min(1.0, w0 / total - ml / total))
    r1 = max(0.0, min(1.0, w1 / total + margin_chars / total))
    x0 = (b["x"] + b["w"] * r0) * W
    x1 = (b["x"] + b["w"] * r1) * W
    y0 = (1.0 - b["y"] - b["h"]) * H
    y1 = (1.0 - b["y"]) * H
    return max(0.0, x0), y0, min(W, x1), y1


def rects_for_line(b, W, H, hits, line, precise, keep_surname=True):
    """返回该行要涂黑的矩形列表。

    precise 时按每处命中分别定位并合并重叠。
    keep_surname=True 时，人名只涂姓氏后面的部分（「赵德福」→ 图上留「赵██」），
    与文档里的化名规则（赵某）保持一致；不保留姓氏会把整个姓名连姓一起糊掉，
    既不符合最高法化名惯例，也让笔录读不出是谁。
    """
    if not precise:
        r = vision_box_to_rect(b, W, H)
        # 2026-11-05 保护：扫描页 OCR 常把整页识别成"一行"，整行框就等于整页，
        # 直接涂会把正文全盖住（268 福昌源、269 福滋源两份浓缩橙汁合同实测整页变黑）。
        # 面积超过页面 12% 就退回按命中片段精确涂；精确涂仍过大则整框丢弃，
        # 宁可漏涂让质检/人工发现，也不能把整页毁掉。
        _area = max(0.0, (r[2] - r[0]) * (r[3] - r[1])) / float(max(1, W * H))
        if _area <= 0.12:
            return [r]
        precise = True
    rects = []
    for h in hits:
        val, _c, s, e = h[0], h[1], h[2], h[3]
        repl = h[4] if len(h) > 4 else None
        # 人名：跳过姓氏不涂，只涂名字
        keep = False
        if keep_surname and is_person_alias(repl):
            skip = surname_len(val)
            if skip and (e - s) > skip:
                s = s + skip
                keep = True
        if e > s:
            # 保留姓氏时左边界收紧到 0.12 字宽，避免盖住姓；
            # 右边界放宽到 0.9，压掉名字末字的轮廓残影
            # （实测涂完「钱晓梅」的「晓梅」后，残留轮廓被 OCR 读成「卫」）。
            # 号码类（手机/身份证/银行卡/账号）另加一条：左边多留 1.2 字宽。
            # 2026-10-27 实测「联系电话13812345678」涂完还露着首位「1」——
            # 字号加权推算对数字偏窄，首位会被推出黑块外。号码没有「姓氏要保留」
            # 的问题，宁可多盖一个字，也不能露出首位数字。
            _num = any(k in (_c or "") for k in ("号", "证", "卡", "账户", "邮箱"))
            rects.append(narrow_box(b, W, H, line, s, e,
                                    margin_chars=0.9 if (keep or _num) else 0.6,
                                    margin_left=(0.12 if keep
                                                 else (0.9 if _num else None))))
    rects.sort(key=lambda r: r[0])
    merged = []
    for r in rects:
        # 只在**实际重叠**时合并。原来用 r[0] <= 前框右边界+1 的容差，
        # 会把「周志强」和「李海涛」中间隔着「、」的两个框连成一片，
        # 连带把保留的姓氏一起涂黑。
        if merged and r[0] < merged[-1][2] and r[1] < merged[-1][3] and r[3] > merged[-1][1]:
            m = merged[-1]
            merged[-1] = [min(m[0], r[0]), min(m[1], r[1]),
                          max(m[2], r[2]), max(m[3], r[3])]
        else:
            merged.append([r[0], r[1], r[2], r[3]])
    # 2026-11-05：精确涂出来的框若仍超过页面 12%，说明定位失准，整框丢弃
    _cap = 0.12 * W * H
    merged = [m for m in merged if (m[2] - m[0]) * (m[3] - m[1]) <= _cap]
    return [tuple(m) for m in merged]


def convert_if_needed(path):
    """HEIC/WebP 等 PIL/Vision 可能不认的格式，先用 sips 转 PNG。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".heic", ".webp"):
        out = os.path.join(tempfile.mkdtemp(), "conv.png")
        subprocess.run(["/usr/bin/sips", "-s", "format", "png", path, "--out", out],
                       capture_output=True)
        if os.path.exists(out):
            return out
    return path


# ============ 遮黑块内的概括文字（Han 2026-10-27 要求）============
# 问题：整段涂黑以后，读者看不出「涂掉的是什么」——是姓名、身份证号，还是整段地址？
#      归档复核时无法判断脱敏是否到位，只能看到一片黑。
# 做法：在黑块里用**白字写类别概括**（姓名 / 身份证 / 机关 / 地址…），只写类别，
#      不写任何原文；块太窄（放不下两个字）就不写，保持版面干净。
_CAT_LABEL = {
    "人名": "姓名", "姓名": "姓名", "姓名栏": "姓名", "词表": "敏感项",
    "自定义词": "敏感项", "政法机关": "机关", "羁押场所": "场所",
    "公司名": "公司", "企业名": "公司", "机关名": "机关",
    "身份证号": "身份证", "统一社会信用代码": "信用代码", "手机号": "电话",
    "固定电话": "电话", "银行卡号": "账号", "电子邮箱": "邮箱",
    "检察文号": "文号", "公文文号": "文号", "法律文书文号": "文号",
    "刑事案号": "案号", "民事案号": "案号", "行政案号": "案号",
    "文书编号": "编号", "律师执业证号": "执业证号", "车牌号": "车牌",
    "地址": "地址", "金额": "金额", "日期": "日期", "护照号": "护照",
    "公司企业": "公司", "企业全称": "公司",
}

# 中文字体候选（macOS 自带，按优先级）
_FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)


def label_for(catstr):
    """'人名/政法机关' → '姓名、机关'（最多三个，去重）。"""
    parts = []
    for c in (catstr or "").split("/"):
        c = c.strip()
        if not c:
            continue
        lb = _CAT_LABEL.get(c, c if len(c) <= 4 else c[:4])
        if lb not in parts:
            parts.append(lb)
    return "、".join(parts[:3])


def merge_blocks(items):
    """把同一行、间隔很近的黑块并成一条，返回 [(x0,y0,x1,y1,label)]。

    items = [(rect4, label)]。不合并的话，一行里三个姓名会变成三个黑块、
    每个都塞「姓名」两个字，既挤又难看；并成一条后写一次「姓名、身份证」就够。
    """
    rows = []
    for r, lb in items:
        x0, y0, x1, y1 = r[:4]
        h = max(1.0, y1 - y0)
        for row in rows:
            rh = max(1.0, row["y1"] - row["y0"])
            if min(y1, row["y1"]) - max(y0, row["y0"]) > 0.5 * min(h, rh):
                row["blocks"].append([x0, y0, x1, y1, [lb]])
                row["x0"], row["x1"] = min(row["x0"], x0), max(row["x1"], x1)
                row["y0"], row["y1"] = min(row["y0"], y0), max(row["y1"], y1)
                break
        else:
            rows.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                         "blocks": [[x0, y0, x1, y1, [lb]]]})
    out = []
    for row in rows:
        cur = None
        for b in sorted(row["blocks"], key=lambda x: x[0]):
            if cur and b[0] - cur[2] <= 0.6 * max(1.0, cur[3] - cur[1]):
                cur[2] = max(cur[2], b[2])
                cur[1], cur[3] = min(cur[1], b[1]), max(cur[3], b[3])
                cur[4].extend(b[4])
            else:
                if cur:
                    out.append(tuple(cur[:4]) + ("、".join(dict.fromkeys(cur[4])),))
                cur = list(b)
        if cur:
            out.append(tuple(cur[:4]) + ("、".join(dict.fromkeys(cur[4])),))
    return out


def _trim_label(label, max_chars):
    """按黑块宽度截短标签，整项取舍，不切半个词。

    「姓名、信用代码、身份证」塞进 100px 的窄块只能缩成 7px 小字，
    不如只写「姓名」——读者知道遮的是姓名就够了，字号还能大一倍。
    """
    if not label or max_chars <= 0:
        return ""
    parts = [x for x in label.split("、") if x]
    out = ""
    for p in parts:
        cand = (out + "、" + p) if out else p
        if len(cand) <= max_chars:
            out = cand
        else:
            break
    return out


def _fit_fontsize(w, h, label, ratio=0.55, char_w=1.06):
    """黑块里能塞多大的字：高度六成、宽度按字数均分，取小的那个。"""
    if not label:
        return 0
    return min(h * ratio, w / (len(label) * char_w))


def draw_labels_image(draw, blocks):
    """PIL：在黑块里写白字类别。

    两条规矩：
      1. 字必须完整落在黑块内——放不下就截短标签（整项取舍），再放不下就不写；
      2. 窄块只写第一项（「姓名」），别把 11 个字缩成 7px 的小蚂蚁。
    """
    from PIL import ImageFont
    font_cache = {}

    def _font(sz):
        if sz not in font_cache:
            f = None
            for p in _FONT_CANDIDATES:
                try:
                    f = ImageFont.truetype(p, sz)
                    break
                except Exception:
                    continue
            font_cache[sz] = f
        return font_cache[sz]

    for x0, y0, x1, y1, label in blocks:
        w, h = x1 - x0, y1 - y0
        if not label or h < 9:
            continue
        max_chars = max(1, int((w - 2) / max(1.0, h * 0.62)))
        lab = _trim_label(label, max_chars)
        if not lab:
            continue
        fs = _fit_fontsize(w, h, lab, ratio=0.5, char_w=1.15)
        # 左右各留 7% 余量，别让首尾字贴着黑块边缘（OCR 框常比字略窄）
        fs = min(fs, w * 0.86 / max(1, len(lab) * 1.15))
        if fs < 6.5:
            continue
        font = _font(int(fs))
        if not font:
            continue
        try:
            tw = draw.textlength(lab, font=font)
        except Exception:
            tw = fs * len(lab)
        if tw > w - 2:
            continue
        draw.text((x0 + (w - tw) / 2, y0 + (h - fs) / 2 - fs * 0.12),
                  lab, font=font, fill=(255, 255, 255))


def draw_labels_pdf(page, blocks):
    """PyMuPDF：在黑块里写白字类别（内置中文宋体 china-s，不需要外部字体）。"""
    import pymupdf
    for x0, y0, x1, y1, label in blocks:
        w, h = x1 - x0, y1 - y0
        if not label or h < 4:
            continue
        max_chars = max(1, int((w - 1.5) / max(1.0, h * 0.62)))
        lab = _trim_label(label, max_chars)
        if not lab:
            continue
        fs = _fit_fontsize(w, h, lab, ratio=0.5, char_w=1.15)
        fs = min(fs, w * 0.86 / max(1, len(lab) * 1.15))
        if fs < 5.0:
            continue
        try:
            tw = pymupdf.get_text_length(lab, fontname="china-s", fontsize=fs)
        except Exception:
            tw = fs * len(lab)
        if tw > w - 1.6:
            continue
        tx = x0 + (w - tw) / 2
        ty = y0 + (h + fs * 0.68) / 2
        try:
            page.insert_text((tx, ty), lab, fontsize=fs, fontname="china-s",
                             color=(1, 1, 1), overlay=True)
        except Exception:
            pass


def redact_image_file(inp, outp, terms, precise=False):
    from PIL import Image, ImageDraw
    src = convert_if_needed(inp)
    img = Image.open(src).convert("RGB")
    W, H = img.size
    boxes = ocr(src)
    draw = ImageDraw.Draw(img)
    records = []
    label_items = []
    for b in boxes:
        hits = find_sensitive(b["text"], terms, precise)
        if not hits:
            continue
        line = b["text"]
        lb = label_for("/".join(sorted({h[1] for h in hits})))
        for rect in rects_for_line(b, W, H, hits, line, precise):
            draw.rectangle(rect, fill=(0, 0, 0))
            label_items.append((rect, lb))
        records.append({
            "page": 1, "text": line, "category": "/".join(sorted({h[1] for h in hits})),
            "box": "整行" if not precise else " / ".join(
                "[%.1f,%.1f,%.1f,%.1f]" % r for r in rects_for_line(b, W, H, hits, line, True)),
        })
    if label_items:
        draw_labels_image(draw, merge_blocks(label_items))
    img.save(outp, quality=95)
    return records, len(boxes)


def span_rects(bbox, text, hits, keep_surname=True, chars=None):
    """算出每处命中的绝对矩形。

    chars 非空时用 PyMuPDF 的**逐字符 bbox**（rawdict 提供），这是像素级精确的——
    电子版 PDF 完全不需要估算，直接取命中字符的 bbox 并集即可。
    只在拿不到 chars 时才退回按字宽比例估算。

    bbox 是 (x0, y0, x1, y1) 绝对坐标；text 是该 span 的原文。
    """
    x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    rects = []

    def _precise_rect(s, e):
        """用逐字符 bbox 求命中片段的并集。"""
        boxes = []
        for i in range(max(0, s), min(e, len(chars))):
            cb = chars[i].get("bbox")
            if cb:
                boxes.append(cb)
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    total_w = x1 - x0
    weights = [_char_weight(c) for c in text]
    total = sum(weights)

    for h in hits:
        val, s, e = h[0], h[2], h[3]
        repl = h[4] if len(h) > 4 else None
        keep = False
        if keep_surname and is_person_alias(repl):
            skip = surname_len(val)
            if skip and (e - s) > skip:
                s = s + skip
                keep = True
        if e <= s:
            continue
        got = None
        if chars:
            got = _precise_rect(s, e)
            if got:
                # 逐字符 bbox 已经很准，只需给上下留一点余量防切边
                got = (max(x0, got[0] - 0.6), y0, min(x1, got[2] + 0.9), y1)
        if not got:
            if total <= 0 or total_w <= 0:
                got = (x0, y0, x1, y1)
            else:
                w0 = sum(weights[:max(0, s)])
                w1 = sum(weights[:max(0, min(e, len(text)))])
                ml = 0.12 if keep else 0.6
                mr = 0.9 if keep else 0.6
                rx0 = x0 + total_w * max(0.0, w0 / total - ml / total)
                rx1 = x0 + total_w * min(1.0, w1 / total + mr / total)
                got = (max(x0, rx0), y0, min(x1, rx1), y1)
        rects.append(got)
    # 只在真正重叠时合并
    rects.sort(key=lambda r: r[0])
    merged = []
    for r in rects:
        if merged and r[0] < merged[-1][2] and r[1] < merged[-1][3] and r[3] > merged[-1][1]:
            m = merged[-1]
            merged[-1] = (min(m[0], r[0]), min(m[1], r[1]),
                          max(m[2], r[2]), max(m[3], r[3]))
        else:
            merged.append(r)
    return merged


def redact_pdf_by_textlayer(doc, terms, records, precise=True):
    """有文字层的 PDF：按**逐字符坐标**精确涂黑，不用 OCR（最准最快）。

    用 rawdict 拿到每个字符的 bbox，命中片段直接取其字符 bbox 并集，
    定位精度是像素级的，不存在「字宽估算错位」的问题。
    span 整体涂黑是错的——电子版 PDF 一个 span 往往就是一整行，
    整行涂会把地址、工作单位一起糊掉。
    """
    import pymupdf
    for pno, page in enumerate(doc, start=1):
        data = page.get_text("rawdict")
        hits = 0
        label_items = []
        for block in data.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars") or []
                    if chars:
                        # rawdict 把文本拆在 chars 里，拼回来才是完整 span 文本
                        txt = "".join(c.get("c", "") for c in chars)
                    else:
                        txt = span.get("text", "")
                    if not txt.strip():
                        continue
                    got = find_sensitive(txt, terms)
                    if not got:
                        continue
                    if precise:
                        boxes = span_rects(span["bbox"], txt, got, chars=chars)
                    else:
                        boxes = [tuple(span["bbox"])]
                    applied = []
                    lb = label_for("/".join(sorted({h[1] for h in got})))
                    for bx in boxes:
                        rect = pymupdf.Rect(bx)
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                        label_items.append((tuple(rect), lb))
                        applied.append("[%.1f,%.1f,%.1f,%.1f]"
                                       % (rect.x0, rect.y0, rect.x1, rect.y1))
                    records.append({
                        "page": pno, "text": txt.strip(),
                        # find_sensitive 返回 5 元组 (命中, 类别, 起, 止, 替换词)，
                        # 这里只取类别；漏改解包会抛 too many values to unpack
                        "category": "/".join(sorted({h[1] for h in got})),
                        "box": "整行" if not precise else " / ".join(applied),
                    })
                    hits += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
        # 涂黑之后再写概括文字：先写会被 redaction 一起抹掉
        if label_items:
            draw_labels_pdf(page, merge_blocks(label_items))
    return len(records)


def redact_pdf_file(inp, outp, terms, dpi=200, precise=True):
    """有文字层的 PDF 默认走**精确涂黑**（只涂命中片段）。

    2026-10-27 实测：默认 False 时直接取 span 整个 bbox，而电子版 PDF 一个 span
    往往就是一整行，于是「被告人某某，男，1990年…住…」整行变黑——这就是用户
    反馈的「大段遮黑」。整行模式只保留给「复检发现残留」时的安全兜底。
    """
    import pymupdf
    doc = pymupdf.open(inp)
    records = []

    # 优先走文字层精确路线
    # 只探前 3 页判断有没有文字层就够了。原来拼全部页的文字，
    # 一本几百页的卷宗（实测用户 23MB 的 PDF）会白占大量内存和时间。
    try:
        _n_probe = min(3, doc.page_count)
        _probe = "".join(doc[i].get_text() for i in range(_n_probe)).strip()
    except Exception:
        _probe = ""
    # 2026-10-27：原来要求 `terms` 非空才走文字层，可是脱敏词表经常是空的
    # （全靠 REGEX_RULES 兜），结果电子版 PDF 被当成扫描件跑 OCR，
    # 定位靠估算、漏涂一半。文字层在就一律走精确路线。
    if len(_probe) > 20:
        n = redact_pdf_by_textlayer(doc, terms, records, precise)
        doc.save(outp, garbage=4, deflate=True)
        doc.close()
        return records, n

    total_ocr = 0
    total_pages = doc.page_count
    tmpdir = tempfile.mkdtemp()
    _t_start = time.time()
    for pno, page in enumerate(doc, start=1):
        # 逐页报进度。扫描件每页要渲染+OCR，一本几百页的卷宗要跑十几分钟，
        # 没有进度输出用户会以为卡死（上次就问过「是不是卡了」）。
        if pno == 1 or pno % 5 == 0 or pno == total_pages:
            _el = time.time() - _t_start
            _eta = (_el / pno) * (total_pages - pno) if pno else 0
            print("  扫描页 %d/%d ｜ 已涂 %d 处 ｜ 已用 %d 分 %02d 秒 ｜ 预计还需 %d 分 %02d 秒"
                  % (pno, total_pages, len(records), int(_el) // 60, int(_el) % 60,
                     int(_eta) // 60, int(_eta) % 60), flush=True)
        pix = page.get_pixmap(dpi=dpi)
        img_path = os.path.join(tmpdir, "p%04d.png" % pno)
        pix.save(img_path)
        W, H = pix.width, pix.height
        # 低 DPI 渲染会让小字糊掉，OCR 大量漏识别。
        # 这里在识别前做一次「几何安全」强化（不旋转不裁剪，坐标仍对应原图）：
        # 放大 + 去噪 + 局部对比度，实测能显著提高漏字识别率。
        boxes = ocr(img_path)
        if _need_enhance(boxes):
            try:
                import scan_enhance
                from PIL import Image as _Im
                with _Im.open(img_path) as _im:
                    _enh, _p, _lg = scan_enhance.enhance(
                        _im.convert("RGB"), "auto", geometric_safe=True)
                _tmp2 = os.path.join(tmpdir, "p%04d_enh.png" % pno)
                _enh.save(_tmp2)
                _boxes2 = ocr(_tmp2)
                # 只接受「识别内容更多」的结果，避免强化反而丢字
                if _nonspace_len(_boxes2) > _nonspace_len(boxes):
                    boxes = _boxes2
            except Exception:
                pass
        total_ocr += len(boxes)
        pw, ph = page.rect.width, page.rect.height
        label_items = []
        for b in boxes:
            hits = find_sensitive(b["text"], terms, precise)
            if not hits:
                continue
            line = b["text"]
            applied = []
            lb = label_for("/".join(sorted({h[1] for h in hits})))
            for (x0, y0, x1, y1) in rects_for_line(b, W, H, hits, line, precise):
                # 图像像素坐标 → PDF 点坐标
                rect = pymupdf.Rect(x0 / W * pw, y0 / H * ph, x1 / W * pw, y1 / H * ph)
                page.add_redact_annot(rect, fill=(0, 0, 0))
                label_items.append((tuple(rect), lb))
                applied.append("[%.1f,%.1f,%.1f,%.1f]" % (rect.x0, rect.y0, rect.x1, rect.y1))
            records.append({
                "page": pno, "text": line,
                "category": "/".join(sorted({h[1] for h in hits})),
                "box": "整行" if not precise else " / ".join(applied),
            })
        # 真正删除底层文字/像素，而不是盖黑框
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
        if label_items:
            draw_labels_pdf(page, merge_blocks(label_items))
    doc.save(outp, garbage=4, deflate=True)
    doc.close()
    return records, total_ocr


def redact_bytes(data, terms, precise=False):
    """对内存中的图片字节做脱敏（供 docx 内嵌图片使用）。

    返回 (新字节, 记录列表)。识别不到敏感项时原样返回。
    """
    import io
    from PIL import Image, ImageDraw

    src = Image.open(io.BytesIO(data))
    fmt = (src.format or "PNG").upper()
    W, H = src.size
    tmp = os.path.join(tempfile.mkdtemp(), "m.png")
    src.convert("RGB").save(tmp)
    boxes = ocr(tmp)
    if not boxes:
        return data, []

    img = src.convert("RGB")
    draw = ImageDraw.Draw(img)
    recs = []
    label_items = []
    for b in boxes:
        hits = find_sensitive(b["text"], terms)
        if not hits:
            continue
        lb = label_for("/".join(sorted({h[1] for h in hits})))
        for rect in rects_for_line(b, W, H, hits, b["text"], precise):
            draw.rectangle(rect, fill=(0, 0, 0))
            label_items.append((rect, lb))
        recs.append({
            "page": "-", "text": b["text"].strip(),
            "category": "/".join(sorted({h[1] for h in hits})),
            "box": "整行" if not precise else "多处",
        })
    if not recs:
        return data, []
    if label_items:
        draw_labels_image(draw, merge_blocks(label_items))

    out = io.BytesIO()
    save_fmt = "PNG" if fmt in ("PNG", "GIF", "BMP", "TIFF") else "JPEG"
    if save_fmt == "JPEG":
        img.save(out, format="JPEG", quality=95)
    else:
        img.save(out, format="PNG")
    return out.getvalue(), recs


def has_residual_image(path, terms):
    """复检图片：重新 OCR，看是否仍能识别到敏感内容。"""
    for b in ocr(convert_if_needed(path)):
        if find_sensitive(b["text"], terms):
            return True
    return False


def has_residual_pdf(path, terms, dpi=200):
    """复检 PDF：逐页渲染后重新 OCR，看是否仍能识别到敏感内容。"""
    import pymupdf
    doc = pymupdf.open(path)
    tmp = tempfile.mkdtemp()
    try:
        for pno, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            ip = os.path.join(tmp, "v%04d.png" % pno)
            pix.save(ip)
            for b in ocr(ip):
                if find_sensitive(b["text"], terms):
                    return True
        return False
    finally:
        doc.close()


def expand_fragments(terms):
    """给长地址/机构条目补「门牌级片段」，专治跨行断句漏脱。

    实测：词表里有「湖北省武汉市洪山区珞南街道民院路128号3栋502室」，
    但笔录里这条地址被 OCR 切成两行，第二行只剩「民院路128号3栋502室」，
    整条匹配不上 → 门牌号原样留在图上。
    这里从长条目里拆出「XX路128号」「3栋502室」这类片段追加进规则。
    """
    extra = []
    rx = re.compile(r"[\u4e00-\u9fa5]{2,6}(?:路|街|道|巷|胡同|里弄)"
                    r"[\d〇零一二三四五六七八九十百千]{1,5}号"
                    r"(?:[\d]{1,3}栋)?(?:[\d]{1,4}室)?"
                    r"|[\d]{1,3}栋[\d]{1,4}室"
                    r"|[\d〇零一二三四五六七八九十]{1,5}(?:组|队|号楼|单元)")
    for orig, repl in terms:
        if not orig or len(orig) < 8:
            continue
        base = repl or ""
        for m in rx.finditer(orig):
            frag = m.group(0)
            if len(frag) >= 4 and frag != orig:
                extra.append((frag, base or "[地名]"))
    return extra


def main():
    ap = argparse.ArgumentParser(description="扫描件/照片 敏感文字涂黑（本地 OCR）")
    ap.add_argument("input")
    ap.add_argument("--terms", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--map", default="")
    ap.add_argument("--dpi", type=int, default=200, help="PDF 渲染分辨率，300 更准但更慢")
    ap.add_argument("--precise", dest="precise", action="store_true", default=True,
                    help="只涂命中的片段（默认开启）。整行涂黑会把地址、工作单位等"
                         "非敏感内容一起糊掉，实测一份 33 行的笔录只剩 10 行。")
    ap.add_argument("--whole-line", dest="precise", action="store_false",
                    help="整行涂黑（最保险，但文书可读性差，仅在精确模式复检不过时用）")
    args = ap.parse_args()

    inp = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.exists(inp):
        print("文件不存在：", inp)
        return 1
    ext = os.path.splitext(inp)[1].lower()
    if ext not in IMAGE_EXT | PDF_EXT:
        print("仅支持 PDF 与图片：", ext)
        return 1
    if not os.path.exists(OCR_BIN):
        print("OCR 组件缺失，请先编译：swiftc -O ocr_vision.swift -o ocr_vision")
        return 1

    terms = load_terms(args.terms) if args.terms else []
    if terms:
        frag = expand_fragments(terms)
        if frag:
            terms = terms + frag
            terms.sort(key=lambda x: -len(x[0]))
    stem, _ = os.path.splitext(inp)
    outp = args.out or (stem + "_已脱敏" + ext)
    mapf = args.map or (os.path.splitext(outp)[0] + "_涂黑记录.csv")

    try:
        if ext in PDF_EXT:
            records, ocr_count = redact_pdf_file(inp, outp, terms, args.dpi, args.precise)
        else:
            records, ocr_count = redact_image_file(inp, outp, terms, args.precise)
    except Exception as e:
        print("处理失败：", e)
        return 1

    # 复检闸门：精细模式可能因字符定位误差残留半个字，若复检仍能识别出敏感内容，
    # 自动退回「整行涂黑」重做一遍（安全优先，宁可多涂不可漏涂）。
    if args.precise:
        try:
            if ext in PDF_EXT:
                residual = has_residual_pdf(outp, terms, args.dpi)
            else:
                residual = has_residual_image(outp, terms)
        except Exception:
            residual = False
        if residual:
            print("⚠ 复检发现仍有敏感内容可被识别（精细模式定位不准），自动改用整行涂黑重做…")
            if ext in PDF_EXT:
                records, ocr_count = redact_pdf_file(inp, outp, terms, args.dpi, False)
            else:
                records, ocr_count = redact_image_file(inp, outp, terms, False)
            print("已改用整行模式重做，涂黑 %d 处" % len(records))
            try:
                if ext in PDF_EXT:
                    if has_residual_pdf(outp, terms, args.dpi):
                        print("⚠⚠ 整行模式复检仍有残留，请人工检查后再使用！")
                else:
                    if has_residual_image(outp, terms):
                        print("⚠⚠ 整行模式复检仍有残留，请人工检查后再使用！")
            except Exception:
                pass

    with open(mapf, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["页", "被涂黑的原文", "类别", "涂黑范围"])
        for r in records:
            w.writerow([r["page"], r["text"], r["category"], r["box"]])

    print("脱敏成品：", outp)
    print("涂黑记录（还原钥匙，单独保管）：", mapf)
    print("OCR 识别到 %d 段文字，涂黑 %d 处" % (ocr_count, len(records)))
    if args.precise:
        print("精细模式：只涂命中片段，人名保留姓氏（赵德福 → 图上只留「赵」）。")
        print("  字符位置按字宽加权推算并留了安全边距；重要卷宗交付前仍建议看图抽查一眼。")
        print("  若发现残留半个字，加 --whole-line 改用整行涂黑（最保险，但文书可读性差）。")
    if ocr_count == 0:
        print("提示：没识别到任何文字。可能是分辨率太低、图片倾斜或不是扫描件，建议提高 --dpi 或先矫正。")
    elif not records:
        print("提示：识别到文字但未命中敏感项。请确认是否提供了词表（人名、公司名只靠词表识别）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
