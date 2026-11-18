# -*- coding: utf-8 -*-
"""
脱敏工坊批处理器 —— 把「投放区」里的文件批量脱敏，成品放进「已脱敏」。

流程（全本地，不联网）：
  投放区/合同.docx
    → 已脱敏/合同_已脱敏.docx          （文件名自动标注「已脱敏」）
    → 映射表-勿外传/合同_映射表.csv     （还原钥匙，单独存放）
    → 补漏提示/合同_补漏待确认.txt      （本地千问扫出的隐性残留线索）
    → 投放区/已处理/合同.docx          （原件移到已处理，避免重复跑）

用法：
  python3 dropbox_run.py                      # 处理默认工坊 ~/Documents/脱敏工坊
  python3 dropbox_run.py --workshop /某路径
  python3 dropbox_run.py --no-scan            # 跳过本地千问补漏扫描（快）
"""
import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess

# 2026-11-10 用户指令：去掉所有脱敏检测。总开关见 ~/.workbuddy/scripts/detect_policy.py
try:
    sys.path.insert(0, os.path.expanduser("~/.workbuddy/scripts"))
    import detect_policy as _dp
except ImportError:
    _dp = None

HERE = os.path.dirname(os.path.abspath(__file__))
DESENSITIZE = os.path.join(HERE, "desensitize.py")
GATE = os.path.join(HERE, "desensitize_gate.py")
LLM_SCAN = os.path.join(HERE, "llm_scan.py")
IMAGE_REDACT = os.path.join(HERE, "image_redact.py")
GEN_TERMS = os.path.join(HERE, "gen_terms.py")
SHEET_REDACT = os.path.join(HERE, "sheet_redact.py")
OLLAMA_HOST = "http://127.0.0.1:11434"


def _imports_ok(exe, mods):
    try:
        r = subprocess.run([exe, "-c", "import " + ",".join(mods)],
                           capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def pick_python():
    """挑一个依赖齐全的解释器给所有子进程用。

    为什么必须有这个函数：本脚本所有子步骤都用同一个解释器启动，
    如果启动它的解释器是系统自带的裸 python（没有任何第三方库），
    图片/PDF/Word 全部会报 No module named 'PIL'/'docx' 而失败。
    实测用裸解释器跑扫描件，直接 No module named 'PIL'，图片根本没处理，
    用户看到的就是「人名还在」。

    优先级：环境变量 DESENSITIZE_PYTHON > 当前解释器 > 包内 runtime >
             WorkBuddy venv > 系统装过的。
    图片链路需要 PIL + pymupdf，所以两项都要验。

    2026-11-05 打包分发：加了「本脚本自己所在包里的 runtime/bin/python3」
    与「当前解释器」两个候选。分发包里启动器的 DESENSITIZE_PYTHON 就指向
    包内 python，对方机器上根本没有 ~/.workbuddy，原来那个候选会落空。
    """
    need = ["docx", "PIL", "pymupdf", "openpyxl"]
    _here = os.path.dirname(os.path.abspath(__file__))
    # 包内 runtime 可能在 engine/ 同级，也可能在 engine/ 上一级（App Resources 下）
    _bundled = [os.path.join(_here, "..", "runtime", "bin", "python3"),
                os.path.join(_here, "runtime", "bin", "python3")]
    cands = [
        os.environ.get("DESENSITIZE_PYTHON", ""),
        sys.executable,
    ] + [os.path.abspath(p) for p in _bundled] + [
        os.path.expanduser("~/.workbuddy/binaries/python/envs/default/bin/python3"),
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ]
    seen = set()
    for c in cands:
        if not c or c in seen or not os.path.exists(c):
            continue
        seen.add(c)
        if _imports_ok(c, need):
            return c
    # 齐全的没有，退一步要 Word 能力（文本类仍能处理，图片会报错但至少不静默）
    for c in cands:
        if c and os.path.exists(c) and c not in ("",) and _imports_ok(c, ["docx"]):
            print("警告：找不到同时具备 PIL/pymupdf 的解释器，图片与扫描 PDF 可能无法处理。",
                  file=sys.stderr)
            return c
    print("警告：没有可用解释器，退回当前解释器 %s" % sys.executable, file=sys.stderr)
    return sys.executable


PY_EXE = pick_python()


def _reexec_with_full_python():
    """若当前解释器依赖不齐，用合格解释器重新执行自己。

    本脚本里有大量「当前进程内」的 import（pymupdf 渲染 PDF、PIL、python-docx）。
    只把子进程换成好解释器不够——用裸 python 启动时，_ocr_blob 里的
    import pymupdf 会失败并被吞掉，返回空文本，于是「跳过自动识敏 → 没有词表
    → 人名一个都脱不出来」。实测就是这样：同一份扫描 PDF，图片版人名全脱、
    PDF 版人名全漏。

    注意：**只在直接运行时调用**，不能放在模块级——否则被 import 时会
    意外重新执行整个脚本并跑一遍批处理。
    """
    if not PY_EXE or os.path.abspath(PY_EXE) == os.path.abspath(sys.executable):
        return
    if os.environ.get("_DESENSITIZE_REEXEC") == "1":
        return
    os.environ["_DESENSITIZE_REEXEC"] = "1"
    try:
        os.execv(PY_EXE, [PY_EXE, os.path.abspath(__file__)] + sys.argv[1:])
    except Exception:
        pass        # 换轨失败就继续用当前解释器，各步会各自报错


def convert_doc_to_docx(src, workdir):
    """老版 .doc → .docx（用 macOS textutil）。返回转换后路径，失败返回空。"""
    try:
        import subprocess
        base = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(workdir, base + ".docx")
        r = subprocess.run(["/usr/bin/textutil", "-convert", "docx",
                            "-output", dst, src], capture_output=True, timeout=180)
        if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
            return dst
    except Exception:
        pass
    return ""


# 2026-11-05 用户死命令：本地千问只在 OCR 辅助识敏时使用，纯文本一律不调模型。
# 本标志记录「本次任务是否真的用过 OCR 取文」，只有它为真时才给子进程放行模型。
_USED_OCR = False


def _ocr_blob(path, max_pages=3, dpi=200):
    """对 PDF/图片做 OCR，返回识别出的文字（用于判断词表是否匹配本文件）。

    只取前几页即可判断「这是不是同一个案子」，不必全扫（省时间）。
    出错时**打印原因**，不要静默返回空串——空了会被上层当成「文件没有可读文本」
    从而跳过自动识敏，最后表现为「人名怎么没脱」，极难排查。

    强化：识别前对页面做「几何安全」强化（去噪/光照归一/放大/对比度，
    不旋转不裁剪），显著提高小字、淡字、噪点字的识别率。
    只采纳「识别字符更多」的结果，避免强化反而丢字。
    """
    global _USED_OCR
    _USED_OCR = True          # 本次任务确实走了 OCR，允许千问参与这一路的识敏
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    ext = os.path.splitext(path)[1].lower()
    texts = []
    try:
        from image_redact import ocr, _nonspace_len, _need_enhance
    except Exception as e:
        print("  [OCR 组件不可用] %s（解释器：%s）" % (e, sys.executable), file=sys.stderr)
        return ""

    def _ocr_with_enhance(img_path, tmpdir):
        """先裸识别；若识别偏少或置信度低，再用几何安全强化重认一次。"""
        try:
            base = ocr(img_path)
        except Exception as e:
            print("  [OCR 失败] %s" % e, file=sys.stderr)
            return []
        if not _need_enhance(base):
            return base
        try:
            import scan_enhance
            from PIL import Image as _Im
            with _Im.open(img_path) as _im:
                enh, _p, _lg = scan_enhance.enhance(
                    _im.convert("RGB"), "auto", geometric_safe=True)
            e2 = os.path.join(tmpdir, os.path.basename(img_path).replace(".png", "_e.png"))
            enh.save(e2)
            got = ocr(e2)
            if _nonspace_len(got) > _nonspace_len(base):
                return got
        except Exception:
            pass
        return base

    if ext == ".pdf":
        try:
            import pymupdf
        except Exception as e:
            print("  [缺 pymupdf，无法渲染 PDF] %s（解释器：%s）"
                  % (e, sys.executable), file=sys.stderr)
            return ""
        import tempfile
        try:
            doc = pymupdf.open(path)
            n = min(max_pages, doc.page_count)
            tmp = tempfile.mkdtemp()
            for i in range(n):
                pix = doc[i].get_pixmap(dpi=dpi)
                ip = os.path.join(tmp, "p%03d.png" % i)
                pix.save(ip)
                for b in _ocr_with_enhance(ip, tmp):
                    texts.append(b.get("text", ""))
            doc.close()
        except Exception as e:
            print("  [PDF 渲染失败] %s" % e, file=sys.stderr)
            return ""
    else:
        try:
            import tempfile
            for b in _ocr_with_enhance(path, tempfile.mkdtemp()):
                texts.append(b.get("text", ""))
        except Exception as e:
            print("  [图片 OCR 失败] %s" % e, file=sys.stderr)
            return ""
    return "".join(texts)


def read_text_for_terms(path):
    """读取文件内容供自动识敏使用。

    除 docx/txt/md 外，**有文字层的 PDF 也能直接抽文字**（比 OCR 准得多）；
    纯扫描件没有文字层，返回空串（这类只能靠 OCR 命中已有的敏感特征）。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import pymupdf
        except Exception:
            return ""
        try:
            doc = pymupdf.open(path)
            text = "".join(pg.get_text() for pg in doc)
            doc.close()
            # 扫描件没有文字层 → 走 OCR 取文字（否则识敏阶段拿不到任何内容）
            if len(text.strip()) < 20:
                return _ocr_blob(path, max_pages=6)
            return text
        except Exception:
            return ""
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp"):
        return _ocr_blob(path)
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from llm_scan import read_text
    return read_text(path)

# 文本类：走脱敏替换（生成占位符）
TEXT_EXT = {".docx", ".txt", ".md", ".markdown"}
# 表格类：走 sheet_redact.py（逐单元格替换，保留格式）
SHEET_EXT = {".xlsx", ".xls", ".xlsm"}
# 老版 Word：先用 textutil 转 docx 再处理
LEGACY_DOC = {".doc"}
# 图像/扫描件类：走 OCR + 涂黑（不生成占位符，直接烧黑区域）
IMAGE_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp"}
SUPPORTED = TEXT_EXT | IMAGE_EXT | SHEET_EXT | LEGACY_DOC
# 放在用户主目录而非 ~/Documents：macOS 对文稿/桌面/下载有隐私保护（TCC），
# 脚本型 App 读取会被静默拒绝，表现为「文件夹里明明有文件却说空」。
DEFAULT_WORKSHOP = os.path.expanduser("~/脱敏工坊")


def detect_file_mode(path, base):
    """判断单个文件属刑事还是民事，返回 (mode, 依据)。

    图片（png/jpg 等）没有文字可判，只靠文件名；
    判不出时回 criminal——刑事把人名全脱，多脱只是可用性差，
    反过来把刑事卷宗按民事脱（人名全留）就是事故。
    """
    try:
        from desensitize import detect_doc_type
    except Exception:
        return "criminal", "检测器不可用，按刑事保守处理"
    ext = os.path.splitext(path)[1].lower()
    text = ""
    if ext in (".docx", ".txt", ".md", ".markdown", ".pdf"):
        try:
            text = read_text_for_terms(path)
        except Exception:
            text = ""
    try:
        dt, why = detect_doc_type(text, base)
    except Exception:
        return "criminal", "检测异常，按刑事保守处理"
    return ("civil" if dt == "civil" else "criminal"), why


def has_rules(path):
    """词表里是否至少有一条有效规则（非注释、非空行）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    return True
    except Exception:
        return False
    return False


def find_terms(drop_dir, workshop):
    """在投放区和工坊根目录找**手工写的**有效词表。

    只认文件名以「敏感词表」开头的 .txt。自动生成的词表（自动识敏词表-*.txt）
    绝不参与 —— 否则会把上一个案子的词表套到新案子上，产出「看着脱敏了、其实真名全在」
    的危险成品（实测踩过：周军案被套用了湘粤酒楼案的词表）。
    名字含「示例」「模板」的跳过，避免拿假词表跑真实材料。
    """
    cands = []
    for d in (drop_dir, workshop):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith(".") or name.startswith("~$"):
                continue
            if "示例" in name or "模板" in name:
                continue
            if not name.startswith("敏感词表"):
                continue
            if not name.lower().endswith(".txt"):
                continue
            p = os.path.join(d, name)
            if has_rules(p):
                cands.append(p)
    if not cands:
        return None

    def priority(p):
        n = os.path.basename(p)
        return 0 if n == "敏感词表.txt" else 1

    cands.sort(key=priority)
    return cands[0]


def run(cmd, timeout=600):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 99, "超时"
    except Exception as e:
        return 98, str(e)


def run_gate(red_path, orig_path=None, terms_path=None):
    """成品落盘前的质量闸门（2026-10-28 前置）。

    为什么必须在这里拦：脱敏引擎返回 0 只代表「跑完了」，不代表「成品能用」。
    实测旧引擎把「（￥8180000元）」全脱成「（￥[编号]元）」，rc 依然 0，
    流程照样打印「完成」，用户打开才发现五个金额全没了。
    闸门放在宣布完成之前，不合格就挪进「不合格」子目录，
    宁可当场退回，也不让半成品流进成品区。

    返回 (是否通过, 失败摘要, 结构化问题列表)。
    第三项是 2026-10-31 加的：只知道「不合格」没用，得知道是哪类问题，
    才能判断是「重跑一次就好」「先改规则」还是「改引擎」——这是拦截之后能否闭环的依据。
    """
    if _dp is not None and not _dp.detect_enabled():
        return True, "", []      # 2026-11-10 用户指令：检测已关闭
    if not os.path.exists(GATE):
        # 闸门缺失时不阻断流程，但必须显式报警——静默跳过等于没有闸门
        return True, "（闸门脚本缺失：%s，已跳过质检）" % GATE, []
    cmd = [PY_EXE, GATE, "--json", red_path]
    if orig_path and os.path.exists(orig_path):
        cmd = [PY_EXE, GATE, "--json", orig_path, red_path]
    # 带上本次词表：结构对了不代表脱干净了，得按词表回查「该脱的有没有真脱」
    if terms_path and os.path.exists(terms_path):
        cmd += ["--terms", terms_path]
    rc, log = run(cmd, timeout=180)
    if rc == 0:
        return True, "", []
    if rc in (2, 3):
        # 2=读不了（格式不支持/文件损坏）、3=本格式不做体检。
        # 这两种都**不能**判成品不合格——2026-10-31 就是因为把「读不了 PDF」
        # 当成不合格，130 页的三卷 PDF 被整个拦掉，用户连文件都找不到。
        # 闸门没有结论的时候，默认放行 + 明确提示人工抽查。
        msg = log.strip().splitlines()[-1][:160] if log.strip() else '闸门未给出结论'
        print("        （闸门提示：%s）" % msg)
        return True, "", []
    # 优先读结构化输出；读不到再退回文本里的 [FAIL] 行
    for ln in reversed(log.strip().splitlines()):
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                data = json.loads(ln)
            except Exception:
                continue
            issues = data.get("issues") or []
            brief = "；".join(i.get("text", "") for i in issues)[:400]
            return False, (brief or data.get("error", "")), issues
    fails = [ln.strip() for ln in log.splitlines() if "[FAIL]" in ln]
    brief = "；".join(fails)[:400] if fails else log.strip()[-400:]
    return False, brief, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workshop", default=DEFAULT_WORKSHOP)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--no-scan", action="store_true")
    ap.add_argument("--auto-terms", action="store_true",
                    help="没有现成词表时，先让本地千问读原文自动识敏并生成词表")
    ap.add_argument("--inbox", default="", help="自定义投放目录名（默认「① 丢文件到这里」）")
    ap.add_argument("--outbox", default="", help="自定义成品目录名（默认「② 脱敏成品在这里」）")
    ap.add_argument("--keydir", default="", help="自定义对照表目录名（默认「③ 映射表-勿外传」）")
    ap.add_argument("--scandir", default="", help="自定义补漏目录名（默认「④ 补漏提示-勿外传」）")
    ap.add_argument("--no-learn", action="store_true",
                    help="本次不把经验归纳进学习库（默认会学）")
    ap.add_argument("--mode", default="auto", choices=["auto", "criminal", "civil"],
                    help="刑民分流：auto=每个文件自动判断（默认）；"
                         "criminal=全部按刑事卷宗脱；civil=全部按民事文书脱")
    args = ap.parse_args()

    W = os.path.abspath(os.path.expanduser(args.workshop))
    DROP = os.path.join(W, args.inbox or "① 丢文件到这里")
    OUTD = os.path.join(W, args.outbox or "② 脱敏成品在这里")
    MAPD = os.path.join(W, args.keydir or "③ 映射表-勿外传")
    # 补漏提示按设计会列出「还没脱掉的真名」，本身是最敏感的文件，必须标勿外传
    SCAND = os.path.join(W, args.scandir or "④ 补漏提示-勿外传")
    DONED = os.path.join(DROP, "已处理")

    for d in (DROP, OUTD, MAPD, SCAND, DONED):
        os.makedirs(d, exist_ok=True)

    # 模式开关：在投放区或工坊根目录放「模式.txt」，第一行写 civil / criminal 可整批强制。
    # 命令行 --mode 优先于文件开关；都没写就逐文件自动判断。
    _mode_from_file = None
    if args.mode == "auto":
        for mf in (os.path.join(DROP, "模式.txt"), os.path.join(DROP, "脱敏模式.txt"),
                   os.path.join(W, "模式.txt")):
            if not os.path.isfile(mf):
                continue
            try:
                first = open(mf, encoding="utf-8", errors="ignore").readline().strip()
            except Exception:
                first = ""
            if first in ("civil", "民事"):
                args.mode = "civil"
                _mode_from_file = "模式开关指定（民事）"
                print("模式开关：%s → 民事（只脱主体公司名，姓名不检索）" % os.path.basename(mf))
            elif first in ("criminal", "刑事"):
                args.mode = "criminal"
                _mode_from_file = "模式开关指定（刑事）"
                print("模式开关：%s → 刑事（人名/公司/地址全量）" % os.path.basename(mf))
            break

    if not os.path.isdir(DROP):
        print("找不到投放区：", DROP)
        return 1

    # 词表查找放在文件收集之后（自动识敏需要先知道有哪些文件）

    def is_aux(name):
        """工坊自身的辅助文件，不能当作用户材料处理。"""
        if name.startswith(".") or name.startswith("~$"):
            return True
        if "词表" in name or "使用说明" in name:
            return True
        # 模式开关文件（写 civil/criminal 强制指定刑民规则），不是待脱敏材料
        if name in ("模式.txt", "脱敏模式.txt"):
            return True
        if name.endswith(".command"):
            return True
        return False

    def collect(folder):
        got = []
        if not os.path.isdir(folder):
            return got
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if not os.path.isfile(p):
                continue
            if is_aux(name):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED:
                continue
            # 词表文件由 is_aux 统一排除，这里不再引用 terms（避免闭包未赋值）
            got.append(p)
        return got

    files = collect(DROP)
    # 容错：用户常把文件丢在「脱敏工坊」这一层，而不是「① 丢文件到这里」，一并处理
    stray = collect(W)
    if stray:
        print("提示：有 %d 个文件放在了「脱敏工坊」根目录（正确位置是「① 丢文件到这里」），已一并处理。"
              % len(stray))
        files += stray

    if not files:
        print("没找到待处理文件。支持：Word(.docx)、文本(.txt/.md)、PDF、图片(.png/.jpg/.tif/.heic 等)")
        print("请把文件丢进：", DROP)
        return 0

    terms = find_terms(DROP, W)
    auto_generated = False

    # 没有现成词表，且允许自动识敏 → 让本地千问读原文生成词表
    if not terms and args.auto_terms:
        # 图片也要纳入识敏范围（走 OCR），否则纯图片文件永远得不到词表
        text_files = [f for f in files
                      if os.path.splitext(f)[1].lower() in (
                          ".docx", ".txt", ".md", ".markdown",
                          ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp")]
        if text_files:
            print("没有现成词表，正在让本地千问读原文自动识敏（人名/公司名/地名/案号）…")
            combined = []
            for f in text_files:
                try:
                    combined.append(read_text_for_terms(f))
                except Exception as e:
                    print("  跳过 %s：%s" % (os.path.basename(f), e))
            blob = "\n\n".join(combined)[:200000]
            if blob.strip():
                tmp = os.path.join(W, ".自动识敏输入.txt")
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(blob)
                # 自动词表按次存档到 ③（仅作审计，不参与后续匹配，避免跨案串用）
                auto_path = os.path.join(
                    MAPD, "自动识敏词表-%s.txt" % time.strftime("%Y%m%d-%H%M%S"))
                # 2026-11-05：只有本批真的走过 OCR（扫描件/图片）才放行本地模型；
                # 纯 docx/doc/txt 批次不放行，gen_terms 会被自己的闸门挡回。
                _allow_llm = _USED_OCR
                if _allow_llm:
                    os.environ["DESENS_ALLOW_LLM"] = "1"
                    print("  本批含 OCR 取文（扫描件/图片），允许千问辅助这一路的识敏。")
                rc, log = run([PY_EXE, GEN_TERMS, tmp, "--model", args.model,
                               "--out", auto_path, "--host", OLLAMA_HOST], timeout=1800)
                if _allow_llm:
                    os.environ.pop("DESENS_ALLOW_LLM", None)
                try:
                    open(tmp, "w").close()      # 清空而非删除，避免触发批量删除保护
                except Exception:
                    pass
                if rc == 0 and os.path.exists(auto_path) and has_rules(auto_path):
                    terms = auto_path
                    auto_generated = True
                    tail = [ln for ln in log.strip().splitlines() if "共识别" in ln]
                    print("  自动识敏完成：%s" % (tail[0] if tail else auto_path))
                else:
                    print("  自动识敏失败或未识别到内容，将回退为无词表模式。")
                    if log.strip():
                        print("  " + log.strip().splitlines()[-1][:200])
            else:
                print("  待处理文件里没有可读文本，跳过自动识敏。")

    # 文件名本身也是泄露口：正文里都成了「周某」，文件名还写着真名就白脱了。
    # 所以输出文件名同样过一遍词表。
    try:
        from desensitize import load_terms as _load_terms
        _rules = _load_terms(terms) if terms else []
    except Exception:
        _rules = []

    def safe_stem(s):
        """文件名只替换「明确的真人/真单位」，且必须完整匹配到 2 字以上的专有名词。

        注意：不能无脑全替换，否则「湘粤酒楼执行案」会被换成「机构1执行案」，
        用户根本认不出这是哪个案子。
        """
        for o, r in _rules:
            if not o or len(o) < 2:
                continue
            # 只处理人名和完整单位名；地名/机构泛称不动文件名
            if re.search(r"(省|市|县|区|镇|村|路|街|号)$", o) and len(o) <= 3:
                continue
            if o in s:
                s = s.replace(o, r)
        return s

    print("工坊：", W)
    if terms and auto_generated:
        print("词表：%s（本地千问自动生成，建议复核）" % os.path.basename(terms))
    elif terms:
        print("词表：", os.path.basename(terms))
    else:
        print("词表：未提供（只能自动抓证件号/车牌/机构名等，抓不到人名公司名）")
    print("待处理：%d 个文件" % len(files))
    print("-" * 60)

    ok = fail = skipped = 0
    for src in files:
        base = os.path.basename(src)
        stem, ext = os.path.splitext(base)
        file_terms = terms          # 缺省用全局词表；触发单文件识敏时会被替换
        # 2026-11-06：手工词表（投放区里的「敏感词表*.txt」）是用户确认过的，
        # 民事模式也不该把里面的人名丢掉；自动识敏生成的要保持原过滤。
        _trusted = bool(file_terms) and file_terms == terms
        stem = safe_stem(stem)          # 文件名里的真名也替换掉
        out = os.path.join(OUTD, "%s_已脱敏%s" % (stem, ext))
        mapf = os.path.join(MAPD, "%s_映射表.csv" % stem)

        # ---------- 刑民分流：逐文件判断 ----------
        # 用户要求「每次脱敏前检查是民事还是刑事，然后选取对应的脱敏规则」。
        # 一批材料里可能同时丢进刑事卷宗和民事合同，所以判断必须落在文件级，
        # 不能整批一个模式。
        file_mode, mode_why = args.mode, "手工指定" if _mode_from_file is None else _mode_from_file
        if args.mode == "auto":
            file_mode, mode_why = detect_file_mode(src, base)
        tag = "民事" if file_mode == "civil" else "刑事"
        print("[%s] %s：%s" % (tag, base, mode_why))

        # 【关键闸门】词表与本文本零匹配 → 说明这是另一个案子，词表根本没覆盖它。
        # 这种情况若照跑，会产出一份「看着脱敏了、其实真名全在」的假成品，必须拦住。
        # 覆盖范围：文本类直接读；PDF/图片走 OCR 取文字（否则扫描件永远是「零命中」却照样出成品）。
        TEXT_LIKE = (".docx", ".txt", ".md", ".markdown")
        IMG_LIKE = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp")
        if _rules and (ext.lower() in TEXT_LIKE or ext.lower() in IMG_LIKE):
            try:
                # 一律用 read_text_for_terms：它对 PDF 内部已做「有文字层取文字层、
                # 没有才 OCR 前 6 页」的判断，和自动识敏的输入完全同源，命中数才准。
                # 原来 PDF 固定走 _ocr_blob(3 页)，扫描带文字层的卷宗（实测 97 页
                # 48738 字）会因取样页不一致而误报「词表仅命中 2 条」。
                blob = read_text_for_terms(src)
            except Exception:
                blob = ""
            if blob:
                matched = sum(1 for o, _r in _rules if o and o in blob)
                if matched == 0:
                    if args.auto_terms:
                        # 允许自动识敏时，为这一个文件单独生成词表并继续处理（不影响其他文件）
                        print("[换案子] %s：现有词表零匹配，正在让千问为它单独识敏…" % base)
                        tmp_in = os.path.join(W, ".识敏输入-%s.txt" % stem)
                        with open(tmp_in, "w", encoding="utf-8") as fh:
                            fh.write(blob)
                        per_terms = os.path.join(
                            MAPD, "本案词表-%s-%s.txt" % (stem, time.strftime("%H%M%S")))
                        # 2026-11-05：同上，逐文件识敏也只在 OCR 来源时放行模型
                        _allow2 = _USED_OCR
                        if _allow2:
                            os.environ["DESENS_ALLOW_LLM"] = "1"
                        rc2, log2 = run([PY_EXE, GEN_TERMS, tmp_in, "--model", args.model,
                                         "--out", per_terms, "--host", OLLAMA_HOST], timeout=1800)
                        if _allow2:
                            os.environ.pop("DESENS_ALLOW_LLM", None)
                        try:
                            open(tmp_in, "w").close()
                        except Exception:
                            pass
                        if rc2 == 0 and os.path.exists(per_terms) and has_rules(per_terms):
                            new_rules = _load_terms(per_terms)
                            hit2 = sum(1 for o, _r in new_rules if o and o in blob)
                            print("        已生成本案词表：%d 条（命中本文本 %d 条）" % (len(new_rules), hit2))
                            if hit2 == 0:
                                print("[跳过] %s：新词表仍无法命中，请人工检查后重跑。" % base)
                                skipped += 1
                                continue
                            _rules = new_rules
                            file_terms = per_terms
                            _trusted = False      # 模型识敏生成的，保持原有过滤
                            print("        提示：该词表存于 ③，仅适用于本案；如确认无误可改名成「敏感词表.txt」复用。")
                        else:
                            print("[跳过] %s：自动识敏失败，未生成成品。" % base)
                            skipped += 1
                            continue
                    else:
                        # 2026-11-06 mk15 修：原来这里直接「跳过」，而 App 投递（server.py 的 run_job）
                        # 从不传 --auto-terms，于是**任何新案子都零产出**——预览目录空、页面空白，
                        # 用户以为后台坏了。根因是「换案子唯一出路是千问」，而千问已被
                        # 2026-11-05 死命令禁用（文本脱敏不得调模型）。
                        # 改法：把不匹配的词表当空，交给 desensitize 的规则＋结构兜底自动脱主体，
                        # 成品仍进预览界面由使用者本人核对（质检不替人判断）。
                        # 非主体公司可能只靠结构识别兜底，故必须提示人工抽查。
                        print("[换案子] %s：现有词表零匹配，改用规则自动脱敏（不调模型）。" % base)
                        print("        自动模式只保证甲乙方公司与证件号；非主体公司靠结构兜底，请逐页抽查。")
                        _rules = []
                        _trusted = False
                elif matched <= 2:
                    # 只提醒不阻断。对多页卷宗（一份几十上百页），前 6 页往往只涉及
                    # 少数当事人，命中少是正常的，不能说成「不是本案词表」去吓用户。
                    print("[提醒] %s：前 6 页仅命中词表 %d 条。卷宗页数多时属正常，"
                          "脱敏仍会按全文件执行；建议成品抽查几页确认。" % (base, matched))

        # 跳过仍在写入的文件（大小在 1 秒内还在变），等下次触发再处理
        try:
            s1 = os.path.getsize(src)
            time.sleep(1.0)
            s2 = os.path.getsize(src)
            if s1 != s2:
                print("[等待] %s 仍在写入，本次跳过，稍后重新触发" % base)
                skipped += 1
                continue
        except Exception:
            pass

        ext_l = ext.lower()
        is_image = ext_l in IMAGE_EXT

        # 已存在同名成品时先删掉，否则 PyMuPDF/PIL 无法覆盖（实测会报 cannot remove file）
        for old in (out, mapf):
            if os.path.exists(old):
                try:
                    os.remove(old)
                except Exception as e:
                    print("        （旧成品删除失败，将尝试覆盖：%s）" % e)

        if is_image:
            # 扫描件/照片：先体检质量，再 OCR 识别、涂黑。
            # 体检的意义：质量太差的件无论怎么处理都救不回来（实测低分辨率件
            # 认字命中 1/11，放大到 400dpi 也一样），与其交付一份漏字的成品，
            # 不如提前告诉用户重新扫描。判断只看字高/对比度/置信度，不读内容。
            try:
                import scan_enhance as _SE
                import tempfile as _td
                probe = src
                if ext_l == ".pdf":
                    import pymupdf as _pm
                    _d = _pm.open(src)
                    probe = os.path.join(_td.mkdtemp(), "probe.png")
                    _d[0].get_pixmap(dpi=200).save(probe)
                    _d.close()
                q = _SE.assess_quality(probe)
                if q["level"] == "poor":
                    print("[质量警告] %s：%s" % (base, "；".join(q["issues"]) or "扫描质量差"))
                    for ad in q["advice"]:
                        print("           → %s" % ad)
                    print("           仍会尝试处理，但漏字风险高，成品务必逐页核对。")
                elif q["level"] == "fair":
                    print("[质量提示] %s：%s（已自动强化后再识别）"
                          % (base, "；".join(q["issues"]) or "质量一般"))
            except Exception:
                pass

            # 扫描件/照片：OCR 识别后把敏感区域真正涂黑
            mapf = os.path.join(MAPD, "%s_涂黑记录.csv" % stem)
            cmd = [PY_EXE, IMAGE_REDACT, src, "--out", out, "--map", mapf]
            if file_terms:
                cmd += ["--terms", file_terms]
            rc, log = run(cmd, timeout=1800)
        elif ext_l in SHEET_EXT:
            # 表格：逐单元格替换，保留原格式
            mapf = os.path.join(MAPD, "%s_单元格对照表.csv" % stem)
            cmd = [PY_EXE, SHEET_REDACT, src, "--out", out, "--map", mapf]
            if file_terms:
                cmd += ["--terms", file_terms]
            rc, log = run(cmd, timeout=1800)
        elif ext_l in LEGACY_DOC:
            # 老版 .doc：先转 docx，处理后再存回 .docx（.doc 无法保格式回写）
            conv = convert_doc_to_docx(src, W)
            if not conv:
                print("[失败] %s：.doc 转换失败（请用 Word/WPS 另存为 .docx）" % base)
                fail += 1
                continue
            out = os.path.join(OUTD, "%s_已脱敏.docx" % stem)
            mapf = os.path.join(MAPD, "%s_映射表.csv" % stem)
            cmd = [PY_EXE, DESENSITIZE, conv, "--out", out, "--map", mapf]
            if file_terms:
                cmd += ["--terms", file_terms]
                if _trusted:
                    cmd += ["--trusted-terms"]
            cmd += ["--mode", file_mode]
            rc, log = run(cmd)
        else:
            cmd = [PY_EXE, DESENSITIZE, src, "--out", out, "--map", mapf]
            if file_terms:
                cmd += ["--terms", file_terms]
                if _trusted:
                    cmd += ["--trusted-terms"]
            cmd += ["--mode", file_mode]
            rc, log = run(cmd)

        # 失败自动重试一次（应对文件刚落盘时被占用等瞬时问题）
        if rc not in (0, 2):
            time.sleep(1.5)
            rc, log = run(cmd)

        if rc == 2:
            # 引擎自己都报了残留，不能当成功直接放进成品区。
            # 2026-10-31 改：以前这里 ok += 1 就放行了，用户不翻日志根本不知道
            # 这份成品漏了词；现在交给闸门复核（闸门会按词表回查），该拦就拦。
            print("[注意] %s → 已生成，但引擎报残留，交由闸门复核" % base)
            print(log.strip()[:1500])
        elif rc != 0:
            print("[失败] %s：%s" % (base, log.strip()[-1500:]))
            fail += 1
            continue

        # 【落盘前闸门】2026-10-28：rc==0 只说明引擎跑完了，不代表成品可用。
        # 旧引擎把五个金额全脱成 [编号] 时 rc 依然是 0，流程照样打印「完成」，
        # 用户打开才发现数字没了。这里在宣布完成之前再过一道闸门。
        # rc==2（引擎自报残留）也走这里——不核一遍不算完。
        passed, why, issues = run_gate(out, src, file_terms)
        if not passed:
            # 【2026-11-05 用户死命令】质检闸门只做提示，不替使用者挡文件。
            # 原话：「以后合不合格都丢到预览界面要我看，你在后台等我」。
            # 不合格件照常留在预览任务 output，由本人核对后决定导不导出；
            # 原因、原件、台账仍在「不合格」留底可追溯。
            # server.py 扫描 OUTD 生成 preview.json / index.json / 账本 preview，
            # 成品一旦被移走，预览页就看不到，人工确认这一步也就断了。
            rec = {}
            try:
                import reject_store
                bad_root = os.environ.get("DESENSITIZE_BAD_DIR") or os.path.join(OUTD, "不合格")
                # keep_in_place=True：成品**原地不动**，和合格件同一个目录，
                # 界面按台账标红提示（2026-11-05 用户死命令：合格不合格放一个路径）。
                rec = reject_store.record_reject(OUTD, out, src, issues, why,
                                                 bad_dir=bad_root, keep_in_place=True)
            except Exception as e:
                print("        （质检留底写入失败，成品仍原地保留：%s）" % str(e)[:120])
            print("[闸门拦截] %s：%s（质检未通过，成品仍与合格件同目录，界面标红提示）"
                  % (base, why))
            if rec:
                print("        原因已留底，处置建议：%s"
                      % reject_store.FIX_LABEL.get(rec.get("fix"), ""))
            ok += 1
            # 不 continue：继续走图片涂黑 / 补漏 / 原件归位，与合格件同一条收尾
            # （原写法在这里移走 src，收尾会再移一次报「原件移动失败」，故不再重复移）
        print("[完成] %s → %s" % (base, os.path.basename(out)))
        ok += 1

        # docx 内嵌图片也要脱敏：文字处理完再把 word/media 里的图逐张 OCR 涂黑
        if ext_l == ".docx" and os.path.exists(out) and file_terms:
            try:
                from desensitize import load_terms as _load
                from docx_media import redact_docx_media
                rules = _load(file_terms)
                if rules:
                    recs, total, touched = redact_docx_media(out, rules, False, out)
                    if total:
                        print("        文档内嵌图片 %d 张，涂黑处理 %d 张（共 %d 处）"
                              % (total, touched, len(recs)))
                        if recs:
                            mf = os.path.join(MAPD, "%s_图片涂黑记录.csv" % stem)
                            with open(mf, "w", encoding="utf-8", newline="") as fh:
                                import csv as _csv
                                wr = _csv.writer(fh)
                                wr.writerow(["图片", "被涂黑的原文", "类别"])
                                for r in recs:
                                    wr.writerow([r.get("file", ""), r.get("text", ""), r.get("category", "")])
            except Exception as e:
                print("        （文档内图片脱敏失败：%s）" % str(e)[:150])

        # 本地千问补漏（仅对文本类产物有效；图像已涂黑，不适用文本扫描）
        if (not is_image) and (not args.no_scan) and (_dp is None or _dp.detect_enabled()) and os.path.exists(LLM_SCAN) and os.path.exists(out):
            rc2, log2 = run([PY_EXE, LLM_SCAN, out, "--model", args.model], timeout=900)
            scanfile = os.path.join(SCAND, "%s_补漏待确认.txt" % stem)
            with open(scanfile, "w", encoding="utf-8") as f:
                f.write("# ⚠ 本文件含真实姓名等原始信息，仅限本人复核使用，切勿外发或上传\n"
                        "# 用途：找出词表没覆盖的敏感词，确认后补进「敏感词表.txt」再重跑\n")
                f.write("文件：%s\n生成时间：由本地模型 %s 扫描\n" % (os.path.basename(out), args.model))
                f.write("=" * 50 + "\n")
                f.write(log2.strip() + "\n")
            if rc2 == 0:
                print("        补漏提示 → %s" % os.path.basename(scanfile))
            else:
                print("        补漏扫描未完成（模型可能未启动），已记录到 %s" % os.path.basename(scanfile))

        # 原件移入已处理
        try:
            shutil.move(src, os.path.join(DONED, base))
        except Exception as e:
            print("        （原件移动失败，请手动清理：%s）" % e)

    print("-" * 60)
    if skipped:
        print("成功 %d 个，失败 %d 个，跳过 %d 个（词表不匹配或文件未写完）。成品在：%s"
              % (ok, fail, skipped, OUTD))
    else:
        print("成功 %d 个，失败 %d 个。成品在：%s" % (ok, fail, OUTD))
    print("提醒：映射表是还原钥匙，在 %s，切勿外发。" % MAPD)

    # ===== 自动学习：每次处理完顺手归纳经验，下次更准 =====
    # 这是「越用越聪明」的关键——不靠人记得手动跑 learning.py。
    # 从本批的映射表里归纳新姓氏/新机构类型，进候选区，
    # 同一现象出现两次即自动转正，下次脱敏直接生效。
    if ok and not getattr(args, "no_learn", False):
        try:
            _auto_learn(MAPD, DROP, W)
        except Exception as e:
            print("（自动学习跳过：%s）" % e)

    return 0 if fail == 0 else 1


def _auto_learn(mapd, dropd, workdir):
    """从本批映射表自动归纳经验。静默执行，失败不影响主流程。"""
    import glob
    maps = sorted(glob.glob(os.path.join(mapd, "*映射表*.csv")),
                  key=os.path.getmtime, reverse=True)
    if not maps:
        return
    # 只学最近 5 分钟内产生的映射表（即本批的产物），避免重复学旧账
    cutoff = time.time() - 300
    fresh = [m for m in maps if os.path.getmtime(m) >= cutoff]
    if not fresh:
        return
    learned_n = 0
    for m in fresh[:10]:
        rc, log = run([PY_EXE, os.path.join(HERE, "learning.py"),
                       "observe", "--map", m, "--case",
                       os.path.splitext(os.path.basename(m))[0]], timeout=120)
        if "自动转正" in (log or ""):
            for ln in log.splitlines():
                if "自动转正" in ln:
                    print("学习：%s" % ln.strip())
                    learned_n += 1
    if learned_n == 0:
        # 没有转正的也提一句，让用户知道系统在积累
        print("学习：本次经验已记入候选区（同类现象出现 2 次即自动生效）。")


if __name__ == "__main__":
    _reexec_with_full_python()
    sys.exit(main())
