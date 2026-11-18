# -*- coding: utf-8 -*-
"""PDF 水印去除 —— 只删文字绘制指令，不动扫描图。

2026-11-11 用户要求：「能不能加个去除水印的功能，先去 pdf 文件上面的水印」

## 能做什么

针对**后压在 PDF 上的矢量文字水印**（律师执业证号、律所名、内部编号、
「仅供XX使用」这类）。典型形态是一串固定文字以 45 度角平铺整页，
灰色半透明，每页重复 6~20 次。

做法：定位 content stream 里对应的 `BT ... Tj ... ET` 文字块，整块删掉。
扫描图（`/Fm Do` 引用的整页图片）、OCR 文字层、注释、书签全部原样保留。

## 不能做什么（别让用户误会）

1. **水印已经烧进扫描图**（纸上印的、拍照/扫描时就有的）—— 文字层里根本
   没有这串字，删无可删。这种只能图像修复，本模块不做。
2. **加密 PDF**（需要打开密码）—— 直接报错，不去猜密码。
3. **表单域 / 注释型水印** —— 本版只处理页面内容流里的文字。

## 为什么按字号删，而不是按文本内容

PDF 里的中文通常是 Identity-H 编码的 CID 序列，content stream 里
只有 `<9ee68354...>` 这样的十六进制，反查文本要解 CMap，成本高且字体一换就废。
而字号在 content stream 里是明文 `23.63 Tf`，且水印字号通常与正文明显不同
（实测 24 vs 正文 31/32），按字号定位又稳又快。

代价是同字号的其他文字会被一起删。所以 scan 阶段必须把「覆盖页数」
卡死（≥30% 页数）—— 正文重复词只覆盖 2~8 页，永远进不了候选。
"""
import collections
import os
import re

try:
    import pymupdf
except Exception:                                    # pragma: no cover
    pymupdf = None


# 候选水印的最低分（五信号投票，见 scan）
SCORE_THRESHOLD = 3
# 覆盖页数硬门槛：占总页数的比例
MIN_PAGE_RATIO = 0.3


def available():
    return pymupdf is not None


def _is_gray(color):
    """颜色是否接近灰（r≈g≈b）。水印绝大多数是灰的。"""
    c = color or 0
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    return abs(r - g) <= 6 and abs(g - b) <= 6


def scan_pdf(path, threshold=SCORE_THRESHOLD):
    """扫描 PDF，返回 (候选列表, 总页数)。

    候选按 score 降序排列，前端按顺序展示，用户勾选后交给 remove_pdf。
    """
    if not pymupdf:
        raise RuntimeError("缺少 pymupdf，无法处理 PDF")
    doc = pymupdf.open(path)
    try:
        n = doc.page_count
        page_cnt = []
        body_sizes = collections.Counter()
        for pno in range(n):
            c = collections.Counter()
            for b in doc[pno].get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    for s in ln.get("spans", []):
                        t = (s.get("text") or "").strip()
                        if not t:
                            continue
                        # 字号桶化到整数：同一水印在 23.61~23.85 间抖动，
                        # 不桶化会被拆成十几个「不同水印」
                        sz = int(round(s.get("size", 0)))
                        key = (t, s.get("font"), sz, s.get("color"))
                        c[key] += 1
                        body_sizes[sz] += 1
            page_cnt.append(c)
    finally:
        doc.close()

    main_size = body_sizes.most_common(1)[0][0] if body_sizes else 0

    agg = collections.Counter()
    pages = collections.defaultdict(set)
    for pno, c in enumerate(page_cnt):
        for key, v in c.items():
            if v < 2:                   # 同页不重复 → 正文
                continue
            agg[key] += v
            pages[key].add(pno)

    out = []
    for key, total in agg.items():
        text, font, size, color = key
        npg = len(pages[key])
        per_page = total / max(1, npg)
        # ⚡ 硬条件：平铺水印覆盖整篇（实测 100%）。
        # 正文重复词（「人民币」「扫二维码付款」）只覆盖 2~8 页，被这一刀挡掉。
        # 没有这层，remove 会照着正文字号把正文删了。
        #
        # ⚡ 2026-11-11 补短文档分支：`max(3, n*0.3)` 对 1~2 页的文件是死条件
        #    （永远够不到 3 页），实测单页 PDF 扫描结果恒为 0，自动去水印直接失效。
        #    但简单放开页数会让「单页里的正文重复词」也混进来 —— 页数这条路
        #    在单页文档上根本区分不了水印和重复词。所以短文档改用**同页密度**：
        #    平铺水印一页 6~20 处，正文重复词一页 2~5 次，用 4 次/页 切开。
        if n >= 10:
            if npg < max(3, n * MIN_PAGE_RATIO):
                continue
        else:
            if npg < max(1, int(round(n * 0.7))):
                continue
            if per_page < 4:
                continue
        score = 0
        if _is_gray(color):
            score += 2
        if len(text) >= 6:
            score += 1
        if npg >= n * 0.5:
            score += 1
        if per_page >= 3:
            score += 1
        if size != main_size:
            score += 1
        if score < threshold:
            continue
        out.append({
            "text": text,
            "font": font,
            "size": size,
            "color": color,
            "hex": "#%06x" % (color or 0),
            "total": total,
            "pages": npg,
            "per_page": round(per_page, 1),
            "gray": _is_gray(color),
            "score": score,
        })
    out.sort(key=lambda x: (-x["score"], -x["total"]))
    return out, n


def _num_tf(block):
    """取 BT...ET 块里所有 Tf 的字号（float）。"""
    return [float(m.group(1)) for m in
            re.finditer(r"/[^\s/]+\s+([\d.]+)\s+Tf", block)]


def remove_pdf(src, dst, sizes, tol=1.0):
    """删掉 content stream 里字号落在 sizes 内的文字块。

    返回 (删除块数, 处理页数)。
    """
    if not pymupdf:
        raise RuntimeError("缺少 pymupdf，无法处理 PDF")
    sizes = [float(s) for s in (sizes or [])]
    if not sizes:
        raise ValueError("没有指定要删除的字号")
    doc = pymupdf.open(src)
    total_cut = 0
    touched = 0
    try:
        for pno in range(doc.page_count):
            page = doc[pno]
            page_cut = 0
            for xref in page.get_contents():
                try:
                    stream = doc.xref_stream(xref).decode("latin-1")
                except Exception:
                    continue
                pieces, i, cut = [], 0, 0
                while True:
                    j = stream.find("BT", i)
                    if j < 0:
                        pieces.append(stream[i:])
                        break
                    k = stream.find("ET", j)
                    if k < 0:
                        pieces.append(stream[i:])
                        break
                    k += 2
                    block = stream[j:k]
                    tfs = _num_tf(block)
                    if tfs and any(abs(t - s) < tol for t in tfs for s in sizes):
                        pieces.append(stream[i:j])
                        cut += 1
                    else:
                        pieces.append(stream[i:k])
                    i = k
                if cut:
                    doc.update_stream(xref, "".join(pieces).encode("latin-1"))
                    page_cut += cut
            if page_cut:
                touched += 1
            total_cut += page_cut
        # garbage=3 收掉不再被引用的对象；deflate 保持体积
        doc.save(dst, garbage=3, deflate=True)
    finally:
        doc.close()
    return total_cut, touched


def render_page(path, page_no=0, dpi=90):
    """渲染单页成 PNG 字节，给前端做前后对比。"""
    if not pymupdf:
        raise RuntimeError("缺少 pymupdf")
    doc = pymupdf.open(path)
    try:
        if page_no < 0 or page_no >= doc.page_count:
            page_no = 0
        pix = doc[page_no].get_pixmap(dpi=dpi)
        return pix.tobytes("png"), doc.page_count
    finally:
        doc.close()


def page_count(path):
    if not pymupdf:
        return 0
    try:
        d = pymupdf.open(path)
        try:
            return d.page_count
        finally:
            d.close()
    except Exception:
        return 0
