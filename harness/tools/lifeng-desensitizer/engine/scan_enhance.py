# -*- coding: utf-8 -*-
"""扫描件 / 照片 文字强化 —— 只处理像素，不读内容。

【这个模块解决什么】
扫描件、手机拍的照片，OCR 经常漏字，主因有五类，逐个对症：

  1. 分辨率不足 —— 手机拍整页 A4，「讯问人」三个字只有 20 像素高，
     Vision 认不清。→ 超分放大（LANCZOS 2~3 倍）
  2. 光线不均 —— 手机拍纸，中间亮四角暗，暗处笔画糊成一团。
     → 背景估计 + 除法归一化（把纸面拍平成均匀白底）
  3. 纸面发黄发灰 —— 旧卷宗、复印件叠加，前景背景对比度低。
     → 自适应二值化（局部阈值，不是全图一刀切）
  4. 轻微倾斜 —— 扫描仪放歪 1~3 度，整行字高度不一致，Vision 按行切分就错。
     → 投影法测倾角 + 反向旋转
  5. 噪点 / 印章压字 / 复印拖影 —— 笔画周围散点被当成笔画。
     → 中值滤波 + 形态学开运算

【安全边界】
本模块**只改像素**，不提取、不打印、不落盘任何文本内容。
它产出的是「更清楚的图片」，交给 OCR 去读；我看不到内容。
"""
import os
import sys


def _np():
    import numpy as np
    return np


# PIL 的各个子模块统一在模块级导入一次，避免每个函数都解包、
# 解包时漏项（曾出现 ImageOps 未定义）。
from PIL import Image, ImageFilter, ImageOps, ImageEnhance  # noqa: E402


def _pil():
    """保留旧接口，兼容早期调用方式。"""
    return Image, ImageFilter, ImageOps, ImageEnhance


# ============================================================
# 一、单个处理步骤
# ============================================================
def to_gray(img):
    """转灰度。彩扫件转灰度后 OCR 更稳（去掉了彩色噪点的干扰）。"""
    Image, *_ = _pil()
    if img.mode == "L":
        return img
    return ImageOps.grayscale(img)


def estimate_skew(img, max_angle=5.0, step=0.25):
    """投影法估计倾斜角。

    原理：文字行是水平的，把图像按角度旋转后做水平投影，
    行与行之间会出现明显的「空白谷」；倾斜时谷被抹平。
    谷最深的那个角度就是需要回正的角度。
    只处理 ±max_angle，避免把竖排文书转歪。
    """
    np = _np()
    Image, *_ = _pil()
    g = to_gray(img)
    # 缩到小图估角，快且够准
    w, h = g.size
    scale = min(1.0, 800.0 / max(w, 1))
    small = g.resize((max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1 else g
    arr0 = np.asarray(small, dtype=np.float32)
    # 反相：文字变亮，背景变暗，投影峰值对应文字行
    arr0 = 255.0 - arr0

    best_angle, best_score = 0.0, -1.0
    a = -max_angle
    while a <= max_angle + 1e-6:
        rotated = small.rotate(a, resample=Image.BILINEAR, fillcolor=255)
        arr = 255.0 - np.asarray(rotated, dtype=np.float32)
        proj = arr.mean(axis=1)                 # 每行的平均亮度
        # 行间差异越大，说明行分得越清
        score = float(np.var(np.diff(proj)))
        if score > best_score:
            best_score, best_angle = score, a
        a += step
    return best_angle


def deskew(img, max_angle=5.0):
    """自动纠偏。返回 (新图, 实际旋转角度)。角度过小则原样返回。"""
    try:
        ang = estimate_skew(img, max_angle)
    except Exception:
        return img, 0.0
    if abs(ang) < 0.3:          # 半度以内不值得转，转了反而引入插值模糊
        return img, 0.0
    Image, *_ = _pil()
    return img.rotate(ang, resample=Image.BICUBIC, fillcolor=255,
                      expand=False), ang


def upscale(img, min_height=2000, max_scale=3.0):
    """分辨率不足就放大。OCR 对字高很敏感，通常 30px 以上才稳。

    min_height：希望整图至少这么高（A4@200dpi 约 2339）。
    max_scale：放大上限，避免超大图拖慢 OCR。
    """
    Image, *_ = _pil()
    w, h = img.size
    if h >= min_height:
        return img, 1.0
    scale = min(max_scale, min_height / float(h))
    if scale <= 1.02:
        return img, 1.0
    nw, nh = int(w * scale), int(h * scale)
    return img.resize((nw, nh), Image.LANCZOS), scale


def flatten_illumination(img, blur_radius=61):
    """消除光照不均（手机拍照的中间亮四角暗）。

    做法：大半径高斯模糊得到「背景亮度图」，原图除以背景 → 纸面被拍平。
    这一步对手机拍照的 OCR 提升最明显，比简单提高对比度有效得多。
    """
    np = _np()
    Image, ImageFilter, *_ = _pil()
    g = to_gray(img)
    bg = g.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    a = np.asarray(g, dtype=np.float32)
    b = np.asarray(bg, dtype=np.float32)
    b[b < 1e-3] = 1.0
    out = a / b
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="L")


def binarize_adaptive(img, block=31, c=12):
    """自适应二值化（局部均值阈值）。

    为什么不用全图一刀切：卷宗常一半清楚一半淡（复印叠印、装订阴影），
    全局阈值会把淡的那一半整片吃掉。局部阈值按邻域算，淡处也能留住笔画。
    没有 cv2，用积分图实现，速度够。
    """
    np = _np()
    Image, *_ = _pil()
    g = to_gray(img)
    a = np.asarray(g, dtype=np.float32)
    h, w = a.shape
    r = max(3, block // 2)

    # 积分图
    ii = np.zeros((h + 1, w + 1), dtype=np.float64)
    ii[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)

    ys = np.arange(h)
    xs = np.arange(w)
    y0 = np.clip(ys - r, 0, h)[:, None]
    y1 = np.clip(ys + r + 1, 0, h)[:, None]
    x0 = np.clip(xs - r, 0, w)[None, :]
    x1 = np.clip(xs + r + 1, 0, w)[None, :]
    s = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
    cnt = (y1 - y0) * (x1 - x0)
    mean = s / np.maximum(cnt, 1)

    binary = (a > mean - c).astype(np.uint8) * 255
    return Image.fromarray(binary, mode="L")


def denoise(img, median_size=3):
    """中值滤波去散点噪点 / 复印拖影。比高斯模糊更能保笔画边缘。"""
    Image, ImageFilter, *_ = _pil()
    if median_size < 3:
        return img
    return img.filter(ImageFilter.MedianFilter(size=median_size))


def open_morph(img, radius=1):
    """形态学开运算：去掉孤立小点（印章残点、纸屑），保留连通的笔画。"""
    np = _np()
    Image, *_ = _pil()
    a = np.asarray(img.convert("L"))
    # 用 PIL 的 MinFilter/MaxFilter 近似实现腐蚀→膨胀
    from PIL import ImageFilter
    im = Image.fromarray(a, mode="L")
    k = radius * 2 + 1
    eroded = im.filter(ImageFilter.MinFilter(size=k))
    dilated = eroded.filter(ImageFilter.MaxFilter(size=k))
    return dilated


def boost_contrast(img, factor=1.8):
    """最后微调对比度，让笔画更「实」。"""
    Image, ImageFilter, ImageOps, ImageEnhance = _pil()
    return ImageEnhance.Contrast(img).enhance(factor)


# ============================================================
# 二、预设策略组合
# ============================================================
# 不同来源用不同组合，避免「一套参数打天下」把好图也弄坏。
PROFILES = {
    # 扫描仪扫的（通常已经二值化、很干净），只需纠偏 + 适度放大
    "scan": {"deskew": True, "upscale": True, "flatten": False,
             "binarize": False, "denoise": False, "morph": False,
             "contrast": 1.2, "min_height": 2000},
    # 手机拍的（光照不均、有倾斜、有噪点）
    "photo": {"deskew": True, "upscale": True, "flatten": True,
              "binarize": False, "denoise": True, "morph": False,
              "contrast": 1.5, "min_height": 2400},
    # 旧卷宗 / 复印件（发黄、对比度低、噪点多）
    "copy": {"deskew": True, "upscale": True, "flatten": True,
             "binarize": True, "denoise": True, "morph": True,
             "contrast": 1.0, "min_height": 2400},
    # 传真件 / 极差质量（笔画断裂、噪点严重）
    "fax": {"deskew": True, "upscale": True, "flatten": True,
            "binarize": True, "denoise": True, "morph": True,
            "contrast": 1.2, "min_height": 2800},
    # 只做最轻的处理，用于「原图已经很干净、只是被判不清」的情形
    "lite": {"deskew": True, "upscale": True, "flatten": False,
             "binarize": False, "denoise": False, "morph": False,
             "contrast": 1.0, "min_height": 1800},
}


def guess_profile(img):
    """自动猜图像来源类型，选对应策略。"""
    np = _np()
    Image, *_ = _pil()
    g = to_gray(img)
    a = np.asarray(g, dtype=np.float32)
    h, w = a.shape
    # 1) 已经接近二值（只有很亮/很暗两种像素）→ 扫描仪产物
    hist = np.histogram(a, bins=32, range=(0, 256))[0].astype(np.float64)
    hist /= max(hist.sum(), 1)
    bimodal = float(np.max(hist))
    # 2) 四角与中心亮度差 → 手机拍照（光照不均）
    ch = max(1, h // 8)
    cw = max(1, w // 8)
    center = a[h//2-ch:h//2+ch, w//2-cw:w//2+cw].mean()
    corners = np.mean([
        a[:ch, :cw].mean(), a[:ch, -cw:].mean(),
        a[-ch:, :cw].mean(), a[-ch:, -cw:].mean()])
    uneven = abs(float(center) - float(corners))
    # 3) 分辨率
    small = h < 1500

    if bimodal > 0.55 and uneven < 25:
        return "scan"
    if uneven > 35:
        return "photo"
    if small:
        return "photo"
    return "copy"


def enhance(img, profile="auto", geometric_safe=False):
    """按策略强化图像。返回 (新图, 实际使用的策略, 执行日志)。

    geometric_safe=True 时**不做会改变几何位置的处理**（纠偏旋转、裁剪）。
    为什么需要它：OCR 返回的是归一化坐标，涂黑要按坐标画框。
    一旦图像被旋转过，坐标就对不上原图，框会画歪。
    所以：
      · 需要坐标的场合（涂黑）→ geometric_safe=True，只做光照/去噪/对比度/放大
      · 只要文字的场合（词表识敏、补漏扫描）→ False，可以用完整强化含纠偏
    """
    Image, *_ = _pil()
    if profile == "auto":
        profile = guess_profile(img)
    cfg = dict(PROFILES.get(profile) or PROFILES["copy"])
    log = ["策略=%s%s" % (profile, "（几何安全）" if geometric_safe else "")]

    out = img
    if cfg.get("deskew") and not geometric_safe:
        out, ang = deskew(out)
        if ang:
            log.append("纠偏 %.2f°" % ang)
    if cfg.get("upscale"):
        out, sc = upscale(out, min_height=cfg.get("min_height", 2000))
        if sc > 1.02:
            log.append("放大 %.2fx" % sc)
    if cfg.get("flatten"):
        try:
            out = flatten_illumination(out)
            log.append("光照归一")
        except Exception as e:
            log.append("光照归一失败(%s)" % e)
    if cfg.get("denoise"):
        out = denoise(out, 3)
        log.append("去噪")
    if cfg.get("binarize"):
        try:
            out = binarize_adaptive(out)
            log.append("自适应二值化")
        except Exception as e:
            log.append("二值化失败(%s)" % e)
    if cfg.get("morph"):
        try:
            out = open_morph(out, 1)
            log.append("去孤立点")
        except Exception as e:
            log.append("形态学失败(%s)" % e)
    if cfg.get("contrast", 1.0) != 1.0:
        out = boost_contrast(out, cfg["contrast"])
        log.append("对比度 %.1f" % cfg["contrast"])
    return out, profile, log


def enhance_file(src, dst, profile="auto"):
    """对文件做强化（支持图片与 PDF）。PDF 逐页处理另存为图片目录。

    返回 {"dst":..., "profile":..., "log": [...], "pages": n}
    """
    from PIL import Image
    ext = os.path.splitext(src)[1].lower()
    if ext == ".pdf":
        import pymupdf
        doc = pymupdf.open(src)
        outdir = dst
        os.makedirs(outdir, exist_ok=True)
        logs, pages = [], 0
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=250)      # 250dpi 起步，比 150 清楚得多
            tmp = os.path.join(outdir, "_p%03d.png" % i)
            pix.save(tmp)
            with Image.open(tmp) as im:
                out, prof, lg = enhance(im.convert("RGB"), profile)
                final = os.path.join(outdir, "p%03d.png" % i)
                out.save(final)
            try:
                os.remove(tmp)
            except Exception:
                pass
            logs.append("第%d页 %s" % (i, "，".join(lg)))
            pages += 1
        doc.close()
        return {"dst": outdir, "profile": profile, "log": logs, "pages": pages}

    with Image.open(src) as im:
        out, prof, lg = enhance(im.convert("RGB"), profile)
        out.save(dst)
    return {"dst": dst, "profile": prof, "log": lg, "pages": 1}




# ============================================================================
# 三、强化效果优选 —— 用 OCR 置信度判断，不读内容
# ============================================================================
# 为什么需要这一步：实测「盲目强化可能让结果更差」（综合劣化件 10/11 → 9/11）。
# macOS Vision 本身对原图已经相当鲁棒，有些处理反而引入干扰。
#
# 正确做法：跑几个候选方案，**用 OCR 自己的置信度挑最好的那个**。
# 置信度是模型给的数值（0~1），不是文本内容，所以这一步完全不涉及读内容。
#
# 评分公式（越大越好）：
#   score = 平均置信度 × 0.6  +  低置信行占比的反向分 × 0.25  +  识别行数充足度 × 0.15
# 只看数值，不看字。

def _ocr_stats(image_path, ocr_bin=None):
    """跑一次 OCR，返回 (行数, 字符数, 平均置信度, 低置信占比)。**不返回文本。**"""
    import subprocess, json as _json
    bin_path = ocr_bin or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "ocr_vision")
    try:
        r = subprocess.run([bin_path, image_path], capture_output=True,
                           text=True, timeout=300)
        if r.returncode != 0:
            return 0, 0, 0.0, 1.0
        arr = _json.loads(r.stdout)
    except Exception:
        return 0, 0, 0.0, 1.0
    if not arr:
        return 0, 0, 0.0, 1.0
    n = len(arr)
    chars = sum(len(x.get("text", "")) for x in arr)
    confs = [float(x.get("conf", 0.0)) for x in arr]
    avg = sum(confs) / max(n, 1)
    low = sum(1 for c in confs if c < 0.5) / max(n, 1)
    return n, chars, avg, low


def _score(stats):
    """把统计量折算成 0~1 分。"""
    n, chars, avg, low = stats
    # 行数充足度：太少说明大量内容没识别出来
    enough = min(1.0, n / 12.0)
    return avg * 0.60 + (1.0 - low) * 0.25 + enough * 0.15


def enhance_best(src, dst, candidates=None, ocr_bin=None, keep_report=None):
    """多策略试跑，选出 OCR 效果最好的方案。

    candidates：要试的策略列表，默认 ["auto","scan","photo","copy","lite"]。
    返回 {dst, profile, log, pages, baseline, best, report}
      report 里只有分数与统计量，**没有任何文本**。
    """
    from PIL import Image
    import tempfile, shutil

    if candidates is None:
        candidates = ["auto", "lite", "scan", "photo", "copy"]

    ext = os.path.splitext(src)[1].lower()
    is_pdf = ext == ".pdf"

    # PDF 只取第 1 页做策略评测（省时间），选定策略后再整份处理
    if is_pdf:
        import pymupdf
        doc = pymupdf.open(src)
        pix = doc[0].get_pixmap(dpi=250)
        probe = os.path.join(tempfile.mkdtemp(), "probe.png")
        pix.save(probe)
        doc.close()
        base_stats = _ocr_stats(probe, ocr_bin)
    else:
        probe = src
        base_stats = _ocr_stats(src, ocr_bin)

    base_score = _score(base_stats)
    report = [{"profile": "原图(不处理)", "score": round(base_score, 4),
               "stats": base_stats}]
    best_prof, best_score = None, base_score

    for prof in candidates:
        try:
            tmpdir = tempfile.mkdtemp()
            if is_pdf:
                outdir = os.path.join(tmpdir, "pages")
                res = enhance_file(probe, outdir, prof)
                first = os.path.join(outdir, "p001.png")
                test_img = first
            else:
                test_img = os.path.join(tmpdir, "t.png")
                with Image.open(src) as im:
                    out, got_prof, lg = enhance(im.convert("RGB"), prof)
                    out.save(test_img)
            if not os.path.exists(test_img):
                continue
            st = _ocr_stats(test_img, ocr_bin)
            sc = _score(st)
            report.append({"profile": prof, "score": round(sc, 4), "stats": st})
            if sc > best_score:
                best_prof, best_score = prof, sc
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception as e:
            report.append({"profile": prof, "error": str(e)[:80]})
            continue

    # 原图已经最好 → 不做处理，直接用原图（避免白折腾还降质）
    if best_prof is None:
        if is_pdf:
            import pymupdf
            doc = pymupdf.open(src)
            outdir = dst if not dst.endswith(".pdf") else dst + "_pages"
            os.makedirs(outdir, exist_ok=True)
            for i, page in enumerate(doc, 1):
                page.get_pixmap(dpi=250).save(os.path.join(outdir, "p%03d.png" % i))
            doc.close()
            result = {"dst": outdir, "profile": "原图(不处理)",
                      "log": ["原图已最优，未做像素处理"], "pages": doc.page_count}
        else:
            shutil.copy2(src, dst)
            result = {"dst": dst, "profile": "原图(不处理)",
                      "log": ["原图已最优，未做像素处理"], "pages": 1}
    else:
        result = enhance_file(src, dst, best_prof)
        result["log"] = (result["log"] if isinstance(result["log"], list)
                         else [result["log"]])

    result["baseline"] = round(base_score, 4)
    result["best"] = round(best_score, 4)
    result["report"] = report
    if keep_report:
        import json as _json
        with open(keep_report, "w", encoding="utf-8") as f:
            _json.dump(report, f, ensure_ascii=False, indent=1)
    return result


# ============================================================================
# 四、扫描质量体检 —— 先告诉用户「这份能不能救」
# ============================================================================
# 实测结论：**真正的低分辨率救不回来**。
# 一份 310×438 的图（字高约 8px），不管怎么放大、怎么换 OCR 配置，
# 识别命中都是 1/11 —— 因为像素信息在缩小时就丢了，插值只能造出模糊的假像素。
#
# 所以最有价值的不是「拼命修」，而是**先判断能不能修**：
#   · 能修（光照不均、噪点、对比度低、轻微倾斜）→ 修完识别率显著上升
#   · 不能修（原生低分辨率、严重模糊、手写潦草）→ 直接告诉用户重新扫描
# 让用户早知道，比交付一份漏字的成品强。

def assess_quality(image_path, ocr_bin=None):
    """体检扫描件质量，返回诊断结果（不含任何文字内容）。

    返回 dict:
      ok            : bool，是否适合做脱敏
      level         : "good" / "fair" / "poor"
      dpi_estimate  : 估算等效分辨率
      text_height_px: 估算中位字高（像素）
      issues        : [问题描述]
      advice        : [建议]
      ocr_lines     : OCR 识别行数
      ocr_conf      : 平均置信度
      char_count    : 识别出的非空字符数
    """
    np = _np()
    from PIL import Image
    res = {"ok": True, "level": "good", "issues": [], "advice": []}

    with Image.open(image_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        g = to_gray(im)
        a = np.asarray(g, dtype=np.float32)

        # ---- 1. 估算字高：用水平投影的峰间距近似行距，行距≈1.6倍字高 ----
        inv = 255.0 - a
        proj = inv.mean(axis=1)
        thr = proj.mean() + proj.std() * 0.5
        rows = proj > thr
        # 找连续文字行的平均高度
        runs, cur = [], 0
        for v in rows:
            if v:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        runs = [r for r in runs if r >= 2]
        line_h = float(np.median(runs)) if runs else 0.0
        char_h = line_h / 1.6 if line_h else 0.0
        res["text_height_px"] = round(char_h, 1)

        # A4 高 297mm，换算等效 DPI：char_h ≈ 字号(mm) × dpi / 25.4
        # 中文正文常见三号字(5.6mm)、小四(4.2mm)，取 5mm 估
        if char_h > 0:
            res["dpi_estimate"] = int(char_h * 25.4 / 5.0)
        else:
            res["dpi_estimate"] = 0

        # ---- 2. 对比度 ----
        contrast = float(a.std())
        # ---- 3. 光照不均 ----
        ch, cw = max(1, h // 8), max(1, w // 8)
        center = float(a[h//2-ch:h//2+ch, w//2-cw:w//2+cw].mean())
        corners = float(np.mean([a[:ch, :cw].mean(), a[:ch, -cw:].mean(),
                                 a[-ch:, :cw].mean(), a[-ch:, -cw:].mean()]))
        uneven = abs(center - corners)

    # ---- 4. OCR 实测 ----
    n, chars, avg_conf, low_ratio = _ocr_stats(image_path, ocr_bin)
    res["ocr_lines"], res["ocr_conf"], res["char_count"] = n, round(avg_conf, 3), chars

    # ---- 5. 判定 ----
    # 阈值必须按「能不能可靠识别」校准，不是按画质好不好看。
    # 实测标定（1240×1754、30px 字体的自造件，OCR 全部 11/11 命中）：
    #   清晰件  字高估算 15~18px、对比度 16~35、置信度 0.78~0.83
    #   真·低分辨率件 字高 3.8px、置信度 0.37，怎么修都只认 1/11
    # 所以：字高 <8 才判不可用；对比度 <15 才算问题（16 以上都能认）。
    if char_h and char_h < 8:
        res["issues"].append("字高仅约 %.0f 像素（正常应 ≥15）" % char_h)
        res["advice"].append("这份图分辨率不足，放大也救不回丢失的笔画。"
                            "请用 300dpi 重新扫描，或手机靠近分段拍。")
        res["level"] = "poor"
    elif char_h and char_h < 12:
        res["issues"].append("字高偏小（约 %.0f 像素）" % char_h)
        res["level"] = "fair" if res["level"] == "good" else res["level"]
        res["advice"].append("字略小，建议强化后处理并抽查。")

    if contrast < 15:
        res["issues"].append("对比度很低（%.0f）" % contrast)
        if res["level"] != "poor":
            res["advice"].append("纸面发灰/复印叠印，建议用「copy」策略强化。")
            res["level"] = "fair" if res["level"] == "good" else res["level"]

    if uneven > 90:
        res["issues"].append("光照严重不均（中心与四角差 %.0f）" % uneven)
        if res["level"] != "poor":
            res["advice"].append("手机拍摄常见，建议用「photo」策略做光照归一。")
            res["level"] = "fair" if res["level"] == "good" else res["level"]

    if n and n < 5:
        res["issues"].append("只识别出 %d 行文字" % n)
        res["level"] = "poor"
    if avg_conf and avg_conf < 0.45:
        res["issues"].append("识别置信度低（%.2f），可能有大量字认不准" % avg_conf)
        if res["level"] != "poor":
            res["level"] = "fair"
    if avg_conf and avg_conf < 0.35:
        res["level"] = "poor"

    if res["level"] == "poor":
        res["ok"] = False
        if not res["advice"]:
            res["advice"].append("这份扫描件质量不足以可靠脱敏，"
                                "脱完很可能漏掉真名。建议重新扫描后再处理。")
    elif res["level"] == "fair":
        res["advice"].append("质量一般，建议开启强化后再脱敏，并人工抽查。")
    else:
        res["advice"].append("质量良好，可直接脱敏。")
    return res


def report_quality(image_path, ocr_bin=None):
    """体检并打印人类可读报告（不含文字内容）。"""
    r = assess_quality(image_path, ocr_bin)
    mark = {"good": "✅ 良好", "fair": "⚠️  一般", "poor": "❌ 差"}[r["level"]]
    print("扫描件质量体检：%s" % mark)
    print("  估算字高：%s px   等效分辨率：约 %s dpi"
          % (r["text_height_px"], r["dpi_estimate"] or "未知"))
    print("  OCR 识别：%d 行 / %d 字符 / 平均置信度 %.3f"
          % (r["ocr_lines"], r["char_count"], r["ocr_conf"]))
    if r["issues"]:
        print("  发现问题：")
        for x in r["issues"]:
            print("    ·", x)
    print("  建议：")
    for x in r["advice"]:
        print("    ·", x)
    return r


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="扫描件/照片文字强化（只改像素，不读内容）")
    ap.add_argument("input", help="图片或 PDF")
    ap.add_argument("--out", default="", help="输出路径（PDF 输出为图片目录）")
    ap.add_argument("--profile", default="best",
                    choices=list(PROFILES) + ["auto", "best"],
                    help="best=多策略试跑选最优（默认）；auto=按图像特征猜；"
                         "其余为固定策略")
    ap.add_argument("--check", action="store_true",
                    help="只做质量体检，不生成文件")
    ap.add_argument("--report", default="", help="把评测明细写成 JSON")
    args = ap.parse_args()

    src = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.exists(src):
        print("文件不存在：", src)
        return 1
    ext = os.path.splitext(src)[1].lower()

    # ---- 只体检 ----
    if args.check:
        probe = src
        if ext == ".pdf":
            import pymupdf, tempfile
            d = pymupdf.open(src)
            probe = os.path.join(tempfile.mkdtemp(), "probe.png")
            d[0].get_pixmap(dpi=200).save(probe)
            n = d.page_count
            d.close()
            print("PDF 共 %d 页（体检取第 1 页）" % n)
        r = report_quality(probe)
        return 0 if r["ok"] else 2

    if ext == ".pdf":
        dst = args.out or (os.path.splitext(src)[0] + "_强化")
    else:
        dst = args.out or (os.path.splitext(src)[0] + "_强化.png")

    if args.profile == "best":
        res = enhance_best(src, dst, keep_report=args.report or None)
        print("强化完成：", res["dst"])
        print("采用策略：%s（基线分 %.4f → 最优 %.4f）"
              % (res["profile"], res["baseline"], res["best"]))
        print("评测明细（只含分数，无文本）：")
        for r in res["report"]:
            if "score" in r:
                st = r.get("stats", (0, 0, 0, 0))
                print("   %-14s 分 %.4f   行%3d  均信 %.3f  低信占比 %.2f"
                      % (r["profile"], r["score"], st[0], st[2], st[3]))
            else:
                print("   %-14s 失败：%s" % (r["profile"], r.get("error", "")))
    else:
        res = enhance_file(src, dst, args.profile)
        print("强化完成：", res["dst"])
        print("采用策略：", res["profile"])
        for ln in (res["log"] if isinstance(res["log"], list) else [res["log"]]):
            print("   ", ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
