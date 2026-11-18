#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
立丰脱敏 本地服务 —— 给图形界面提供后端，全部在本机回环，不联网。

工作目录藏在 ~/Library/Application Support/立丰脱敏/，用户完全不用管文件夹。
"""
import os
import re
import sys
import json
import time
import csv
import hashlib
import signal
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# 代码可以放在 App 外面（~/Library/Application Support/立丰脱敏/runtime-code），
# 这样改脚本不必重签 App —— ad-hoc 签名每次重签都会让 macOS 重置隐私授权。
# 用 LF_CODE_DIR 指明真实代码目录；未设置时退回本文件所在目录，行为不变。
_CODE_DIR = os.environ.get("LF_CODE_DIR") or os.path.dirname(os.path.abspath(__file__))

HOME = os.path.expanduser("~")
APP_SUPPORT = os.path.join(HOME, "Library", "Application Support", "立丰脱敏")
WORK = os.path.join(APP_SUPPORT, "工作区")
INBOX = os.path.join(WORK, "待处理")
# 所有产出集中在一个总目录下，文稿根目录不再散落四五个"立丰脱敏xx"。
# 注意：~/Documents/立丰脱敏 以前是指向 App 的符号链接（老启动方式），
# 那个链接已于 2026-11-02 换成真实目录；App 从「应用程序」启动，不依赖它。
BASE_DIR = os.path.join(HOME, "Documents", "立丰脱敏")
# 成品直接放总目录下的「成品」，方便用户找
OUTBOX = os.path.join(BASE_DIR, "成品")
# 去水印成品单独一个文件夹（2026-11-11 用户要求：「专门做个脱水印的文件夹」）。
# 不混进「成品」的理由：那边全是脱敏件，混进一批「只去了水印、没脱敏」的文件，
# 用户很容易当成脱敏成品拿走 —— 那是一次实打实的泄密。
WM_OUTBOX = os.path.join(BASE_DIR, "去水印")
# 被闸门拦下的成品单独放，既不混进成品区，也不至于就此消失
BAD_DIR = os.path.join(OUTBOX, "不合格")
KEYS = os.path.join(WORK, "对照表")
SCANS = os.path.join(WORK, "补漏提示")
TERMS_FILE = os.path.join(APP_SUPPORT, "敏感词表.txt")
# 网页上传的文件先落这里，避免和流水线清空的待处理区混在一起
UPLOADS = os.path.join(APP_SUPPORT, "上传暂存")
# 预览任务：脱敏结果先落这里，用户点「导出」才复制进成品目录
PREVIEW_ROOT = os.path.join(APP_SUPPORT, "预览")
# 手动涂黑任务：扫描件/PDF 没有文字可点，只能让人在页面上拉框
PAINT_ROOT = os.path.join(APP_SUPPORT, "涂黑任务")
# 复原产物单独放一个目录：成品夹是会被整包外发的，真名文件绝不能混在里面
RESTORE_DIR = os.path.join(BASE_DIR, "还原")
MEMORY = os.path.join(APP_SUPPORT, "memory.py")
# 本地 AI 配置：开关、模型、地址。没有本地模型时全部功能自动降级，不影响规则脱敏。
AI_CONF = os.path.join(APP_SUPPORT, "ai.json")
AI_DEFAULT = {"enabled": False, "model": "qwen2.5:7b", "host": "http://127.0.0.1:11434"}


def ai_config():
    # 分发版可以带一份初始配置（App 内 seed/ai.json），首次启动就落成用户配置。
    # 分发包里写的是 enabled=false —— 对方机器没有本地模型，别让它白试。
    try:
        if not os.path.exists(AI_CONF):
            _seed = os.path.join(_CODE_DIR, "seed", "ai.json")
            if os.path.exists(_seed):
                os.makedirs(APP_SUPPORT, exist_ok=True)
                import shutil as _sh
                _sh.copy2(_seed, AI_CONF)
    except Exception:
        pass
    d = dict(AI_DEFAULT)
    try:
        with open(AI_CONF, encoding="utf-8") as f:
            d.update(json.load(f) or {})
    except Exception:
        pass
    return d


def ai_save(conf):
    d = ai_config()
    for k in ("enabled", "model", "host"):
        if k in conf:
            d[k] = conf[k]
    d["enabled"] = bool(d.get("enabled"))
    try:
        os.makedirs(APP_SUPPORT, exist_ok=True)
        with open(AI_CONF, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return d

_HERE = _CODE_DIR
# 分发包把脚本装在 App 内部的 engine/ 里；本机开发时仍用工作目录那份。
# 先看包内，再回落，两种形态同一份代码。
_ENGINE = os.path.join(_HERE, "engine")
SCRIPTS = _ENGINE if os.path.isdir(_ENGINE) else os.path.join(
    HOME, ".workbuddy", "skills", "legal-desensitize", "scripts")
RUNNER = os.path.join(SCRIPTS, "dropbox_run.py")
GEN_TERMS = os.path.join(SCRIPTS, "gen_terms.py")

# 规则配置层与本服务同源：把引擎目录挂进 sys.path，才能 import rules_store
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

# 启动即预热引擎：desensitize 模块加载时会生成缺失的规则配置，
# 并把内置规则快照交给 rules_store，「恢复默认」才能立即重建。
try:
    import desensitize as _engine  # noqa: F401
except Exception as _e:
    print("引擎预热失败（脱敏时仍会重试）：%s" % _e, flush=True)
WEB_DIR = os.path.join(_CODE_DIR, "web")


def _self_reexec():
    """若当前解释器缺 PIL/pymupdf，用合格解释器重新执行自己。

    本进程内会直接 import pymupdf 做 PDF 判断、用 PIL 处理图片上传。
    用裸 python 启动时这些 import 会抛错，表现为「扫描件处理失败」或
    「人名没被抹掉」，用户完全看不出是解释器的问题。
    """
    if os.environ.get("_LF_REEXEC") == "1":
        return
    need = "import docx, PIL, pymupdf, openpyxl"
    # 2026-11-05 打包分发：包内 runtime 排第一，其次当前解释器，
    # 最后才是 WorkBuddy venv（对方机器上没有 ~/.workbuddy）。
    cands = [os.path.join(_HERE, "runtime", "bin", "python3"),
             sys.executable,
             os.path.join(HOME, ".workbuddy", "binaries", "python", "envs",
                          "default", "bin", "python3"),
             "/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
    for p in cands:
        if os.path.abspath(p) == os.path.abspath(sys.executable):
            return
        if not os.path.exists(p):
            continue
        try:
            r = subprocess.run([p, "-c", need], capture_output=True, timeout=15)
            if r.returncode == 0:
                os.environ["_LF_REEXEC"] = "1"
                os.execv(p, [p, os.path.abspath(__file__)] + sys.argv[1:])
        except Exception:
            continue


_self_reexec()

# 分发包自带 Python（App 内 runtime/），对方电脑不需要装任何东西；
# 本机没有 runtime 时回落到 WorkBuddy 的 venv。
_BUNDLED_PY = os.path.join(_HERE, "runtime", "bin", "python3")
VENV_PY = _BUNDLED_PY if os.path.exists(_BUNDLED_PY) else os.path.join(
    HOME, ".workbuddy", "binaries", "python", "envs", "default", "bin", "python3")
# 分发包里 App 的 Resources 就是 _HERE，runtime 与 server.py 平级；
# 而引擎脚本在 engine/ 里，它算包内 python 时要往上一级找 —— 统一由这个
# 环境变量告诉所有子脚本，免得每处各写一套相对路径。
if os.path.exists(_BUNDLED_PY):
    os.environ.setdefault("DESENSITIZE_PYTHON", _BUNDLED_PY)
    os.environ.setdefault("LF_ENGINE_DIR", SCRIPTS)

SUPPORTED = {".docx", ".doc", ".txt", ".md", ".markdown",
             ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic", ".webp"}

# 当前跑着的子进程。取消按钮要能真正掐断流水线，
# 光把界面状态改掉是假的 —— 后台还在跑，成品照样落盘。
_CURRENT = {"proc": None}

_state = {"running": False, "cancelled": False, "log": [], "done": [], "failed": [], "started": 0,
          # 真实进度（用户要求「能看到脱敏的进度条」）
          "total": 0,          # 本批文件总数
          "index": 0,          # 当前处理到第几个
          "current": "",       # 当前文件名
          "stage": "",         # 当前阶段（中文说明）
          "stage_no": 0,       # 阶段序号
          "stage_total": 5,    # 阶段总数
          "percent": 0}        # 总进度百分比


# 日志行 → 阶段识别。dropbox_run 的输出有固定格式，据此推断当前在干什么。
# 这样用户看到的是「第 2/5 个：某某笔录.pdf —— 正在识别敏感信息 42%」，
# 而不是一条不知进度的无限循环动画。
_STAGE_RULES = (
    (("已接收",), "准备中", 1),
    (("没有现成词表", "正在让本地千问", "换案子"), "正在识别敏感信息", 2),
    (("自动识敏完成", "本案词表", "词表："), "敏感信息识别完成", 2),
    (("质量警告", "质量提示", "体检"), "检查扫描件质量", 2),
    (("扫描页", "OCR 识别到"), "正在逐页识别扫描件", 3),
    (("词表仅命中", "前 6 页仅命中", "词表零匹配"), "核对词表覆盖", 3),
    (("补漏", ), "补漏复查", 4),
    (("[完成]", "→"), "已生成成品", 5),
    (("[闸门拦截]",), "质检未通过，仍照常进预览待本人确认", 5),
    (("学习", "已学习"), "把经验记入学习库", 5),
    (("[失败]", "[跳过]", "[等待]"), "处理结束", 5),
)


def _detect_stage(line, total, index):
    """从一行日志推断当前阶段与进度。返回 (阶段名, 阶段序号, 文件名)。"""
    stage, sno, fname = "", 0, ""
    for keys, name, no in _STAGE_RULES:
        if any(k in line for k in keys):
            stage, sno = name, no
            break
    # 文件名提取：日志里形如「[完成] xxx.pdf → …」「[失败] xxx.pdf：…」「[闸门拦截] xxx.pdf：…」
    m = re.search(r"[\[【](?:完成|失败|跳过|等待|提醒|质量警告|质量提示|闸门拦截)[\]】]\s*([^：:→]+)", line)
    if m:
        fname = m.group(1).strip()
    if not fname:
        m = re.search(r"已接收：(.+)$", line)
        if m:
            fname = m.group(1).strip()
    return stage, sno, fname


def py_exe():
    """挑一个依赖齐全的解释器。

    只验 `import docx` 是不够的：图片/扫描 PDF 要 PIL + pymupdf，
    表格要 openpyxl。缺了就会在脱敏时抛 No module named 'PIL'，
    用户看到的结果就是「扫描件里的人名压根没被抹掉」。
    """
    need = "import docx, PIL, pymupdf, openpyxl"
    # 2026-11-05 打包分发：VENV_PY 已改成「包内 runtime 优先，没有才回落
    # ~/.workbuddy」，所以这里不用再单独判断，顺序天然正确。
    cands = (VENV_PY, "/opt/homebrew/bin/python3", "/usr/local/bin/python3")
    for p in cands:
        if os.path.exists(p):
            try:
                r = subprocess.run([p, "-c", need], capture_output=True, timeout=15)
                if r.returncode == 0:
                    return p
            except Exception:
                pass
    # 退一步只要 Word 能力，至少文本类能跑（图片会在日志里明确报错）
    for p in cands:
        if os.path.exists(p):
            try:
                r = subprocess.run([p, "-c", "import docx"], capture_output=True, timeout=15)
                if r.returncode == 0:
                    return p
            except Exception:
                pass
    return sys.executable


def ensure_dirs():
    for d in (APP_SUPPORT, WORK, INBOX, OUTBOX, KEYS, SCANS, UPLOADS, PREVIEW_ROOT, RESTORE_DIR):
        os.makedirs(d, exist_ok=True)


def ollama_up():
    try:
        import urllib.request
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open("http://127.0.0.1:11434/api/version", timeout=2) as r:
            return b"version" in r.read()
    except Exception:
        return False


def _case_key(stem):
    """由文件名推导案件键：去掉日期、副本、定稿等后缀。"""
    n = re.sub(r"[-_ ]?\d{6,8}.*$", "", stem or "")
    n = re.sub(r"(副本\d*|终版|定稿|修改版\d*|已脱敏)$", "", n)
    return n.strip("-_ ")[:40]


def _run(cmd, timeout=120):
    """跑子进程，返回 (rc, 输出文本)。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def _verify_terms_cover(path, terms_path):
    """验证某份词表是否真的覆盖这个文件（文本直接读，PDF/图片走 OCR）。

    至少命中 3 条才算「同一案子」，否则视为不匹配。
    """
    try:
        sys.path.insert(0, SCRIPTS)
        from desensitize import load_terms
        if not terms_path or not os.path.exists(terms_path):
            return False
        rules = load_terms(terms_path)
        if not rules:
            return False

        ext = os.path.splitext(path)[1].lower()
        blob = ""
        if ext in (".docx", ".txt", ".md", ".markdown"):
            from llm_scan import read_text
            blob = read_text(path)
        elif ext == ".pdf":
            import pymupdf
            doc = pymupdf.open(path)
            blob = "".join(pg.get_text() for pg in doc)
            doc.close()
            if len(blob.strip()) < 20:      # 扫描件 → 前 2 页 OCR
                import tempfile
                doc = pymupdf.open(path)
                tmp = tempfile.mkdtemp()
                parts = []
                for i in range(min(2, doc.page_count)):
                    ip = os.path.join(tmp, "v%03d.png" % i)
                    doc[i].get_pixmap(dpi=200).save(ip)
                    parts.append(_ocr_text(ip))
                doc.close()
                blob = "".join(parts)
        else:
            blob = _ocr_text(path)

        if not blob:
            return False
        hit = sum(1 for o, _r in rules if o and o in blob)
        return hit >= 3
    except Exception:
        return False


def _ocr_text(path):
    """调用本机 Vision OCR 取文字。"""
    try:
        OCR = os.path.join(SCRIPTS, "ocr_vision")
        if not os.path.exists(OCR):
            return ""
        p = subprocess.run([OCR, path], capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return ""
        items = json.loads(p.stdout or "[]")
        return "".join(x.get("text", "") for x in items)
    except Exception:
        return ""


# ============ 逆向还原（2026-11-12 用户要求）============
# 场景：脱敏件投给 AI → AI 写出一份提纲/纪要（里面沿用同样的占位符）
#       → 在本机拿映射表把提纲里的占位符换回真名。
# 与「文件还原」的区别：那个是还原**原来的那份文档**（占位符位置与脱敏件一一对应）；
# 这个是还原**AI 新写的文本**（内容完全不同，只是用了同一套占位符）。
def _read_map_csv(path):
    """读映射表 CSV → [(原值, 占位符)]。列序是「原值,占位符,类别」。"""
    rows = []
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.reader(f):
                if len(r) < 2:
                    continue
                a, b = (r[0] or "").strip(), (r[1] or "").strip()
                if not a or not b or a == "原值":
                    continue
                rows.append((a, b))
    except Exception:
        pass
    return rows


def terms_pairs():
    """读当前生效的脱敏词表 → [(原值, 替代词)]，供逆向还原反向使用。

    词表格式「原值=替代词」（规则设置里的「本案词条」）：正向脱敏把原值换成替代词，
    逆向还原要反过来把替代词换回原值 —— 这正好与映射表 CSV 的
    「(原值, 占位符)」列序一致，直接并进 rows 即可。
    只有单边、没有替代词的行跳过：它们没有可用于反向匹配的占位符。
    2026-11-12 用户要求：「逆向也能用脱敏词表才正常，反向一下就可以」。
    """
    out = []
    if not os.path.isfile(TERMS_FILE):
        return out
    try:
        with open(TERMS_FILE, encoding="utf-8") as f:
            for line in f:
                t = line.strip()
                if not t or t.startswith("#") or "=" not in t:
                    continue
                a, b = t.split("=", 1)
                a, b = a.strip(), b.strip()
                if a and b:
                    out.append((a, b))
    except Exception:
        pass
    return out


def _replace_in_string(text, rows):
    """按占位符长度降序，把文本里的占位符换回原值，返回 (新文本, 处数)。"""
    n = 0
    for orig, ph in rows:
        if ph and ph in text:
            n += text.count(ph)
            text = text.replace(ph, orig)
    return text, n


def _derestore_rows(names):
    """把界面传来的还原依据合成 (rows, conflicts, terms_used, paths, err)。

    文字还原与文件还原共用这一份：映射表是本次脱敏生成的精确对照，优先；
    词表只补没覆盖的替代词。rows 已按占位符长度降序排好。
    """
    names = [os.path.basename(str(x)) for x in (names or []) if str(x).strip()]
    use_terms = "__terms__" in names
    names = [n for n in names if n != "__terms__"]
    if not names and not use_terms:
        return [], [], 0, [], "没有选择还原依据"
    paths, bad = [], []
    for n in names:
        fp = os.path.join(KEYS, n)
        if os.path.isfile(fp) and n.endswith(".csv"):
            paths.append(fp)
        else:
            bad.append(n)
    if not paths and not use_terms:
        return [], [], 0, [], "映射表不存在：%s" % "、".join(bad[:3])
    rows, conflicts = _merge_maps(paths) if paths else ([], [])
    terms_used = 0
    if use_terms:
        seen = {ph: o for o, ph in rows}
        for orig, ph in terms_pairs():
            if ph in seen:
                if seen[ph] != orig:
                    conflicts.append({"placeholder": ph, "kept": seen[ph],
                                      "dropped": orig, "from": "脱敏词表"})
                continue
            rows.append((orig, ph))
            seen[ph] = orig
            terms_used += 1
    if not rows:
        return [], [], 0, paths, "还原依据里读不到对照关系"
    rows.sort(key=lambda x: -len(x[1]))
    return rows, conflicts, terms_used, paths, ""


def restore_file_inplace(src, rows):
    """在**原文件的副本**上只替换文字，保留原格式，返回 (输出路径, 替换处数, 错误)。

    2026-11-12 用户原话：「文件丢进去出来变样了，我要你在原文件上动手」。
    旧流程是抽文字 → Document() 新建 → 逐行 add_paragraph，排版全丢。
    这里：docx 打开原件只改 w:t 文本节点（复用引擎 redact_paragraph 的跨 run
    补偿，含表格与页眉页脚），另存到「还原」目录；xlsx 只改单元格字符串；
    txt/md 本就是纯文本。原文件一律不动。
    PDF 无法在保留版式的前提下可靠替换中文，明确拒绝，不给一个烂结果。
    """
    if not os.path.isfile(src):
        return "", 0, "文件不存在"
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".docx", ".xlsx", ".xlsm", ".txt", ".md", ".markdown"):
        return "", 0, ("PDF 无法在保留版式的前提下替换文字；请先转成 docx，"
                       "或用「读入文字」模式（会丢格式）")
    stem = os.path.splitext(os.path.basename(src))[0]
    os.makedirs(RESTORE_DIR, exist_ok=True)
    out = os.path.join(RESTORE_DIR, stem + "_已还原" + ext)
    k = 2
    while os.path.exists(out):
        out = os.path.join(RESTORE_DIR, "%s_已还原-%d%s" % (stem, k, ext))
        k += 1
    total = 0
    try:
        if ext == ".docx":
            import desensitize as _dz
            from docx import Document
            doc = Document(src)

            class _R(object):
                """把还原动作伪装成引擎要的 redactor，只实现 redact_text。"""
                def __init__(self, pairs):
                    self.pairs = pairs
                    self.count = 0
                def prescan(self, text):
                    pass
                def redact_text(self, text):
                    t, n = _replace_in_string(text, self.pairs)
                    self.count += n
                    return t

            r = _R(rows)
            for p in doc.paragraphs:
                _dz.redact_paragraph(p, r)
            for tbl in doc.tables:
                for row in tbl.rows:
                    for cell in row.cells:
                        for p in cell.paragraphs:
                            _dz.redact_paragraph(p, r)
            try:
                for p in _dz.iter_hf_paragraphs(doc):
                    _dz.redact_paragraph(p, r)
            except Exception:
                pass
            try:
                _dz.redact_all_text_nodes(doc, r)   # 文本框 / 形状内文字兜底
            except Exception:
                pass
            doc.save(out)
            total = r.count
        elif ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(src)
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        if isinstance(c.value, str) and c.value:
                            t, n = _replace_in_string(c.value, rows)
                            if n:
                                c.value = t
                                total += n
            wb.save(out)
            wb.close()
        else:
            with open(src, encoding="utf-8", errors="ignore") as f:
                t = f.read()
            t, total = _replace_in_string(t, rows)
            with open(out, "w", encoding="utf-8") as f:
                f.write(t)
    except Exception as e:
        return "", 0, "处理失败：%s" % str(e)[:140]
    return out, total, ""


# 汉字/数字之间的排版空格，以及中文标点两侧的空格。
# 只认全角空格、不间断空格等排版字符；英文单词之间的空格**绝不能动**，
# 否则「United States」会被压成「UnitedStates」。
_CJK_GAP = r"[ \t\u00a0\u3000\u200b-\u200d\ufeff]+"
_CJK_PUNCT = "，。；：！？、（）《》【】「」"


def _squeeze_cjk_spaces(text):
    """删掉汉字之间、数字之间、中文标点两侧的排版空格。

    2026-11-12 用户要求：「还原以后，原本字中间有空格的内容，你自动删一下」。

    这些空格不是人打的，是脱敏/排版/AI 转述时塞进去的：
        王  海 涛 → 某某某        湖 北 省 → 湖北省
        000000 00000000 0000 → 000000000000000000
        秭归县 ， 群众 → 秭归县，群众
    还原出来还带着它们，读起来像没洗干净。

    守住的边界：
      · 英文/字母之间的空格保留（United States、AI 生成）
      · 中英文之间的空格保留（AI 生成的提纲）
      · 只有「汉字↔汉字」「数字↔数字」「中文标点两侧」才动
    """
    n = 0
    # 汉字之间
    text, k = re.subn(
        r"(?<=[\u4e00-\u9fff])" + _CJK_GAP + r"(?=[\u4e00-\u9fff])",
        "", text)
    n += k
    # 数字之间（身份证、手机号、账号被排版断开）
    text, k = re.subn(r"(?<=\d)" + _CJK_GAP + r"(?=\d)", "", text)
    n += k
    # 中文标点两侧：拆成「前」「后」两条，各自都要求真有空格，
    # 别写成一条带可选空格的正则 —— 那样会把每个标点都算成一次"清理"，
    # 而且标点后没空格时（句末「学历 。」换行）反而匹配不上。
    text, k = re.subn(_CJK_GAP + r"([" + _CJK_PUNCT + r"])", r"\1", text)
    n += k
    text, k = re.subn(r"([" + _CJK_PUNCT + r"])" + _CJK_GAP, r"\1", text)
    n += k
    return text, n


def _merge_maps(paths):
    """把多份映射表合并成一张，返回 ([(原值, 占位符)], 冲突列表)。

    用户要求：「可以选择多份，如果多份里面有相同的词，就不管，不同的词要叠加起来」。

    - 同一个占位符指向同一个原值 → 静默去重；
    - 同一个占位符指向**不同**原值 → 保留先选的那份，并记一条冲突。
      为什么不自动覆盖：那会把前一份文档里那个人的事，写到后一份的人头上。
      宁可少还原一个词，也不能张冠李戴 —— 冲突交给用户自己判断。
    """
    merged = {}          # 占位符 -> 原值
    conflicts = []
    for p in paths or []:
        base = os.path.basename(p)
        for orig, ph in _read_map_csv(p):
            if ph in merged:
                if merged[ph] != orig:
                    conflicts.append({
                        "placeholder": ph,
                        "kept": merged[ph],
                        "dropped": orig,
                        "from": base,
                    })
                continue
            merged[ph] = orig
    rows = [(orig, ph) for ph, orig in merged.items()]
    return rows, conflicts


def _derestore_text(text, rows):
    """把文本里的占位符换回原值，返回 (新文本, [(占位符, 原值, 处数)])。

    - **占位符长的先替换**：否则「米兰」会先把「米兰市」里的字吃掉，留下「市」。
    - 占位符本身带空格时（如「王 大 海」），允许原文空格数不同 ——
      AI 转述时常把空格删掉或改成全角，精确匹配会全漏。
      反过来占位符不带空格时不做放宽，避免「米兰」这种干净词误伤正常文本。
    """
    hits = []
    for orig, ph in sorted(rows, key=lambda x: -len(x[1])):
        if not ph:
            continue
        if ph in text:
            n = text.count(ph)
            text = text.replace(ph, orig)
            hits.append([ph, orig, n])
            continue
        if any(c.isspace() for c in ph):
            core = [c for c in ph if not c.isspace()]
            if len(core) >= 2:
                try:
                    pat = r"\s*".join(re.escape(c) for c in core)
                    text2, n = re.subn(pat, orig, text)
                except Exception:
                    continue
                if n:
                    text = text2
                    hits.append([ph, orig, n])
    return text, hits


def _auto_strip_watermark(batch, skip=False):
    """投递后自动去水印 —— **默认执行**（2026-11-11 用户要求）。

    用户原话：「去水印也加到脱敏里面，我点脱敏以后，先去水印再脱敏呗。
    默认进行这个操作，脱完以后在预览界面，用户要是发现水印去错了，
    还能自己还原一下」。

    所以流程改成：投递 → **去水印** → 脱敏 → 预览。
    原件另存到 `APP_SUPPORT/水印原件/`，撤销时用它重跑一遍（跳过去水印）。

    为什么放在这里而不是引擎里：
      · 引擎（dropbox_run.py）只管脱敏，不该知道水印这回事；
      · 原件备份要在「复制进待处理区」之后、「启动引擎」之前，正好是这一段；
      · 只有 PDF 需要处理，引擎那边没有 PDF 分支的判断入口。

    安全阀：
      · 只认 scan_pdf 的候选（已过「覆盖 ≥30% 页数」硬条件，
        正文重复词只覆盖 2~8 页，进不来）；
      · 一个文件都没命中就原样放过，不碰任何东西；
      · 任何异常只记日志、继续脱敏 —— 去水印失败不能把整批活卡住。
    """
    if skip:
        return {}
    try:
        import watermark as WM
    except Exception as e:
        _state["log"].append("去水印模块没加载（%s），本批按原样脱敏" % str(e)[:60])
        return {}

    report = {}
    bakdir = os.path.join(APP_SUPPORT, "水印原件")
    for base in list(batch):
        if os.path.splitext(base)[1].lower() != ".pdf":
            continue
        src = os.path.join(INBOX, base)
        if not os.path.exists(src):
            continue
        try:
            cands, npg = WM.scan_pdf(src)
            if not cands:
                continue
            sizes = sorted({c["size"] for c in cands})
            # 原件单独存一份：撤销时用它重跑，不能用已经去过水印的那份
            os.makedirs(bakdir, exist_ok=True)
            bak = os.path.join(bakdir, base)
            if not os.path.exists(bak):
                shutil.copy2(src, bak)
            tmp = src + ".nowm"
            cut, pages = WM.remove_pdf(src, tmp, sizes)
            if cut <= 0:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                continue
            os.replace(tmp, src)
            report[base] = {
                "cut": cut, "pages": pages, "sizes": sizes,
                "total_pages": npg,
                "sample": (cands[0].get("text") or "")[:60],
                "backup": bak,
            }
            _state["log"].append(
                "已自动去水印：%s（%d 处 / %d 页）" % (base, cut, pages))
        except Exception as e:
            _state["log"].append("去水印跳过 %s：%s" % (base, str(e)[:70]))
    return report


def run_job(files, auto_terms=True, outbox=None, task_id=None, skip_watermark=False):
    """后台线程：把文件放进待处理区，跑流水线，收集结果。

    注意顺序：必须**先把文件复制进待处理区、再清掉上一轮残留中不属于本批的文件**。
    早期版本先清空整个目录再复制，结果把刚上传到该目录的文件删掉了，
    表现为「No such file or directory」失败。
    """
    outdir = outbox or OUTBOX
    task_dir = os.path.join(PREVIEW_ROOT, task_id) if task_id else ""
    _state.update({"running": True, "cancelled": False, "log": [], "done": [], "failed": [], "started": time.time(),
                   "percent": 0, "index": 0, "current": "", "stage": "准备中", "stage_no": 1,
                   "task_id": task_id or "",
                   "watermark": {}})
    try:
        os.makedirs(INBOX, exist_ok=True)
        os.makedirs(outdir, exist_ok=True)
        if task_dir:
            os.makedirs(task_dir, exist_ok=True)

        # 本批要处理的文件名
        batch = set()
        for f in files:
            if not os.path.exists(f):
                _state["failed"].append("文件已不存在：%s" % os.path.basename(f))
                continue
            base = os.path.basename(f)
            dst = os.path.join(INBOX, base)
            # 源文件若已在待处理区，跳过复制（避免 SameFileError）
            if os.path.abspath(f) != os.path.abspath(dst):
                shutil.copy(f, dst)
            batch.add(base)
            _state["log"].append("已接收：%s" % base)

        if not batch:
            _state["failed"].append("没有可处理的文件")
            return

        # ---- 老版 .doc 先转成 .docx ----
        # .doc 是二进制格式，python-docx 读不了，整条流水线都跑不动。
        # macOS 自带 textutil，转完再走同一条路；输出统一是 .docx。
        for base in list(batch):
            if os.path.splitext(base)[1].lower() != ".doc":
                continue
            src = os.path.join(INBOX, base)
            newbase = os.path.splitext(base)[0] + ".docx"
            dst = os.path.join(INBOX, newbase)
            try:
                rc = subprocess.run(["/usr/bin/textutil", "-convert", "docx",
                                     "-output", dst, src],
                                    capture_output=True, timeout=180).returncode
                if rc != 0 or not os.path.exists(dst):
                    raise RuntimeError("textutil 返回 %s" % rc)
                batch.discard(base)
                batch.add(newbase)
                _state["log"].append("老版 .doc 已转成 .docx 再处理：%s" % base)
            except Exception as e:
                batch.discard(base)
                _state["failed"].append("%s：老版 .doc 转换失败（%s）" % (base, str(e)[:60]))

        # 复制完成后再清理上一轮的其它残留（保留本批 + 已处理子目录）
        for n in os.listdir(INBOX):
            if n in batch or n == "已处理" or n == "敏感词表.txt":
                continue
            p = os.path.join(INBOX, n)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except Exception:
                pass
        os.makedirs(os.path.join(INBOX, "已处理"), exist_ok=True)

        # ---- 自动去水印（默认执行；撤销重跑时 skip_watermark=True 跳过）----
        _wm = _auto_strip_watermark(batch, skip=skip_watermark)
        if _wm:
            _state["watermark"] = _wm
            # 落盘一份，_state 是内存的，刷新就没了；预览页要能一直看到这条提示
            if task_dir:
                try:
                    with open(os.path.join(task_dir, "watermark.json"), "w",
                              encoding="utf-8") as _f:
                        json.dump(_wm, _f, ensure_ascii=False, indent=1)
                except Exception:
                    pass

        # 上轮成品既不删除、也不搬走 —— 原样留在成品目录里，同名直接被新成品覆盖。
        # （曾经这里 os.remove 全清，把用户刚做完的成品删了；后来改成搬到「历史」子目录，
        #   用户明确说「历史文件夹没啥用」，于是干脆什么都不做。）
        # 界面只显示本批次产出的文件，靠下面的 mtime 过滤，不需要靠清空目录实现。

        # ⚡ 2026-11-06 修「导入的词表脱敏时没用上」：
        # 先算清楚这一轮**有没有用户手工词表**，这个判断决定了后面所有分支。
        # 用户自己导进来的词条就是他明确要盖的东西，优先级必须高于记忆库和模型识敏。
        _n_terms = 0
        if os.path.exists(TERMS_FILE):
            try:
                with open(TERMS_FILE, encoding="utf-8") as _tf:
                    _n_terms = sum(1 for _l in _tf
                                   if _l.strip() and not _l.strip().startswith("#"))
            except Exception:
                _n_terms = 0
        has_user_terms = _n_terms > 0
        if has_user_terms:
            shutil.copy(TERMS_FILE, os.path.join(INBOX, "敏感词表.txt"))
            _state["log"].append("已按你导入的 %d 条词表执行（不再查记忆库、不再自动识敏）"
                                 % _n_terms)

        # ---- 先查记忆库：这个案子以前脱过，就复用旧词表，跳过慢的模型识敏 ----
        # 只在**没有用户词表**时才查。原来这里没有这个条件，导致：
        #   用户导入 4 条 → 记忆库按文件名命中某个老案件（案件键里有「一卷」「购销合同」
        #   这种两三个字的通用词，几乎必中）→ 该案件没词表文件 → verify 失败 →
        #   把刚复制进来的用户词表 os.remove 掉 → 引擎报「词表：未提供」→
        #   界面上的词条一条也没用上。用户反馈原话：「界面有显示，但脱敏没用到」。
        mem_case = ""
        mem_why = ""
        try:
            if os.path.exists(MEMORY) and auto_terms and not has_user_terms:
                rc, out = _run([py_exe(), MEMORY, "recall",
                                "--file", os.path.join(INBOX, list(batch)[0])], 60)
                if rc == 0 and out.strip():
                    info = json.loads(out.strip().splitlines()[-1])
                    mem_case = info.get("case", "")
                    mem_why = info.get("reason", "")
                    mem_terms = info.get("terms", "") or ""
                    # ⚡ 2026-11-06：历史案件**没存词表**（mem_terms 为空）时，
                    # 原来会继续走 _verify_terms_cover("") → 必然 False → 被当成
                    # 「词表与该文件内容不匹配」把用户词表删掉。两件事完全不同：
                    #   没词表 = 这个案子当时就没留下词表，什么都不该动；
                    #   不匹配 = 有词表但不是这份文件的，才谈得上替换。
                    if mem_case and info.get("library", 0) > 0 and not (
                            mem_terms and os.path.exists(mem_terms)):
                        _state["log"].append(
                            "记忆库命中案件「%s」，但该案没有留下词表，忽略（不影响你导入的词表）"
                            % mem_case)
                        mem_case = ""
                    if mem_case and info.get("library", 0) > 0:
                        # 只按文件名匹配还不够，必须验证词表真能覆盖这个文件
                        # （否则会拿别的案子的词表跑，产出「看着脱敏了、其实没脱」的假成品）
                        verify_ok = _verify_terms_cover(os.path.join(INBOX, list(batch)[0]),
                                                        mem_terms)
                        if not verify_ok:
                            _state["log"].append(
                                "记忆库虽匹配到案件「%s」，但词表与该文件内容不匹配，改为重新识敏" % mem_case)
                            mem_case = ""
                            # 关键：把已经放进去的旧词表删掉，否则后面还会拿它去匹配。
                            # 但**绝不删用户自己导的** —— has_user_terms 为真时根本不会走到这里，
                            # 这里再加一道闸，防止以后有人改条件把这条保护弄丢。
                            stale = os.path.join(INBOX, "敏感词表.txt")
                            if os.path.exists(stale) and not has_user_terms:
                                try:
                                    os.remove(stale)
                                except Exception:
                                    pass
                        else:
                            # 只有验证通过才导出并复用
                            dst = os.path.join(INBOX, "敏感词表.txt")
                            rc2, o2 = _run([py_exe(), MEMORY, "export",
                                            "--case", mem_case, "--out", dst], 60)
                            m = re.search(r"已导出 (\d+) 条", o2 or "")
                            n_exp = int(m.group(1)) if m else 0
                            if n_exp >= 3:
                                auto_terms = False   # 有词表了，不用再让模型识敏
                                _state["log"].append(
                                    "记忆库命中：案件「%s」（%s），复用 %d 条词表，跳过模型识敏（几秒完成）"
                                    % (mem_case, mem_why, n_exp))
                            else:
                                mem_case = ""
                                if os.path.exists(dst):
                                    try:
                                        os.remove(dst)
                                    except Exception:
                                        pass
                                _state["log"].append(
                                    "记忆库案件「%s」可用词条不足（%d 条），改走模型识敏" % (mem_case, n_exp))
        except Exception as e:
            _state["log"].append("记忆库查询跳过：%s" % str(e)[:80])

        _ai = ai_config()
        cmd = [py_exe(), RUNNER, "--workshop", WORK, "--no-scan",
               "--inbox", "待处理", "--outbox", outdir,
               "--keydir", "对照表", "--scandir", "补漏提示"]
        # 2026-11-02 用户决定：**AI 不参与识敏**。
        # 实测它把「周军的」「周军有」这类半截词当成人名写进词表，
        # 结果脱敏越帮越乱（原话：「脱敏很多是错的，让 AI 不要参与脱敏环节」）。
        # 现在只走规则 + 词表；AI 留给「化名」和「复原猜名」两处，
        # 那两处 AI 猜错也只是建议，人还要过一眼。
        _ai_model = _ai.get("model") if _ai.get("enabled") else ""

        # 关键：让子进程**无缓冲**实时输出。
        # 否则 Python 默认块缓冲，日志攒够一批才到，界面上就是
        # 「0% 卡很久 → 突然 99% → 100%」，用户以为卡死（实测过）。
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        # 2026-11-05 用户死命令：质检不合格件也要进预览界面由本人判断。
        # 所以 DESENSITIZE_BAD_DIR 只是「原因＋原件＋台账」的留底位置，
        # 不再是成品的最终去向；dropbox_run.py 会把留底那份复制回预览任务 output，
        # 本文件扫描 OUTD 时照常为它生成 preview.json / index.json / 账本 preview 条目。
        # 质检结论只写进日志提示，绝不替使用者把文件挡在预览之外。
        env["DESENSITIZE_BAD_DIR"] = BAD_DIR
        # 子进程也用同一个解释器（分发包里就是 App 自带的那个），
        # 否则对方电脑上没有 WorkBuddy 的 venv，图片/PDF 会直接报缺库。
        try:
            env["DESENSITIZE_PYTHON"] = py_exe()
        except Exception:
            pass
        # start_new_session：让流水线自成进程组，「取消」时能整组掐断。
        # 只 terminate 直接子进程的话，它再拉起的 OCR / 模型进程会变孤儿继续跑。
        # stdin 必须显式接 /dev/null（2026-11-05 实测）：本进程若从父进程继承到
        # 已关闭的 fd 0，引擎子进程会在 init_sys_streams 阶段直接崩，
        # 表现为「投递后 0 产出、预览目录空」。
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, env=env, start_new_session=True)
        _CURRENT["proc"] = proc
        _state["total"] = len(files)
        _state["index"] = 0
        # 每个阶段的目标进度：日志一出现就推到对应百分比，
        # 不再依赖"完成一个文件"才动。否则首次识敏那几十秒里进度一直 0%，
        # 用户会以为卡死（实测 5 个文件时从 0% 直接跳到 100%）。
        _STAGE_PCT = {1: 5, 2: 25, 3: 60, 4: 85, 5: 99}
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            _state["log"].append(line)

            # ---- 实时解析进度 ----
            stage, sno, fname = _detect_stage(line, _state["total"], _state["index"])
            if stage:
                _state["stage"] = stage
                _state["stage_no"] = sno
            if fname:
                _state["current"] = fname
            # 注意 [提醒]/[质量警告] 只是提示，不算完成。
            # [闸门拦截] 必须计入——它是「本文件已处理完但不合格」，
            # 不计的话界面会卡在 99% 且文件凭空消失，用户以为程序挂了。
            if re.match(r"^\s*\[(完成|失败|跳过|闸门拦截)\]", line):
                _state["index"] = min(_state["total"], _state["index"] + 1)

            # 总进度：已完成文件占比为主，当前文件内按阶段推进
            total = max(1, _state["total"])
            base = _state["index"] / total
            inner_pct = _STAGE_PCT.get(_state["stage_no"], 5) / 100.0
            step = (1.0 / total) * inner_pct
            pct = int(round(min(0.99, base + step) * 100))
            # 进度只能前进不能倒退（日志里阶段可能来回跳）
            _state["percent"] = max(_state["percent"], pct)
        proc.wait()
        _CURRENT["proc"] = None

        if _state.get("cancelled"):
            _state["stage"] = "已取消"
            _state["log"].append("任务已取消，未完成的产物不会计入本次结果")
            return

        # 收集成品（成品目录即文稿/立丰脱敏/成品）
        # 只收本批次产出的：按修改时间过滤，早于本次开始时间的属上一批，
        # 留着但不显示（成品不能删，界面也不能把旧成品当成本次结果）。
        if os.path.isdir(outdir):
            t0 = float(_state.get("started") or 0) - 3
            for n in sorted(os.listdir(outdir)):
                p = os.path.join(outdir, n)
                if not os.path.isfile(p) or n.startswith("."):
                    continue
                try:
                    if t0 and os.path.getmtime(p) < t0:
                        continue
                except Exception:
                    pass
                _state["done"].append({"name": n, "path": p,
                                       "size": os.path.getsize(p)})
        # ---- 学习：把本次的对照关系存进记忆库，下次同类案子直接复用 ----
        try:
            if os.path.exists(MEMORY):
                keysdir = os.path.join(WORK, "对照表")
                case = ""
                for f in files:
                    b = os.path.basename(f)
                    stem = os.path.splitext(b)[0]
                    case = _case_key(stem)
                    break
                learned = 0
                if os.path.isdir(keysdir):
                    for n in os.listdir(keysdir):
                        if not n.endswith("_映射表.csv"):
                            continue
                        mp = os.path.join(keysdir, n)
                        rc, out = _run([py_exe(), MEMORY, "add", "--case", case, "--map", mp], 120)
                        m = re.search(r"新增 (\d+) 条", out or "")
                        if m:
                            learned += int(m.group(1))
                        # 也从自动识敏词表学
                        stem2 = n[:-len("_映射表.csv")]
                        auto_t = os.path.join(keysdir, "本案词表-%s" % stem2)
                        for an in os.listdir(keysdir):
                            if an.startswith("本案词表-") and stem2[:12] in an:
                                rc2, o2 = _run([py_exe(), MEMORY, "add", "--case", case,
                                                "--terms", os.path.join(keysdir, an)], 120)
                                m2 = re.search(r"新增 (\d+) 条", o2 or "")
                                if m2:
                                    learned += int(m2.group(1))
                if learned:
                    _state["log"].append("已学习 %d 条到记忆库（下次同类案子会更快）" % learned)
                # 登记案件
                _run([py_exe(), MEMORY, "case", "--case", case] +
                     sum([["--file", f] for f in files], []), 60)
        except Exception as e:
            _state["log"].append("记忆库学习失败：%s" % e)

        # ---- 预览模式：为成品生成浏览数据（每个文件独立子目录）----
        # 2026-10-30 修：原来所有文件都往同一个 task_dir 写，
        # 实测提交两个文件时成品两份都在，preview.json 只剩最后一份，
        # 第一个文件的预览凭空消失，历史里也只剩一条 —— 这就是「浏览失败」的主因。
        auto_saved = []
        if task_dir and _state["done"]:
            index = []
            try:
                import preview_build as PB
                import history_store as HS
                for i, item in enumerate(_state["done"], 1):
                    stem = os.path.splitext(item["name"])[0]
                    src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
                    map_csv = os.path.join(KEYS, "%s_映射表.csv" % src_stem)
                    orig = ""
                    # 先看待处理区里的同名 docx —— .doc 转换后的文件就在这里，
                    # 拿原始 .doc 去建预览必失败（python-docx 读不了老格式）
                    for _cand in (os.path.join(INBOX, src_stem + ".docx"),
                                  os.path.join(INBOX, "已处理", src_stem + ".docx")):
                        if os.path.exists(_cand) and not orig:
                            orig = _cand
                    for f in files:
                        if orig:
                            break
                        if os.path.splitext(os.path.basename(f))[0] == src_stem:
                            orig = f
                            break
                    if not orig:
                        cand = os.path.join(INBOX, "已处理", os.path.basename(src_stem))
                        orig = cand if os.path.exists(cand) else ""

                    # ⚡ 2026-11-18 修「任务不能预览也不能导出」：
                    # 成品文件名本身也会被词表脱敏（实测「某某集团…」→「某 某集团…」），
                    # 于是 src_stem 拿脱敏名去 已处理/ 找原件，永远找不到 →
                    # orig="" → 不生成 preview.json → /api/preview 报「任务不存在」→
                    # 预览打不开、导出按钮也就无从点起。而成品和原件其实都好好在盘上。
                    #
                    # 兜底：按**正文段落交集**在「已处理」区精确配对。
                    # 脱敏只改命中的词，未命中的整段原文一字不动，
                    # 所以正确配对的段落交集 0.3~0.8，配错的必然是 0（实测三个文件全分离）。
                    # 注意不能按序号猜 done↔files 的对应：接收顺序和处理顺序未必一致。
                    if not orig:
                        _by_content = _find_orig_by_content(item["path"])
                        if _by_content:
                            orig = _by_content
                            _state["log"].append(
                                "原件按正文配对找回：%s ← %s"
                                % (item["name"][:30], os.path.basename(_by_content)[:30]))

                    fdir = os.path.join(task_dir, "files", str(i))
                    auto_done = False
                    meta_pv = {"file": os.path.basename(orig) or (src_stem + ".docx"),
                               "count": 0, "by_category": {}, "blocks": []}
                    if orig:
                        try:
                            meta_pv = PB.build_preview(orig, item["path"], map_csv, fdir,
                                                       os.path.basename(orig))
                            # build_preview 返回的 meta 里没有 file 字段（它在 preview.json 里），
                            # 不补的话预览页的文件切换器会显示「未命名」
                            meta_pv["file"] = os.path.basename(orig)
                        except Exception as e:
                            _state["log"].append("预览生成失败（%s）：%s"
                                                 % (item["name"], str(e)[:100]))
                            # 【2026-11-02 用户报「成品文件夹里没内容」】
                            # PDF/图片没有 docx 那套段落结构，预览建不出来；
                            # 以前只记一行日志，成品留在预览任务目录里等用户点导出，
                            # 可他既看不到预览、又不知道要导出，成品目录自然一直是空的。
                            # 预览不了就直接交付：复制进成品文件夹，并明确写进日志。
                            try:
                                os.makedirs(OUTBOX, exist_ok=True)
                                dst = os.path.join(OUTBOX, item["name"])
                                # 2026-11-05 用户死命令：成品一律留在预览任务，等本人点导出。
                                # 原来这里 copy 进成品区并把账本直接写成 exported，
                                # 等于绕过人工确认——PDF 预览必失败，每次都会中招。
                                _state["log"].append(
                                    "该格式没有逐页预览，成品仍在预览任务里，请核对后手动点「导出到成品文件夹」：%s"
                                    % item["name"])
                            except Exception as e2:
                                _state["log"].append("预览失败处理异常：%s" % str(e2)[:100])
                    else:
                        _state["log"].append("预览数据跳过：找不到原件 %s" % src_stem)

                    meta_pv["output_path"] = item["path"]
                    meta_pv["preview_path"] = item["path"]
                    meta_pv["task_id"] = task_id
                    meta_pv["index"] = i

                    # 账本：即便预览失败也要记一条 —— 复原只需要映射表，不需要预览。
                    # 这一步同时把映射表冻结下来，后面「一键复原」才敢用。
                    try:
                        ent = HS.add_entry(task_id=task_id, index=i,
                                           source=os.path.basename(orig) or (src_stem + ".docx"),
                                           output_name=item["name"],
                                           output_path=item["path"],
                                           preview_path=item["path"],
                                           count=meta_pv.get("count", 0),
                                           by_category=meta_pv.get("by_category", {}),
                                           map_csv=map_csv,
                                           status=("exported" if auto_done else "preview"))
                        meta_pv["entry_id"] = ent["id"]
                        meta_pv["map_count"] = ent.get("map_count", 0)
                    except Exception as e:
                        _state["log"].append("账本写入失败：%s" % str(e)[:100])

                    try:
                        os.makedirs(fdir, exist_ok=True)
                        with open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8") as _f:
                            json.dump(meta_pv, _f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    # output_name 必须写进去：导出时靠它把成品和「这一份的标记」对上，
                    # 漏了就会 marks_applied=0，标记静默失效（2026-10-30 实测）
                    meta_pv["output_name"] = item["name"]
                    index.append({k: meta_pv.get(k) for k in
                                  ("index", "file", "count", "by_category",
                                   "entry_id", "output_name")})
                    _state["log"].append("预览已生成：%s，%d 处替换"
                                         % (meta_pv.get("file", ""), meta_pv.get("count", 0)))
                with open(os.path.join(task_dir, "index.json"), "w", encoding="utf-8") as _f:
                    json.dump({"task_id": task_id, "files": index}, _f,
                              ensure_ascii=False, indent=2)
            except Exception as e:
                _state["log"].append("预览数据生成失败：%s" % str(e)[:140])
            if auto_saved:
                _state["log"].append("有 %d 份成品无法预览，已直接放入成品文件夹" % len(auto_saved))

        if not _state["done"]:
            # 全是「被闸门拦下」时，不能只说「没有生成成品」——用户会以为程序坏了。
            # 如实告诉他：文件在，只是没过质检，去哪儿处理。
            n_bad = 0
            try:
                import reject_store as _RS
                t0 = time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(float(_state.get("started") or 0) - 3))
                n_bad = len([r for r in _RS.load_records(OUTBOX)
                             if r.get("status") == "pending" and r.get("ts", "") >= t0])
            except Exception:
                n_bad = 0
            if n_bad:
                _state["failed"].append("有 %d 份未通过质检，已在「未通过质检」里列出，"
                                        "可直接重脱或查看原因" % n_bad)
            else:
                _state["failed"].append("没有生成成品，请查看下方处理日志")
    except Exception as e:
        _state["failed"].append(str(e))
    finally:
        _state["running"] = False
        # 结束：有成品就是 100%，失败则停在当前进度（让用户看出没走完）
        if _state["done"]:
            _state["percent"] = 100
            _state["stage"] = "全部完成"
        else:
            _state["stage"] = _state["stage"] or "未生成成品"


def rejected_items():
    """读「不合格」台账，折叠成当前状态列表。"""
    try:
        import reject_store as RS
        return RS.load_records(OUTBOX)
    except Exception:
        return []


def run_retry(rec_id):
    """重脱一份被闸门拦下的成品。

    原料是拦截时留底的原件（不合格/原件/），走的是同一条流水线，
    所以词表、规则、识别方式与首次完全一致——用户改了规则再点，
    生效的正是新规则，不需要他记得当初用了什么参数。
    """
    try:
        import reject_store as RS
    except Exception as e:
        return {"ok": False, "msg": "台账模块不可用：%s" % str(e)[:120]}

    rec = None
    for it in RS.load_records(OUTBOX):
        if it.get("id") == rec_id:
            rec = it
            break
    if not rec:
        return {"ok": False, "msg": "找不到这条记录"}

    orig = os.path.join(BAD_DIR, rec.get("orig_rel") or "")
    if not rec.get("orig_rel") or not os.path.exists(orig):
        RS.update(OUTBOX, rec_id, "retry", ok=False, note="原件缺失")
        return {"ok": False, "msg": "原件已不在「不合格/原件」里，无法重脱；"
                                    "请把原文件重新拖进来处理一次"}

    t0 = time.time()
    try:
        # 有词表就沿用（快且口径一致），没有才让模型重新识敏
        run_job([orig], not os.path.exists(TERMS_FILE))
    except Exception as e:
        RS.update(OUTBOX, rec_id, "retry", ok=False, note=str(e)[:200])
        return {"ok": False, "msg": "重脱失败：%s" % str(e)[:160]}

    out_path = os.path.join(OUTBOX, rec.get("output") or "")
    ok = bool(rec.get("output")) and os.path.exists(out_path) and os.path.getmtime(out_path) >= t0 - 2
    RS.update(OUTBOX, rec_id, "retry", ok=ok,
              note="" if ok else "仍未通过质检：" + (rec.get("why") or "")[:160])

    if ok:
        # 旧的不合格件挪进历史：界面上只留「已重脱」这一条，成品区才是唯一真相
        try:
            sub = os.path.join(BAD_DIR, "历史", time.strftime("%Y%m%d-%H%M%S"))
            os.makedirs(sub, exist_ok=True)
            stem = rec.get("stem") or ""
            for fn in (rec.get("output"), ("%s_原因.txt" % stem) if stem else ""):
                p = os.path.join(BAD_DIR, fn or "")
                if fn and os.path.exists(p):
                    shutil.move(p, os.path.join(sub, fn))
        except Exception:
            pass
        return {"ok": True, "msg": "已重新脱敏并通过质检：%s" % (rec.get("output") or "")}
    return {"ok": False, "msg": "重脱完成但仍未通过质检，原因已更新"}


def sync_failed_state():
    """放行之后，把「未通过质检」这条提示从状态里撤掉。

    用户原话（2026-11-02）：「不合格品变成合格以后提示也不要出来」。
    以前这条提示一旦写入就永远留着，界面每 25 秒轮询一次 → 每 25 秒弹一次窗，
    弹到人想把 App 关了。现在没有待处理的不合格件，就不再算失败。
    """
    try:
        import reject_store as RS
        recs = RS.load_records(OUTBOX)
        pending = [r for r in recs if r.get("status") == "pending"]
        if not pending:
            _state["failed"] = [f for f in _state.get("failed", []) if "未通过质检" not in f]
    except Exception:
        pass


def accept_rejected(rid, note=""):
    """把一份不合格件放行：成品进成品区，旧件与原因说明归档，界面不再显示。

    用户场景（2026-11-02）：手动涂黑/手动标记改完之后，这份就该算合格，
    不能再躺在「不合格」里让人以为还有事没做。
    """
    try:
        import reject_store as RS
    except Exception as e:
        return {"ok": False, "msg": "台账模块不可用：%s" % str(e)[:100]}
    rec = None
    for it in RS.load_records(OUTBOX):
        if it.get("id") == rid:
            rec = it
            break
    if not rec:
        return {"ok": False, "msg": "找不到这条记录"}

    moved = []
    out_name = rec.get("output") or ""
    src = os.path.join(BAD_DIR, out_name)
    dst = os.path.join(OUTBOX, out_name)
    if out_name and os.path.exists(src):
        try:
            if not os.path.exists(dst):
                shutil.move(src, dst)
            else:
                sub = os.path.join(BAD_DIR, "历史", time.strftime("%Y%m%d-%H%M%S"))
                os.makedirs(sub, exist_ok=True)
                shutil.move(src, os.path.join(sub, out_name))
            moved.append(out_name)
        except Exception:
            pass
    stem = rec.get("stem") or ""
    if stem:
        rp = os.path.join(BAD_DIR, "%s_原因.txt" % stem)
        if os.path.exists(rp):
            try:
                sub = os.path.join(BAD_DIR, "历史", time.strftime("%Y%m%d-%H%M%S"))
                os.makedirs(sub, exist_ok=True)
                shutil.move(rp, os.path.join(sub, os.path.basename(rp)))
            except Exception:
                pass
    try:
        RS.update(OUTBOX, rid, "accept", ok=True, note=note or "人工确认后放行")
    except Exception:
        pass
    sync_failed_state()

    # 写进「最近脱敏」：这份改好了，要在记录里显示为「合格」，不能凭空消失
    # （用户原话：2026-11-02「记录直接消失了，而不是在生成记录里面显示合格」）
    try:
        import history_store as HS
        task_id = "rej-%s" % rid
        dst = os.path.join(OUTBOX, out_name) if out_name else ""
        ent = HS.update_by_task(task_id, out_name, status="accepted",
                                output_path=dst,
                                exported_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        if not ent:
            src_name = rec.get("source") or out_name
            stem = rec.get("stem") or os.path.splitext(out_name)[0]
            map_csv = ""
            for cand in ("%s_映射表.csv" % os.path.splitext(src_name)[0],
                         "%s_映射表.csv" % stem):
                p2 = os.path.join(KEYS, cand)
                if os.path.exists(p2):
                    map_csv = p2
                    break
            HS.add_entry(task_id=task_id, index=1, source=src_name,
                         output_name=out_name, output_path=dst,
                         map_csv=map_csv, status="accepted", preview_path=dst)
    except Exception:
        pass
    return {"ok": True, "moved": moved, "name": out_name}


def build_review_task(rec):
    """把「不合格」的成品直接做成一个预览任务，让用户自己勾。

    关键区别（2026-10-31 用户纠正）：
        以前「手动处理」= 拿原件再跑一遍流水线，跑完还是同一份结果、还是不合格，
        用户白等十几分钟，什么也没改到。
        真正的需求是「打开这份失败的文件，我自己挑哪儿要脱」——所以这里**不跑引擎**，
        直接把不合格成品拿来生成预览数据，进预览页手动标记、导出覆盖。

    只支持 docx：预览页是按段落/表格文字渲染的，扫描件 PDF 没有可点的文字。
    """
    import preview_build as PB
    import history_store as HS

    rid = rec.get("id") or ""
    task = "rej-%s" % rid
    tdir = os.path.join(PREVIEW_ROOT, task)
    fdir = os.path.join(tdir, "files", "1")
    outd = os.path.join(tdir, "output")

    out_src = os.path.join(BAD_DIR, rec.get("output") or "")
    orig = os.path.join(BAD_DIR, rec.get("orig_rel") or "")
    if not rec.get("output") or not os.path.exists(out_src):
        return {"ok": False, "msg": "不合格成品已不在，无法打开"}
    if not rec.get("orig_rel") or not os.path.exists(orig):
        return {"ok": False, "msg": "原件已不在，无法对照生成预览"}
    if os.path.splitext(out_src)[1].lower() not in (".docx", ".docm"):
        # 扫描件/PDF 没有可点的文字层，给了预览也勾不了
        subprocess.run(["/usr/bin/open", "-R", out_src], capture_output=True)
        return {"ok": False, "msg": "这份是 PDF/扫描件，暂时只能逐页看、不能逐处勾选。"
                                    "已在访达里定位到文件，建议补词表后按规则重脱。"}

    for d in (fdir, outd):
        os.makedirs(d, exist_ok=True)
    # 每次重开都从"当前的不合格成品"重新生成，避免上次的旧标记串进来
    for junk in ("marks.json", "preview.json", "origs.json", "meta.json"):
        p = os.path.join(fdir, junk)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    dst = os.path.join(outd, os.path.basename(out_src))
    shutil.copy2(out_src, dst)

    # 映射表命名不统一：批量里可能按源文件名存，也可能按「_已脱敏」后的名字存。
    # 猜错就整份预览没有一个高亮（count=0），用户看不到"哪些已经脱过了"，等于白开。
    map_csv = ""
    stems = []
    for k in ("stem", "output", "source"):
        v = rec.get(k) or ""
        if v:
            stems.append(os.path.splitext(os.path.basename(v))[0])
    for st in stems:
        for cand in ("%s_映射表.csv" % st, "%s_映射表.csv" % st.replace("_已脱敏", "")):
            p = os.path.join(KEYS, cand)
            if os.path.exists(p):
                map_csv = p
                break
        if map_csv:
            break
    meta = PB.build_preview(orig, dst, map_csv, fdir, os.path.basename(orig))
    meta["file"] = os.path.basename(orig)
    meta.update({"output_path": dst, "preview_path": dst,
                 "task_id": task, "index": 1,
                 "output_name": os.path.basename(out_src)})

    # 账本：导出后要能复原，映射表必须跟着这一条冻结
    try:
        ent = HS.add_entry(task_id=task, index=1,
                           source=os.path.basename(orig),
                           output_name=os.path.basename(out_src),
                           output_path=dst, preview_path=dst,
                           count=meta.get("count", 0),
                           by_category=meta.get("by_category", {}),
                           map_csv=map_csv, status="preview")
        meta["entry_id"] = ent["id"]
        meta["map_count"] = ent.get("map_count", 0)
    except Exception:
        pass

    with open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(tdir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"task_id": task,
                   "files": [{k: meta.get(k) for k in
                              ("index", "file", "count", "by_category",
                               "entry_id", "output_name")}]},
                  f, ensure_ascii=False, indent=2)
    return {"ok": True, "task_id": task}


def _paint_dir(task):
    """涂黑任务目录，只接受 paint- 开头且必须是纯文件名（防路径穿越）。"""
    task = os.path.basename(str(task or ""))
    if not task.startswith("paint-"):
        return ""
    return os.path.join(PAINT_ROOT, task)


def _paint_build(src, task, record_id=""):
    """把一份 PDF/图片复制成涂黑任务；返回 (结果字典, 是否成功)。"""
    import pymupdf
    ext = os.path.splitext(src)[1].lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        return {"ok": False, "msg": "这种格式不能涂黑（只支持 PDF 与图片）"}
    tdir = _paint_dir(task)
    for d in (tdir, os.path.join(tdir, "pages")):
        os.makedirs(d, exist_ok=True)
    dst = os.path.join(tdir, "source" + ext)
    shutil.copy2(src, dst)

    pages = []
    if ext == ".pdf":
        doc = pymupdf.open(dst)
        for i in range(len(doc)):
            r = doc[i].rect
            pages.append({"n": i + 1, "w": round(r.width, 2), "h": round(r.height, 2)})
        doc.close()
        kind = "pdf"
    else:
        from PIL import Image
        with Image.open(dst) as im:
            w, h = im.size
        pages.append({"n": 1, "w": w, "h": h})
        kind = "image"

    meta = {"task": task, "name": os.path.basename(src), "kind": kind,
            "pages": pages, "source": dst,
            # 记下原件：清理自动涂黑要靠它按坐标回贴（涂黑是破坏性的，文字已删）
            "orig": _find_original(os.path.basename(src)) or "",
            "record_id": record_id, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(tdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(tdir, "boxes.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    return {"ok": True, "task_id": task, "kind": kind, "name": meta["name"],
            "pages": pages}


def paint_init(rec):
    """从「不合格」的成品开一个涂黑任务。

    为什么单独一套：PDF/扫描件是整页图片，没有文字可选中，
    预览页那套「选中文字→标记」根本点不动，只能让人在页面上拉框涂黑。
    """
    src = os.path.join(BAD_DIR, rec.get("output") or "")
    if not rec.get("output") or not os.path.exists(src):
        return {"ok": False, "msg": "不合格成品已不在，无法打开"}
    task = "paint-%s" % (rec.get("id") or time.strftime("%Y%m%d-%H%M%S"))
    return _paint_build(src, task, rec.get("id") or "")


def paint_from_task(task, fno="1"):
    """从「已经合格」的成品开涂黑任务。

    用户的要求（2026-11-02）：合格了也要能手动改，不能只有被拦下的文件才给工具。
    这里直接拿任务里的**成品**当底图——他看到的、要涂的，正是准备交付的那份。
    """
    base = os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")))
    outd = os.path.join(base, "output")
    if task and not os.path.isdir(outd):
        # 2026-11-07：预览任务被清过 → 按账本重建后再开涂黑任务，
        # 否则用户看到「任务不存在或已过期」，而他手上那份成品是好的
        if revive_task_from_ledger(task):
            outd = os.path.join(base, "output")
    if not task or not os.path.isdir(outd):
        return {"ok": False, "msg": "任务不存在或已过期（成品可从成品文件夹直接打开）"}
    name = ""
    ip = os.path.join(base, "index.json")
    try:
        with open(ip, encoding="utf-8") as f:
            data = json.load(f)
        want = int(fno or 1)
        for it in data.get("files", []):
            if int(it.get("index") or 1) == want:
                name = it.get("output_name") or ""
                break
    except Exception:
        pass
    if not name:
        cand = [x for x in sorted(os.listdir(outd)) if not x.startswith(".")]
        name = cand[0] if cand else ""
    src = os.path.join(outd, name)
    if not name or not os.path.exists(src):
        return {"ok": False, "msg": "这份成品还没生成，稍后再试"}
    # 已经为这份成品开过涂黑任务 → 直接复用，别拿「已涂黑」的成品再开一个。
    # 否则第二次打开看到的是烧过框的图，想删都删不掉（2026-11-02 用户反馈）。
    try:
        for d in os.listdir(PAINT_ROOT):
            mp = os.path.join(PAINT_ROOT, d, "meta.json")
            if not os.path.exists(mp):
                continue
            try:
                with open(mp, encoding="utf-8") as f:
                    mm = json.load(f)
            except Exception:
                continue
            if mm.get("name") == name and os.path.isdir(os.path.join(PAINT_ROOT, d)):
                return {"ok": True, "task_id": d, "kind": mm.get("kind"),
                        "name": mm.get("name"), "pages": mm.get("pages") or [],
                        "reused": True}
    except Exception:
        pass

    suffix = re.sub(r"[^0-9A-Za-z\-]", "", os.path.basename(str(task)))
    return _paint_build(src, "paint-t%s-%s" % (suffix, int(fno or 1)), "")


def _find_original(name):
    """按成品名找回原件（去掉 _已脱敏 后缀）。

    清理自动涂黑的前提：原件还在。涂黑是破坏性的（文字被真删），
    想撤掉某一块只能用原件那块区域盖回去。
    """
    if not name:
        return ""
    stem, ext = os.path.splitext(name)
    for suf in ("_已脱敏", "_已还原"):
        if stem.endswith(suf):
            stem = stem[:-len(suf)]
    cands = [
        os.path.join(INBOX, stem + ext),
        os.path.join(INBOX, "已处理", stem + ext),
    ]
    # 有的原件是 .doc/.docx 转过来的，名字可能带括号变体，退一步模糊匹配
    for c in cands:
        if os.path.exists(c):
            return c
    try:
        for d in (INBOX, os.path.join(INBOX, "已处理")):
            if not os.path.isdir(d):
                continue
            for n in os.listdir(d):
                if os.path.splitext(n)[0] == stem and os.path.splitext(n)[1].lower() == ext.lower():
                    return os.path.join(d, n)
    except Exception:
        pass
    return ""


def _find_orig_by_content(red_docx):
    """成品文件名被词表脱敏后，在「已处理」区找回原件。

    2026-11-18 事故：词表里有 `某省=某某`、`某某=某某`，引擎的 safe_stem()
    会把**文件名**也脱敏（这是 2026-11-06 的既定行为，为了成品名不泄露真名），
    于是按成品名反推的 src_stem 在 已处理/ 里永远找不到 →
    preview.json 不生成 → 预览页「任务不存在」、导出无从点起。

    判据（按可靠性排序）：
      1. **段落数 + 表格数完全相等** —— 脱敏只改文字，不增删段落/表格，
         实测三份材料 70/57/52 段各自唯一，一次就能分开；
      2. 并列时用**正文段落交集**排序 —— 未命中词的长段落一字不动；
      3. 再并列用**总字符数最接近**兜底。
    单凡不能唯一确定的，宁可返回空，也不能把 A 的原件配给 B（会显示出别人的原文）。
    """
    try:
        import docx as _dx

        def _stats(p):
            try:
                d = _dx.Document(p)
                paras = [x.text for x in d.paragraphs]
                return {"np": len(paras), "nt": len(d.tables),
                        "chars": sum(len(x) for x in paras),
                        "long": {x.strip() for x in paras if len(x.strip()) > 15}}
            except Exception:
                return None

        red = _stats(red_docx)
        if not red:
            return ""
        pd = os.path.join(INBOX, "已处理")
        if not os.path.isdir(pd):
            return ""
        cands = []
        for n in os.listdir(pd):
            if not n.lower().endswith(".docx") or n.startswith("."):
                continue
            st = _stats(os.path.join(pd, n))
            if not st:
                continue
            if st["np"] != red["np"] or st["nt"] != red["nt"]:
                continue
            inter = len(red["long"] & st["long"]) / max(1, min(len(red["long"]), len(st["long"])))
            cands.append((inter, -abs(st["chars"] - red["chars"]),
                          os.path.join(pd, n)))
        if not cands:
            return ""
        cands.sort(reverse=True)
        # 唯一候选直接用；多个并列时至少要有一项能分开，否则不猜
        if len(cands) == 1:
            return cands[0][2]
        if cands[0][:2] > cands[1][:2]:
            return cands[0][2]
        return ""
    except Exception:
        return ""


def _norm_text(t):
    """归一化原文，用于"同内容"判定：去掉所有空白与换行。"""
    return "".join((t or "").split())


def _fw2hw(t):
    """全角转半角：OCR/文字层经常混着来，不统一就分不成一组。"""
    out = []
    for ch in t or "":
        c = ord(ch)
        if 0xFF01 <= c <= 0xFF5E:
            out.append(chr(c - 0xFEE0))
        elif c == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _fuzzy_key(t):
    """把一段被遮住的文字压成"可比对"的形式：去空白、全角转半角、去标点。"""
    s = _fw2hw(_norm_text(t))
    s = re.sub(r"[，。、；：！？（）()《》〈〉“”\"'·—\-_/\\|]+", "", s)
    return s


def _lcs_len(a, b):
    """最长公共子串长度。用于判断两段文字是不是"同一段被切开的"。"""
    if not a or not b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    best = 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                v = prev[j - 1] + 1
                cur[j] = v
                if v > best:
                    best = v
        prev = cur
    return best


def _cluster_texts(texts):
    """把"其实是同一段内容、只是被黑块截得不一样"的归并成一组。

    为什么必须做：同一段水印在不同页被切成
        '张律师000000000000000000湖北立丰律师事务所'
        '0000000000000湖北立丰律师事务所'
        '202011201303湖北立丰律师事务所'
    按原文精确分组就是十几个组，用户得挨个清（2026-11-03 实反馈）。

    做法分两步，缺一不可：
      1. 8-gram 倒排只在候选之间比对（全量两两比是 O(n²)，1055 组会卡死）；
      2. 候选再验"最长公共子串 ≥ 较短串的 70%"，才合并。
    只做第一步会误并 —— 实测中文里 8 个字的巧合太多，
    整份 1220 块曾被并成一组（2026-11-03 踩过）。
    """
    keys = list(texts.keys())
    norm = {}
    for k in keys:
        v = texts[k]
        norm[k] = _fuzzy_key(v[0] if isinstance(v, list) else v)

    parent = {k: k for k in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # 第一步：8-gram 生成候选对（不做合并，只缩小范围）
    idx = {}
    cand = set()
    for k in keys:
        nk = norm[k]
        if not nk:
            continue
        grams = {nk} if len(nk) <= 8 else {nk[i:i + 8] for i in range(len(nk) - 7)}
        for g in grams:
            prev = idx.get(g)
            if prev is None:
                idx[g] = k
            else:
                pair = (prev, k) if prev < k else (k, prev)
                cand.add(pair)

    # 第二步：候选里按"长公共子串占比"确认，够像才合并
    for a, b in cand:
        na, nb = norm[a], norm[b]
        if not na or not nb:
            continue
        short = min(len(na), len(nb))
        if short < 4:                     # 太短的串（如"男"）不做模糊匹配
            continue
        need = max(6, int(short * 0.7))
        if _lcs_len(na, nb) >= need:
            union(a, b)

    out = {}
    for k in keys:
        out.setdefault(find(k), []).append(k)
    return list(out.values())


def _spot_sig(it, tol=40.0):
    """把一个黑块压成「位置签名」，同一签名＝同一位置。

    只按**位置**分桶，不看尺寸。为什么不看尺寸：
    同一枚水印在不同页的框大小会差（实测 277 / 279 / 314pt 都有），
    把尺寸也算进签名，同一位置就裂成好几组，用户还得多点几次（2026-11-03 实测 258→143 组）。

    为什么不用绝对坐标取整：每页尺寸不一样（1240~1247pt），同一位置的绝对坐标差十几 pt。
    所以先换算成「占页面的千分比」再按 tol 分桶。

    tol 取 40（约页宽 3.3%）：实测同一枚水印在不同页会落在 y=440 / 448 / 482，
    差 42pt，桶太小就分家。

    返回 (bx, by, gid)，都是签名单位，**不是坐标**——本页真实坐标要读 items。
    """
    try:
        w = float(it.get("pw") or 0) or 1.0
        h = float(it.get("ph") or 0) or 1.0
        x0, y0 = float(it["x0"]), float(it["y0"])
    except Exception:
        return (0, 0, "0")
    bx = int(round(x0 / w * 1000 / tol))
    by = int(round(y0 / h * 1000 / tol))
    gid = hashlib.md5(("%d|%d" % (bx, by)).encode("utf-8")).hexdigest()[:10]
    return (bx, by, gid)


def _group_by_content(spots, min_len=8, min_ratio=0.55):
    """把「遮黑内容其实是一回事」的位置组归成一族，返回 [[位置组下标...], ...]。

    用户要的是"相同遮黑的内容全部删除"（2026-11-03），不是"同一位置"。
    一枚水印被黑块切成十几段文字、又平铺在页面 6 个角落 —— 按位置分是十几个组，
    按内容归才是一组，点一次才清得干净。

    判据用的是「短串是长串的连续子串」，而不是模糊相似度：
      被黑块切断只会产生原文的子串（'…立丰律师事务所' ⊂ '张律师1101…立丰律师事务所'），
      不会凭空造出新内容；所以子串判据既能把碎片归族，又不会把压在水印下面的正文串进来。
    模糊相似度实测会把 '本卷材料为王某某涉嫌贪污…' 这类正文并进 997 块的水印族
    （2026-11-03 踩过），不能用。

    min_ratio=0.55：短串至少占长串一半才算同一处内容，
    否则 '湖' 这种单字碎片会把不相干的位置全串起来。
    """
    keys = [_fuzzy_key(sp.get("text") or "") for sp in spots]
    parent = list(range(len(spots)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    n = len(spots)
    for i in range(n):
        a = keys[i]
        if len(a) < min_len:
            continue
        for j in range(i + 1, n):
            b = keys[j]
            if len(b) < min_len:
                continue
            if a == b:
                union(i, j)
                continue
            short, lng = (a, b) if len(a) <= len(b) else (b, a)
            if short in lng and len(short) >= len(lng) * min_ratio:
                union(i, j)

    fams = {}
    for i in range(n):
        fams.setdefault(find(i), []).append(i)
    return list(fams.values())


def paint_auto_scan(task, use_cache=True):
    """扫描整份 PDF 的自动黑块，按「同一枚水印/同一段文字」分组。

    分组要解决两层问题，只做一层都不够：
      1. **水印被黑块切碎**：同一枚水印在页面上被切成
         '张律师000000000000000000湖北立丰律师事务所' / '0000000000000湖北立丰律师事务所'
         / '00000000000000湖北立丰律师事务所' 等十几个不同文字，按原文精确分组
         永远是十几组，用户得挨个清（2026-11-03 实测 1055 组）。
      2. **同一枚水印平铺在多处**：它每页固定出现在 6 个角落，按位置分组又会把
         一枚水印拆成 6 组，用户还得点 6 次。

    做法：先按「位置+尺寸」把碎块收拢，再用 _cluster_texts 按文字相似度把
    "其实是一回事"的几个位置合族。落盘时给出「位置组」明细，方便按页高亮。
    实测 129 页 1325 块 → 105 族 / 142 位置，水印那一族 1016 块 / 129 页，
    点一次清完全文（2026-11-03）。
    """
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("kind") != "pdf":
        return {"ok": True, "groups": [], "note": "图片没有可分离的黑块"}
    src = meta["source"]
    orig = meta.get("orig") or _find_original(meta.get("name") or "")
    cp = os.path.join(tdir, "auto_scan.json")
    stamp = None
    try:
        st = os.stat(src)
        stamp = "%d-%d" % (int(st.st_mtime), st.st_size)
    except Exception:
        stamp = None
    if use_cache and stamp and os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("stamp") == stamp:
                return cached.get("data") or {"ok": True, "groups": []}
        except Exception:
            pass

    if not orig or not os.path.exists(orig):
        return {"ok": False,
                "msg": "找不到原件，无法按内容分组（清理会把原文贴回来，必须有原件）"}

    doc = pymupdf.open(src)
    odoc = pymupdf.open(orig)
    groups = {}
    try:
        for pno in range(len(doc)):
            pg = doc[pno]
            # 记下页宽高：不同页尺寸不一致，位置聚类必须先换算成比例。
            # 这里必须用 pg.rect（已随 rotation 转正），并且和下面 items 里的
            # 坐标保持同一套基准 —— 全都用「视觉坐标」。
            # 为什么（2026-11-05）：get_drawings 吐的是底层坐标，rotation=270 的页
            # 底层是 842x595、视觉是 595x842，拿底层 x 除以视觉宽算出来的比例是错的，
            # 同一枚水印会被拆成好几族，前端高亮也会画到页外。
            _pr = pg.rect
            _pw, _ph = round(_pr.width, 2), round(_pr.height, 2)
            for dr in pg.get_drawings():
                f = dr.get("fill")
                if not f or any(c > 0.06 for c in f):
                    continue
                r = dr.get("rect")
                if not r or r.width < 6 or r.height < 3:
                    continue
                try:
                    # 取文字必须用底层坐标（get_text 不认旋转）
                    txt = odoc[pno].get_text("text", clip=r)
                except Exception:
                    txt = ""
                nt = _norm_text(txt)
                key = nt if nt else "∅%d-%d" % (pno + 1, int(r.y0))
                g = groups.setdefault(key, {"text": nt[:120], "items": []})
                # 存视觉坐标：前端在渲染图上画高亮，server 端清理时再换回底层
                rv = _page_box_to_vis(pg, r)
                g["items"].append({"page": pno + 1,
                                   "pw": _pw, "ph": _ph,
                                   "x0": round(rv.x0, 2), "y0": round(rv.y0, 2),
                                   "x1": round(rv.x1, 2), "y1": round(rv.y1, 2)})
        # 按「位置」聚类，而不是按文字。
        # 为什么不能按文字：同一枚水印被黑块切成十几段不同的文字，按原文分组
        # 永远是十几组（实测 1055 组）。而水印每页固定落在同一位置，
        # 按位置分组，一个位置就是一组，点一次清掉全文同位置的上百处
        # （2026-11-03 用户明确："我这几篇水印都是一个地方"）。
        #
        # 为什么不进一步按内容合族：实测会把正文并进来 —— 水印压在讯问笔录正文上，
        # 黑块下取到的原文是「正文+水印」混在一起，按相似度归族时
        # '本卷材料为王某某涉嫌贪污…' 这类正文会被一路串进水印族（2026-11-03 踩过）。
        # 要一次清多个位置，交给界面上的清单勾选，风险可控。
        buckets = {}
        for key, g in groups.items():
            for it in g["items"]:
                sig = _spot_sig(it)
                b = buckets.setdefault(sig, {"items": [], "texts": []})
                b["items"].append(it)
                b["texts"].append(g["text"])

        out = []
        for sig, b in buckets.items():
            texts = b["texts"]
            # 组名取众数：同一位置的几十处里，众数最能代表这块是什么
            label = max(set(texts), key=texts.count) if texts else ""
            uniq = sorted({t for t in texts if t}, key=len, reverse=True)[:3]
            # 组的位置取「实际块的平均值」，别用签名——签名是千分比单位，不是坐标
            its = b["items"]
            x0 = sum(it["x0"] for it in its) / len(its)
            y0 = sum(it["y0"] for it in its) / len(its)
            x1 = sum(it["x1"] for it in its) / len(its)
            y1 = sum(it["y1"] for it in its) / len(its)
            out.append({"sig": sig[2], "text": label[:160],
                        "samples": [u[:90] for u in uniq],
                        "count": len(its),
                        "pages": len({it["page"] for it in its}),
                        "x0": round(x0, 1), "y0": round(y0, 1),
                        "w": round(x1 - x0, 1), "h": round(y1 - y0, 1),
                        "items": its,
                        "_norm": _fuzzy_key(label)})

        # 第三层：按「遮黑的内容」归族 —— 这是用户真正要的粒度。
        # 同一枚水印被断成十几段（'张律师1101…立丰律师事务所' / '0000000000000立丰律师事务所'…）
        # 又平铺在页面 6 个角落，按位置只会分成十几组，用户还得一个个点。
        # 判据：短串是长串的**连续子串** —— 被黑块切断只会产生子串，不会凭空产生新内容，
        # 所以这个判据能把"同一处内容的不同碎片"精确归到一起，而不会像模糊相似度那样
        # 把压在水印下面的正文也串进来（2026-11-03 实测：模糊归并 997 块那组混进了
        # '本卷材料为王某某涉嫌贪污…' 这类正文，子串判据则干净）。
        fams = _group_by_content(out)

        final = []
        for f in fams:
            items, texts, sigs = [], [], []
            for k in f:
                items.extend(out[k]["items"])
                texts.extend([out[k]["text"]] * out[k]["count"])
                sigs.append(out[k]["sig"])
            items.sort(key=lambda x: (x["page"], x["y0"], x["x0"]))
            label = max(set(texts), key=texts.count) if texts else ""
            uniq = sorted({t for t in out[f[0]]["samples"]} |
                          {t for t in texts if t}, key=len, reverse=True)[:3]
            gid = hashlib.md5(("|".join(sorted(sigs))).encode("utf-8")).hexdigest()[:10]
            shots = []
            for k in f:
                shots.append({"x0": out[k]["x0"], "y0": out[k]["y0"],
                              "w": out[k]["w"], "h": out[k]["h"],
                              "count": out[k]["count"]})
            final.append({"gid": gid, "text": label[:160],
                          "samples": [u[:90] for u in uniq],
                          "count": len(items),
                          "pages": len({it["page"] for it in items}),
                          # 这族命中页面上哪几个位置（界面按页高亮用）
                          "spots": shots,
                          "x0": shots[0]["x0"] if shots else 0,
                          "y0": shots[0]["y0"] if shots else 0,
                          "w": shots[0]["w"] if shots else 0,
                          "h": shots[0]["h"] if shots else 0,
                          "items": items})
        # 覆盖页数多的排前面：用户最想清的多半是每页都有的那枚水印
        final.sort(key=lambda x: (-x["pages"], -x["count"], x["y0"], x["x0"]))
        data = {"ok": True, "groups": final, "pages": len(doc),
                "positions": len(out),
                "blocks": sum(g["count"] for g in final)}
    finally:
        doc.close()
        odoc.close()

    if stamp:
        try:
            with open(cp, "w", encoding="utf-8") as f:
                json.dump({"stamp": stamp, "data": data}, f, ensure_ascii=False)
        except Exception:
            pass
    return data


def paint_clear_items(task, items):
    """按「坐标清单」清理自动涂黑，支持一次跨多页。

    items: [{"page":1,"x0":..,"y0":..,"x1":..,"y1":..}, ...]
    同内容的多处一次传进来，一趟就清完——不用用户一页页点。

    实现要点（踩过的坑）：
       不能"把原文贴到黑块上"，黑块图形还在，盘点照样数得到。
       必须**整页重建**：原件该页当底 → 只把不清理的黑块重新画上 → 替换该页。
    """
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("kind") != "pdf":
        return {"ok": False, "msg": "只有 PDF 有可清理的自动黑块"}
    orig = meta.get("orig") or _find_original(meta.get("name") or "")
    if not orig or not os.path.exists(orig):
        return {"ok": False,
                "msg": "找不到这份文件的原件，无法还原被涂黑的内容（原件在 待处理/已处理 里）"}
    src = meta["source"]

    # 按页归拢要清掉的矩形
    #
    # 坐标基准：全部换算成**底层坐标**再比。为什么（2026-11-05）：
    # 前端 boxes.json / auto_scan 给的是「视觉坐标」（渲染图已随 rotation 转正），
    # 而 get_drawings() 吐出的黑块是「底层坐标」。rotation=270 的页这两组数字
    # 完全不同，直接比会一个都对不上 —— 表现就是"怎么点都清不掉"。
    want = {}
    total = 0
    for b in items or []:
        try:
            pno = int(b["page"])
            r = pymupdf.Rect(float(b["x0"]), float(b["y0"]),
                             float(b["x1"]), float(b["y1"]))
        except Exception:
            continue
        if r.is_empty or r.width < 2 or r.height < 2:
            continue
        want.setdefault(pno, []).append(r)
        total += 1
    if not want:
        return {"ok": False, "msg": "没有要清理的块"}

    def same(r1, r2):
        return (abs(r1.x0 - r2.x0) < 1.5 and abs(r1.y0 - r2.y0) < 1.5 and
                abs(r1.x1 - r2.x1) < 1.5 and abs(r1.y1 - r2.y1) < 1.5)

    try:
        doc = pymupdf.open(src)
        odoc = pymupdf.open(orig)
        n_pages = len(doc)
        done_pages = []
        cleared_total = 0
        # 从后往前替换，避免页序变动影响后面的页号
        for pno in sorted(want.keys(), reverse=True):
            if pno < 1 or pno > n_pages or pno > len(odoc):
                continue
            pg = doc[pno - 1]
            # 本页要清的块：视觉 → 底层，才能和 get_drawings 的矩形比
            want_dev = [_vis_box_to_page(pg, w) for w in want[pno]]
            cur = []
            for dr in pg.get_drawings():
                f = dr.get("fill")
                if not f or any(c > 0.06 for c in f):
                    continue
                r = dr.get("rect")
                if not r or r.width < 6 or r.height < 3:
                    continue
                cur.append(r)
            keep = [r for r in cur if not any(same(r, w) for w in want_dev)]
            removed = len(cur) - len(keep)
            if removed <= 0:
                continue
            tmpdoc = pymupdf.open()
            tmpdoc.insert_pdf(odoc, from_page=pno - 1, to_page=pno - 1)
            np_ = tmpdoc[0]
            for r in keep:
                np_.draw_rect(r, color=None, fill=(0, 0, 0), width=0)
            doc.delete_page(pno - 1)
            doc.insert_pdf(tmpdoc, from_page=0, to_page=0, start_at=pno - 1)
            tmpdoc.close()
            done_pages.append(pno)
            cleared_total += removed

        if not done_pages:
            doc.close(); odoc.close()
            return {"ok": False, "msg": "这些块已经不在文档里了"}

        # 先把要记账的矩形算好，再关文档 —— 顺序反了会报 "document closed"。
        # （2026-11-05：改坐标基准时踩过，odoc 在下面 save 后就 close 了。）
        log_rows = {}
        for pno in done_pages:
            log_rows[pno] = []
            _dpage = odoc[pno - 1] if pno - 1 < len(odoc) else None
            for r in want[pno]:
                rr = _vis_box_to_page(_dpage, r) if _dpage is not None else r
                log_rows[pno].append([round(rr.x0, 2), round(rr.y0, 2),
                                      round(rr.x1, 2), round(rr.y1, 2)])

        tmp = src + ".tmp"
        doc.save(tmp, garbage=4, deflate=True)
        doc.close(); odoc.close()
        os.replace(tmp, src)

        # 受影响的页缓存都作废
        for pno in done_pages:
            c = os.path.join(tdir, "pages", "%d.png" % pno)
            if os.path.exists(c):
                try:
                    os.remove(c)
                except Exception:
                    pass
        # 扫描缓存也作废：下次进来要按新状态重新分组
        sc = os.path.join(tdir, "auto_scan.json")
        if os.path.exists(sc):
            try:
                os.remove(sc)
            except Exception:
                pass

        log = {}
        lp = os.path.join(tdir, "cleared.json")
        if os.path.exists(lp):
            try:
                with open(lp, encoding="utf-8") as f:
                    log = json.load(f) or {}
            except Exception:
                log = {}
        for pno in done_pages:
            log.setdefault(str(pno), [])
            for row in log_rows.get(pno) or []:
                log[str(pno)].append(row)
        with open(lp, "w", encoding="utf-8") as f:
            # _v=2 表示坐标已统一为「底层（未旋转）」。
            # 老记录（无 _v 或 _v<2）存的是视觉坐标，撤回时按视觉→底层换算，
            # 否则旋转页上一条都对不上（2026-11-05）。
            log["_v"] = 2
            json.dump(log, f, ensure_ascii=False)
        return {"ok": True, "pages": sorted(done_pages), "count": cleared_total,
                "requested": total}
    except Exception as e:
        return {"ok": False, "msg": "清理失败：%s" % str(e)[:160]}


def paint_clear_groups(task, gids):
    """清掉 task 里属于 gids 这些位置的全部黑块（跨页一次清完）。

    界面点一个位置就会清掉全文同位置的几十上百处 —— 用户要的正是这个：
    "我这几篇水印都是一个地方"（2026-11-03）。
    """
    scan = paint_auto_scan(task, use_cache=True)
    if not scan.get("ok"):
        return scan
    items, hit = [], set()
    for g in scan.get("groups") or []:
        if g.get("gid") in gids:
            items.extend(g.get("items") or [])
            hit.add(g.get("gid"))
    if not items:
        return {"ok": False, "msg": "找不到这些位置（可能已经清过了）"}
    r = paint_clear_items(task, items)
    r["matched"] = len(hit)
    return r


def paint_tasks():
    """列出所有涂黑任务，供「同类涂黑一次性应用到全部任务」用。"""
    out = []
    if not os.path.isdir(PAINT_ROOT):
        return out
    for d in sorted(os.listdir(PAINT_ROOT), reverse=True):
        tdir = _paint_dir(d)
        mp = os.path.join(tdir, "meta.json")
        if not os.path.exists(mp):
            continue
        try:
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        if m.get("kind") != "pdf":
            continue
        out.append({"task": d, "name": m.get("name") or d,
                    "pages": len(m.get("pages") or []),
                    "created": m.get("created") or ""})
    return out


def paint_clear_all_tasks(sig_src, gids, include_self=True):
    """把「某个任务里选中的遮黑内容」套用到**全部涂黑任务**。

    按**内容**匹配，不按位置：用户原话"不是只删同一个地方遮黑的，
    是只要相同遮黑的内容就要全部删除"（2026-11-03）。
    同一枚水印在别的文件里可能挪了位置、换了几十几百页，但遮住的字是一样的，
    所以拿源任务的文字当"指纹"，在别的任务里找含同样文字的黑块。

    匹配规则（宽严两档，宁窄勿宽）：
      1. 归一化后互相包含，且较短串 ≥ 8 字；
      2. 或者两串的最长公共子串 ≥ 较短串的 70%（处理个别字符识别差异）。
    太短（<8 字）的碎片不参与，避免 '湖' 这种单字把整份文件都匹配上。

    sig_src: 提供内容的源任务编号；gids: 源任务里选中的族。
    """
    scan = paint_auto_scan(sig_src, use_cache=True)
    if not scan.get("ok"):
        return scan

    seeds = []       # 源任务选中的内容（归一化后）
    labels = []
    for g in scan.get("groups") or []:
        if g.get("gid") not in gids:
            continue
        for t in [g.get("text") or ""] + (g.get("samples") or []):
            nk = _fuzzy_key(t)
            if len(nk) >= 8 and nk not in seeds:
                seeds.append(nk)
        if g.get("text"):
            labels.append(g["text"])
    if not seeds:
        return {"ok": False, "msg": "选中的位置取不到文字，无法按内容匹配"}

    def hit(text):
        nk = _fuzzy_key(text or "")
        if len(nk) < 8:
            return False
        for sd in seeds:
            if sd in nk or nk in sd:
                return True
            short = min(len(nk), len(sd))
            if short >= 8 and _lcs_len(nk, sd) >= int(short * 0.7):
                return True
        return False

    results = []
    for t in paint_tasks():
        tid = t["task"]
        if not include_self and tid == sig_src:
            continue
        ns = paint_auto_scan(tid, use_cache=True)
        if not ns.get("ok"):
            results.append({"task": tid, "name": t["name"], "ok": False,
                            "count": 0, "msg": ns.get("msg") or "扫描失败"})
            continue
        items = []
        for g in ns.get("groups") or []:
            if hit(g.get("text") or "") or any(hit(s) for s in (g.get("samples") or [])):
                items.extend(g.get("items") or [])
        if not items:
            results.append({"task": tid, "name": t["name"], "ok": True, "count": 0,
                            "msg": "这个文件里没有相同遮黑的内容"})
            continue
        r = paint_clear_items(tid, items)
        results.append({"task": tid, "name": t["name"], "ok": bool(r.get("ok")),
                        "count": r.get("count") or 0,
                        "pages": len(r.get("pages") or []),
                        # 页号原样带回去：别的文件也要能一键撤回，
                        # 撤回要按页重画，光有页数不够（2026-11-03）。
                        "pages_list": r.get("pages") or [],
                        "msg": r.get("msg") or ""})
    return {"ok": True, "results": results, "labels": labels[:3],
            "total": sum(x.get("count") or 0 for x in results)}


def paint_redraw(task, pages=None):
    """把清理过的黑块重新盖回去（撤销"清理自动涂黑"）。

    关键：**不能直接在成品页面上补画**。
    成品页是"原件 + 拉升补齐的黑块"拼出来的；再往上补画，会和重建时补的块叠在一起，
    同一处出现两个矩形，盘点数量翻倍、位置也可能偏（2026-11-03 实测 1325 块掉到 364）。

    正确做法与清理完全对称：
      取出该页当前的原始黑块 → 扣掉要补回来的 → 以原件该页为底重画 → 替换整页。
    这样一遍下来每处只有一块，和从没清过一样。

    pages: 只撤这几页（不传＝撤全部）。
    """
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    src = meta.get("source") or ""
    if not src or not os.path.exists(src):
        return {"ok": False, "msg": "成品文件不在了"}
    orig = meta.get("orig") or _find_original(meta.get("name") or "")
    if not orig or not os.path.exists(orig):
        return {"ok": False, "msg": "找不到原件，无法还原（原件在 待处理/已处理 里）"}
    lp = os.path.join(tdir, "cleared.json")
    if not os.path.exists(lp):
        return {"ok": False, "msg": "没有清理记录，无法撤回"}
    try:
        with open(lp, encoding="utf-8") as f:
            log = json.load(f) or {}
    except Exception:
        return {"ok": False, "msg": "清理记录读不出来"}
    # 老记录存的是视觉坐标（当时只按视觉逻辑写的），新记录统一为底层坐标。
    # 不区分就会在旋转页上把黑块盖回错位置（2026-11-05）。
    log_ver = int(log.get("_v") or 1)
    log.pop("_v", None)

    want_pages = None
    if pages:
        try:
            want_pages = {int(p) for p in pages}
        except Exception:
            want_pages = None

    def same(r1, r2):
        return (abs(r1.x0 - r2.x0) < 1.5 and abs(r1.y0 - r2.y0) < 1.5 and
                abs(r1.x1 - r2.x1) < 1.5 and abs(r1.y1 - r2.y1) < 1.5)

    try:
        doc = pymupdf.open(src)
        odoc = pymupdf.open(orig)
        n_pages = len(doc)
        drew = 0
        touched = []
        for k in sorted(log.keys(), key=lambda x: int(x) if str(x).isdigit() else 0,
                        reverse=True):
            try:
                pno = int(k)
            except Exception:
                continue
            if want_pages is not None and pno not in want_pages:
                continue
            if pno < 1 or pno > n_pages or pno > len(odoc):
                continue
            rows = log.get(k) or []
            if not rows:
                continue
            back = []
            # 老记录是视觉坐标，先换成底层；新记录本来就是底层，原样用
            _bpage = odoc[pno - 1] if pno - 1 < len(odoc) else None
            for row in rows:
                try:
                    r = pymupdf.Rect(float(row[0]), float(row[1]),
                                     float(row[2]), float(row[3]))
                except Exception:
                    continue
                if r.is_empty:
                    continue
                if log_ver < 2 and _bpage is not None:
                    r = _vis_box_to_page(_bpage, r)
                back.append(r)
            if not back:
                continue

            pg = doc[pno - 1]
            cur = []
            for dr in pg.get_drawings():
                f = dr.get("fill")
                if not f or any(c > 0.06 for c in f):
                    continue
                r = dr.get("rect")
                if not r or r.width < 6 or r.height < 3:
                    continue
                cur.append(r)
            # 要补的块已经在了就不重复（幂等：连点两次撤回不会叠两层）
            keep = list(cur)
            added = 0
            for r in back:
                if not any(same(r, c) for c in cur):
                    keep.append(r)
                    added += 1
            if added == 0:
                # 这页已经盖回去了，记录可以放心销掉
                del log[k]
                continue

            tmpdoc = pymupdf.open()
            tmpdoc.insert_pdf(odoc, from_page=pno - 1, to_page=pno - 1)
            np_ = tmpdoc[0]
            for r in keep:
                np_.draw_rect(r, color=None, fill=(0, 0, 0), width=0)
            doc.delete_page(pno - 1)
            doc.insert_pdf(tmpdoc, from_page=0, to_page=0, start_at=pno - 1)
            tmpdoc.close()
            touched.append(pno)
            drew += added
            del log[k]          # 撤过的不再留着，避免重复盖

        if not drew:
            doc.close(); odoc.close()
            return {"ok": False, "msg": "这几页没有可撤回的清理记录"}

        tmp = src + ".tmp"
        doc.save(tmp, garbage=4, deflate=True)
        doc.close(); odoc.close()
        os.replace(tmp, src)

        with open(lp, "w", encoding="utf-8") as f:
            # 剩下的记录仍按底层坐标存，统一标 _v=2（老记录已在上面的循环里
            # 换算过一次，这里必须升级版本号，否则下次又会被当老记录再转一遍）
            log["_v"] = 2
            json.dump(log, f, ensure_ascii=False)
        for pno in touched:
            c = os.path.join(tdir, "pages", "%d.png" % pno)
            if os.path.exists(c):
                try:
                    os.remove(c)
                except Exception:
                    pass
        sc = os.path.join(tdir, "auto_scan.json")
        if os.path.exists(sc):
            try:
                os.remove(sc)
            except Exception:
                pass
        return {"ok": True, "count": drew, "pages": sorted(touched)}
    except Exception as e:
        return {"ok": False, "msg": "撤回失败：%s" % str(e)[:160]}


def paint_redraw_multi(jobs):
    """跨任务撤回：一次把「清掉全部文件」影响到的每个文件都退回来。

    用户点「清掉全部文件里的同样内容」时，被改的是好几个任务；
    撤回入口只有一个，所以必须一次退全部，不能只退当前这个文件
    （2026-11-03：以前别的文件要单独打开才能退，等于退不回来）。

    jobs: [{"task": "paint-xxx", "pages": [1,2,3]}, ...]
    """
    results, total = [], 0
    for j in (jobs or []):
        tid = str(j.get("task") or "")
        if not tid:
            continue
        pages = j.get("pages") or []
        r = paint_redraw(tid, pages if pages else None)
        n = r.get("count") or 0
        total += n
        name = tid
        try:
            with open(os.path.join(_paint_dir(tid), "meta.json"), encoding="utf-8") as f:
                name = json.load(f).get("name") or tid
        except Exception:
            pass
        results.append({"task": tid, "name": name, "ok": bool(r.get("ok")),
                        "count": n, "msg": r.get("msg") or ""})
    if not total:
        return {"ok": False, "msg": "这些文件里没有可撤回的清理记录",
                "results": results, "total": 0}
    return {"ok": True, "results": results, "total": total}


def paint_clear_auto(task, page, blocks):
    """兼容旧调用：单页清理。"""
    items = []
    for b in blocks or []:
        it = dict(b)
        it.setdefault("page", page)
        items.append(it)
    return paint_clear_items(task, items)


def paint_auto_blocks(task, page):
    """列出某页上的「自动涂黑」块（矢量黑块）。

    只认纯黑填充的图形；涂黑时 add_redact_annot(fill=(0,0,0)) 会留下这样一个矩形。
    """
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("kind") != "pdf":
        return {"ok": True, "blocks": [], "note": "图片没有可分离的黑块，只能用涂黑页补画"}
    src = meta["source"]
    doc = pymupdf.open(src)
    try:
        n = int(page)
        if n < 1 or n > len(doc):
            return {"ok": False, "msg": "页码超出范围"}
        pg = doc[n - 1]
        out = []
        for dr in pg.get_drawings():
            fill = dr.get("fill")
            if not fill or any(c > 0.06 for c in fill):
                continue
            r = dr.get("rect")
            if not r:
                continue
            w, h = r.width, r.height
            if w < 6 or h < 3:          # 细线、页码标记之类，不当涂黑块
                continue
            out.append({"x0": round(r.x0, 2), "y0": round(r.y0, 2),
                        "x1": round(r.x1, 2), "y1": round(r.y1, 2),
                        "w": round(w, 1), "h": round(h, 1)})
        out.sort(key=lambda b: (b["y0"], b["x0"]))
        for i, b in enumerate(out):
            b["id"] = "p%d-%d" % (n, i)
        return {"ok": True, "page": n, "blocks": out,
                "has_orig": bool(meta.get("orig") and os.path.exists(meta.get("orig") or ""))}
    finally:
        doc.close()


def paint_page_png(task, n):
    """按需渲染某一页成 PNG（首次渲染后缓存）。"""
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return ""
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    n = int(n)
    cache = os.path.join(tdir, "pages", "%d.png" % n)
    if os.path.exists(cache):
        return cache
    src = meta["source"]
    if meta["kind"] == "pdf":
        doc = pymupdf.open(src)
        if n < 1 or n > len(doc):
            doc.close()
            return ""
        # 110dpi：字够看清，单页体积也不至于太大；涂黑坐标只在点值里算，跟 dpi 无关
        pix = doc[n - 1].get_pixmap(dpi=110)
        pix.save(cache)
        doc.close()
    else:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGB")
            # 超大图先缩到长边 2000，避免浏览器端卡死
            m = max(im.size)
            if m > 2000:
                k = 2000.0 / m
                im = im.resize((int(im.width * k), int(im.height * k)))
            im.save(cache, "PNG")
    return cache


def _ocr_blocks(png, min_conf=0.0):
    """OCR 一页图，返回带归一化坐标的文字块。

    OCR 给的是 Vision 坐标（原点左下、0~1），这里换成**左上原点**的
    归一化坐标，跟 paint.html 里 x0/w 那套算法一致，省得两头各转一次出错。
    """
    OCR = os.path.join(SCRIPTS, "ocr_vision")
    if not os.path.exists(OCR) or not os.path.exists(png):
        return []
    try:
        p = subprocess.run([OCR, png], capture_output=True, text=True, timeout=180)
        if p.returncode != 0:
            return []
        items = json.loads(p.stdout or "[]")
    except Exception:
        return []
    out = []
    for it in items:
        t = (it.get("text") or "").strip()
        if not t:
            continue
        if min_conf and float(it.get("conf") or 0) < min_conf:
            continue
        try:
            x, y = float(it["x"]), float(it["y"])
            w, h = float(it["w"]), float(it["h"])
        except Exception:
            continue
        out.append({"text": t, "x0": x, "y0": max(0.0, 1.0 - y - h),
                    "x1": x + w, "y1": 1.0 - y,
                    "conf": float(it.get("conf") or 0)})
    return out


# AI 找漏的提示词：只判断「这块要不要盖」，不要求模型改写任何原文。
# 与 llm_scan.py 同一个原则——模型只做标记者，动不动刀由人决定。
#
# 实测教训（2026-11-03）：提示词只写"哪些要盖"，qwen2.5:7b 会把
# 「保管期限」「案卷号」「全宗号」「目录号」这类档案封面的栏目标签也标出来，
# 60 页跑出 62 条里一大半是废话。必须把"已脱敏过的原文长什么样"和
# "常见误报"都写死，否则律师光删误报就比手工涂还慢。
AI_FIND_SYS = (
    "你是法律扫描件的脱敏审核员，主要处理**刑事案卷**。"
    "输入是同一页 OCR 出来的文本块，每行形如『序号. 文字』。\n"
    "请挑出【一旦保持可见，就能认出具体某个自然人 / 具体单位 / 具体地点 / 具体案件】的块。\n\n"
    "★ 第一优先，必须一个不漏：**人名**。\n"
    "刑事案卷的核心可识别信息就是人。凡是真实姓名，无论出现在哪里都要挑出来：\n"
    "  · 正文叙述里：『王某某于2023年4月收受…』\n"
    "  · 角色词后面：『被调查人王某某』『讯问人张律师』『记录人某某某』『证人某某某』\n"
    "  · 案件名/卷宗封面/目录里：『（二）王純博的笔录与自书材料』\n"
    "  · 签名、公章旁、具名落款\n"
    "  · 只有姓+名、没有职务的行（如单列一行的『张律师』）\n"
    "  · 繁体字姓名也算（王純博、陳志明）—— 老档案影印件常见\n"
    "  · 同音/近似写法（王某某 / 王純博 / 王淳博）都当作本人\n"
    "连带要挑的：能指向特定人的称呼（某某、小李、张队、某警官、李主任），"
    "以及紧贴人名的身份证号、电话、住址、职务。\n\n"
    "【也要挑】\n"
    "1. 具体单位名：公司、工厂、医院、学校、银行、物流公司的全称或特定简称；\n"
    "2. 政法机关具体名称：XX看守所、XX派出所、XX公安局、XX法院、XX检察院、XX监狱、XX纪委监委XX室；\n"
    "3. 精确到日或月的日期（2024年3月5日、2024年3月、去年冬天）；\n"
    "4. 各类编号：车牌号、身份证号、手机号、银行账号、统一社会信用代码、案号、文号、合同编号；\n"
    "5. 具体地址：精确到街道、门牌、楼栋、小区、村组；\n"
    "6. 金额与账号（涉案金额、账户余额这类可反查的精确数字）；\n"
    "7. 若干要素叠加后能锁定唯一事件的组合。\n\n"
    "【绝对不要挑】（这类占了误报的大头）\n"
    "- 罪名、法条名称、法律术语：贪污、受贿、挪用公款、刑法第382条；\n"
    "- 文书体裁与栏目标签：询问笔录、证明材料、保管期限、案卷号、全宗号、目录号、\n"
    "  卷内目录、第X页、共X页、密级、归档单位、立卷人、日期栏这种表单抬头；\n"
    "- 通用称谓：民警、律师、法官、检察官、证人、被调查人、犯罪嫌疑人（**只有称谓没有名字时才不挑**）；\n"
    "- 纯数字页码、单个汉字、标点、OCR 明显识别错的乱码碎片；\n"
    "- 已经变成占位符的内容（含 [ ] 的，如 [姓名]、[手机号]）；\n"
    "- 只有机构类型没有具体名字的（如『监察委员会』『人民法院』单独出现时）。\n\n"
    "判断口诀：\n"
    "  先问是不是人名 —— 是就挑，不要犹豫，宁可错杀；\n"
    "  不是人名，再问把它单独拿给陌生人看，能不能靠它找到具体某个单位或事件；\n"
    "  不能，就不要挑。\n\n"
    "只输出一个 JSON 数组，元素是文本块的序号（整数），不要任何解释文字。\n"
    "示例输出：[0,3,7]\n"
    "没有需要盖的就输出 []"
)


def _ai_find_one_page(host, model, blocks, timeout=180):
    """让本地模型挑出该盖的块序号。返回 (序号集合, 错误信息)。"""
    if not blocks:
        return set(), ""
    lines = []
    for i, b in enumerate(blocks):
        t = re.sub(r"\s+", " ", b["text"])[:120]
        lines.append("%d. %s" % (i, t))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": AI_FIND_SYS},
            {"role": "user", "content": "文本块如下：\n" + "\n".join(lines)},
        ],
        "stream": False,
        # 不设 format="json"：实测会逼 qwen2.5 输出畸形结构（见 llm_scan.py 注释）
        "options": {"temperature": 0, "num_predict": 512, "top_p": 0.9},
    }
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(
            host.rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with op.open(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return set(), str(e)[:120]
    content = ((resp.get("message") or {}).get("content") or "").strip()
    # 模型可能裹代码块或加解释，抓第一个数组
    m = re.search(r"\[[^\]]*\]", content, re.S)
    if not m:
        return set(), ""
    try:
        arr = json.loads(m.group(0))
    except Exception:
        # 兜底：把里面的整数抠出来
        arr = [int(x) for x in re.findall(r"\d+", m.group(0))]
    idx = set()
    for v in arr if isinstance(arr, list) else []:
        try:
            k = int(v)
        except Exception:
            continue
        if 0 <= k < len(blocks):
            idx.add(k)
    return idx, ""


def _names_in_text(text):
    """用姓名库确定性地扫出中文姓名（不靠模型判断）。

    为什么单独来这一道：刑事案卷的核心可识别信息就是**人名**，
    这东西不能让 7B 小模型"看心情"决定盖不盖 —— 漏一个真名，
    整份脱敏就白做了。用户原话（2026-11-03）：
    "ai 对于刑事案卷要着重启动姓名这项屏蔽啊"。

    所以姓名走规则：姓氏是封闭集合，字形结构稳定，规则比模型靠谱得多。
    模型只管它擅长的（哪些是单位、地址、独特事实组合），姓名由规则保底。
    """
    try:
        sys.path.insert(0, SCRIPTS)
        import chinese_names as _cn
    except Exception:
        return []
    try:
        hit = _cn.scan_names_by_surname(text or "")
    except Exception:
        return []
    return [n for n in hit if n and len(n) >= 2]


def _name_hit_boxes(blocks):
    """从 OCR 块里挑出含姓名的块，返回其序号集合。

    一块 OCR 里常常是一整行（「被调查人王某某，男，1985年3月出生」），
    只要行内命中一个姓名，整块就该盖 —— 因为涂黑是按块（矩形）盖的，
    没法只盖半行。
    """
    idx = set()
    for i, b in enumerate(blocks):
        if _names_in_text(b.get("text") or ""):
            idx.add(i)
    return idx


def paint_ai_find(task, pages=None, model=""):
    """AI 找漏：OCR 取坐标 → 本地模型判断哪块该盖 → 落成待确认的涂黑框。

    为什么必须有这一步：规则引擎和"扫黑块"都依赖**文字可提取**。
    扫描件 PDF 和照片里文字是像素，规则一条也命中不了，黑块也无从谈起，
    只能靠 OCR + 模型判断。用户原话（2026-11-03）：
    "有些东西软件出不来，只有 pdf 和照片这种复杂的，介入 ai 脱敏"。

    严格边界：模型只回答"第几块要盖"，**不许改写任何原文**；
    结果写进 ai_boxes.json 并在界面上以黄色候选框呈现，律师点确认才真盖。
    """
    conf = ai_config()
    if not conf.get("enabled"):
        return {"ok": False, "msg": "本地 AI 未启用（设置里打开「本地 AI 补漏」）"}
    # 模型挂了不等于这一步做不了：姓名是规则扫的，跟 Ollama 一点关系都没有。
    # 刑事案卷最要紧的就是姓名，不能因为模型没启动就整条链停掉。
    model_up = ollama_up()
    model = model or conf.get("model") or "qwen2.5:7b"
    host = conf.get("host") or "http://127.0.0.1:11434"

    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    total_pages = len(meta.get("pages") or []) or 1

    if pages:
        try:
            want = sorted(set(int(x) for x in pages if 1 <= int(x) <= total_pages))
        except Exception:
            want = []
    else:
        want = list(range(1, total_pages + 1))
    if not want:
        return {"ok": False, "msg": "没有要扫描的页"}

    # 型号大的 PDF 逐页跑模型会很慢，先给个上限，超了让用户自己选页
    if len(want) > 60:
        want = want[:60]

    found, per_page, note = [], {}, ""
    name_blocks_total = 0
    for n in want:
        png = paint_page_png(task, n)
        if not png:
            continue
        blocks = _ocr_blocks(png, min_conf=0.0)
        per_page[n] = len(blocks)
        if not blocks:
            continue
        # ① 姓名：规则强制命中，不交模型判断（漏一个真名整份就白做）
        name_idx = _name_hit_boxes(blocks)
        name_blocks_total += len(name_idx)
        # ② 其他类别：模型判断（单位、地址、独特事实组合它更在行）
        #    模型没起来就只做姓名，照样出结果——小模型是加分项，不是前置条件。
        if model_up:
            idx, err = _ai_find_one_page(host, model, blocks)
            if err and not note:
                note = "模型调用出错：%s" % err
        else:
            idx = set()
            note = "Ollama 没在运行，只做了姓名屏蔽（规则），其他敏感项未扫描"
        # 并集：姓名优先，模型没挑到的姓名照样盖
        for k in sorted(set(idx) | name_idx):
            b = blocks[k]
            found.append({
                "page": n,
                "x0": round(b["x0"] * meta["pages"][n - 1]["w"], 2),
                "y0": round(b["y0"] * meta["pages"][n - 1]["h"], 2),
                "x1": round(b["x1"] * meta["pages"][n - 1]["w"], 2),
                "y1": round(b["y1"] * meta["pages"][n - 1]["h"], 2),
                "text": b["text"][:60],
                # 标出来源：姓名是规则定的（必盖），其余是模型建议的
                "why": "姓名" if k in name_idx else "AI",
            })

    # 落盘成"待确认候选"，不直接进 boxes.json —— 模型会误报，必须人过一眼
    with open(os.path.join(tdir, "ai_boxes.json"), "w", encoding="utf-8") as f:
        json.dump(found, f, ensure_ascii=False, indent=1)

    r = {"ok": True, "count": len(found), "pages": len(want),
         "scanned": sum(per_page.values()), "model": model,
         "names": name_blocks_total, "model_up": model_up,
         "items": found, "msg": note}
    if not found:
        r["msg"] = (note or "") + "AI 没发现需要补盖的地方（也可能本地模型判断偏保守）"
    return r


def paint_ai_boxes(task):
    """取已存下的 AI 候选（重开页面时回显）。"""
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    p = os.path.join(tdir, "ai_boxes.json")
    items = []
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                items = json.load(f) or []
        except Exception:
            items = []
    return {"ok": True, "items": items}


def paint_ai_accept(task, items=None, all_items=False, drop=None):
    """把 AI 候选并入 boxes.json（人工确认这一步）。

    items  = 指定接受哪几条（按 page+x0+y0 匹配）
    all_items = 全部接受
    drop   = 丢掉的候选（用户判断模型误报），从候选里删掉，别再冒出来
    """
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    ap = os.path.join(tdir, "ai_boxes.json")
    cand = []
    if os.path.exists(ap):
        try:
            with open(ap, encoding="utf-8") as f:
                cand = json.load(f) or []
        except Exception:
            cand = []

    def key(x):
        return "%s|%.1f|%.1f" % (x.get("page"), float(x.get("x0") or 0), float(x.get("y0") or 0))

    # 前端传回来的坐标是取整后的（840），存的是 840.19 —— 直接按字符串比会全部落空。
    # 改成"页号相同 + 左上角相差 2pt 以内即为同一条"。
    def match(a, b):
        try:
            if int(a.get("page") or 0) != int(b.get("page") or 0):
                return False
            return (abs(float(a.get("x0") or 0) - float(b.get("x0") or 0)) <= 2.0 and
                    abs(float(a.get("y0") or 0) - float(b.get("y0") or 0)) <= 2.0)
        except Exception:
            return False

    drop_keys = set(str(d) for d in (drop or []))
    want = None
    if not all_items:
        want = list(items or [])

    bp = os.path.join(tdir, "boxes.json")
    boxes = {}
    if os.path.exists(bp):
        try:
            with open(bp, encoding="utf-8") as f:
                boxes = json.load(f) or {}
        except Exception:
            boxes = {}

    added, rest = 0, []
    for c in cand:
        k = key(c)
        if k in drop_keys or any(match(c, d) for d in (drop or []) if isinstance(d, dict)):
            continue                       # 用户说是误报，直接弃掉
        take = all_items or (want is not None and any(match(c, w) for w in want))
        if not take:
            rest.append(c)
            continue
        pg = str(int(c.get("page") or 1))
        arr = boxes.get(pg) or []
        # 同一位置已经有框就别重复叠
        dup = False
        for b in arr:
            try:
                if (abs(float(b[0]) - float(c["x0"])) < 1.5 and
                        abs(float(b[1]) - float(c["y0"])) < 1.5 and
                        abs(float(b[2]) - float(c["x1"])) < 1.5 and
                        abs(float(b[3]) - float(c["y1"])) < 1.5):
                    dup = True
                    break
            except Exception:
                continue
        if not dup:
            arr.append([round(float(c["x0"]), 2), round(float(c["y0"]), 2),
                        round(float(c["x1"]), 2), round(float(c["y1"]), 2), "AI"])
            added += 1
        boxes[pg] = arr

    with open(bp, "w", encoding="utf-8") as f:
        json.dump(boxes, f)
    with open(ap, "w", encoding="utf-8") as f:
        json.dump(rest, f, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in boxes.values())
    return {"ok": True, "added": added, "left": len(rest), "total": total,
            "msg": "已加入 %d 处（还没烧进 PDF，导出时才生效）" % added}


def _vis_box_to_page(page, b):
    """把「视觉坐标」下的框换算成该页底层坐标，供 add_redact_annot / draw_rect 使用。

    为什么必须有这一步（2026-11-05 实打实翻过车）：
    前端是在**渲染出来的图**上拉框的，图已经跟着 page.rotation 转正了，
    所以前端量到的是「转正后、原点左上」的视觉坐标。
    而 add_redact_annot 吃的是**未旋转**的底层坐标系 —— 页面若是 90/180/270，
    同一组数字落下去就会拧到别处：实测那份 14 页的劳动合同，
    前 1 页和第 8~14 页都是 rotation=270，结果黑框全跑到页边空白里，
    「张某」「000000000000000000」原样露在外面，等于没脱敏。

    注意 page.rect 已经带旋转（595x842），page.mediabox 才是底层（842x595），
    所以判断要不要换算只能看 page.rotation，不能用 rect 比大小。
    """
    # 已经是 Rect 就别再当四元组拆（get_drawings 出来就是 Rect）
    # 本文件所有 pymupdf 都在函数内 import（沿用原写法，避免启动时依赖重）
    import pymupdf
    if isinstance(b, pymupdf.Rect):
        r = pymupdf.Rect(b)
    else:
        r = pymupdf.Rect(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    rot = int(getattr(page, "rotation", 0) or 0) % 360
    if rot == 0:
        return r
    # derotation_matrix 把视觉坐标映射回底层坐标；对矩形做矩阵变换后
    # 上下边可能颠倒，统一归一化成正向矩形
    r = r * page.derotation_matrix
    return pymupdf.Rect(min(r.x0, r.x1), min(r.y0, r.y1),
                        max(r.x0, r.x1), max(r.y0, r.y1))


def _page_box_to_vis(page, r):
    """_vis_box_to_page 的反向换算：底层坐标 → 视觉坐标。

    清理逻辑必须用它。为什么（2026-11-05 同一批 bug 的另一半）：
    get_drawings() 吐出的黑块矩形是**底层坐标**，而 boxes.json / auto_scan
    给出的都是**视觉坐标**。旋转页上两者数值不同，不换算就一个都对不上 ——
    表现正是用户说的"我还是不能清理，自动涂黑的内容"。
    """
    import pymupdf
    rot = int(getattr(page, "rotation", 0) or 0) % 360
    if rot == 0:
        return pymupdf.Rect(r)
    v = pymupdf.Rect(r) * page.rotation_matrix
    return pymupdf.Rect(min(v.x0, v.x1), min(v.y0, v.y1),
                        max(v.x0, v.x1), max(v.y0, v.y1))


def _label_on_box(page, vis_box, text, color=(1, 1, 1), fontsize=9.0,
                  font="china-s"):
    """把标注文字写在黑块正中（白字），返回实际字号；写不下返回 0。

    这是「导出时把标注烧进 PDF」的唯一入口，踩过的坑全在这：

    1. **必须写在底层坐标系**。视觉框要先换算。旋转页上宽高会互换：
       视觉上 70x300 的竖块，底层其实是 300x70 的横块，字号约束要用后者。

    2. **角度等于 page.rotation 本身**，不是 360-rot，也不是差值。
       2026-11-05 实测两种取值 × 四种旋转，结论一边倒：
       (rot=0,ang=0)(90,90)(180,180)(270,270) 全部正向，
       (360-rot) 那一列全部倒置 180°。这与"rotate 是逆时针"的直觉相反，
       别凭推理改，改了就是倒着的字。

    3. **落点用公式算，不要试写**。insert_text 的基线点会随 rotate 朝四个
       不同方向长出字框（下面 ASC/DESC 那组公式就是实测反推的）。
       曾试过"写一次不可见字→量 bbox→平移重写"，位置能收敛，
       但 render_mode=3 的试写会**在文字层留下重复的隐形文字**
       （get_text 里能看到一串同样的词），成品会被搜出几十份重复，
       所以现在改成纯解析计算，一次写准。

    4. 放不下就不写，返回 0。宁可这块没字，也不写半截截断的字。
    """
    import pymupdf
    if not text or not str(text).strip():
        return 0
    text = str(text).strip()
    rot = int(getattr(page, "rotation", 0) or 0) % 360

    vis = pymupdf.Rect(vis_box)
    pad = 1.2
    inner = pymupdf.Rect(vis.x0 + pad, vis.y0 + pad, vis.x1 - pad, vis.y1 - pad)
    if inner.width <= 4 or inner.height <= 4:
        return 0

    # 视觉框 → 底层框（旋转页上宽高互换）
    dev = pymupdf.Rect(inner) * page.derotation_matrix
    dev = pymupdf.Rect(min(dev.x0, dev.x1), min(dev.y0, dev.y1),
                       max(dev.x0, dev.x1), max(dev.y0, dev.y1))

    # 字号自适应：字的「长度」沿哪个轴，取决于是不是 90/270
    size = float(fontsize)
    while size > 3.5:
        tw = pymupdf.get_text_length(text, fontname=font, fontsize=size)
        # 90/270 时字沿纵向排，长度受高度约束；0/180 时受宽度约束
        span = dev.height if rot in (90, 270) else dev.width
        thick = dev.width if rot in (90, 270) else dev.height
        # 笔画厚度方向要有字号那么高，留一点余量
        if tw <= span - 1 and size * 1.15 <= thick + 1:
            break
        size -= 0.5
    if size <= 3.5:
        return 0

    tw = pymupdf.get_text_length(text, fontname=font, fontsize=size)
    fo = pymupdf.Font(fontname=font)
    asc = fo.ascender * size
    desc = -fo.descender * size

    tcx, tcy = (dev.x0 + dev.x1) / 2.0, (dev.y0 + dev.y1) / 2.0
    # 反解基线点：让 bbox 中心落在 (tcx, tcy)。
    # 四个方向的 bbox 相对基线点的偏移（实测，见 docstring 第 3 条）
    if rot == 0:
        bx, by = tcx - tw / 2.0, tcy + (asc - desc) / 2.0
    elif rot == 90:
        bx, by = tcx + (asc - desc) / 2.0, tcy + tw / 2.0
    elif rot == 180:
        bx, by = tcx + tw / 2.0, tcy - (asc - desc) / 2.0
    else:                                   # 270
        bx, by = tcx - (asc - desc) / 2.0, tcy - tw / 2.0

    page.insert_text((bx, by), text, fontname=font, fontsize=size,
                     color=color, rotate=rot)
    return size


def paint_reset(task):
    """把工作副本恢复成「原件」，清掉所有已经烧进去的黑块。

    为什么需要（2026-11-05）：旧版导出没有处理页面旋转，rotation=90/270 的页
    黑框全画歪了，可它们是**真 redaction**——歪掉的黑框连同无辜的文字一起被
    烧进了 source.pdf。工作副本从此变成"原件+一堆错位黑块"，
    再修好坐标也没用，因为脏块已经在底图里了。

    这个动作只动工作副本，不碰原件、不碰成品。做完等于回到刚建任务的干净状态：
      · source = 原件（逐页复制，保留原 rotation）
      · boxes.json 清空、cleared.json 与页面缓存删除
    用户重新拉框即可，之前歪掉的框本来就该重画。
    """
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("kind") != "pdf":
        return {"ok": False, "msg": "只有 PDF 需要重置（图片没有坐标层）"}
    orig = meta.get("orig") or _find_original(meta.get("name") or "")
    if not orig or not os.path.exists(orig):
        return {"ok": False,
                "msg": "找不到原件，无法重置（原件在 待处理/已处理 里）"}
    src = meta.get("source")
    if not src:
        return {"ok": False, "msg": "工作副本路径缺失"}

    try:
        # 必须先备份：万一用户本来是想保留一部分手改，还能捞回来
        if os.path.exists(src):
            bak = src + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(src, bak)
        shutil.copy2(orig, src)
    except Exception as e:
        return {"ok": False, "msg": "重置失败：%s" % str(e)[:160]}

    # 框、清理记录、页面缓存全部作废：它们描述的是旧底图，留着就是错的
    try:
        with open(os.path.join(tdir, "boxes.json"), "w", encoding="utf-8") as f:
            json.dump({}, f)
    except Exception:
        pass
    for fn in ("cleared.json", "deleted.json", "auto_scan.json"):
        p = os.path.join(tdir, fn)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    pdir = os.path.join(tdir, "pages")
    if os.path.isdir(pdir):
        for fn in os.listdir(pdir):
            if fn.lower().endswith(".png"):
                try:
                    os.remove(os.path.join(pdir, fn))
                except Exception:
                    pass

    # 页尺寸从原件重算（原件才是准的）
    try:
        doc = pymupdf.open(src)
        pages = []
        for i in range(len(doc)):
            r = doc[i].rect
            pages.append({"n": i + 1, "w": round(r.width, 2),
                          "h": round(r.height, 2)})
        doc.close()
        meta["pages"] = pages
        meta["reset_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(tdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {"ok": True, "pages": len(meta.get("pages") or []),
            "msg": "已恢复成原件，之前的框和错位黑块都清掉了"}


def paint_export(task):
    """把 boxes.json 里的框烧进 PDF/图片，落到成品目录。"""
    import pymupdf
    tdir = _paint_dir(task)
    if not tdir or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在"}
    with open(os.path.join(tdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    boxes = {}
    bp = os.path.join(tdir, "boxes.json")
    if os.path.exists(bp):
        try:
            with open(bp, encoding="utf-8") as f:
                boxes = json.load(f)
        except Exception:
            boxes = {}

    total = sum(len(v) for v in boxes.values())
    if not total:
        return {"ok": False, "msg": "还没有涂任何一块，先框几处再导出"}

    src = meta["source"]
    os.makedirs(OUTBOX, exist_ok=True)
    out = os.path.join(OUTBOX, meta["name"])

    # 标注一律烧进成品 —— 2026-11-05 用户定：
    # 「以后默认自动到黑块上，不要做个选项了」。
    #
    # 演变过程（别再改回去）：
    #   2026-11-02 定"不烧"，理由是成品外发时附注类别等于把线索递回去；
    #   2026-11-05 上午做成开关，默认关；
    #   2026-11-05 下午用户明确要默认烧，理由是"我标注了却导不出来，等于白标"。
    # 现在没有开关。标注只在该块真有标注文字时才写，没标注的块仍是纯黑。
    want_label = True
    labeled = 0

    if meta["kind"] == "pdf":
        doc = pymupdf.open(src)
        for k, rects in boxes.items():
            try:
                pi = int(k) - 1
            except Exception:
                continue
            if pi < 0 or pi >= len(doc):
                continue
            page = doc[pi]
            for b in rects:
                try:
                    # 旋转页必须换算，否则黑框会拧到别处（见 _vis_box_to_page 的注释）
                    r = _vis_box_to_page(page, b)
                except Exception:
                    continue
                # 用 redaction 而不是画黑框：画框只是盖住，底下的文字还能被复制搜索出来
                page.add_redact_annot(r, fill=(0, 0, 0))
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
            # 标注必须在 apply_redactions **之后**写：
            # redaction 会把落在框内的所有文字一并删掉，先写等于白写。
            if want_label:
                for b in rects:
                    lab = str(b[4]).strip() if len(b) >= 5 else ""
                    if not lab:
                        continue
                    vis = pymupdf.Rect(float(b[0]), float(b[1]),
                                       float(b[2]), float(b[3]))
                    try:
                        if _label_on_box(page, vis, lab) > 0:
                            labeled += 1
                    except Exception:
                        pass
        doc.save(out, garbage=3, deflate=True)
        doc.close()
    else:
        from PIL import Image, ImageDraw, ImageFont
        with Image.open(src) as im:
            im = im.convert("RGB")
            # boxes 存的是原图坐标；若渲染时缩过，这里按原图尺寸用，不需要换算
            dr = ImageDraw.Draw(im)
            for rects in boxes.values():
                for b in rects:
                    dr.rectangle([float(b[0]), float(b[1]), float(b[2]), float(b[3])],
                                 fill=(0, 0, 0))
            # 图片没有旋转问题，但同样要在画完黑块之后再写字
            if want_label:
                fnt = None
                for _pf in ("/System/Library/Fonts/Supplemental/Songti.ttc",
                            "/System/Library/Fonts/PingFang.ttc",
                            "/System/Library/Fonts/STHeiti Light.ttc"):
                    if os.path.exists(_pf):
                        try:
                            fnt = ImageFont.truetype(_pf, 14)
                            break
                        except Exception:
                            continue
                if fnt:
                    for rects in boxes.values():
                        for b in rects:
                            lab = str(b[4]).strip() if len(b) >= 5 else ""
                            if not lab:
                                continue
                            x0, y0, x1, y1 = (float(b[0]), float(b[1]),
                                              float(b[2]), float(b[3]))
                            try:
                                tb = dr.textbbox((0, 0), lab, font=fnt)
                                tw_, th_ = tb[2]-tb[0], tb[3]-tb[1]
                                if tw_ <= (x1-x0)-2 and th_ <= (y1-y0)-2:
                                    dr.text((x0 + (x1-x0-tw_)/2, y0 + (y1-y0-th_)/2 - tb[1]),
                                            lab, fill=(255, 255, 255), font=fnt)
                                    labeled += 1
                            except Exception:
                                pass
            im.save(out)

    # 标注清单：留一份「这块涂的是什么」的记录。
    # 放对照表目录而不是成品目录——成品是要外发的，附一张写着"这里涂的是身份证号"的表格，
    # 等于把线索又递回去。
    try:
        import csv as _csv
        rows = []
        for _k, _rects in boxes.items():
            for _b in _rects:
                _lab = str(_b[4]).strip() if len(_b) >= 5 else ""
                rows.append([_k, _b[0], _b[1],
                             round(float(_b[2]) - float(_b[0]), 2),
                             round(float(_b[3]) - float(_b[1]), 2), _lab])
        if any(r[5] for r in rows):
            _stem = os.path.splitext(meta["name"])[0]
            _cp = os.path.join(KEYS, "%s_涂黑记录.csv" % _stem)
            os.makedirs(KEYS, exist_ok=True)
            with open(_cp, "w", encoding="utf-8-sig", newline="") as _f:
                _w = _csv.writer(_f)
                _w.writerow(["页", "左上X", "左上Y", "宽", "高", "标注"])
                _w.writerows(rows)
    except Exception:
        pass

    # 涂黑完就是改好了：这份直接放行——成品在成品区，旧件归档，界面里不再算不合格
    if meta.get("record_id"):
        try:
            accept_rejected(meta["record_id"], "手动涂黑 %d 处后放行" % total)
        except Exception:
            pass

    # 关键：把改好的这份同步回去，否则界面上看到的还是改前那份。
    # 用户反馈的是「导出的内容不是我改的版本」——成品本身没错，
    # 错在 App 里点开预览/历史读的仍是预览目录下那份没改过的（2026-11-03）。
    sync_note = _paint_sync_back(meta, out)
    r = {"ok": True, "saved": meta["name"], "count": total, "path": out,
         "labeled": labeled, "label_on": want_label}
    if sync_note:
        r["sync"] = sync_note
    return r


def _paint_sync_back(meta, out):
    """把涂黑改好的成品同步回「预览任务」与「账本」，让 App 各处都看到改后版本。

    为什么要做：涂黑任务是从预览任务的成品复制出来的（`paint_from_task`），
    改完只往成品文件夹写一份，预览目录里那份还是原样 ——
    从界面点开预览、或在历史里点「打开」，看到的就是没改过的旧件。
    用户会以为「导出没生效」，其实导出是对的（2026-11-03 用户反馈）。

    为什么是"所有同名任务"而不是只同步自己那一条：
    同一份文件被重复脱敏过，就会有多个预览任务、历史里也躺着多条同名记录；
    历史按时间倒序排，用户点到的往往是**最新那条**（也就是重跑出来的、没涂黑过的）。
    只同步自己那条，等于每次都被新的那条盖回去 —— 所以按成品名全量同步。

    做法（三步都做，缺一处就会有一处显示旧的）：
      1. 覆盖所有预览任务 output/ 下的同名成品；
      2. 作废它们的 preview.json 与逐页缓存，让预览页重读；
      3. 账本里所有同名记录的 output_path 指向成品目录，并记 exported_at/status。

    返回一句人话说明同步了几个地方（全都没同步上就返回空串）。
    """
    name = meta.get("name") or os.path.basename(out)
    done = []

    # ① 找齐所有「output 下有同名成品」的预览任务
    pv_tasks = []
    try:
        own = ""
        m = re.match(r"^paint-t(\d{8}-\d{6}-\d{3})-\d+$", str(meta.get("task") or ""))
        if m:
            own = m.group(1)
        for d in os.listdir(PREVIEW_ROOT):
            pv_out = os.path.join(PREVIEW_ROOT, d, "output", name)
            if os.path.exists(pv_out):
                pv_tasks.append(d)
        # 自己那条排前面，日志里好认
        if own in pv_tasks:
            pv_tasks.remove(own)
            pv_tasks.insert(0, own)
    except Exception:
        pv_tasks = []

    synced = 0
    for t in pv_tasks:
        pv_out = os.path.join(PREVIEW_ROOT, t, "output", name)
        try:
            if os.path.abspath(pv_out) != os.path.abspath(out):
                shutil.copy2(out, pv_out)
            synced += 1
        except Exception:
            continue
        # 预览数据要作废重读：时间戳比成品旧才会重建
        pj = os.path.join(PREVIEW_ROOT, t, "files", "1", "preview.json")
        if os.path.exists(pj):
            try:
                now = time.time()
                os.utime(pj, (now - 5, now - 5))
            except Exception:
                pass
        # 逐页缓存图（pdfview / paint 都用它）也要清，否则缩略图还是旧的
        try:
            pdir = os.path.join(PREVIEW_ROOT, t, "pages")
            if os.path.isdir(pdir):
                for f in os.listdir(pdir):
                    if f.lower().endswith(".png"):
                        try:
                            os.remove(os.path.join(pdir, f))
                        except Exception:
                            pass
        except Exception:
            pass
    if synced:
        done.append("预览 %d 份" % synced if synced > 1 else "预览")

    # ② 账本：所有同名记录都指到成品目录（历史里点哪条都是改好的这份）
    try:
        import history_store as HS
        hit = 0
        for ent in HS.list_entries(500):
            if (ent.get("output_name") or "") != name:
                continue
            if os.path.abspath(ent.get("output_path") or "") == os.path.abspath(out):
                hit += 1
                continue
            try:
                HS.update_entry(ent["id"], output_path=out, preview_path=out,
                                status="exported",
                                exported_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                hit += 1
            except Exception:
                pass
        if hit:
            done.append("账本 %d 条" % hit if hit > 1 else "账本")
    except Exception:
        pass

    return "、".join(done)


def _human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return ("%.0f%s" % (n, u)) if u == "B" else ("%.1f%s" % (n, u))
        n /= 1024.0


def _dir_stat(path, skip=(), include_hidden=False):
    """统计一个目录（或单个文件）里的文件数与体积（只统计，不动手）。

    ⚡ 2026-11-07 补两条能力，起因是「清除全部删不干净」：
      1. **单文件**：根目录那个老账本 `账本.json` 是个文件不是目录，
         原实现直接 `return 0,0`，界面上显示「0 个文件」，
         用户以为没东西可清，其实文件一直在。
      2. **隐藏文件**：`工作区/.自动识敏输入.txt` 是喂给模型的原文副本，
         名字带点，被 `f.startswith(".")` 无条件跳过 —— 最该清的东西反而清不掉。
         默认仍跳过（`.DS_Store` 满目录都是，统计进去数字很吵），
         由目标自己声明 `include_hidden=True` 才计入。
    """
    cnt = 0
    size = 0
    if os.path.isfile(path):
        try:
            if not include_hidden and os.path.basename(path).startswith("."):
                return 0, 0
            return 1, os.path.getsize(path)
        except Exception:
            return 0, 0
    if not os.path.isdir(path):
        return 0, 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if f.startswith(".") and not include_hidden:
                continue
            try:
                size += os.path.getsize(os.path.join(root, f))
                cnt += 1
            except Exception:
                pass
    return cnt, size


def clear_targets():
    """要清的东西和要留的东西，都写死在这里，界面按这个清单展示。

    刻意不清：脱敏规则配置、敏感词表、记忆库。
    那三样是「配置与积累」，不是「这次跑出来的东西」——
    删了以后下次脱敏会从零开始，跟「清记录」不是一回事。

    ⚡ 2026-11-07 修「预览任务不存在」：这里多一个 `default` 字段。
    `default=False` 的组前端一律**默认不勾**，必须用户自己勾才清。

    为什么必须这样（本次事故复盘）：
        原来前端是「除了涂黑，其余全部默认勾上」，而「预览任务」「导出账本」
        都在清单里 —— 用户每点一次「清除全部」，还没导出核对的预览任务
        就连同账本被整组搬进废纸篓。此后历史里点「查看」、旧标签页、
        书签，全部报「任务不存在或已过期」，看着像 App 丢了东西。
        实测废纸篓里躺着 8 个「立丰脱敏-清除-」目录，每个都装着几十个
        预览任务编号（20261106-224442-380 等），证据确凿。

    哪些该默认不勾：
        · preview  预览任务 —— 这是「还没点导出、正等着你核对」的东西，
                   清历史记录不等于要把在办的任务一起扔掉；
        · history  导出账本 —— 账本是「三年后还想复原一份旧件」用的，
                   它跟「这次跑出来的临时文件」不是一回事；
        · paint    涂黑任务 —— 用户一页页拉框画出来的活儿（原有规则）。
    真正的临时件（成品副本、上传暂存、补漏提示、md）才默认勾上。
    """
    return [
        {"key": "products", "label": "成品文件（不含不合格件）", "path": OUTBOX,
         "note": "文稿/立丰脱敏/成品 里的成品；不合格件单独一组",
         "exclude": ["不合格"], "default": True},
        {"key": "wmout", "label": "去水印成品与记录",
         "path": WM_OUTBOX,
         "note": "文稿/立丰脱敏/去水印 里的文件；只去了水印、没脱敏，别和成品混。"
                 "连隐藏的临时残留一起清（否则清完页面还挂着旧记录）",
         "include_hidden": True, "default": True},
        {"key": "rejected", "label": "未通过质检的成品与原件留底", "path": BAD_DIR,
         "note": "不合格目录：成品、原件副本、历史与台账都会清掉", "default": True},
        {"key": "history", "label": "导出账本与冻结的映射表",
         "path": os.path.join(APP_SUPPORT, "历史"),
         "note": "清掉后，旧成品无法再一键复原（复原靠的就是这里的映射表）；"
                 "历史记录也会整条消失，默认不勾",
         "default": False},
        {"key": "preview", "label": "预览任务", "path": PREVIEW_ROOT,
         "note": "还没点导出的成品就放在这里；清了以后历史里「查看」会报"
                 "「任务不存在或已过期」，默认不勾",
         "default": False},
        {"key": "paint", "label": "涂黑任务", "path": PAINT_ROOT,
         "note": "手动涂黑画到一半的框", "default": False},
        {"key": "uploads", "label": "上传暂存", "path": UPLOADS,
         "note": "网页拖进来的临时副本", "default": True},
        {"key": "inbox", "label": "待处理与已处理原件", "path": INBOX,
         "note": "脱敏时复制进来的原件副本；你自己原来的文件不动", "default": True},
        {"key": "maps", "label": "映射表与本案词表", "path": KEYS,
         "note": "对照表目录；清掉后没法再复原任何东西", "default": True},
        {"key": "scans", "label": "补漏提示", "path": SCANS,
         "note": "本地模型扫出来的待确认线索，含原文，本来就该少留", "default": True},
        {"key": "restore", "label": "还原产物", "path": RESTORE_DIR,
         "note": "文稿/立丰脱敏/还原 里的文件", "default": True},
        # 转出来的 md 是「给 agent 吃的成品副本」，同样是这次跑出来的东西。
        # 以前漏了这一项：清了成品，md 还在，等于旧脱敏结果继续留在磁盘上
        # （2026-11-02 用户发现「删除里没有勾选 md 的选项」）。
        {"key": "md", "label": "转出的 Markdown 与记录", "path": md_out_dir(),
         "note": "文稿/立丰脱敏/MD 里的 md；给研判 agent 读的成品副本，"
                 "含脱敏后正文，删了不影响原成品。"
                 "2026-11-12 补：连 .~排版*.md 这类隐藏临时残留一起清，"
                 "否则预览统计成 0、清除也跳过，页面「已转出的 MD」还挂着旧记录",
         "include_hidden": True, "default": True},

        # ⚡ 2026-11-07 补「删不干净」漏掉的七处（用户原话：「最近脱敏删不干净，修一下」）。
        #
        # 排查发现这些位置从来没进过清除清单 —— 不是清除失败，是**压根没被列入**，
        # 所以界面上看着清完了，磁盘上原始案件材料还在：
        #   已处理/      72MB（3 份原始笔录 PDF + 3 份公司 docx）
        #   原件/        43MB（原始笔录 PDF）
        # 更麻烦的是它们属于**老版本遗留**：现行代码只认 `工作区/待处理/已处理`
        # 和 `成品/不合格/原件`，根目录这两个目录零引用，等于永远不会被任何流程再碰，
        # 只能靠「清除全部」手动带走。默认勾上：这就是「这次跑出来的原件副本」。
        {"key": "legacy_handled", "label": "遗留：已处理原件（老版本）",
         "path": os.path.join(APP_SUPPORT, "已处理"),
         "note": "老版本把脱敏用的原件副本放在这里，现行代码已不再读写；"
                 "里面是原始案件材料，默认清理", "default": True},
        {"key": "legacy_orig", "label": "遗留：原件目录（老版本）",
         "path": os.path.join(APP_SUPPORT, "原件"),
         "note": "同上，老版本的原件留底；现行代码用的是「成品/不合格/原件」",
         "default": True},
        # 交付凭证里存的是**原始文件的完整路径和文件名**
        # （如 `~/Documents/工作/…/（批注修订）协议0713.docx`），
        # 清掉成品却留下凭证，等于文件名和目录结构还摊在那儿。
        {"key": "receipts", "label": "交付凭证（含原始文件路径）",
         "path": os.path.join(APP_SUPPORT, "交付凭证"),
         "note": "每次导出发的凭证 json，记着原件的绝对路径、文件名、哈希；"
                 "属于本次交付的产物，默认清理", "default": True},
        # 运行日志里会摘原文片段。reject_store 的台账记的是「哪句话没脱干净」，
        # 本身就是敏感内容；agent_calls 记的是 agent 读了哪些文件。
        {"key": "rejectlog", "label": "拦截台账（含原文片段）",
         "path": os.path.join(APP_SUPPORT, "_拦截记录.jsonl"),
         "note": "质检拦截时摘录的原文与判据；清了不影响重脱，默认清理",
         "default": True},
        {"key": "agentlog", "label": "agent 调用日志",
         "path": os.path.join(APP_SUPPORT, "agent_calls.jsonl"),
         "note": "记录 agent 读过哪些文件；属运行痕迹，默认清理", "default": True},
        # 老账本：活的账本在 `历史/账本.json`（history_store.LEDGER），
        # 根目录这个是老版本遗留的单文件，没有任何代码再读它。
        {"key": "root_ledger", "label": "遗留：旧账本（根目录）",
         "path": os.path.join(APP_SUPPORT, "账本.json"),
         "note": "老版本账本；现行账本是「历史/账本.json」。"
                 "和导出账本同性质，默认不勾", "default": False},
        # `.自动识敏输入.txt` 是喂给识敏模型的原文副本，名字带点，
        # 以前被 `n.startswith(".")` 无条件跳过 —— 最该清的反而清不掉。
        # 自动去水印时另存的原件副本（撤销去水印要用它重跑）。
        # 和「导出账本」同性质：是还原依据，不勾就不清；勾了以后
        # 预览页的「保留水印重做」会变成灰色不可点。
        {"key": "wmbackup", "label": "去水印原件备份",
         "path": os.path.join(APP_SUPPORT, "水印原件"),
         "note": "自动去水印前的原件；撤销去水印靠它重跑，默认不勾",
         "default": False},
        {"key": "aiinput", "label": "识敏输入缓存（原文副本）",
         "path": os.path.join(WORK, ".自动识敏输入.txt"),
         "include_hidden": True,
         "note": "自动识敏时落下的整篇原文；含未脱敏正文，默认清理",
         "default": True},
    ]


def clear_undo(bucket=None):
    """把「上一次清除」的东西从废纸篓搬回去。

    为什么必须做：清除是整目录搬走，涂黑任务里是用户一页页拉框画的，
    预览任务是跑了几分钟的中间件，一旦清错，手工从废纸篓往回搬极易放错位置
    （2026-11-03 实际发生过：3 个涂黑任务被丢回 APP_SUPPORT 根目录，
    界面完全认不出来，等于丢了）。有 _清除清单.json 就按清单回位，
    没有（旧版本清的）就按名字猜分组，猜不到的原样放回 APP_SUPPORT。
    """
    trash = os.path.join(os.path.expanduser("~"), ".Trash")
    if bucket:
        cand = [os.path.join(trash, os.path.basename(bucket))]
    else:
        try:
            cand = [os.path.join(trash, d) for d in os.listdir(trash)
                    if d.startswith("立丰脱敏-清除-")]
        except Exception:
            cand = []
        cand.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
    cand = [p for p in cand if os.path.isdir(p)]
    if not cand:
        return {"ok": False, "msg": "废纸篓里没有「立丰脱敏-清除-」文件夹，没有可还原的内容"}

    src_dir = cand[0]
    # 分组 key → 落地目录；有清单就精确定位，没有就靠名字猜
    by_key = {t["key"]: t["path"] for t in clear_targets()}
    manifest = {}
    mp = os.path.join(src_dir, "_清除清单.json")
    if os.path.exists(mp):
        try:
            with open(mp, encoding="utf-8") as f:
                for it in json.load(f) or []:
                    manifest[it.get("name") or ""] = it.get("from") or ""
        except Exception:
            manifest = {}

    def guess(name):
        """清单缺失时的兜底：按名字认它原来属于哪一组。"""
        if name.startswith("paint-"):
            return by_key.get("paint")
        if re.match(r"^\d{8}-\d{6}-\d{3,}", name):
            return by_key.get("preview")
        if name.startswith("202") and "-" in name:
            return by_key.get("preview")
        return None

    moved, skipped, failed = [], [], []
    for n in sorted(os.listdir(src_dir)):
        # 只跳过清单自己，不能按「下划线开头」一刀切 ——
        # `_拦截记录.jsonl` 也是下划线开头，那是用户可能想撤回来的台账。
        if n == "_清除清单.json":
            continue
        s = os.path.join(src_dir, n)
        tgt_dir = manifest.get(n) or guess(n) or APP_SUPPORT
        try:
            os.makedirs(tgt_dir, exist_ok=True)
            t = os.path.join(tgt_dir, n)
            if os.path.exists(t):
                skipped.append(n)
                continue
            shutil.move(s, t)
            moved.append({"name": n, "to": tgt_dir})
        except Exception as e:
            failed.append("%s（%s）" % (n, str(e)[:60]))
    return {"ok": True, "moved": len(moved), "items": moved,
            "skipped": skipped, "failed": failed, "from": src_dir}


def clear_all(keys):
    """把选中的分组整体移入废纸篓（不是直接删，留一条回头路）。

    空列表必须直接拒绝：曾经因为参数名不匹配传进来空列表，
    循环里 `key not in []` 恒真 → 变成"什么都不选却清光全部"
    （2026-11-02 实打实清掉了成品、账本、映射表、预览 24 个文件）。
    宁可报错，也不能让"没有选择"等同于"全选"。
    """
    keys = [str(k) for k in (keys or []) if str(k)]
    if not keys:
        return {"ok": False, "msg": "没有选中任何一组，已中止（不会删除任何文件）",
                "done": [], "failed": [], "bucket": ""}
    # 白名单：不认识的 key 一律不认。以前只要没被"选中"就跳过，
    # 于是参数写错时可能把全部组都跑一遍（2026-11-02 两次误清）。
    valid = {t["key"] for t in clear_targets()}
    unknown = [k for k in keys if k not in valid]
    if unknown:
        return {"ok": False, "msg": "存在未知分组：%s，已中止" % "、".join(unknown[:5]),
                "done": [], "failed": [], "bucket": ""}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bucket = os.path.join(os.path.expanduser("~"), ".Trash", "立丰脱敏-清除-%s" % stamp)
    done = []
    failed = []
    # 落一份「谁从哪来」的清单：不同分组的文件都平铺进同一个废纸篓目录，
    # 光看名字分不清该回「成品」还是「涂黑任务」，手工恢复极易放错位置
    # （2026-11-03 恢复时真放错过：3 个涂黑任务被丢回 APP_SUPPORT 根目录）。
    manifest = []
    for t in clear_targets():
        if t["key"] not in keys:
            continue
        p = t["path"]
        _inc_hidden = bool(t.get("include_hidden"))
        # ⚡ 单文件目标：根目录遗留的 `账本.json` 就是一个文件。
        #   原实现 `if not os.path.isdir(p): continue` 直接跳过，
        #   界面上显示得清清楚楚、点下去什么也没发生。
        if os.path.isfile(p):
            try:
                os.makedirs(bucket, exist_ok=True)
                n = os.path.basename(p)
                dst = os.path.join(bucket, n)
                i = 1
                while os.path.exists(dst):
                    base, ext = os.path.splitext(n)
                    dst = os.path.join(bucket, "%s-%d%s" % (base, i, ext))
                    i += 1
                shutil.move(p, dst)
                done.append(n)
                manifest.append({"name": os.path.basename(dst), "key": t["key"],
                                 "label": t.get("label") or "",
                                 "from": os.path.dirname(p)})
            except Exception as e:
                failed.append("%s（%s）" % (os.path.basename(p), str(e)[:60]))
            continue
        if not os.path.isdir(p):
            continue
        for n in os.listdir(p):
            if n.startswith(".") and not _inc_hidden:
                continue
            if n in (t.get("exclude") or []):
                continue
            src = os.path.join(p, n)
            try:
                os.makedirs(bucket, exist_ok=True)
                dst = os.path.join(bucket, n)
                i = 1
                while os.path.exists(dst):
                    base, ext = os.path.splitext(n)
                    dst = os.path.join(bucket, "%s-%d%s" % (base, i, ext))
                    i += 1
                shutil.move(src, dst)
                done.append(n)
                manifest.append({"name": os.path.basename(dst), "key": t["key"],
                                 "label": t.get("label") or "", "from": p})
            except Exception as e:
                failed.append("%s（%s）" % (n, str(e)[:60]))
    if manifest:
        try:
            with open(os.path.join(bucket, "_清除清单.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    # 状态与日志一并归零，界面不会还挂着上一批结果
    _state.update({"log": [], "done": [], "failed": [], "percent": 0, "index": 0,
                   "current": "", "stage": "", "total": 0})
    return {"ok": True, "moved": len(done), "failed": failed,
            "trash": bucket if done else ""}


def ai_remap(task):
    """按案件批量重命名假名：本地模型给占位符起名，校验唯一后替换成品与映射表。

    为什么放在「成品之后」而不是重跑：占位符是唯一的，全文替换不会误伤，
    也不需要重新识别一遍；错了还能拿原映射表回滚。
    """
    tdir = os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")))
    outd = os.path.join(tdir, "output")
    if not tdir or not os.path.isdir(outd):
        return {"ok": False, "msg": "任务不存在或已过期"}
    conf = ai_config()
    if not conf.get("enabled"):
        return {"ok": False, "msg": "本地 AI 已关闭，先到「本地 AI」里启用"}
    try:
        import alias_ai as AA
        import preview_build as PB
    except Exception as e:
        return {"ok": False, "msg": "化名模块不可用：%s" % str(e)[:120]}

    files = [f for f in sorted(os.listdir(outd))
             if f.lower().endswith(".docx") and not f.startswith(".")]
    if not files:
        return {"ok": False, "msg": "只支持 Word 成品；PDF/扫描件请用「手动涂黑」"}

    changed = 0
    notes = []
    for fn in files:
        p = os.path.join(outd, fn)
        stem = os.path.splitext(fn)[0]
        src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        map_csv = os.path.join(KEYS, "%s_映射表.csv" % src_stem)
        if not os.path.exists(map_csv):
            notes.append("%s：找不到映射表，跳过" % fn)
            continue
        head, rows = AA.load_mapping(map_csv)
        # 给模型看脱敏后的正文（无真名），让它按角色/行业起名，而不是瞎猜
        ctx = ""
        try:
            from docx import Document as _Doc
            ctx = "\n".join(x.text for x in _Doc(p).paragraphs if (x.text or "").strip())
        except Exception:
            ctx = ""
        plan, why = AA.rename_plan(rows, conf.get("host"), conf.get("model"), context=ctx)
        if not plan:
            notes.append("%s：%s" % (fn, why))
            continue
        # 改之前留一份，改错了能回滚
        try:
            shutil.copy2(p, p + ".bak")
            shutil.copy2(map_csv, map_csv + ".bak")
        except Exception:
            pass
        _, cnt = AA.apply_plan_to_docx(p, plan, p)
        newrows = [(o, plan.get(ph, ph), c) for o, ph, c in rows]
        AA.save_mapping(map_csv, head, newrows)
        changed += len(plan)
        notes.append("%s：%s（替换 %d 处）" % (fn, why, cnt))

        # 预览数据重算，否则页面上还是旧化名
        fdir = os.path.join(tdir, "files", "1")
        orig = ""
        for cand in (os.path.join(INBOX, "已处理", src_stem + ".docx"),
                     os.path.join(INBOX, src_stem + ".docx")):
            if os.path.exists(cand):
                orig = cand
                break
        if orig and os.path.isdir(fdir):
            try:
                meta = PB.build_preview(orig, p, map_csv, fdir, os.path.basename(orig))
                meta["file"] = os.path.basename(orig)
                meta.update({"output_path": p, "preview_path": p,
                             "task_id": os.path.basename(tdir), "index": 1,
                             "output_name": fn})
                with open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                with open(os.path.join(tdir, "index.json"), "w", encoding="utf-8") as f:
                    json.dump({"task_id": os.path.basename(tdir),
                               "files": [{k: meta.get(k) for k in
                                          ("index", "file", "count", "by_category",
                                           "entry_id", "output_name")}]},
                              f, ensure_ascii=False, indent=2)
            except Exception as e:
                notes.append("%s：预览重算失败（%s）" % (fn, str(e)[:80]))
    return {"ok": True, "changed": changed, "notes": notes}


# ---------------- 还原预览：逐处列出占位符，允许人工指定 ----------------
def _iter_blocks(doc):
    """按固定顺序产出 (区块编号, 段落对象)，plan 与 apply 必须用同一套编号。"""
    i = 0
    for p in doc.paragraphs:
        yield ("p%d" % i, p)
        i += 1
    ti = 0
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield ("t%d" % ti, p)
                    ti += 1
    for sec in doc.sections:
        for hf in (sec.header, sec.footer):
            for p in hf.paragraphs:
                yield ("h%d" % ti, p)
                ti += 1


def restore_plan(docx_path, map_csv):
    """把脱敏件里每个占位符出现的位置、上下文、候选原值列出来。

    为什么要逐处而不是整表替换：一个占位符可能对应多个真实主体
    （早版本「敏感1」把张总李总都吞了），整表替换只能挑一个，
    剩下的全被换成同一个人，而且不报错。这里把每一处摊开，人能一眼看出哪处不对。
    """
    import csv as _csv
    from docx import Document

    if not (docx_path and os.path.exists(docx_path)):
        return {"ok": False, "msg": "文件不存在"}
    if not (map_csv and os.path.exists(map_csv)):
        return {"ok": False, "msg": "映射表不存在"}

    by_ph = {}
    try:
        with open(map_csv, encoding="utf-8-sig") as f:
            for row in _csv.reader(f):
                if len(row) < 2:
                    continue
                o, ph = row[0].strip(), row[1].strip()
                if not o or not ph or o == "原值":
                    continue
                cat = row[2].strip() if len(row) > 2 else ""
                by_ph.setdefault(ph, {"orig": o, "cat": cat,
                                      "candidates": []})["candidates"].append(o)
    except Exception as e:
        return {"ok": False, "msg": "映射表读取失败：%s" % str(e)[:100]}
    if not by_ph:
        return {"ok": False, "msg": "映射表是空的"}

    phs = sorted(by_ph, key=len, reverse=True)
    try:
        doc = Document(docx_path)
    except Exception as e:
        return {"ok": False, "msg": "只支持 Word 成品还原（%s）" % str(e)[:80]}

    occ = []
    for bid, p in _iter_blocks(doc):
        text = p.text or ""
        if not text:
            continue
        taken = []
        hits = []
        for ph in phs:
            start = 0
            while True:
                k = text.find(ph, start)
                if k < 0:
                    break
                if not any(a <= k < b for a, b in taken):
                    taken.append((k, k + len(ph)))
                    hits.append((k, ph))
                start = k + len(ph)
        hits.sort()
        for k, ph in hits:
            pre = text[max(0, k - 14):k].replace("\n", " ")
            post = text[k + len(ph):k + len(ph) + 14].replace("\n", " ")
            info = by_ph[ph]
            occ.append({
                "id": "%s#%d" % (bid, k),
                "block": bid,
                "pos": k,
                "ph": ph,
                "cat": info["cat"],
                "orig": info["orig"],
                "candidates": info["candidates"],
                "before": pre,
                "after": post,
            })

    groups = []
    for ph, info in by_ph.items():
        cnt = sum(1 for o in occ if o["ph"] == ph)
        if not cnt:
            continue
        groups.append({"ph": ph, "cat": info["cat"], "orig": info["orig"],
                       "candidates": info["candidates"], "count": cnt,
                       "conflict": len(info["candidates"]) > 1})
    groups.sort(key=lambda g: (-g["count"], g["ph"]))
    return {"ok": True, "file": os.path.basename(docx_path),
            "groups": groups, "occurrences": occ,
            "total": len(occ)}


def _span_positions(text, phs):
    """按「长占位符优先、不重叠」找出所有出现位置。plan 与 apply 共用。"""
    taken, hits = [], []
    for ph in phs:
        k = 0
        while True:
            k = text.find(ph, k)
            if k < 0:
                break
            if not any(a <= k < b for a, b in taken):
                taken.append((k, k + len(ph)))
                hits.append((k, ph))
            k += len(ph)
    hits.sort()
    return hits


def _load_map_pairs(map_csv):
    import csv as _csv
    by_ph = {}
    with open(map_csv, encoding="utf-8-sig") as f:
        for row in _csv.reader(f):
            if len(row) < 2:
                continue
            o, ph = row[0].strip(), row[1].strip()
            if not o or not ph or o == "原值":
                continue
            by_ph.setdefault(ph, {"orig": o, "cat": row[2].strip() if len(row) > 2 else "",
                                  "candidates": []})["candidates"].append(o)
    return by_ph


def restore_blocks(docx_path, map_csv):
    """把脱敏件按「正文块」吐出来，供还原预览页就地渲染。

    为什么不用一条条的清单：用户要的是"跟手动涂黑一样，在文件上直接看"，
    清单看不出语境——同一句里两个「张某」谁是谁，只有看到整段才分得清。
    """
    from docx import Document
    if not (docx_path and os.path.exists(docx_path)):
        return {"ok": False, "msg": "文件不存在"}
    try:
        by_ph = _load_map_pairs(map_csv)
        doc = Document(docx_path)
    except Exception as e:
        return {"ok": False, "msg": "打开失败：%s" % str(e)[:90]}
    phs = sorted(by_ph, key=len, reverse=True)

    blocks, total = [], 0
    for bid, p in _iter_blocks(doc):
        text = p.text or ""
        if not text.strip():
            continue
        occ = []
        for pos, ph in _span_positions(text, phs):
            info = by_ph[ph]
            occ.append({"pos": pos, "len": len(ph), "ph": ph,
                        "oid": "%s#%d" % (bid, pos),
                        "orig": info["orig"], "cands": info["candidates"]})
        total += len(occ)
        bold = False
        try:
            bold = bool(p.runs and p.runs[0].bold)
        except Exception:
            pass
        blocks.append({"id": bid, "text": text, "occ": occ, "bold": bold,
                       "align": str(getattr(p.alignment, "name", "") or "")})

    groups = []
    for ph, info in by_ph.items():
        cnt = sum(1 for b in blocks for o in b["occ"] if o["ph"] == ph)
        if cnt:
            groups.append({"ph": ph, "cat": info["cat"], "orig": info["orig"],
                           "candidates": info["candidates"], "count": cnt,
                           "conflict": len(info["candidates"]) > 1})
    groups.sort(key=lambda g: (-g["count"], g["ph"]))
    return {"ok": True, "file": os.path.basename(docx_path), "blocks": blocks,
            "groups": groups, "total": total}


def restore_ai_suggest(docx_path, map_csv, host="", model="", limit=40):
    """让本地模型按上下文判断「这一处该还原成谁」。

    只在有歧义时才有意义：同一个假名对应多个真实主体（老版本把张总李总
    都脱成「敏感1」）。映射表一对一的时候不必问模型——答案是确定的。
    """
    blk = restore_blocks(docx_path, map_csv)
    if not blk.get("ok"):
        return blk
    items = []
    for b in blk["blocks"]:
        for o in b["occ"]:
            if len(o.get("cands") or []) < 2:
                continue
            items.append({
                "id": o["oid"],
                "占位符": o["ph"],
                "前文": (b["text"][max(0, o["pos"] - 40):o["pos"]] or "").strip(),
                "后文": (b["text"][o["pos"] + o["len"]:o["pos"] + o["len"] + 40] or "").strip(),
                "候选": (o.get("cands") or [])[:8],
            })
    if not items:
        return {"ok": True, "suggest": {},
                "note": "没有需要 AI 判断的歧义（每个假名只对应一个原值）"}
    items = items[:limit]

    try:
        from llm_scan import http_json, DEFAULT_HOST, DEFAULT_MODEL
    except Exception as e:
        return {"ok": False, "msg": "模型模块不可用：%s" % str(e)[:80]}
    host = host or DEFAULT_HOST
    model = model or DEFAULT_MODEL
    sys_p = ("你在帮助还原一份脱敏法律文书。每一处占位符都可能对应多个真实主体，"
             "请根据上下文（前文/后文）判断这一处最可能是候选里的哪一个。"
             "只输出 JSON 对象：键是 id，值是候选中的某一个；拿不准就不要输出该条。"
             "不要解释，不要编造候选以外的名字。")
    payload = {"model": model, "stream": False,
               "options": {"temperature": 0},
               "messages": [{"role": "system", "content": sys_p},
                            {"role": "user", "content": json.dumps(items, ensure_ascii=False)}]}
    try:
        data = http_json(host.rstrip("/") + "/api/chat", payload, timeout=180)
        raw = (data.get("message") or {}).get("content", "")
    except Exception as e:
        return {"ok": False, "msg": "模型调用失败：%s" % str(e)[:100]}
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j <= i:
        return {"ok": True, "suggest": {}, "note": "模型没有给出可用的判断"}
    try:
        got = json.loads(raw[i:j + 1])
    except Exception:
        return {"ok": True, "suggest": {}, "note": "模型返回格式不对，已忽略"}
    cand_of = {it["id"]: it["候选"] for it in items}
    out = {}
    for k, v in (got or {}).items():
        if k in cand_of and str(v) in cand_of[k]:
            out[k] = str(v)
    return {"ok": True, "suggest": out,
            "note": "AI 给出 %d 处判断（其余拿不准的保持默认）" % len(out)}


def restore_apply(docx_path, map_csv, choices, out_dir, name_hint=""):
    """按逐处指定把占位符换回真名。

    choices 只是**覆盖**：没指定的位置仍按映射表的原值还原。
    这样用户只改他看出来不对的那几处，其余照旧，不用逐条填。
    """
    from docx import Document
    if not (docx_path and os.path.exists(docx_path)):
        return {"ok": False, "msg": "文件不存在"}
    if not (map_csv and os.path.exists(map_csv)):
        return {"ok": False, "msg": "映射表不存在"}
    try:
        by_ph = _load_map_pairs(map_csv)
        doc = Document(docx_path)
    except Exception as e:
        return {"ok": False, "msg": "打开失败：%s" % str(e)[:90]}
    if not by_ph:
        return {"ok": False, "msg": "映射表是空的"}

    phs = sorted(by_ph, key=len, reverse=True)
    stat = {"n": 0, "over": 0, "blocks": 0}
    choices = choices or {}

    for bid, p in _iter_blocks(doc):
        text = p.text or ""
        if not text:
            continue
        occ = _span_positions(text, phs)
        if not occ:
            continue
        edits = []
        for pos, ph in occ:
            key = "%s#%d" % (bid, pos)
            val = choices.get(key) or by_ph[ph]["orig"]
            if key in choices:
                stat["over"] += 1
            edits.append((pos, ph, val))
        edits.sort(reverse=True)

        runs = p.runs
        offs, cur = [], 0
        for r in runs:
            offs.append(cur)
            cur += len(r.text or "")
        spanning = False
        for pos, ph, _v in edits:
            endp = pos + len(ph)
            if not any(o <= pos and endp <= o + len(r.text or "") for r, o in zip(runs, offs)):
                spanning = True
                break

        if not spanning:
            for pos, ph, val in edits:
                endp = pos + len(ph)
                for idx, (r, o) in enumerate(zip(runs, offs)):
                    rl = len(r.text or "")
                    if o <= pos and endp <= o + rl:
                        t = r.text
                        a, b = pos - o, pos - o + len(ph)
                        r.text = t[:a] + val + t[b:]
                        stat["n"] += 1
                        delta = len(val) - len(ph)
                        # 只挪后面的 run：把自己这一段的起点也加上 delta，
                        # 下一次替换就会少算一个字（实测吞掉「：」，留下孤零零的「]」）
                        for j in range(idx + 1, len(offs)):
                            offs[j] += delta
                        break
        else:
            t = text
            for pos, ph, val in edits:
                t = t[:pos] + val + t[pos + len(ph):]
                stat["n"] += 1
            if runs:
                runs[0].text = t
                for r in runs[1:]:
                    r.text = ""
        stat["blocks"] += 1

    # 还原后还有没有漏网的占位符：批注修订把占位符切碎时，这一处就匹配不上，
    # 只会在成品里留一个 [地址]（2026-11-02 用户问「批注后还能不能复原」）。
    residual = []
    try:
        for _bid, _p in _iter_blocks(doc):
            _t = _p.text or ""
            for _ph in phs:
                if _ph and _ph in _t:
                    residual.append(_ph)
        residual = sorted(set(residual))
    except Exception:
        residual = []

    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(docx_path))[0]
    if base.endswith("_已脱敏"):
        base = base[:-len("_已脱敏")]
    out = os.path.join(out_dir, "%s_已还原.docx" % (name_hint or base))
    doc.save(out)
    return {"ok": True, "out": out, "replaced": stat["n"],
            "overridden": stat["over"], "blocks": stat["blocks"],
            "residual": residual, "residual_count": len(residual)}


def unredact_log_path(task, fno="1"):
    return os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")),
                        "files", str(fno), "unredact_log.json")


def unredact_log(task, fno="1"):
    p = unredact_log_path(task, fno)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def redo_unredact(task, ph, fno="1"):
    """把误撤销的脱敏再装回去：原文 → 假名，映射表也补回一条。

    用户场景（2026-11-02）：「不小心删了正确的脱敏项，我想退回去」。
    """
    log = unredact_log(task, fno)
    entry = None
    for it in log:
        if it.get("ph") == ph:
            entry = it
            break
    if not entry:
        return {"ok": False, "msg": "没有这一条撤销记录"}
    tdir = os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")))
    outd = os.path.join(tdir, "output")
    name = ""
    try:
        with open(os.path.join(tdir, "index.json"), encoding="utf-8") as f:
            data = json.load(f)
        for it in data.get("files", []):
            if str(it.get("index")) == str(fno):
                name = it.get("output_name") or ""
                break
    except Exception:
        pass
    if not name:
        cand = [x for x in sorted(os.listdir(outd)) if not x.startswith(".")]
        name = cand[0] if cand else ""
    src = os.path.join(outd, name)
    if not (name and os.path.exists(src)):
        return {"ok": False, "msg": "成品已不在"}
    orig = entry.get("orig") or ""
    if not orig:
        return {"ok": False, "msg": "撤销记录里没有原文"}
    try:
        import alias_ai as AA
        _, cnt = AA.apply_plan_to_docx(src, {orig: ph}, src)
        # 映射表补回这一条
        stem = os.path.splitext(name)[0]
        src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        map_csv = ""
        for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
            p2 = os.path.join(KEYS, cand)
            if os.path.exists(p2):
                map_csv = p2
                break
        if map_csv:
            head, rows = AA.load_mapping(map_csv)
            if not any(q == ph for _o, q, _c in rows):
                rows.append((orig, ph, entry.get("cat") or ""))
                AA.save_mapping(map_csv, head, rows)
    except Exception as e:
        return {"ok": False, "msg": "恢复失败：%s" % str(e)[:120]}

    # 记下这次撤销，准备下一轮
    log = [it for it in unredact_log(task, fno) if it.get("ph") != ph]
    try:
        with open(unredact_log_path(task, fno), "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    # 预览重算
    try:
        refresh_preview_if_stale(tdir, fno)
    except Exception:
        pass
    return {"ok": True, "ph": ph, "orig": orig, "count": cnt}


def refresh_preview_if_stale(tdir, fno="1"):
    """成品比预览数据新 → 重建预览。

    为什么要在读接口里做：撤销脱敏、AI 改化名、手工替换都会改动成品，
    如果只在那几处各自刷新，漏掉一处页面就挂着旧标记 ——
    用户看到"撤销了但红字还在"，就是这个原因（2026-11-02）。
    """
    try:
        import preview_build as PB
        ip = os.path.join(tdir, "index.json")
        name = ""
        try:
            with open(ip, encoding="utf-8") as f:
                d = json.load(f)
            for it in d.get("files", []):
                if str(it.get("index")) == str(fno):
                    name = it.get("output_name") or ""
                    break
        except Exception:
            pass
        if not name:
            cand = [x for x in sorted(os.listdir(os.path.join(tdir, "output")))
                    if not x.startswith(".")]
            name = cand[0] if cand else ""
        out = os.path.join(tdir, "output", name)
        pj = os.path.join(tdir, "files", str(fno), "preview.json")
        if not (name and os.path.exists(out)):
            return False
        if os.path.exists(pj) and os.path.getmtime(pj) >= os.path.getmtime(out) - 0.5:
            return False
        stem = os.path.splitext(name)[0]
        src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        map_csv = ""
        for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
            p2 = os.path.join(KEYS, cand)
            if os.path.exists(p2):
                map_csv = p2
                break
        orig = ""
        for cand in (os.path.join(INBOX, src_stem + ".docx"),
                     os.path.join(INBOX, "已处理", src_stem + ".docx")):
            if os.path.exists(cand):
                orig = cand
                break
        # 2026-11-06 mk15 修：词表里含项目名/字号时，成品文件名本身也会被脱敏
        # （实测 …-远景科技园三期土建工程施工合同 → …-[项目名称]施工合同），
        # 按成品名反推的 src_stem 在待处理区根本不存在 → orig 永远找不到 →
        # preview.json 永不重建 → 预览页空白、count=0，用户以为后台坏了。
        # 回落：按文件名对不上时，若「已处理」+「待处理」里只有一份 docx，就用它；
        # 多文件批次不猜（宁可不建，也不能把 A 的原件配给 B 的成品）。
        if not orig:
            _pool = []
            for _d in (os.path.join(INBOX, "已处理"), INBOX):
                if os.path.isdir(_d):
                    _pool += [os.path.join(_d, x) for x in os.listdir(_d)
                              if x.lower().endswith(".docx") and not x.startswith(".")]
            if len(_pool) == 1:
                orig = _pool[0]
        # ⚡ 2026-11-18：多文件批次不能靠数量猜，改用正文交集精确配对。
        # （成品名被词表脱敏，「某某集团」→「某 某集团」时按名字必失败）
        if not orig:
            orig = _find_orig_by_content(out)
        # 映射表同理：成品名被脱敏后，…_映射表.csv 的前缀也对不上。
        if not map_csv and os.path.isdir(KEYS):
            _maps = [os.path.join(KEYS, x) for x in os.listdir(KEYS)
                     if x.endswith("_映射表.csv")]
            if len(_maps) == 1:
                map_csv = _maps[0]
            elif len(_maps) > 1:
                # 多份映射表里按名字挑：成品名（脱敏后的）本身就对应映射表名，
                # 之前 1015 行已按 src_stem 找过，这里再兜一次按完整 stem 找
                for _m in _maps:
                    if os.path.basename(_m) == "%s_映射表.csv" % stem:
                        map_csv = _m
                        break
        if not (orig and map_csv):
            return False
        fdir = os.path.join(tdir, "files", str(fno))
        os.makedirs(fdir, exist_ok=True)
        # 重建会覆盖 preview.json，而 build_preview 数不出「脱了几处」。
        # 先记下旧的计数，重建完原样补回，否则界面从「已脱敏 42 处」掉成 0。
        _old_cnt, _old_byc = 0, {}
        try:
            with open(os.path.join(fdir, "preview.json"), encoding="utf-8") as _f:
                _old = json.load(_f)
            _old_cnt = int(_old.get("count") or 0)
            _old_byc = _old.get("by_category") or {}
        except Exception:
            pass
        meta = PB.build_preview(orig, out, map_csv, fdir, os.path.basename(orig))
        meta["file"] = os.path.basename(orig)
        meta.update({"output_path": out, "preview_path": out,
                     "task_id": os.path.basename(tdir), "index": int(fno),
                     "output_name": name})
        with open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        if _old_cnt or _old_byc:
            try:
                _pj = os.path.join(fdir, "preview.json")
                with open(_pj, encoding="utf-8") as _f:
                    _pv = json.load(_f)
                if not _pv.get("count"):
                    _pv["count"] = _old_cnt
                if not _pv.get("by_category"):
                    _pv["by_category"] = _old_byc
                with open(_pj, "w", encoding="utf-8") as _f:
                    json.dump(_pv, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return True
    except Exception:
        return False


def _trash_ledger_entries(HS):
    """当前账本 + 废纸篓里所有历史账本，合并去重（只读）。

    ⚡ 2026-11-07 为什么必须合并**全部**而不是只看最近一本：
    用户每点一次「清除全部」，`历史/` 整组（含账本.json）就被
    shutil.move 进 ~/.Trash/立丰脱敏-清除-<时间>/，新账本从空开始记。
    于是废纸篓里躺着一串账本，每个只记住自己那一轮的任务：
        012630 那一轮 → 012608-861
        012029 那一轮 → 010314-229 / 010106-954 / 011719-014 …
    只看最近一本，早一轮的任务就永远找不回来 —— 实测 010314-229 会报
    「任务不存在」，用户看到的就是「预览不可用」。
    """
    out, seen = [], set()

    def _take(items, tdir):
        for it in items or []:
            if not isinstance(it, dict):
                continue
            eid = it.get("id") or ""
            if eid and eid in seen:
                continue
            if eid:
                seen.add(eid)
            # 账本里记的路径多半已随目录搬走，就地改指废纸篓那份
            sp = it.get("map_snapshot") or ""
            if sp and not os.path.exists(sp) and eid:
                alt = os.path.join(tdir, eid, "映射表.csv")
                if os.path.exists(alt):
                    it["map_snapshot"] = alt
            op = it.get("output_path") or ""
            if op and not os.path.exists(op):
                alt2 = os.path.join(tdir, it.get("task_id") or "",
                                    "output", os.path.basename(op))
                if os.path.exists(alt2):
                    it["output_path"] = alt2
            out.append(it)

    if HS is not None:
        try:
            _take(HS.list_entries(0), "")
        except Exception:
            pass
    try:
        trash = os.path.join(HOME, ".Trash")
        if os.path.isdir(trash):
            for d in sorted(os.listdir(trash), reverse=True):
                if not d.startswith("立丰脱敏-清除-"):
                    continue
                p = os.path.join(trash, d, "账本.json")
                if not os.path.exists(p):
                    continue
                try:
                    with open(p, encoding="utf-8") as f:
                        doc = json.load(f)
                except Exception:
                    continue
                items = doc.get("entries") if isinstance(doc, dict) else doc
                if isinstance(items, list):
                    _take(items, os.path.join(trash, d))
    except Exception:
        pass
    return out


_TRASH_ROOT = os.path.join(HOME, ".Trash")


def _alive_path(p):
    """这个路径还算「用户手上真有的文件」吗？

    三条都要满足：非空、存在、**不在废纸篓里**。
    第三条是 2026-11-07 补的：`_trash_ledger_entries` 为了修「任务找不回」，
    会把已搬走的路径改指到 `~/.Trash/立丰脱敏-清除-*/` 下的备份。
    文件确实还在，但用户已经点过「清除」了 —— 再把它列进「最近脱敏」，
    用户看到的就是「我明明清了，列表里还挂着」，即所谓的「删不干净」。
    """
    if not p:
        return False
    try:
        if not os.path.exists(p):
            return False
    except Exception:
        return False
    try:
        rp = os.path.realpath(p)
        rt = os.path.realpath(_TRASH_ROOT)
        if rp == rt or rp.startswith(rt + os.sep):
            return False
    except Exception:
        pass
    return True


def _ledger_entries_for_history(HS):
    """历史页用：按创建时间倒序，最多 50 条。

    ⚡ 2026-11-07 补「过滤已失效条目」，起因是用户说「最近脱敏删不干净」：
    回落逻辑会遍历**废纸篓里所有旧账本**（为了修「任务找不到」），
    但那些旧账本记的任务，文件多半已经被「清除全部」搬走了。
    结果清完之后，首页「最近脱敏」里还挂着一串点不开的条目 ——
    点进去就是「任务不存在或已过期」，看着就像没清干净。

    判据：`preview_path` 和 `output_path` **都不存在**时才算失效。
    不能只看预览 —— 「账本被清、成品还在」是上一轮特意救回来的场景，
    那种条目点进去仍然能看成品，必须留着。
    """
    items = _trash_ledger_entries(HS)
    alive = []
    for it in items:
        pp = it.get("preview_path") or ""
        op = it.get("output_path") or ""
        # 废纸篓里的副本**不算活着**。`_trash_ledger_entries` 会把已搬走的路径
        # 改指到 ~/.Trash/立丰脱敏-清除-*/ 下的备份，文件确实存在，
        # 但用户已经点过「清除」了，再把它列进「最近脱敏」就是「删不干净」的观感。
        if _alive_path(pp) or _alive_path(op):
            alive.append(it)
    alive.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return alive[:50]


def revive_task_from_ledger(task):
    """任务目录被清掉了，但成品和账本还在 → 原地重建一个能用的预览任务。

    ⚡ 2026-11-07 修「预览任务不存在」的**根**：

    用户看到的报错是「任务不存在或已过期」。查下来不是 App 算错了 id，
    而是预览目录被「清除全部」整组搬进废纸篓了（废纸篓里 8 个
    「立丰脱敏-清除-」目录，每个都装着几十个任务编号）。目录没了，
    历史里的 task_id 自然指向空 —— 任何旧链接都必然 404。

    第一层修法是「别再默认勾上预览任务」（已改 clear_targets + 前端）。
    但那只防住以后：**已经被清掉的、以及别处清掉的**，还是要能看。
    硬道理是：预览任务只是中间件，真正的成品一直在
    `~/Documents/立丰脱敏/成品/<名字>`，账本里还冻结着当时的映射表。
    有这两样，预览数据 100% 能重算出来 —— 那就重算，不要甩报错。

    做法：
      1. 账本里找这个 task 的条目（历史账本 task_id 字段）；
      2. 成品必须还在（output_path，或退回预览 output/、成品目录同名）；
      3. 用账本冻结的映射表 + 原件重建 preview.json（原件找不到时，
         只要有映射表也能建，只是「点开看原值」那一步会缺）；
      4. 重建 index.json / meta.json，让任务目录重新成立。

    返回 True 表示目录现在可用了。
    """
    task = os.path.basename(str(task or ""))
    if not task:
        return False
    base = os.path.join(PREVIEW_ROOT, task)
    if os.path.isdir(os.path.join(base, "output")):
        return True          # 本来就活着，不是这个函数的活
    try:
        import history_store as HS
        import preview_build as PB
    except Exception:
        return False

    # ---- 1. 账本里认领这个 task_id ----
    #  ⚡ 2026-11-07 二次补洞：账本本身也在「历史」目录里，
    #  「清除全部」把整组历史搬进废纸篓时，账本.json 一起走了。
    #  于是 list_entries() 返回空 → 下面全线失守 → 用户看到的就是
    #  「预览任务不存在」。清过之后连账本都读不到，这个找回等于没做。
    #  所以改走 _trash_ledger_entries（当前账本 + 废纸篓全部历史账本）。
    ents = []
    try:
        for e in _trash_ledger_entries(HS):
            if (e.get("task_id") or "") == task:
                ents.append(e)
    except Exception:
        ents = []
    if not ents:
        return False

    # 先把成品找回来。这里必须多路找，不能只信账本的 output_path ——
    # 实测发现一个致命细节：**没导出过的任务，账本记的 output_path 就是
    # 预览任务自己那个目录**（…/预览/<task>/output/xxx.docx），
    # 任务目录一被清，这条路径跟着一起没了，等于账本什么都没记住。
    ent = ents[0]
    out_src = ""

    def _looks_like(name):
        """成品名字得像个成品：扩展名是 docx 系列、不是备份/临时件。"""
        low = (name or "").lower()
        return (low.endswith((".docx", ".docm"))
                and not low.endswith((".bak", ".tmp"))
                and ".bak" not in low)

    # ① 账本记的路径还活着（已导出过的任务走这里）
    for e in ents:
        p = e.get("output_path") or ""
        if p and os.path.exists(p) and _looks_like(os.path.basename(p)):
            out_src = p
            ent = e
            break
    name = ent.get("output_name") or (os.path.basename(out_src) if out_src else "")

    # ② 成品目录里同名的那份（最常见的情况：用户点过导出，或本来就自动落了盘）
    if not out_src and name:
        cand = os.path.join(OUTBOX, name)
        if os.path.exists(cand):
            out_src = cand

    # ③ 还没找到 → 在成品目录里按「去掉 _已脱敏 后同名」再找一遍
    if not out_src and name:
        stem = os.path.splitext(name)[0]
        bare = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        for cand_name in (name, bare + ".docx", bare + "_已脱敏.docx"):
            cand = os.path.join(OUTBOX, cand_name)
            if os.path.exists(cand):
                out_src = cand
                name = cand_name
                break

    # ④ 最后一条路：用账本冻结的映射表去成品目录里比对内容。
    #    映射表里的原值虽然不能读（那是真名），但**占位符**能读，
    #    成品里一定含这些占位符 —— 命中最多的那份就是它。
    if not out_src:
        snap = ent.get("map_snapshot") or ""
        phs = []
        if snap and os.path.exists(snap):
            try:
                import csv as _csv
                with open(snap, encoding="utf-8-sig") as _f:
                    rd = list(_csv.reader(_f))
                head = [c.strip() for c in (rd[0] if rd else [])]
                iph = head.index("占位符") if "占位符" in head else 1
                for r in rd[1:]:
                    if len(r) > iph and r[iph].strip():
                        phs.append(r[iph].strip())
            except Exception:
                phs = []
        if phs:
            best, best_hit = "", 0
            try:
                for fn in os.listdir(OUTBOX):
                    if not _looks_like(fn):
                        continue
                    fp = os.path.join(OUTBOX, fn)
                    try:
                        from docx import Document
                        txt = "\n".join(p.text for p in Document(fp).paragraphs)
                    except Exception:
                        continue
                    hit = sum(1 for ph in phs if ph and ph in txt)
                    if hit > best_hit:
                        best, best_hit = fp, hit
            except Exception:
                pass
            # 至少命中一半占位符才认，避免配错文件
            if best and best_hit >= max(1, len(phs) // 2):
                out_src = best
                name = os.path.basename(best)

    if not out_src:
        # ⑤ 最后一条路：去废纸篓里找。
        #    「清除全部」是把整组目录 shutil.move 进 ~/.Trash/立丰脱敏-清除-<时间>/，
        #    未导出的成品就躺在里面 …/<task>/output/<名字>。
        #    用户点历史里的「查看」时，我们照样能把它捞回来重建成预览 ——
        #    「清过」不等于「没了」，只是换了个地方。
        try:
            trash = os.path.join(HOME, ".Trash")
            cands = []
            if os.path.isdir(trash):
                for d in os.listdir(trash):
                    if not d.startswith("立丰脱敏-清除-"):
                        continue
                    # ① 整个任务目录被搬走：<桶>/<task>/output/<name>
                    p1 = os.path.join(trash, d, task, "output")
                    if name and os.path.isdir(p1):
                        p = os.path.join(p1, name)
                        if os.path.exists(p):
                            cands.append((os.path.getmtime(p), p))
                    # ② 只有 output 里的文件被搬出来：<桶>/<name>
                    if name:
                        p2 = os.path.join(trash, d, name)
                        if os.path.exists(p2):
                            cands.append((os.path.getmtime(p2), p2))
                    # ③ 名称被去重加了 -1/-2 后缀
                    if name:
                        stem, ext = os.path.splitext(name)
                        for k in range(1, 6):
                            p3 = os.path.join(trash, d, "%s-%d%s" % (stem, k, ext))
                            if os.path.exists(p3):
                                cands.append((os.path.getmtime(p3), p3))
            if cands:
                cands.sort(reverse=True)     # 最近一次清除的优先
                out_src = cands[0][1]
                if not name:
                    name = os.path.basename(out_src)
        except Exception:
            pass

    if not out_src:
        return False         # 连带废纸篓里都没有，重建不了，老实报错

    if not name:
        name = os.path.basename(out_src)
    fno = str(ent.get("index") or 1)

    # ---- 2. 映射表：账本冻结的那份最准 ----
    map_csv = ent.get("map_snapshot") or ""
    if not (map_csv and os.path.exists(map_csv)):
        map_csv = ""
        # 账本记的快照路径失效 → 先去废纸篓按 entry id / 任务编号找
        _eid = ent.get("id") or ""
        if _eid:
            try:
                trash = os.path.join(HOME, ".Trash")
                for d in sorted(os.listdir(trash), reverse=True) \
                        if os.path.isdir(trash) else []:
                    if not d.startswith("立丰脱敏-清除-"):
                        continue
                    for cand in (os.path.join(trash, d, _eid, "映射表.csv"),
                                 os.path.join(trash, d, task, "映射表.csv")):
                        if os.path.exists(cand):
                            map_csv = cand
                            break
                    if map_csv:
                        break
            except Exception:
                pass
    if not map_csv:
        stem = os.path.splitext(name)[0]
        src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
            p2 = os.path.join(KEYS, cand)
            if os.path.exists(p2):
                map_csv = p2
                break

    try:
        fdir = os.path.join(base, "files", fno)
        outd = os.path.join(base, "output")
        os.makedirs(fdir, exist_ok=True)
        os.makedirs(outd, exist_ok=True)
        dst = os.path.join(outd, name)
        if os.path.abspath(dst) != os.path.abspath(out_src):
            shutil.copy2(out_src, dst)

        # ---- 3. 原件：能找就找，找不到也要建（预览只显示脱敏后的文字）----
        stem = os.path.splitext(name)[0]
        src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        orig = ""
        for cand in (os.path.join(INBOX, src_stem + ".docx"),
                     os.path.join(INBOX, "已处理", src_stem + ".docx"),
                     os.path.join(BAD_DIR, "原件", src_stem + ".docx")):
            if os.path.exists(cand):
                orig = cand
                break
        if not orig:
            # 单文件批次才可以猜；多文件时宁可不对齐，也不能把 A 的原件配给 B
            pool = []
            for d in (os.path.join(INBOX, "已处理"), INBOX):
                if os.path.isdir(d):
                    pool += [os.path.join(d, x) for x in os.listdir(d)
                             if x.lower().endswith(".docx") and not x.startswith(".")]
            if len(pool) == 1:
                orig = pool[0]
        # 原件实在没有就拿成品自己当「原件」：这样段落/表格结构照常出，
        # 只是每处替换的「原值」查不到（origs 为空），比整页报错强得多。
        src_for_build = orig or dst

        meta = PB.build_preview(src_for_build, dst, map_csv, fdir, os.path.basename(name))
        meta["file"] = os.path.basename(name)
        # 重建时 build_preview 是从文件反推的，数不出「脱了几处」——
        # 但账本里记着当时的 count / by_category，直接拿账本的数盖回去，
        # 否则界面会显示「已脱敏 0 处」，用户以为白脱了。
        # 注意：这两个数 **preview.json 里也有一份**，而且前端读的是 preview.json，
        # 只改 meta.json 没用（实测 count 仍是 0）。
        _cnt = int(ent.get("count") or 0)
        _byc = ent.get("by_category") or {}
        if not meta.get("count"):
            meta["count"] = _cnt
        if not meta.get("by_category"):
            meta["by_category"] = _byc
        meta.update({"output_path": out_src, "preview_path": out_src,
                     "task_id": task, "index": int(fno) if str(fno).isdigit() else 1,
                     "output_name": name, "revived_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        with open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        # 同步写进 preview.json：前端只认它里面的 count/by_category
        _pj = os.path.join(fdir, "preview.json")
        if _cnt or _byc:
            try:
                with open(_pj, encoding="utf-8") as f:
                    _pv = json.load(f)
                if not _pv.get("count"):
                    _pv["count"] = _cnt
                if not _pv.get("by_category"):
                    _pv["by_category"] = _byc
                with open(_pj, "w", encoding="utf-8") as f:
                    json.dump(_pv, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # ---- 4. index.json：预览页的文件切换器、导出都要读它 ----
        files = []
        for i, e in enumerate(ents):
            nm = e.get("output_name") or name
            files.append({"index": int(e.get("index") or (i + 1)),
                          "file": nm.replace("_已脱敏", ""),
                          "count": e.get("count") or 0,
                          "by_category": e.get("by_category") or {},
                          "entry_id": e.get("id") or "",
                          "output_name": nm})
        with open(os.path.join(base, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"task_id": task, "files": files or
                       [{"index": 1, "file": name.replace("_已脱敏", ""),
                         "count": 0, "output_name": name}]},
                      f, ensure_ascii=False, indent=2)
        _state["log"].append("预览任务 %s 已按成品与账本重建（原目录被清过，数据不影响核对）" % task)
        return True
    except Exception as e:
        _state["log"].append("预览任务 %s 重建失败：%s" % (task, str(e)[:100]))
        return False


def unredact_one(task, ph, nth=1, fno="1"):
    """只还原某一处出现，其余同名的保留脱敏。

    用户原话（2026-11-02）：「单个脱敏项还原，不要一次还原」。
    做法：把全文按占位符切开，只把第 nth 处换回原文；
    其余靠「先换成哨兵 → 再换回」两步走，避免替换时互相串。
    """
    from docx import Document
    tdir = os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")))
    if not task or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在或已过期"}
    outd = os.path.join(tdir, "output")
    name = ""
    try:
        with open(os.path.join(tdir, "index.json"), encoding="utf-8") as f:
            data = json.load(f)
        for it in data.get("files", []):
            if str(it.get("index")) == str(fno):
                name = it.get("output_name") or ""
                break
    except Exception:
        pass
    if not name:
        cand = [x for x in sorted(os.listdir(outd)) if not x.startswith(".")]
        name = cand[0] if cand else ""
    src = os.path.join(outd, name)
    if not (name and os.path.exists(src)):
        return {"ok": False, "msg": "成品还没生成"}
    if not name.lower().endswith(".docx"):
        return {"ok": False, "msg": "PDF/图片请用「手动涂黑」处理"}

    stem = os.path.splitext(name)[0]
    src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
    map_csv = ""
    for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
        p2 = os.path.join(KEYS, cand)
        if os.path.exists(p2):
            map_csv = p2
            break
    if not map_csv:
        return {"ok": False, "msg": "找不到映射表，无法确定原文"}
    try:
        import alias_ai as AA
    except Exception as e:
        return {"ok": False, "msg": "模块不可用：%s" % str(e)[:80]}
    head, rows = AA.load_mapping(map_csv)
    hit = [(o, q, c) for o, q, c in rows if q == ph]
    if not hit:
        return {"ok": False, "msg": "映射表里没有「%s」" % ph}
    orig = hit[0][0]

    # 精确定位「第 nth 处」：逐段逐 run 数出现次数，记下落在哪个 run 的哪个偏移
    try:
        doc = Document(src)
        spots = []          # (段落, run, run 内偏移)
        for _bid, para in _iter_blocks(doc):
            for r in para.runs:
                t = r.text or ""
                k = 0
                while True:
                    k = t.find(ph, k)
                    if k < 0:
                        break
                    spots.append((para, r, k))
                    k += len(ph)
        want = int(nth)
        if want < 1 or want > len(spots):
            return {"ok": False, "msg": "全文只有 %d 处「%s」，没有第 %d 处"
                                        % (len(spots), ph, want)}
        para, run, off = spots[want - 1]
        t = run.text or ""
        run.text = t[:off] + orig + t[off + len(ph):]
        doc.save(src)
    except Exception as e:
        return {"ok": False, "msg": "还原失败：%s" % str(e)[:120]}

    # 这一处撤了，但同名可能还在 → 只有全文再没有该占位符才删映射表
    try:
        remain = 0
        d2 = Document(src)
        for _bid, _p in _iter_blocks(d2):
            remain += (_p.text or "").count(ph)
        if remain == 0:
            AA.save_mapping(map_csv, head, [(o, q, c) for o, q, c in rows if q != ph])
    except Exception:
        pass

    try:
        lg = [x for x in unredact_log(task, fno) if x.get("ph") != ph]
        lg.append({"ph": ph, "orig": orig,
                   "cat": (hit[0][2] if len(hit[0]) > 2 else ""),
                   "nth": int(nth), "one": True,
                   "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
        with open(unredact_log_path(task, fno), "w", encoding="utf-8") as f:
            json.dump(lg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    try:
        refresh_preview_if_stale(tdir, fno)
    except Exception:
        pass
    return {"ok": True, "ph": ph, "orig": orig, "nth": int(nth), "count": 1}


def unredact_item(task, ph):
    """撤销某一处脱敏：把成品里这个假名换回原文，并从映射表里删掉这一条。

    为什么整组撤：映射表是一对一，一个假名只对应一个原值；
    用户说"这个脱敏项错了"，指的就是这个假名判错了，应当整组恢复。
    """
    tdir = os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")))
    if not task or not os.path.isdir(tdir):
        return {"ok": False, "msg": "任务不存在或已过期"}
    outd = os.path.join(tdir, "output")
    name = ""
    ip = os.path.join(tdir, "index.json")
    try:
        with open(ip, encoding="utf-8") as f:
            data = json.load(f)
        files = data.get("files") or []
        if files:
            name = files[0].get("output_name") or ""
    except Exception:
        pass
    if not name:
        cand = [x for x in sorted(os.listdir(outd)) if not x.startswith(".")]
        name = cand[0] if cand else ""
    src = os.path.join(outd, name)
    if not name or not os.path.exists(src):
        return {"ok": False, "msg": "成品还没生成"}
    if not name.lower().endswith(".docx"):
        return {"ok": False, "msg": "PDF/图片请在「手动涂黑」里删框后重新导出"}

    stem = os.path.splitext(name)[0]
    src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
    map_csv = ""
    for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
        p2 = os.path.join(KEYS, cand)
        if os.path.exists(p2):
            map_csv = p2
            break
    if not map_csv:
        return {"ok": False, "msg": "找不到映射表，无法确定原文"}
    try:
        import alias_ai as AA
    except Exception as e:
        return {"ok": False, "msg": "模块不可用：%s" % str(e)[:80]}

    head, rows = AA.load_mapping(map_csv)
    hit = [(o, q, c) for o, q, c in rows if q == ph]
    if not hit:
        return {"ok": False, "msg": "映射表里没有「%s」" % ph}
    orig = hit[0][0]

    try:
        _, cnt = AA.apply_plan_to_docx(src, {ph: orig}, src)
    except Exception as e:
        return {"ok": False, "msg": "恢复原文失败：%s" % str(e)[:100]}
    rest = [(o, q, c) for o, q, c in rows if q != ph]
    AA.save_mapping(map_csv, head, rest)

    # 预览数据重算，否则页面上还挂着已撤销的标记
    try:
        import preview_build as PB
        fdir = os.path.join(tdir, "files", "1")
        o = ""
        for cand in (os.path.join(INBOX, src_stem + ".docx"),
                     os.path.join(INBOX, "已处理", src_stem + ".docx")):
            if os.path.exists(cand):
                o = cand
                break
        if o and os.path.isdir(fdir):
            meta = PB.build_preview(o, src, map_csv, fdir, os.path.basename(o))
            meta["file"] = os.path.basename(o)
            meta.update({"output_path": src, "preview_path": src,
                         "task_id": os.path.basename(tdir), "index": 1,
                         "output_name": name})
            with open(os.path.join(fdir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 记一笔：误撤销还能退回来（供「恢复脱敏」用）
    try:
        lg = [x for x in unredact_log(task) if x.get("ph") != ph]
        lg.append({"ph": ph, "orig": orig,
                   "cat": (hit[0][2] if len(hit[0]) > 2 else ""),
                   "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
        with open(unredact_log_path(task), "w", encoding="utf-8") as f:
            json.dump(lg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {"ok": True, "ph": ph, "orig": orig, "count": cnt}


def _map_fallback(ent):
    """账本里冻结的映射表路径为空/失效时，按成品文件名回到对照表找一份。

    为什么会空：早期几个入口写账本时没带 map_csv，导出后一条记录连映射表都没绑，
    点「复原」就报"映射表已丢失"（2026-11-02 用户踩到）。
    对照表的文件名是稳定的（{源文件名}_映射表.csv），能救回来就先救。
    """
    try:
        import history_store as HS
        mp = HS.resolve_map(ent) if hasattr(HS, "resolve_map") else (ent.get("map_csv") or "")
        if mp and os.path.exists(mp):
            return mp
    except Exception:
        pass
    name = ent.get("output_name") or ""
    stem = os.path.splitext(name)[0]
    for cand in (stem.replace("_已脱敏", ""), stem):
        p2 = os.path.join(KEYS, "%s_映射表.csv" % cand)
        if os.path.exists(p2):
            return p2
    return ent.get("map_csv") or ""

def _unique_repl(base, taken):
    """给手动标记分一个不与现有映射表冲突的占位符。

    用户原话（2026-11-02）：「手动勾选的时候你就自己给它命名一个新名字，
    不然和自动脱敏肯定会存在冲突」。确实如此——手动标记如果也生成 [地址]，
    映射表就出现两条 [地址]，复原时不知道填哪个，只能报冲突。
    """
    base = (base or "").strip() or "[敏感项]"
    if base not in taken:
        return base
    bracket = base.startswith("[") and base.endswith("]")
    core = base[1:-1] if bracket else base
    k = 2
    while True:
        cand = ("[%s%d]" % (core, k)) if bracket else ("%s%d" % (base, k))
        if cand not in taken:
            return cand
        k += 1


def _map_paths_for_task(task, fno="1"):
    """从预览任务反推映射表路径与成品名。"""
    tdir = os.path.join(PREVIEW_ROOT, os.path.basename(str(task or "")))
    name = ""
    try:
        with open(os.path.join(tdir, "index.json"), encoding="utf-8") as f:
            d = json.load(f)
        for it in d.get("files", []):
            if str(it.get("index")) == str(fno):
                name = it.get("output_name") or ""
                break
    except Exception:
        pass
    stem = os.path.splitext(name)[0]
    src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
    mp = ""
    for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
        p2 = os.path.join(KEYS, cand)
        if os.path.exists(p2):
            mp = p2
            break
    return mp, name


# ---------------- 成品转 Markdown（供案件研判 agent 读取） ----------------
MD_DIR_NAME = "MD"


def md_out_dir():
    d = os.path.join(BASE_DIR, MD_DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def md_out_for(src, out_dir=""):
    """按独立入口选的输出位置算 md 路径。

    out_dir 只认三种：空（统一 MD 文件夹）、"source"（源文件同目录）、
    已存在的目录绝对路径。前端只给前两种；这里不接受任意字符串拼路径，
    免得网页传个 "../../" 把文件写到不该写的地方。
    """
    stem = os.path.splitext(os.path.basename(src))[0]
    stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
    if out_dir == "source":
        d = os.path.dirname(os.path.abspath(src))
    elif out_dir and os.path.isdir(out_dir):
        d = os.path.abspath(out_dir)
    else:
        d = md_out_dir()
    return os.path.join(d, stem + ".md")


def to_md(src, out_path="", ocr=True):
    """调用引擎脚本把成品转 md；返回脚本的 JSON 结果。"""
    src = os.path.abspath(str(src or ""))
    if not src or not os.path.exists(src):
        return {"ok": False, "msg": "文件不存在：%s" % src}
    if not out_path:
        stem = os.path.splitext(os.path.basename(src))[0]
        stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
        out_path = os.path.join(md_out_dir(), stem + ".md")
    script = os.path.join(SCRIPTS, "to_markdown.py")
    if not os.path.exists(script):
        return {"ok": False, "msg": "缺少转换脚本 to_markdown.py"}
    # 用哪个解释器跑转换：服务进程自己可能装得精简（没有 openpyxl），
    # 而 env/default 那份是全的。谁 import 得全就用谁，避免 xlsx 转换失败。
    # 2026-11-05 打包分发：改用 py_exe()，它已按「包内 runtime → 系统 → venv」
    # 顺序验过依赖；原来这里写死 ~/.workbuddy，对方机器上取不到。
    # 注意：局部变量不能叫 py_exe，否则会把同名函数遮住（原来就差点踩到）。
    _py = sys.executable
    try:
        _pick = py_exe()
        if _pick:
            _py = _pick
    except Exception:
        pass
    cmd = [_py, script, src, "-o", out_path, "--json"]
    if not ocr:
        cmd.append("--no-ocr")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        out = (r.stdout or b"").decode("utf-8", "ignore").strip()
        i = out.find("{")
        if i >= 0:
            return json.loads(out[i:])
        return {"ok": False, "msg": (out or (r.stderr or b"").decode("utf-8", "ignore"))[:200]}
    except Exception as e:
        return {"ok": False, "msg": "转换失败：%s" % str(e)[:160]}


def to_md_batch(paths, ocr=True):
    """批量转：逐份调，失败不中断，最后汇总。"""
    items = []
    for p0 in paths or []:
        items.append(to_md(p0, ocr=ocr))
    okc = sum(1 for x in items if x.get("ok"))
    return {"ok": True, "count": len(items), "ok_count": okc,
            "fail_count": len(items) - okc, "dir": md_out_dir(), "items": items}


# ---------------- Agent 接入（让本机的 agent 调用本 App） ----------------
AGENT_CONF = os.path.join(APP_SUPPORT, "agent.json")
AGENT_LOG = os.path.join(APP_SUPPORT, "agent_calls.jsonl")


def agent_config():
    d = {"enabled": False, "token": ""}
    try:
        with open(AGENT_CONF, encoding="utf-8") as f:
            d.update(json.load(f) or {})
    except Exception:
        pass
    if not d.get("token"):
        import secrets
        d["token"] = secrets.token_hex(12)
        try:
            os.makedirs(APP_SUPPORT, exist_ok=True)
            with open(AGENT_CONF, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return d


def agent_save(conf):
    d = agent_config()
    if "enabled" in conf:
        d["enabled"] = bool(conf["enabled"])
    if conf.get("new_token"):
        import secrets
        d["token"] = secrets.token_hex(12)
    try:
        with open(AGENT_CONF, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return d


def agent_log(action, ok, reason="", extra=""):
    try:
        import time as _t
        rec = {"ts": _t.strftime("%Y-%m-%d %H:%M:%S"), "action": action,
               "ok": bool(ok), "reason": reason, "extra": extra}
        with open(AGENT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# Agent 驱动界面：它说"打开哪个页面"，App 窗口就跳过去。
# 网页每 1.5 秒问一次，所以 agent 调完接口，界面会自己跟上来。
_NAV = {"url": "", "ts": 0.0}


def agent_recent(n=20):
    out = []
    try:
        with open(AGENT_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return []
    return out[-n:][::-1]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # 2026-11-06：下载类响应（词条对照表模板）要带 Content-Disposition，
        # 否则浏览器会把 xlsx 当文本显示成一屏乱码。
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        """返回 JSON 的简写。

        ⚡ 2026-11-11 补：新写的接口用了 self._json()，但本类**从来没有这个方法**，
        调用直接抛 AttributeError，请求既不返回也不报错 —— 客户端拿到的是
        HTTP 000（连接挂着直到超时）。实测 /api/watermark/info 就是这样挂的，
        表现成「点了没反应」，比报错还难查。
        """
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            p = os.path.join(WEB_DIR, "index.html")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, "界面文件缺失", "text/plain; charset=utf-8")
            return
        # 静态资源：图片 + 样式 + 脚本（前端拆成独立文件，便于维护）
        _STATIC = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml", ".ico": "image/x-icon", ".webp": "image/webp",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".html": "text/html; charset=utf-8",
        }
        _ext = os.path.splitext(u.path)[1].lower()
        if _ext in _STATIC:
            name = os.path.basename(u.path)
            p = os.path.join(WEB_DIR, name)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    self._send(200, f.read(), _STATIC[_ext])
            else:
                self._send(404, b"", _STATIC[_ext])
            return
        if u.path == "/api/status":
            # 平滑补偿：日志长时间没新行（例如本地模型正在长时间推理）时，
            # 按已用时间缓慢推进，封顶在当前阶段的目标值，绝不越过下一阶段。
            # 这样用户看到进度条在动，不会以为卡死；但也不会虚报超过真实进度。
            pct = _state["percent"]
            if _state["running"] and _state["started"]:
                _STAGE_CAP = {1: 8, 2: 35, 3: 70, 4: 90, 5: 99}
                cap = _STAGE_CAP.get(_state["stage_no"], 99)
                el = time.time() - _state["started"]
                # 每 20 秒最多爬 1%，且不超过本阶段上限
                creep = pct + int(el / 20)
                pct = min(cap, max(pct, creep))
            self._send(200, json.dumps({
                "running": _state["running"],
                "cancelled": bool(_state.get("cancelled")),
                "log": _state["log"][-120:],
                "done": _state["done"],
                "failed": _state["failed"],
                "elapsed": int(time.time() - _state["started"]) if _state["started"] else 0,
                "ollama": ollama_up(),
                "has_terms": os.path.exists(TERMS_FILE),
                # 真实进度（用户要求能看到进度条）
                "total": _state["total"],
                "index": _state["index"],
                "current": _state["current"],
                "stage": _state["stage"],
                "percent": pct,
            }, ensure_ascii=False))
            return
        if u.path == "/api/open":
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            if p and os.path.exists(p):
                subprocess.run(["/usr/bin/open", "-R", p], capture_output=True)
                self._send(200, json.dumps({"ok": True}))
            else:
                self._send(404, json.dumps({"ok": False, "msg": "文件不存在"}))
            return
        if u.path == "/api/derestore/maps":
            # 列出可用的映射表，让用户在下拉里挑
            out = []
            try:
                for n in os.listdir(KEYS):
                    if not n.endswith("_映射表.csv"):
                        continue
                    fp = os.path.join(KEYS, n)
                    if not os.path.isfile(fp):
                        continue
                    try:
                        st = os.stat(fp)
                        rows = _read_map_csv(fp)
                        out.append({
                            "name": n,
                            "count": len(rows),
                            "mtime": time.strftime("%m-%d %H:%M",
                                                   time.localtime(st.st_mtime)),
                            "_t": st.st_mtime,
                        })
                    except Exception:
                        continue
                # 按修改时间倒序，最新那份排第一（默认选中）。
                # 不能按文件名排：「（已排版）24-…」以全角括号开头，
                # 排在「30-…」后面，用户每次都得手动翻。
                out.sort(key=lambda x: -x["_t"])
            except Exception:
                pass
            # 词表作为一份「虚拟还原依据」放在最前面，反向使用。
            # 刻意放在 try 外面：映射表目录读挂了，词表照样能用。
            _tp = terms_pairs()
            if _tp:
                try:
                    _mt = time.strftime("%m-%d %H:%M",
                                        time.localtime(os.stat(TERMS_FILE).st_mtime))
                except Exception:
                    _mt = ""
                out.insert(0, {"name": "__terms__", "label": "脱敏词表（反向）",
                               "kind": "terms", "count": len(_tp), "mtime": _mt})
            for x in out:
                x.pop("_t", None)
            self._json({"ok": True, "maps": out[:80]})
            return

        if u.path == "/api/watermark/info":
            # 预览页读这个：这个任务有没有自动去过水印、去了多少、能不能撤销
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            p = os.path.join(PREVIEW_ROOT, task, "watermark.json")
            data = {}
            if task and os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        data = json.load(f) or {}
                except Exception:
                    data = {}
            # 顺便告诉前端备份还在不在 —— 备份被清理过就撤销不了，别给个死按钮
            alive = {}
            for k, v in (data or {}).items():
                alive[k] = os.path.exists((v or {}).get("backup") or "")
            self._json({"ok": True, "watermark": data, "undoable": alive,
                        "task": task})
            return

        if u.path == "/api/openout":
            # ⚡ 2026-11-11 修「点不开文件夹」：
            # 原来是 subprocess.run([...], capture_output=True) —— 它会**等 open 返回**，
            # 而 open 在 App 拉起的子进程环境里会等 Finder 响应，结果 HTTP 请求
            # 一直挂着（实测 curl 拿到 000 超时），界面表现就是「点了没反应」。
            # 改成 Popen 不等待 + start_new_session 脱离进程组，立刻返回。
            # ?dir=wm 时打开「去水印」专用文件夹（去水印页面用）。
            # 2026-11-12：各任务完成后由前端自动调这里，按「成品落在哪」选目录：
            #   outbox(默认) / wm / md / restore / bad；?path=<成品文件> 打开它所在目录
            #   （文件转 MD 选「输出到源文件旁」时用）。?dry=1 只算路径不弹 Finder，便于自检。
            try:
                _q = urllib.parse.parse_qs(u.query)
                _key = _q.get("dir", [""])[0]
                _p = _q.get("path", [""])[0]
                _dirs = {"wm": WM_OUTBOX, "watermark": WM_OUTBOX,
                         "md": md_out_dir(), "restore": RESTORE_DIR,
                         "bad": BAD_DIR}
                target = _dirs.get(_key, OUTBOX)
                if _p:
                    _ap = os.path.abspath(_p)
                    if os.path.isfile(_ap):
                        target = os.path.dirname(_ap)
                    elif os.path.isdir(_ap):
                        target = _ap
                os.makedirs(target, exist_ok=True)
                if _q.get("dry", [""])[0] == "1":
                    self._send(200, json.dumps({"ok": True, "path": target,
                                                "dry": True}, ensure_ascii=False))
                    return
                subprocess.Popen(["/usr/bin/open", target],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                self._send(200, json.dumps({"ok": True, "path": target},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(200, json.dumps(
                    {"ok": False, "path": target if 'target' in dir() else "",
                     "msg": "打不开文件夹：%s" % str(e)[:80]}, ensure_ascii=False))
            return
        if u.path == "/api/check":
            # 扫描件质量体检：只判断画质，不返回任何文字内容。
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            if not (p and os.path.exists(p)):
                self._send(404, json.dumps({"ok": False, "msg": "文件不存在"}, ensure_ascii=False))
                return
            try:
                sys.path.insert(0, SCRIPTS)
                import scan_enhance as SE
                probe = p
                if p.lower().endswith(".pdf"):
                    import pymupdf, tempfile
                    d = pymupdf.open(p)
                    probe = os.path.join(tempfile.mkdtemp(), "probe.png")
                    d[0].get_pixmap(dpi=200).save(probe)
                    d.close()
                r = SE.assess_quality(probe)
                self._send(200, json.dumps({"ok": True, "quality": r}, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": str(e)[:200]},
                                           ensure_ascii=False))
            return
        if u.path == "/api/openterms":
            # 词表文件夹固定放文稿，方便用户随时翻看/编辑。
            # 不要用 ~/Documents/立丰脱敏 —— 那是指向 App 的符号链接。
            desk = os.path.join(BASE_DIR, "词表")
            os.makedirs(desk, exist_ok=True)
            subprocess.run(["/usr/bin/open", desk], capture_output=True)
            self._send(200, json.dumps({"ok": True, "path": desk}, ensure_ascii=False))
            return

        if u.path == "/api/terms/template":
            # 2026-11-06：用户要「基础格式」，给他一份能直接填的模板。
            # 浏览器直接下载走这里；App 内（WKWebView 不认 attachment）走 POST 版本落盘。
            q = urllib.parse.parse_qs(u.query)
            fmt = (q.get("fmt", ["xlsx"])[0] or "xlsx").lower()
            try:
                from terms_import import build_template
                data, name, mime = build_template(fmt)
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "模板生成失败：%s" % str(e)[:160]},
                                           ensure_ascii=False))
                return
            self._send(200, data, mime, {
                "Content-Disposition": "attachment; filename*=UTF-8''%s"
                                       % urllib.parse.quote(name)})
            return
        if u.path == "/api/terms/list":
            # 本案词条：当前生效词表的全部条目
            items = []
            if os.path.exists(TERMS_FILE):
                try:
                    with open(TERMS_FILE, encoding="utf-8") as f:
                        for line in f:
                            t = line.strip()
                            if not t or t.startswith("#"):
                                continue
                            if "=" in t:
                                a, b = t.split("=", 1)
                                items.append({"orig": a.strip(), "repl": b.strip()})
                            else:
                                items.append({"orig": t, "repl": ""})
                except Exception:
                    pass
            self._send(200, json.dumps({"ok": True, "items": items,
                                        "path": TERMS_FILE}, ensure_ascii=False))
            return

        if u.path == "/api/task/info":
            # PDF/图片预览要用到的：文件名、页数、最终成品路径
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            base = os.path.join(PREVIEW_ROOT, task)
            outd = os.path.join(base, "output")
            # 2026-11-07：目录被清掉了先试着按账本 + 成品重建，
            # 别让「预览任务不存在」成为最终答案 —— 成品一直在成品目录里。
            if task and not os.path.isdir(outd):
                if revive_task_from_ledger(task):
                    outd = os.path.join(base, "output")
            if not task or not os.path.isdir(outd):
                # 重建也失败时才走到这里。话要说清楚「东西没坏、只是没在这儿」，
                # 不然用户以为 App 把他的文件弄丢了（2026-11-07 原话：「app 也不支持预览文件了」）。
                self._send(404, json.dumps({
                    "ok": False,
                    "msg": "这份预览找不回来了：预览任务目录被清理过，"
                           "成品目录和废纸篓里也没有对应文件。"
                           "成品目录里没有的话，把原文件重新拖进来再脱一次即可。",
                    "gone": True,
                }, ensure_ascii=False))
                return
            cand = [x for x in sorted(os.listdir(outd)) if not x.startswith(".")]
            name = cand[0] if cand else ""
            pages, kind = 0, "unknown"
            src = os.path.join(outd, name)
            ext = os.path.splitext(name)[1].lower()
            if ext == ".pdf":
                kind = "pdf"
                try:
                    import pymupdf
                    doc = pymupdf.open(src)
                    pages = len(doc)
                    doc.close()
                except Exception:
                    pages = 0
            elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"):
                kind, pages = "image", 1
            self._send(200, json.dumps({
                "ok": True, "name": name, "pages": pages, "kind": kind,
                "saved": os.path.join(OUTBOX, name) if name else "",
                "saved_exists": os.path.exists(os.path.join(OUTBOX, name)) if name else False,
            }, ensure_ascii=False))
            return

        if u.path == "/api/wm/page":
            # 去水印的前后对比：把任意一份 PDF 的某一页渲染成 PNG。
            # 前端拿「原文件」和「处理后的成品」各调一次，并排显示。
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            try:
                pg = int(q.get("page", ["0"])[0])
            except Exception:
                pg = 0
            if not (os.path.isfile(p) and p.lower().endswith(".pdf")):
                self._send(400, b"not a pdf", "text/plain; charset=utf-8")
                return
            try:
                import watermark as WM
                data, _n = WM.render_page(p, pg, dpi=90)
                self._send(200, data, "image/png")
            except Exception as e:
                self._send(500, ("渲染失败：%s" % str(e)[:100]).encode("utf-8"),
                           "text/plain; charset=utf-8")
            return

        if u.path == "/api/task/page":
            # PDF / 图片成品的逐页预览：把某一页渲染成 PNG（懒渲染 + 缓存）。
            # 为什么单独做：预览页靠 docx 的段落结构做高亮，PDF 是整页图像，
            # 建不出那套数据；但用户至少要能"看见"成品长什么样，而不是对着空白页发呆。
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            # 2026-11-05 修：前端 pdfview.html 传的是 page，后端原来只认 n，
            # 参数名对不上导致翻页永远取默认 1，用户看到的就是「每页都一样」。
            try:
                n = int(q.get("n", q.get("page", ["1"]))[0])
            except Exception:
                n = 1
            base = os.path.join(PREVIEW_ROOT, task)
            # 2026-11-07：目录被清过就先按账本重建，别让逐页预览直接 404 空白
            if task and not os.path.isdir(base):
                if revive_task_from_ledger(task):
                    base = os.path.join(PREVIEW_ROOT, task)
            if not task or not os.path.isdir(base):
                self._send(404, b"", "image/png")
                return
            # 定位成品文件名：优先 index.json 里登记的 output_name
            name = ""
            ip = os.path.join(base, "index.json")
            try:
                with open(ip, encoding="utf-8") as f:
                    data = json.load(f)
                want = int(q.get("file", ["1"])[0])
                for it in data.get("files", []):
                    if int(it.get("index") or 1) == want:
                        name = it.get("output_name") or ""
                        break
            except Exception:
                pass
            outd = os.path.join(base, "output")
            if not name and os.path.isdir(outd):
                cand = [x for x in sorted(os.listdir(outd)) if not x.startswith(".")]
                name = cand[0] if cand else ""
            src = os.path.join(outd, name)
            if not os.path.exists(src):
                self._send(404, b"", "image/png")
                return
            # docx 不走这条通道：它该由 preview.html 用文字+高亮渲染。
            # 落到下面 PIL 那句会报「cannot identify image file」，
            # 报错内容跟用户做的事毫无关系，看着像 App 坏了。
            _ext0 = os.path.splitext(src)[1].lower()
            if _ext0 not in (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
                self._send(400,
                           ("这份是 %s，不走逐页图片预览，请用文字预览打开"
                            % (_ext0.lstrip(".") or "未知格式")).encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            cache = os.path.join(base, "pages", "%d.png" % n)
            if not os.path.exists(cache):
                try:
                    os.makedirs(os.path.dirname(cache), exist_ok=True)
                    ext = os.path.splitext(src)[1].lower()
                    if ext == ".pdf":
                        import pymupdf
                        doc = pymupdf.open(src)
                        if n < 1 or n > len(doc):
                            doc.close()
                            self._send(404, b"", "image/png")
                            return
                        doc[n - 1].get_pixmap(dpi=110).save(cache)
                        doc.close()
                    else:
                        from PIL import Image
                        with Image.open(src) as im:
                            im = im.convert("RGB")
                            m = max(im.size)
                            if m > 2000:
                                k = 2000.0 / m
                                im = im.resize((int(im.width * k), int(im.height * k)))
                            im.save(cache, "PNG")
                except Exception as e:
                    self._send(500, ("渲染失败：%s" % str(e)[:80]).encode("utf-8"), "text/plain")
                    return
            with open(cache, "rb") as f:
                self._send(200, f.read(), "image/png")
            return

        if u.path == "/api/preview":
            # 取预览数据（脱敏后的内容 + 替换点标记，不含原值）
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            fno = q.get("file", ["1"])[0] or "1"
            base = os.path.join(PREVIEW_ROOT, task)
            # 2026-11-07：目录真没了就先按账本 + 成品重建（根因见 revive_task_from_ledger）。
            # 不重建的话，用户从历史里点「查看」只会看到「任务不存在或已过期」，
            # 而那份成品其实好端端躺在成品目录里。
            if task and not os.path.isdir(base):
                revive_task_from_ledger(task)
            # ⚡ 2026-11-18 顺序修正：重建必须在「找不到就退回 file 1」**之前**跑。
            # 原来先 `fp=files/1/...; fno="1"` 再 refresh(base, fno)，
            # 结果是请求 file=2、file=3 也只会重建第 1 份，
            # 第 2、3 份的 preview.json 永远不生成 —— 多文件任务只有第一份能预览。
            if task and os.path.isdir(os.path.join(base, "output")):
                refresh_preview_if_stale(base, str(fno))
            fp = os.path.join(base, "files", str(fno), "preview.json")
            if not os.path.exists(fp):
                # 序号越界时退回第 1 个文件，而不是直接 404：
                # 从历史点进来时 file 参数可能来自旧的任务编号，
                # 报「任务不存在」会让人以为整份预览都没了。
                fp = os.path.join(base, "files", "1", "preview.json")
                fno = "1"
            if not os.path.exists(fp):
                fp = os.path.join(base, "preview.json")   # 兼容改造前的旧任务
            if not (task and os.path.exists(fp)):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在或已过期"},
                                           ensure_ascii=False))
                return
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "预览数据损坏：%s" % str(e)[:100]},
                                           ensure_ascii=False))
                return
            # 带上文件清单，预览页据此做切换器
            ip = os.path.join(base, "index.json")
            if os.path.exists(ip):
                try:
                    with open(ip, encoding="utf-8") as f:
                        data["files"] = json.load(f).get("files", [])
                except Exception:
                    pass
            data["file_no"] = str(fno)
            # ⚡ 2026-11-07：重建回来的任务，账本里若本来就没记 count（早批次
            # 的任务确实没有这个字段），界面会显示「已脱敏 0 处」，用户以为
            # 白跑了一趟。这里按正文里占位符 [xxx] 的出现次数补一个，
            # 宁可少报也不能报 0。
            if not data.get("count"):
                _c = 0
                for _b in (data.get("blocks") or []):
                    _t = "".join((_r.get("text") or "")
                                 for _r in (_b.get("runs") or []))
                    if not _t:
                        _t = _b.get("text") or ""
                    _c += len(re.findall(r"\[[^\[\]]{1,40}\]", _t))
                if _c:
                    data["count"] = _c
            # 手动标记：浏览阶段只记录，导出时才应用（用户 2026-10-30 决定）
            mp = os.path.join(base, "files", str(fno), "marks.json")
            if os.path.exists(mp):
                try:
                    with open(mp, encoding="utf-8") as f:
                        data["marks"] = json.load(f).get("marks", [])
                except Exception:
                    pass
            self._send(200, json.dumps(data, ensure_ascii=False))
            return

        if u.path == "/api/preview/orig":
            # 按需取单处原值：整篇原值不下发页面
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            rid = q.get("id", [""])[0]
            fno = q.get("file", ["1"])[0] or "1"
            # 2026-11-07：点「查看原文」时报「任务不存在」也是同一个病根，
            # 先按账本 + 成品（含废纸篓）重建任务目录，再取 origs.json。
            if task and not os.path.isdir(os.path.join(PREVIEW_ROOT, task)):
                revive_task_from_ledger(task)
            fp = os.path.join(PREVIEW_ROOT, task, "files", str(fno), "origs.json")
            if not os.path.exists(fp):
                fp = os.path.join(PREVIEW_ROOT, task, "origs.json")   # 兼容旧任务
            if not (task and os.path.exists(fp)):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在"}, ensure_ascii=False))
                return
            try:
                with open(fp, encoding="utf-8") as f:
                    d = json.load(f)
                orig = d.get(str(rid), "")
                if not orig:
                    # 兜底：按占位符文本反查映射表。
                    # 表格单元格里被 Word 拆成多个 run 的占位符，预览侧定位不到 id，
                    # 点上去就报"原文未能定位"（2026-11-02 用户踩到）。
                    ph = q.get("ph", [""])[0]
                    if ph:
                        try:
                            import csv as _csv
                            base = os.path.join(PREVIEW_ROOT, task)
                            name = ""
                            with open(os.path.join(base, "index.json"), encoding="utf-8") as f2:
                                data2 = json.load(f2)
                            for it in data2.get("files", []):
                                if str(it.get("index")) == str(fno):
                                    name = it.get("output_name") or ""
                            stem = os.path.splitext(name)[0]
                            src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
                            for cand in ("%s_映射表.csv" % src_stem, "%s_映射表.csv" % stem):
                                p2 = os.path.join(KEYS, cand)
                                if not os.path.exists(p2):
                                    continue
                                with open(p2, encoding="utf-8-sig") as f3:
                                    for row in _csv.reader(f3):
                                        if len(row) >= 2 and row[1].strip() == ph:
                                            orig = row[0].strip()
                                            break
                                if orig:
                                    break
                        except Exception:
                            pass
                self._send(200, json.dumps({"ok": True, "id": rid, "orig": orig},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": str(e)[:160]}, ensure_ascii=False))
            return

        if u.path in ("/go", "/now"):
            # 2026-11-05 用户反复报「预览不可用」：加一个服务端固定入口。
            # 不带 task 参数、不依赖页面 JS，永远 302 到当前最新 preview 任务；
            # 旧标签、旧书签、旧链接一律落这里，不可能再「任务不存在」。
            try:
                import history_store as _HS
                _items = _HS.list_entries(50)
            except Exception:
                _items = []
            _cand = next((x for x in _items if x.get("status") == "preview"), None)
            if not _cand and _items:
                _cand = _items[0]
            if not _cand:
                self._send(200, "当前没有待确认的预览任务，请先投递文件。",
                           "text/plain; charset=utf-8")
                return
            _ext = os.path.splitext(_cand.get("output_name") or "")[1].lower()
            _page = ("pdfview.html" if _ext in (".pdf", ".png", ".jpg", ".jpeg",
                                                ".tif", ".tiff", ".bmp", ".webp")
                     else "preview.html")
            _loc = "/%s?task=%s&file=%s" % (
                _page, urllib.parse.quote(_cand.get("task_id", "") or ""),
                _cand.get("index") or 1)
            self.send_response(302)
            self.send_header("Location", _loc)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if u.path == "/api/task/file":
            # 2026-11-05：原生 PDF 通道。逐页转图对 14 页扫描件太慢（单页 1.5MB），
            # 浏览器等到超时就显示「无法显示」。这里直接吐 PDF 字节流，
            # 由 Safari/WKWebView 自带的 PDF 阅读器渲染，翻页缩放都不依赖我们的脚本。
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            base = os.path.join(PREVIEW_ROOT, task, "output")
            # 2026-11-07：目录被清过就先按账本重建，否则浏览器只会拿到 404 白屏
            if task and not os.path.isdir(base):
                if revive_task_from_ledger(task):
                    base = os.path.join(PREVIEW_ROOT, task, "output")
            if not task or not os.path.isdir(base):
                self._send(404, b"", "text/plain; charset=utf-8")
                return
            _cand = [x for x in sorted(os.listdir(base)) if not x.startswith(".")]
            if not _cand:
                self._send(404, b"", "text/plain; charset=utf-8")
                return
            _p = os.path.join(base, _cand[0])
            try:
                with open(_p, "rb") as _f:
                    _data = _f.read()
                _ext = os.path.splitext(_p)[1].lower()
                _ct = ("application/pdf" if _ext == ".pdf"
                       else ("image/png" if _ext == ".png" else "application/octet-stream"))
                self._send(200, _data, _ct)
            except Exception as _e:
                self._send(500, ("读取失败：%s" % str(_e)[:120]).encode("utf-8"),
                           "text/plain; charset=utf-8")
            return

        if u.path == "/view":
            # 2026-11-05：原生 PDF + 导出按钮二合一。
            # 逐页转图对十几页扫描件太重（单页 1.5MB），页面等超时就「无法显示」；
            # 这里用 <embed> 交给浏览器原生渲染，翻页缩放不依赖我们的脚本，
            # 顶部保留一个导出按钮，走同一个 /api/export。
            q = urllib.parse.parse_qs(u.query)
            task = os.path.basename(q.get("task", [""])[0])
            base = os.path.join(PREVIEW_ROOT, task, "output")
            # 2026-11-07：目录被清过就先按账本重建（见 revive_task_from_ledger）
            if task and not os.path.isdir(base):
                if revive_task_from_ledger(task):
                    base = os.path.join(PREVIEW_ROOT, task, "output")
            _cand = []
            if task and os.path.isdir(base):
                _cand = [x for x in sorted(os.listdir(base)) if not x.startswith(".")]
            if not _cand:
                self._send(200, "<html><meta charset='utf-8'><body style='font-family:-apple-system;padding:40px'>"
                                "当前没有可看的预览。<a href='/go'>回当前任务</a></body></html>",
                           "text/html; charset=utf-8")
                return
            _name = _cand[0]
            _esc = _name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # ⚡ 2026-11-07 补：docx 不能走逐页图通道。
            # 逐页图是给 PDF/扫描件用的（pymupdf 渲页）；docx 没有「页」，
            # 送进去只会得到一张破图（实测截图：<img> 显示为破损图标，
            # 页面高 152px、只剩「1 / 1」）。docx 的正确入口是 preview.html
            # —— 那里有段落高亮、分类侧栏、逐处核对原值，功能比看图强得多。
            if os.path.splitext(_name)[1].lower() in (".docx", ".docm", ".doc"):
                _to = "/preview.html?task=" + urllib.parse.quote(task)
                self._send(302, b"", "text/plain; charset=utf-8",
                           extra={"Location": _to})
                return
            # ⚡ 2026-11-07 修「App 里不支持预览文件」，实测结论：
            # 原来整页只有一个 <embed type='application/pdf'>，以为交给浏览器
            # 内置阅读器最省事。实测（Edge headless + 本机 App）拿到的是
            # **一整块深灰空白**：HTTP 200、元素有宽有高、就是零绘制，
            # 而且不抛任何错误 —— 探针根本发现不了，用户只看到「打不开」。
            #
            # 所以不再赌内置阅读器，主通道改成逐页图：
            #   /api/task/page → 本机 pymupdf 渲成 PNG → <img> 显示。
            # 这条路跟 WebView 有没有 PDF 阅读器完全无关，已实测能出内容。
            # 代价是选不了文字，但「看得见」比「能选中」重要得多。
            _imgs = ("<div id='pgbox' style='padding:10px 14px 24px;text-align:center'>"
                     "<div id='pgnav' style='margin:0 0 10px;font-size:13px;color:#555;"
                     "display:flex;align-items:center;justify-content:center;gap:6px'>"
                     "<button id='pp' style='padding:4px 12px'>上一页</button>"
                     "<span id='pinfo' style='margin:0 10px'>1 / 1</span>"
                     "<button id='pnx' style='padding:4px 12px'>下一页</button>"
                     "<span id='pwhy' style='margin-left:12px;color:#999'></span></div>"
                     "<img id='pg' style='max-width:100%;box-shadow:0 4px 18px rgba(0,0,0,.16)'>"
                     "</div>")
            _html = (
                "<!doctype html><html><head><meta charset='utf-8'><title>预览 - " + _esc + "</title>"
                "<style>body{margin:0;font-family:-apple-system,'PingFang SC',sans-serif;"
                "background:#f2f2f4}"
                "#bar{height:54px;display:flex;align-items:center;gap:14px;padding:0 16px;"
                "border-bottom:1px solid #e2e2e2;background:#fafafa}"
                "#nm{font-size:13px;font-weight:600;max-width:46vw;overflow:hidden;"
                "text-overflow:ellipsis;white-space:nowrap}"
                "#ex{padding:7px 16px;border-radius:8px;border:0;background:#2f6fed;color:#fff;"
                "font-size:13px;cursor:pointer}#ex:disabled{background:#9db8f0}"
                "#st{font-size:12px;color:#777}</style></head><body>"
                "<div id='bar'><span id='nm'>" + _esc + "</span>"
                "<button id='ex'>导出到成品文件夹</button>"
                "<button id='pt' style='padding:7px 16px;border-radius:8px;border:1px solid #cfcfcf;"
                "background:#fff;font-size:13px;cursor:pointer'>手动涂黑</button>"
                "<span id='st'>左为脱敏后成品，可翻页缩放</span></div>"
                + _imgs +
                "<script>"
                "var T=" + json.dumps(task) + ";"
                "var b=document.getElementById('ex'),s=document.getElementById('st');"
                "var p=document.getElementById('pt');"
                "var pg=document.getElementById('pg'),pi=document.getElementById('pinfo');"
                "var cur=1,all=1;"
                "function show(){pg.src='/api/task/page?task='+encodeURIComponent(T)"
                "+'&n='+cur+'&t='+Date.now();pi.textContent=cur+' / '+all;}"
                "document.getElementById('pgbox').style.display='';"
                "fetch('/api/task/info?task='+encodeURIComponent(T))"
                ".then(function(r){return r.json()})"
                ".then(function(d){all=(d&&d.pages)||1;show();})"
                ".catch(function(){all=1;show();});"
                "document.getElementById('pp').onclick=function(){if(cur>1){cur--;show();}};"
                "document.getElementById('pnx').onclick=function(){if(cur<all){cur++;show();}};"
                "document.addEventListener('keydown',function(e){"
                "if(e.key==='ArrowLeft'&&cur>1){cur--;show();}"
                "if(e.key==='ArrowRight'&&cur<all){cur++;show();}});"
                "if(p)p.onclick=async function(){p.disabled=true;p.textContent='打开中…';"
                "try{var r=await fetch('/api/paint/from-task',{method:'POST',"
                "headers:{'Content-Type':'application/json'},"
                "body:JSON.stringify({task:" + json.dumps(task) + ",file:'1'})});"
                "var d=await r.json();if(!d.ok)throw new Error(d.msg||'打不开');"
                "location.href='paint.html?task='+encodeURIComponent(d.task_id);}"
                "catch(e){alert('打不开涂黑页：'+e.message);p.disabled=false;"
                "p.textContent='手动涂黑';}};"
                "b.onclick=async function(){b.disabled=true;b.textContent='正在导出…';"
                "try{var r=await fetch('/api/export',{method:'POST',"
                "headers:{'Content-Type':'application/json'},"
                "body:JSON.stringify({task:" + json.dumps(task) + "})});"
                "var d=await r.json();if(!d.ok)throw new Error(d.msg||'导出失败');"
                "b.textContent='已导出 '+d.files.length+' 个';"
                "s.textContent='已写入成品文件夹，可关闭本页，不必再操作';}"
                "catch(e){alert('导出失败：'+e.message);b.disabled=false;"
                "b.textContent='导出到成品文件夹';}};"
                "</script></body></html>")
            self._send(200, _html, "text/html; charset=utf-8")
            return

        if u.path == "/api/history":
            # 历史读账本，不再扫预览目录 —— 预览目录会被清理，
            # 而账本要活到「三年后还想复原一份旧件」的时候。
            items = []
            try:
                import history_store as HS
                items = HS.list_entries(50)
            except Exception:
                items = []
            # ⚡ 2026-11-07「删不干净」的第二层：**活账本里的条目也会失效**。
            # 用户勾了「预览任务」清掉预览、却没勾「导出账本」时，账本条目还在，
            # 但 preview_path 已经空指针。此时前端照样渲染出这一条，
            # 点进去报「任务不存在或已过期」——用户看到的就是「清了还挂着」。
            # 所以活账本也要过同一道存活判据，不能只在回落分支里过滤。
            if items:
                items = [it for it in items
                         if _alive_path(it.get("preview_path"))
                         or _alive_path(it.get("output_path"))]
            # ⚡ 2026-11-07：账本被「清除全部」搬走后，列表会整片空白 ——
            # 用户看到的是「历史里什么都没了」，接着点任何旧链接都是
            # 「预览不可用」。所以账本为空时，把废纸篓里历次清除搬走的那几本
            # 账本合并读回来（只读，不写回用户目录）。
            if not items:
                try:
                    import history_store as _HS2
                    items = _ledger_entries_for_history(_HS2)
                except Exception:
                    items = []
            if not items:
                # 兼容改造前的旧任务（那时还没有账本）
                try:
                    for n in os.listdir(PREVIEW_ROOT):
                        mp = os.path.join(PREVIEW_ROOT, n, "meta.json")
                        if not os.path.exists(mp):
                            continue
                        try:
                            with open(mp, encoding="utf-8") as f:
                                items.append(json.load(f))
                        except Exception:
                            continue
                except Exception:
                    pass
                items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            # 2026-11-05 用户死命令：合格不合格放同一个路径，质检结论只在界面标红。
            # 账本条目本身没有质检字段，这里按成品名把质检台账挂上去。
            try:
                import reject_store as _RS
                _rej = {}
                for _r in _RS.load_records(OUTBOX):
                    if (_r.get("status") or "pending") in ("accepted", "retried"):
                        continue
                    _nm = _r.get("output") or ""
                    if _nm:
                        _rej[_nm] = _r
                for _it in items:
                    _r = _rej.get(_it.get("output_name") or "")
                    if _r:
                        _it["quality"] = "rejected"
                        _it["quality_why"] = _r.get("why") or ""
                        _it["quality_issues"] = _r.get("issues") or []
            except Exception:
                pass
            self._send(200, json.dumps({"ok": True, "items": items[:50],
                                        "total": len(items)}, ensure_ascii=False))
            return

        if u.path == "/api/rejected":
            # 未通过质检台账：拦截之后有下文——为什么拦、原件还在不在、该怎么救
            items = rejected_items()
            for it in items:
                # 给前端一个能直接开工的绝对路径：手动处理时要从原件重跑
                rel = it.get("orig_rel") or ""
                it["orig_path"] = os.path.join(BAD_DIR, rel) if rel else ""
            pend = [x for x in items if x.get("status") == "pending"]
            self._send(200, json.dumps({"ok": True, "items": items,
                                        "pending": len(pend),
                                        "running": bool(_state["running"]),
                                        "dir": BAD_DIR}, ensure_ascii=False))
            return

        if u.path == "/api/paint/meta":
            q = urllib.parse.parse_qs(u.query)
            tdir = _paint_dir(q.get("task", [""])[0])
            mp = os.path.join(tdir, "meta.json") if tdir else ""
            if not mp or not os.path.exists(mp):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在"}, ensure_ascii=False))
                return
            with open(mp, encoding="utf-8") as f:
                meta = json.load(f)
            boxes = {}
            bp = os.path.join(tdir, "boxes.json")
            if os.path.exists(bp):
                try:
                    with open(bp, encoding="utf-8") as f:
                        boxes = json.load(f)
                except Exception:
                    boxes = {}
            # 删掉的涂黑框：留在 deleted.json 里等用户反悔，
            # 刷新页面也还在（2026-11-03 用户要求「涂黑删除要能撤销」）
            deleted = []
            dp = os.path.join(tdir, "deleted.json")
            if os.path.exists(dp):
                try:
                    with open(dp, encoding="utf-8") as f:
                        deleted = json.load(f) or []
                except Exception:
                    deleted = []
            self._send(200, json.dumps({"ok": True, "meta": meta, "boxes": boxes,
                                        "deleted": deleted}, ensure_ascii=False))
            return

        if u.path == "/api/paint/page":
            q = urllib.parse.parse_qs(u.query)
            task = q.get("task", [""])[0]
            try:
                n = int(q.get("n", ["1"])[0])
            except Exception:
                n = 1
            p = paint_page_png(task, n)
            if not p or not os.path.exists(p):
                self._send(404, b"", "image/png")
                return
            with open(p, "rb") as f:
                self._send(200, f.read(), "image/png")
            return

        if u.path == "/api/clear-all/preview":
            # 先算清楚「要删什么、多大、删了会怎样」，用户点确认前必须看到这张清单
            groups = []
            total_n = 0
            total_s = 0
            # 默认会清掉多少：与前端拿到的 default 字段同源，避免「说的和做的不一致」
            dflt_n = 0
            dflt_s = 0
            for t in clear_targets():
                n, s = _dir_stat(t["path"], skip=tuple(t.get("exclude") or ()),
                                 include_hidden=bool(t.get("include_hidden")))
                total_n += n
                total_s += s
                if t.get("default", True):
                    dflt_n += n
                    dflt_s += s
                groups.append({"key": t["key"], "label": t["label"], "note": t["note"],
                               "count": n, "bytes": s, "size": _human(s),
                               # default 由服务端给：前端不许自己判断哪些「该默认勾上」。
                               # 以前前端写的是「除涂黑外全勾」，于是预览任务和账本
                               # 被默认带走 —— 那正是「预览任务不存在」的源头。
                               "default": bool(t.get("default", True)),
                               # 目录和单文件都要能显示「有没有东西可清」。
                               # 原判据 `os.path.isdir(...) and n > 0` 会把单文件组
                               # 永远显示成「不存在」，用户点了却发现搬走了文件。
                               "exists": (os.path.isdir(t["path"]) or os.path.isfile(t["path"]))
                                         and n > 0})
            self._send(200, json.dumps({
                "ok": True, "groups": groups,
                "total_count": total_n, "total_size": _human(total_s),
                "default_count": dflt_n, "default_size": _human(dflt_s),
                "running": bool(_state["running"]),
                "keep": ["脱敏规则设置", "敏感词表", "记忆库（学到的姓名/机构）"],
            }, ensure_ascii=False))
            return

        if u.path == "/api/agent/nav":
            self._send(200, json.dumps({"ok": True, "url": _NAV.get("url", ""),
                                        "ts": _NAV.get("ts", 0)}, ensure_ascii=False))
            return

        if u.path == "/api/agent/status":
            conf = agent_config()
            recent = agent_recent(20)
            blocked = sum(1 for r in recent if not r.get("ok"))
            self._send(200, json.dumps({
                "ok": True, "enabled": bool(conf.get("enabled")),
                "token": conf.get("token", ""),
                "base": "http://127.0.0.1:8791",
                "recent": recent, "blocked": blocked,
            }, ensure_ascii=False))
            return

        if u.path == "/api/ai/status":
            conf = ai_config()
            up = False
            models = []
            try:
                op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with op.open(conf["host"].rstrip("/") + "/api/tags", timeout=2) as r:
                    data = json.loads(r.read().decode("utf-8") or "{}")
                models = [m.get("name") for m in (data.get("models") or []) if m.get("name")]
                up = True
            except Exception:
                up = False
            self._send(200, json.dumps({"ok": True, "config": conf, "up": up,
                                        "models": models}, ensure_ascii=False))
            return

        if u.path == "/api/rules":
            # 规则配置快照：分组统计 + 全部条目 + 启用状态
            try:
                import rules_store as RS
                self._send(200, json.dumps(RS.list_for_ui(), ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": str(e)[:200]},
                                           ensure_ascii=False))
            return

        if u.path == "/api/terms":
            q = urllib.parse.parse_qs(u.query)
            p = q.get("path", [""])[0]
            target = p or TERMS_FILE
            if os.path.exists(target):
                subprocess.run(["/usr/bin/open", target], capture_output=True)
                self._send(200, json.dumps({"ok": True}))
            else:
                self._send(404, json.dumps({"ok": False, "msg": "尚无词表"}))
            return
        self._send(404, json.dumps({"ok": False}))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
        except Exception:
            self._send(400, json.dumps({"ok": False}))
            return

        if u.path == "/api/upload":
            # 网页拖入的文件：先落「上传暂存」，不要直接进待处理区（那里会被流水线清理）
            name = urllib.parse.unquote(self.headers.get("X-Filename", "未命名文件"))
            name = os.path.basename(name)
            os.makedirs(UPLOADS, exist_ok=True)
            dst = os.path.join(UPLOADS, name)
            with open(dst, "wb") as f:
                f.write(raw)
            self._send(200, json.dumps({"ok": True, "path": dst}, ensure_ascii=False))
            return

        # ============ PDF 去水印（2026-11-11 用户要求）============
        # 只处理矢量文字水印：删 content stream 里的文字块，
        # 扫描图、OCR 层、注释一根毫毛都不碰。烧进扫描图的水印删不掉。
        if u.path == "/api/wm/scan":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            p = str(meta.get("path") or "")
            if not (os.path.isfile(p) and p.lower().endswith(".pdf")):
                self._send(400, json.dumps(
                    {"ok": False, "msg": "请选择一个 PDF 文件（当前只支持 PDF）"},
                    ensure_ascii=False))
                return
            try:
                import watermark as WM
                cands, n = WM.scan_pdf(p)
                self._send(200, json.dumps({
                    "ok": True, "pages": n, "candidates": cands,
                    "name": os.path.basename(p), "path": p,
                    # 一句人话，前端直接显示：没找到时别让用户以为卡住了
                    "msg": ("发现 %d 处疑似水印" % len(cands)) if cands
                           else "没找到可去除的文字水印（如果水印是扫描进图片里的，去不掉）",
                }, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps(
                    {"ok": False, "msg": "扫描失败：%s" % str(e)[:120]},
                    ensure_ascii=False))
            return

        # ============ 逆向还原：把 AI 提纲里的占位符换回真名 ============
        if u.path == "/api/derestore/text":
            try:
                _m = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                _m = {}
            text = str(_m.get("text") or "")
            # 支持多份映射表：maps 是数组，旧前端传的单个 map 也兼容
            names = _m.get("maps")
            if not isinstance(names, list):
                names = [_m.get("map")] if _m.get("map") else []
            if not text.strip():
                self._json({"ok": False, "msg": "没有内容，先把 AI 写的提纲粘进来"}, 400)
                return
            rows, conflicts, terms_used, paths, err = _derestore_rows(names)
            if err:
                self._json({"ok": False, "msg": err}, 400)
                return
            out, hits = _derestore_text(text, rows)
            # 顺手把还原结果里「字中间」的排版空格压掉（默认开，可关）
            squeeze = _m.get("squeeze", True)
            sq = 0
            if squeeze:
                out, sq = _squeeze_cjk_spaces(out)
            total = sum(h[2] for h in hits)
            # 明细按替换次数排序，前端展示「哪些词换了多少处」
            hits.sort(key=lambda x: -x[2])
            self._json({
                "ok": True, "text": out,
                "maps": [os.path.basename(p) for p in paths],
                "merged": len(rows),
                "terms_used": terms_used,
                "squeezed": sq,
                "conflicts": conflicts[:20],
                "conflict_total": len(conflicts),
                "total": total, "kinds": len(hits),
                "detail": [{"placeholder": h[0], "original": h[1], "count": h[2]}
                           for h in hits[:40]],
                "msg": ("已还原 %d 处（%d 个词）" % (total, len(hits))) if total
                       else "这段文字里没有找到映射表里的占位符",
            })
            return

        if u.path == "/api/derestore/file":
            # 在原文件副本上只换字、保留版式，不做「抽文字再新建」
            try:
                _m = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                _m = {}
            src = str(_m.get("path") or "")
            names = _m.get("maps")
            if not isinstance(names, list):
                names = [_m.get("map")] if _m.get("map") else []
            rows, conflicts, terms_used, _paths, err = _derestore_rows(names)
            if err:
                self._json({"ok": False, "msg": err}, 400)
                return
            out, total, err2 = restore_file_inplace(src, rows)
            if err2:
                self._json({"ok": False, "msg": err2}, 400)
                return
            self._json({
                "ok": True, "path": out, "name": os.path.basename(out),
                "total": total, "merged": len(rows), "terms_used": terms_used,
                "conflicts": conflicts[:20], "conflict_total": len(conflicts),
                "msg": ("已在原文件副本上替换 %d 处，格式保留" % total) if total
                       else "文件里没有找到占位符，已输出一份原样副本",
            })
            return

        if u.path == "/api/derestore/read":
            # 从文件读入 AI 提纲（docx / txt / md / pdf）
            try:
                _m = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                _m = {}
            p = str(_m.get("path") or "")
            if not os.path.isfile(p):
                self._json({"ok": False, "msg": "文件不存在"}, 404)
                return
            ext = os.path.splitext(p)[1].lower()
            text = ""
            try:
                if ext == ".docx":
                    from docx import Document
                    _d = Document(p)
                    parts = [x.text for x in _d.paragraphs]
                    for _t in _d.tables:
                        for _row in _t.rows:
                            for _c in _row.cells:
                                parts.append(_c.text)
                    text = "\n".join(parts)
                elif ext in (".txt", ".md", ".markdown"):
                    with open(p, encoding="utf-8", errors="ignore") as _f:
                        text = _f.read()
                elif ext == ".pdf":
                    import pymupdf as _pm
                    _d = _pm.open(p)
                    text = "\n".join(pg.get_text("text") for pg in _d)
                    _d.close()
                else:
                    self._json({"ok": False,
                                "msg": "只支持 docx / txt / md / pdf"}, 400)
                    return
            except Exception as e:
                self._json({"ok": False, "msg": "读取失败：%s" % str(e)[:100]}, 500)
                return
            self._json({"ok": True, "text": text, "name": os.path.basename(p)})
            return

        if u.path == "/api/derestore/save":
            # 还原稿存成 Word，落在「还原」目录，和脱敏成品分开
            try:
                _m = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                _m = {}
            text = str(_m.get("text") or "")
            if not text.strip():
                self._json({"ok": False, "msg": "没有内容可存"}, 400)
                return
            name = os.path.basename(str(_m.get("name") or "").strip()) or "还原稿"
            if not name.lower().endswith(".docx"):
                name += ".docx"
            try:
                os.makedirs(RESTORE_DIR, exist_ok=True)
                out = os.path.join(RESTORE_DIR, name)
                k = 2
                while os.path.exists(out):
                    out = os.path.join(RESTORE_DIR,
                                       "%s-%d.docx" % (os.path.splitext(name)[0], k))
                    k += 1
                from docx import Document
                _d = Document()
                for line in text.split("\n"):
                    _d.add_paragraph(line)
                _d.save(out)
                self._json({"ok": True, "path": out, "name": os.path.basename(out)})
            except Exception as e:
                self._json({"ok": False, "msg": "保存失败：%s" % str(e)[:100]}, 500)
            return

        if u.path == "/api/wm/apply":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            p = str(meta.get("path") or "")
            sizes = meta.get("sizes") or []
            if not (os.path.isfile(p) and p.lower().endswith(".pdf")):
                self._send(400, json.dumps({"ok": False, "msg": "源文件不存在"},
                                           ensure_ascii=False))
                return
            if not sizes:
                self._send(400, json.dumps({"ok": False, "msg": "没有勾选要删除的水印"},
                                           ensure_ascii=False))
                return
            try:
                import watermark as WM
                # 去水印成品单独放「去水印」文件夹，不混进脱敏成品
                os.makedirs(WM_OUTBOX, exist_ok=True)
                base = os.path.splitext(os.path.basename(p))[0]
                out = os.path.join(WM_OUTBOX, base + "_无水印.pdf")
                k = 2
                while os.path.exists(out):
                    out = os.path.join(WM_OUTBOX, "%s_无水印-%d.pdf" % (base, k))
                    k += 1
                cut, pages = WM.remove_pdf(p, out, sizes)
                self._send(200, json.dumps({
                    "ok": True, "out": out, "name": os.path.basename(out),
                    "cut": cut, "pages": pages,
                    "msg": "已删除 %d 处水印，覆盖 %d 页" % (cut, pages),
                }, ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps(
                    {"ok": False, "msg": "处理失败：%s" % str(e)[:120]},
                    ensure_ascii=False))
            return

        if u.path == "/api/watermark/undo":
            # 撤销自动去水印：拿原件备份重跑一遍脱敏，这次跳过水印步骤。
            # 用户原话：「用户要是发现水印去错了，还能自己还原一下」。
            # 为什么要重跑而不是把水印贴回去：脱敏已经改过内容流，
            # 贴回去的坐标和字体未必对得上，重跑一次才是干净的。
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            name = os.path.basename(str(meta.get("name") or ""))
            if not name:
                self._json({"ok": False, "msg": "没指定文件"}, 400)
                return
            bak = os.path.join(APP_SUPPORT, "水印原件", name)
            if not os.path.exists(bak):
                self._json({"ok": False,
                            "msg": "找不到原件备份（可能出现于清理过「历史」之后），"
                                   "只能重新投一次这个文件"}, 404)
                return
            if _state["running"]:
                self._json({"ok": False, "msg": "正在处理中，等这批跑完再撤销"}, 409)
                return
            try:
                os.makedirs(UPLOADS, exist_ok=True)
                src = os.path.join(UPLOADS, name)
                shutil.copy2(bak, src)
                tid = time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)
                tdir = os.path.join(PREVIEW_ROOT, tid)
                os.makedirs(os.path.join(tdir, "output"), exist_ok=True)
                _has_t = os.path.exists(TERMS_FILE) and os.path.getsize(TERMS_FILE) > 0
                threading.Thread(
                    target=run_job,
                    args=([src], not _has_t, os.path.join(tdir, "output"), tid, True),
                    daemon=True).start()
                self._json({"ok": True, "task_id": tid,
                            "msg": "已按原件重新脱敏（保留水印），稍等生成新预览"})
            except Exception as e:
                self._json({"ok": False, "msg": "撤销失败：%s" % str(e)[:100]}, 500)
            return

        if u.path == "/api/process":
            meta = json.loads(raw.decode("utf-8")) if raw else {}
            paths = meta.get("paths", [])
            paths = [p for p in paths if os.path.exists(p) and
                     os.path.splitext(p)[1].lower() in SUPPORTED]
            if not paths:
                # 别只说「没有可用文件」——用户拖进来的东西为什么被拒，得说清楚
                _raw = meta.get("paths") or [] if isinstance(meta, dict) else []
                _bad = sorted({(os.path.splitext(os.path.basename(x))[1] or x) for x in _raw})
                _msg = ("这些格式不支持：%s。支持 doc/docx、PDF、图片、txt/md、xlsx"
                        % "、".join(_bad[:5])) if _bad else "没有可用文件"
                self._send(400, json.dumps({"ok": False, "msg": _msg}, ensure_ascii=False))
                return
            if _state["running"]:
                self._send(409, json.dumps({"ok": False, "msg": "正在处理中"}, ensure_ascii=False))
                return
            # 2026-11-06：前端从来不传 auto_terms，所以这里原本恒为 True ——
            # 用户已经把词表导好了，还让他走「自动识敏」重认一遍，
            # 结果是词表被覆盖/删掉、白等几十秒。有词表就默认关掉。
            _has_t = os.path.exists(TERMS_FILE) and os.path.getsize(TERMS_FILE) > 0
            _dflt = (not _has_t)
            at = meta.get("auto_terms", _dflt) if isinstance(meta, dict) else _dflt
            threading.Thread(target=run_job, args=(paths, bool(at)), daemon=True).start()
            self._send(200, json.dumps({"ok": True, "count": len(paths)}, ensure_ascii=False))
            return

        if u.path == "/api/pick":
            # 用系统对话框选文件（比网页上传更适合大文件）。
            # ⚡ 2026-11-11：提示语与「是否多选」改成可传参 —— 去水印页面复用这个接口，
            #    总不能让它也弹「选择要脱敏的文件」。
            #    另外记一笔教训：网页里 `<input type="file">` 的 click() 在 WKWebView 里
            #    **没有任何反应**（要 WKUIDelegate.runOpenPanelWith 接管，本 App 没实现），
            #    所以新页面一律走这个接口，别再自己造 input。
            try:
                _m = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                _m = {}
            _prompt = str(_m.get("prompt") or "选择要脱敏的文件（可多选）").replace('"', "'")
            _multi = " with multiple selections allowed" if _m.get("multiple", True) else ""
            script = '''
set out to ""
try
	set fs to choose file with prompt "%s"%s
	-- ⚡ 单选时 choose file 返回的是单个 alias，不是 list，
	-- 直接 repeat 会报 -1708「不理解 count 信息」，被 try 吞掉后返回空，
	-- 前端就以为用户点了取消 —— 表现正是「选完文件没反应」。
	if class of fs is not list then set fs to {fs}
	repeat with f in fs
		set out to out & POSIX path of f & linefeed
	end repeat
end try
return out
''' % (_prompt, _multi)
            try:
                r = subprocess.run(["/usr/bin/osascript", "-e", script],
                                   capture_output=True, text=True, timeout=300)
                paths = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
            except Exception:
                paths = []
            self._send(200, json.dumps({"ok": True, "paths": paths}, ensure_ascii=False))
            return

        if u.path == "/api/agent/config":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            conf = agent_save(meta if isinstance(meta, dict) else {})
            self._send(200, json.dumps({"ok": True, "enabled": bool(conf.get("enabled")),
                                        "token": conf.get("token", "")}, ensure_ascii=False))
            return

        if u.path == "/api/agent/exec":
            # Agent 调用入口：开关没开或令牌不对 → 记一条"拦截"，并明确拒绝。
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            conf = agent_config()
            action = str(meta.get("action") or "")
            if not conf.get("enabled"):
                agent_log(action, False, "Agent 接入已关闭")
                self._send(403, json.dumps({"ok": False, "blocked": True,
                                            "reason": "Agent 接入已关闭，请在 App 里打开开关"},
                                           ensure_ascii=False))
                return
            if str(meta.get("token") or "") != conf.get("token"):
                agent_log(action, False, "令牌不符")
                self._send(403, json.dumps({"ok": False, "blocked": True,
                                            "reason": "令牌不符"}, ensure_ascii=False))
                return
            try:
                if action == "status":
                    agent_log(action, True)
                    self._send(200, json.dumps({"ok": True, "state": _state},
                                               ensure_ascii=False))
                    return
                if action == "products":
                    agent_log(action, True)
                    items = []
                    if os.path.isdir(OUTBOX):
                        for n in sorted(os.listdir(OUTBOX)):
                            p2 = os.path.join(OUTBOX, n)
                            if os.path.isfile(p2) and not n.startswith("."):
                                items.append({"name": n, "size": os.path.getsize(p2),
                                              "mtime": os.path.getmtime(p2)})
                    self._send(200, json.dumps({"ok": True, "items": items}, ensure_ascii=False))
                    return
                if action == "desensitize":
                    paths = [x for x in (meta.get("paths") or [])
                             if os.path.exists(x) and
                             os.path.splitext(x)[1].lower() in SUPPORTED]
                    if not paths:
                        agent_log(action, False, "没有可处理的文件")
                        self._send(400, json.dumps({"ok": False, "msg": "没有可处理的文件"},
                                                   ensure_ascii=False))
                        return
                    if _state["running"]:
                        agent_log(action, False, "已有任务在跑")
                        self._send(409, json.dumps({"ok": False, "msg": "已有任务在跑"},
                                                   ensure_ascii=False))
                        return
                    task_id = time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)
                    th = threading.Thread(target=run_job, args=(paths, True, None, task_id), daemon=True)
                    th.start()
                    agent_log(action, True, "", "%d 个文件" % len(paths))
                    self._send(200, json.dumps({
                        "ok": True, "task_id": task_id,
                        "preview_url": "preview.html?task=%s&file=1" % task_id,
                        "history": "这次跑完会出现在「最近脱敏」里，和手动点按钮一样",
                    }, ensure_ascii=False))
                    return
                if action == "to-md":
                    # agent 最常用的一条：把成品转 md，返回路径供它直接读
                    paths = [str(x) for x in (meta.get("paths") or [])]
                    if meta.get("path"):
                        paths.append(str(meta["path"]))
                    paths = [p2 for p2 in paths if p2]
                    if not paths:
                        agent_log(action, False, "没给文件路径")
                        self._send(400, json.dumps({"ok": False, "msg": "请给 paths 或 path"},
                                                   ensure_ascii=False))
                        return
                    ocr = bool(meta.get("ocr", True))
                    try:
                        if len(paths) == 1:
                            r = to_md(paths[0], meta.get("out") or "", ocr=ocr)
                        else:
                            r = to_md_batch(paths, ocr=ocr)
                    except Exception as e:
                        agent_log(action, False, "转换异常")
                        self._send(500, json.dumps({"ok": False, "msg": str(e)[:140]},
                                                   ensure_ascii=False))
                        return
                    agent_log(action, bool(r.get("ok")), "", r.get("md") or r.get("dir") or "")
                    self._send(200 if r.get("ok") else 409,
                               json.dumps(r, ensure_ascii=False))
                    return

                if action == "list-md":
                    items = []
                    d = md_out_dir()
                    for n in sorted(os.listdir(d)):
                        # 跳过 .~排版*.md 之类的编辑器临时残留：它们是隐藏文件，
                        # 不是转出来的成品，列出来会让人以为「历史记录没删干净」。
                        if n.startswith(".") or not n.endswith(".md"):
                            continue
                        p2 = os.path.join(d, n)
                        items.append({"name": n, "path": p2,
                                      "size": os.path.getsize(p2),
                                      "mtime": os.path.getmtime(p2)})
                    self._send(200, json.dumps({"ok": True, "dir": d, "items": items},
                                               ensure_ascii=False))
                    return

                if action == "restore":
                    path = str(meta.get("path") or "")
                    mp = str(meta.get("map") or "")
                    r = restore_apply(path, mp, meta.get("choices") or {}, RESTORE_DIR,
                                      name_hint=str(meta.get("name") or ""))
                    agent_log(action, bool(r.get("ok")), "" if r.get("ok") else str(r.get("msg"))[:80])
                    self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                    return
                if action == "open":
                    # 让 App 窗口跳到指定页面：preview / history / restore / paint
                    page = str(meta.get("page") or "preview")
                    task = os.path.basename(str(meta.get("task") or ""))
                    fno = str(meta.get("file") or "1")
                    if page == "preview" and task:
                        url = "preview.html?task=%s&file=%s" % (task, fno)
                    elif page == "paint" and task:
                        url = "paint.html?task=%s" % task
                    elif page == "restore-plan" and meta.get("id"):
                        url = "restoreplan.html?id=%s" % str(meta["id"])
                    elif page == "pdfview" and task:
                        url = "pdfview.html?task=%s&file=%s" % (task, fno)
                    else:
                        url = "index.html"
                    _NAV.update({"url": url, "ts": time.time()})
                    agent_log(action, True, "", url)
                    self._send(200, json.dumps({"ok": True, "url": url}, ensure_ascii=False))
                    return

                agent_log(action, False, "未知动作")
                self._send(400, json.dumps({"ok": False, "msg": "未知动作"}, ensure_ascii=False))
            except Exception as e:
                agent_log(action, False, "异常：%s" % str(e)[:80])
                self._send(500, json.dumps({"ok": False, "msg": "执行失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
            return

        if u.path == "/api/ai/config":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            conf = ai_save(meta if isinstance(meta, dict) else {})
            self._send(200, json.dumps({"ok": True, "config": conf}, ensure_ascii=False))
            return

        if u.path == "/api/ai/remap":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            if _state["running"]:
                self._send(409, json.dumps({"ok": False, "msg": "正在脱敏，等这批跑完再改化名"},
                                           ensure_ascii=False))
                return
            try:
                r = ai_remap(meta.get("task"))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "化名失败：%s" % str(e)[:160]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/clear-undo":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            if str(meta.get("confirm") or "") != "1":
                self._send(400, json.dumps(
                    {"ok": False, "msg": "缺少确认标记，未还原任何文件（需 confirm=\"1\"）"},
                    ensure_ascii=False))
                return
            try:
                r = clear_undo(meta.get("bucket") or "")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "还原失败：%s" % str(e)[:160]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/clear-all":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            # groups 是界面用的字段名，keys 是接口文档写法，两个都收
            keys = meta.get("groups") or meta.get("keys") or []
            if not isinstance(keys, list) or not keys:
                self._send(400, json.dumps({"ok": False, "msg": "没有选中任何一组"},
                                           ensure_ascii=False))
                return
            # 删除必须显式确认：脚本、agent、手滑调用都得先带 confirm=1。
            # 今天两次误清都是"参数写对了但本不该执行"，加一道闸比事后恢复划算。
            if str(meta.get("confirm") or "") != "1":
                self._send(400, json.dumps(
                    {"ok": False, "msg": "缺少确认标记，未删除任何文件（需 confirm=\"1\"）"},
                    ensure_ascii=False))
                return
            if _state["running"]:
                self._send(409, json.dumps(
                    {"ok": False, "msg": "正在脱敏，等这一批跑完再清"}, ensure_ascii=False))
                return
            try:
                r = clear_all([str(k) for k in keys])
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "清除失败：%s" % str(e)[:160]},
                                           ensure_ascii=False))
                return
            self._send(200, json.dumps(r, ensure_ascii=False))
            return

        if u.path.startswith("/api/paint/"):
            act = u.path[len("/api/paint/"):]
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            task = meta.get("task") or ""

            if act == "from-task":
                # 合格成品也要能手动涂黑：从**预览任务**的成品建涂黑任务。
                # 注意这一步必须先于 paint- 目录校验——此时 task 还是预览任务编号。
                try:
                    r = paint_from_task(task, meta.get("file") or "1")
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "打开失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                return

            tdir = _paint_dir(task)
            if not tdir or not os.path.isdir(tdir):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在"},
                                           ensure_ascii=False))
                return

            if act == "auto-groups":
                # 整份扫描并按"被遮住的原文"分组：界面直接点黑块，就清这一组全部
                r = paint_auto_scan(task, use_cache=bool(meta.get("refresh") is not True))
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "clear-group":
                gid = str(meta.get("gid") or "")
                scan = paint_auto_scan(task, use_cache=True)
                if not scan.get("ok"):
                    self._send(409, json.dumps(scan, ensure_ascii=False))
                    return
                hit = None
                for g in scan.get("groups") or []:
                    if g.get("gid") == gid:
                        hit = g
                        break
                if not hit:
                    self._send(404, json.dumps({"ok": False, "msg": "找不到这组内容"}, ensure_ascii=False))
                    return
                r = paint_clear_items(task, hit.get("items") or [])
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "clear-groups":
                # 一次清多个位置：用户要"这几个水印一把清掉"，不该点 N 次
                gids = meta.get("gids") or []
                if not isinstance(gids, list):
                    gids = [gids]
                gids = [str(g) for g in gids if g]
                if not gids:
                    self._send(400, json.dumps({"ok": False, "msg": "没有指定要清哪个位置"},
                                               ensure_ascii=False))
                    return
                r = paint_clear_groups(task, gids)
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "redraw":
                r = paint_redraw(task, meta.get("pages"))
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "label-mode":
                # 兼容接口：2026-11-05 用户定"以后默认就把标注烧到黑块上，不要选项了"，
                # 开关已取消。这里保留只是为了别让旧页面/旧脚本报 404，
                # 一律返回 True，不再写 meta。
                self._send(200, json.dumps({"ok": True, "label_boxes": True},
                                           ensure_ascii=False))
                return

            if act == "reset":
                # 把工作副本退回原件：清掉旧版旋转 bug 烧进底图的错位黑块。
                # 危险动作，必须显式确认，避免误点把已做的活儿清光。
                if meta.get("confirm") != "1":
                    self._send(400, json.dumps(
                        {"ok": False, "msg": "重置会清掉本任务所有涂黑框，需要确认"},
                        ensure_ascii=False))
                    return
                try:
                    r = paint_reset(task)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "重置失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "redraw-multi":
                # 跨文件撤回：「清掉全部文件」动了几个，就得能一次退几个
                jobs = meta.get("jobs") or []
                if not isinstance(jobs, list) or not jobs:
                    self._send(400, json.dumps({"ok": False, "msg": "没有要撤回的文件"},
                                               ensure_ascii=False))
                    return
                r = paint_redraw_multi(jobs)
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "tasks":
                # 列出全部涂黑任务：给"同类涂黑一次性应用到所有任务"用
                self._send(200, json.dumps({"ok": True, "tasks": paint_tasks()},
                                           ensure_ascii=False))
                return

            if act == "clear-all-tasks":
                # 把本任务选中的位置，套用到全部涂黑任务
                gids = meta.get("gids") or []
                if not isinstance(gids, list):
                    gids = [gids]
                gids = [str(g) for g in gids if g]
                if not gids:
                    self._send(400, json.dumps({"ok": False, "msg": "没有指定要清哪个位置"},
                                               ensure_ascii=False))
                    return
                r = paint_clear_all_tasks(task, gids)
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "ai-find":
                # PDF/扫描件/照片专用：OCR 取坐标 → 本地模型判断 → 落成待确认候选
                try:
                    r = paint_ai_find(task, meta.get("pages"), meta.get("model") or "")
                except Exception as e:
                    r = {"ok": False, "msg": "AI 找漏失败：%s" % str(e)[:160]}
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "ai-boxes":
                self._send(200, json.dumps(paint_ai_boxes(task), ensure_ascii=False))
                return

            if act == "ai-accept":
                r = paint_ai_accept(task, meta.get("items"),
                                    all_items=bool(meta.get("all")),
                                    drop=meta.get("drop"))
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "ai-drop":
                # 整批丢掉 AI 候选（判断全是误报）
                tdir2 = _paint_dir(task)
                ap = os.path.join(tdir2, "ai_boxes.json")
                try:
                    if os.path.exists(ap):
                        os.remove(ap)
                except Exception:
                    pass
                self._send(200, json.dumps({"ok": True, "left": 0}, ensure_ascii=False))
                return

            if act == "auto-blocks":
                r = paint_auto_blocks(task, meta.get("page") or 1)
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "clear-auto":
                if not meta.get("orig"):
                    # 老任务没记原件，现找一次并写回
                    found = _find_original(meta.get("name") or "")
                    if found:
                        meta["orig"] = found
                        try:
                            with open(os.path.join(tdir, "meta.json"), "w", encoding="utf-8") as f:
                                json.dump(meta, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                items = []
                for b in (meta.get("blocks") or []):
                    it = dict(b)
                    it.setdefault("page", meta.get("page") or 1)
                    items.append(it)
                r = paint_clear_items(task, items)
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "boxes":
                bp = os.path.join(tdir, "boxes.json")

                # 整份覆盖：批量套用（一页的框复制到几十上百页）时用，
                # 一次请求写完，避免 130 次往返。
                if isinstance(meta.get("all"), dict):
                    clean_all = {}
                    for k, arr in meta["all"].items():
                        try:
                            kk = str(int(k))
                        except Exception:
                            continue
                        cc = []
                        for b in (arr or [])[:200]:
                            try:
                                x0, y0, x1, y1 = [float(v) for v in b[:4]]
                            except Exception:
                                continue
                            _item = [round(min(x0, x1), 2), round(min(y0, y1), 2),
                                     round(max(x0, x1), 2), round(max(y0, y1), 2)]
                            # 第 5 位是标注（姓名/身份证号…）：只做记录，不烧进 PDF
                            if len(b) >= 5 and str(b[4]).strip():
                                _item.append(str(b[4]).strip()[:20])
                            cc.append(_item)
                        if cc:
                            clean_all[kk] = cc
                    with open(bp, "w", encoding="utf-8") as f:
                        json.dump(clean_all, f)
                    total = sum(len(v) for v in clean_all.values())
                    self._send(200, json.dumps({"ok": True, "total": total,
                                                "pages": len(clean_all)}, ensure_ascii=False))
                    return

                try:
                    page = str(int(meta.get("page") or 1))
                except Exception:
                    page = "1"
                clean = []
                for b in (meta.get("boxes") or [])[:200]:
                    try:
                        x0, y0, x1, y1 = [float(v) for v in b[:4]]
                    except Exception:
                        continue
                    _item = [round(min(x0, x1), 2), round(min(y0, y1), 2),
                             round(max(x0, x1), 2), round(max(y0, y1), 2)]
                    # 第 5 位是标注（姓名/身份证号…）：只做记录，不烧进 PDF
                    if len(b) >= 5 and str(b[4]).strip():
                        _item.append(str(b[4]).strip()[:20])
                    clean.append(_item)
                try:
                    with open(bp, encoding="utf-8") as f:
                        allb = json.load(f)
                except Exception:
                    allb = {}
                if clean:
                    allb[page] = clean
                else:
                    allb.pop(page, None)
                with open(bp, "w", encoding="utf-8") as f:
                    json.dump(allb, f)
                total = sum(len(v) for v in allb.values())
                self._send(200, json.dumps({"ok": True, "page_count": len(clean),
                                            "total": total}, ensure_ascii=False))
                return

            if act in ("del", "restore-del"):
                # 涂黑框的删除与撤销：
                # 直接把"删掉的那一块"记进 deleted.json，恢复时按 id 拿回来。
                # 为什么不在前端内存里做：刷新页面就没了，等于白删。
                bp = os.path.join(tdir, "boxes.json")
                dp = os.path.join(tdir, "deleted.json")
                try:
                    with open(bp, encoding="utf-8") as f:
                        allb = json.load(f)
                except Exception:
                    allb = {}
                try:
                    with open(dp, encoding="utf-8") as f:
                        trash = json.load(f) or []
                except Exception:
                    trash = []

                if act == "del":
                    try:
                        pg = str(int(meta.get("page") or 1))
                        idx = int(meta.get("index"))
                    except Exception:
                        self._send(400, json.dumps({"ok": False, "msg": "参数不对"},
                                                   ensure_ascii=False))
                        return
                    arr = allb.get(pg) or []
                    if idx < 0 or idx >= len(arr):
                        self._send(404, json.dumps({"ok": False, "msg": "这一块已经不在了"},
                                                   ensure_ascii=False))
                        return
                    box = arr.pop(idx)
                    if arr:
                        allb[pg] = arr
                    else:
                        allb.pop(pg, None)
                    rec2 = {"id": "b%s" % (int(time.time() * 1000) % 100000000),
                            "page": int(pg), "box": box,
                            "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
                    trash.append(rec2)
                    trash = trash[-200:]        # 留最近 200 条，别无限涨
                    with open(bp, "w", encoding="utf-8") as f:
                        json.dump(allb, f)
                    with open(dp, "w", encoding="utf-8") as f:
                        json.dump(trash, f, ensure_ascii=False)
                    total = sum(len(v) for v in allb.values())
                    self._send(200, json.dumps({"ok": True, "id": rec2["id"],
                                                "page": int(pg), "box": box,
                                                "total": total, "deleted": trash},
                                               ensure_ascii=False))
                    return

                # restore-del：把某一块装回去（放回它原来那一页的末尾）
                rid = str(meta.get("id") or "")
                hit = None
                for it in trash:
                    if it.get("id") == rid:
                        hit = it
                        break
                if not hit:
                    self._send(404, json.dumps({"ok": False, "msg": "找不到这条已删除记录"},
                                               ensure_ascii=False))
                    return
                pg = str(hit.get("page") or 1)
                allb.setdefault(pg, []).append(hit.get("box") or [])
                trash = [it for it in trash if it.get("id") != rid]
                with open(bp, "w", encoding="utf-8") as f:
                    json.dump(allb, f)
                with open(dp, "w", encoding="utf-8") as f:
                    json.dump(trash, f, ensure_ascii=False)
                total = sum(len(v) for v in allb.values())
                self._send(200, json.dumps({"ok": True, "page": int(pg),
                                            "box": hit.get("box"), "total": total,
                                            "deleted": trash}, ensure_ascii=False))
                return

            if act == "export":
                try:
                    r = paint_export(task)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "导出失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                return

            self._send(404, json.dumps({"ok": False}, ensure_ascii=False))
            return

        if u.path.startswith("/api/rejected/"):
            # 「不合格」的三件事：看原因、重脱、忽略。
            # 少了任何一件，拦截都会变成黑洞——用户只知道少了文件，不知道怎么办。
            act = u.path[len("/api/rejected/"):]
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            rid = str(meta.get("id", "") or "")
            rec = None
            for it in rejected_items():
                if it.get("id") == rid:
                    rec = it
                    break

            if act == "open":
                if not rec:
                    self._send(404, json.dumps({"ok": False, "msg": "记录不存在"},
                                               ensure_ascii=False))
                    return
                # 有原因说明就打开说明，没有就把文件夹亮出来
                stem = rec.get("stem") or ""
                p = os.path.join(BAD_DIR, "%s_原因.txt" % stem) if stem else ""
                if p and os.path.exists(p):
                    subprocess.run(["/usr/bin/open", p], capture_output=True)
                else:
                    os.makedirs(BAD_DIR, exist_ok=True)
                    subprocess.run(["/usr/bin/open", BAD_DIR], capture_output=True)
                self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
                return

            if act == "accept":
                if not rec:
                    self._send(404, json.dumps({"ok": False, "msg": "记录不存在"},
                                               ensure_ascii=False))
                    return
                try:
                    r = accept_rejected(rid, "人工确认后放行")
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "放行失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                return

            if act == "ignore":
                try:
                    import reject_store as RS
                    if meta.get("undo"):
                        RS.update(OUTBOX, rid, "undo")
                    else:
                        RS.update(OUTBOX, rid, "ignore")
                    self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": str(e)[:160]},
                                               ensure_ascii=False))
                return

            if act == "paint":
                if not rec:
                    self._send(404, json.dumps({"ok": False, "msg": "记录不存在"},
                                               ensure_ascii=False))
                    return
                try:
                    r = paint_init(rec)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "打开失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                return

            if act == "review":
                if not rec:
                    self._send(404, json.dumps({"ok": False, "msg": "记录不存在"},
                                               ensure_ascii=False))
                    return
                try:
                    r = build_review_task(rec)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "生成预览失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200 if r.get("ok") else 409,
                           json.dumps(r, ensure_ascii=False))
                return

            if act == "retry":
                if not rec:
                    self._send(404, json.dumps({"ok": False, "msg": "记录不存在"},
                                               ensure_ascii=False))
                    return
                if _state["running"]:
                    self._send(409, json.dumps({"ok": False, "msg": "正在处理中，请等当前任务结束"},
                                               ensure_ascii=False))
                    return
                if not rec.get("has_orig"):
                    self._send(409, json.dumps(
                        {"ok": False, "msg": "原件已不在「不合格/原件」里，无法重脱；"
                                             "请把原文件重新拖进来处理一次"},
                        ensure_ascii=False))
                    return
                # 先置忙，避免前端轮询抢在下个线程启动前看到 running=false 提前收工
                _state["running"] = True
                _state["percent"] = 0
                threading.Thread(target=run_retry, args=(rid,), daemon=True).start()
                self._send(200, json.dumps({"ok": True, "msg": "已开始重脱"}, ensure_ascii=False))
                return

            self._send(404, json.dumps({"ok": False}, ensure_ascii=False))
            return

        if u.path.startswith("/api/terms/"):
            act = u.path[len("/api/terms/"):]
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            import rules_store  # noqa: F401  确保配置层可用

            def _read():
                out = []
                if os.path.exists(TERMS_FILE):
                    with open(TERMS_FILE, encoding="utf-8") as f:
                        for line in f:
                            t = line.strip()
                            if t and not t.startswith("#"):
                                out.append(t)
                return out

            def _write(lines):
                os.makedirs(os.path.dirname(TERMS_FILE), exist_ok=True)
                if os.path.exists(TERMS_FILE):
                    shutil.copy(TERMS_FILE, TERMS_FILE + ".bak")
                with open(TERMS_FILE, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + ("\n" if lines else ""))

            if act == "save":
                orig = (meta.get("orig") or "").strip()
                repl = (meta.get("repl") or "").strip()
                old = (meta.get("old") or "").strip()
                if not orig:
                    self._send(400, json.dumps({"ok": False, "msg": "原词不能为空"},
                                               ensure_ascii=False))
                    return
                if "=" in orig:
                    self._send(400, json.dumps({"ok": False, "msg": "原词里不能含等号"},
                                               ensure_ascii=False))
                    return
                lines = []
                replaced = False
                for t in _read():
                    k = t.split("=", 1)[0].strip()
                    if k == (old or orig):
                        lines.append("%s=%s" % (orig, repl))
                        replaced = True
                    else:
                        lines.append(t)
                if not replaced:
                    lines.append("%s=%s" % (orig, repl))
                _write(lines)
                self._send(200, json.dumps({"ok": True, "msg": "已保存"}, ensure_ascii=False))
                return

            if act == "delete":
                orig = (meta.get("orig") or "").strip()
                lines = [t for t in _read() if t.split("=", 1)[0].strip() != orig]
                _write(lines)
                self._send(200, json.dumps({"ok": True, "msg": "已删除"}, ensure_ascii=False))
                return

            if act == "parse":
                # 2026-11-06 用户要「支持表格的对照表读取」。
                # 这里只解析、不落盘 —— 先让用户看清读到几条、哪几列当原词，
                # 确认后才走 import。格式不对时把词表写坏，比多一次点击贵得多。
                script = '''
try
	set f to choose file with prompt "选择词条对照表（.xlsx / .csv / .txt / .docx）"
	return POSIX path of f
on error
	return ""
end try'''
                # 不写 of type 白名单：写窄了用户会「选不到自己的表」，
                # 那是最难自己诊断的故障。让他随便选，后端按扩展名给人话提示。
                # meta.path 是给自己复测/以后接拖拽用的，同一套解析，不走弹窗。
                src = (meta.get("path") or "").strip()
                if not src:
                    try:
                        r = subprocess.run(["/usr/bin/osascript", "-e", script],
                                           capture_output=True, text=True, timeout=300)
                        src = (r.stdout or "").strip()
                    except Exception:
                        src = ""
                if not src or not os.path.exists(src):
                    self._send(200, json.dumps({"ok": False, "cancel": True,
                                                "msg": "已取消"}, ensure_ascii=False))
                    return
                try:
                    from terms_import import parse_terms_file
                except Exception as e:
                    self._send(500, json.dumps({"ok": False,
                                                "msg": "解析模块不可用：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                res = parse_terms_file(src)
                res["path"] = src
                self._send(200, json.dumps(res, ensure_ascii=False))
                return

            if act == "import":
                # 落盘。merge = 保留旧词条、同名的用新值覆盖；replace = 整表替换。
                try:
                    from terms_import import normalize_items, terms_to_lines, parse_lines
                except Exception as e:
                    self._send(500, json.dumps({"ok": False,
                                                "msg": "解析模块不可用：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                items = meta.get("items")
                mode = (meta.get("mode") or "merge").strip().lower()
                if mode not in ("merge", "replace"):
                    mode = "merge"
                if not isinstance(items, list) or not items:
                    self._send(400, json.dumps({"ok": False, "msg": "没有要导入的词条"},
                                               ensure_ascii=False))
                    return
                raw = []
                for i, it in enumerate(items):
                    if not isinstance(it, dict):
                        continue
                    raw.append((str(it.get("orig") or ""), str(it.get("repl") or ""), i + 1))
                norm, skipped = normalize_items(raw, source="import")
                if not norm:
                    self._send(400, json.dumps(
                        {"ok": False, "msg": "这批词条一条有效的都没有，没有写入",
                         "skipped": skipped[:20]}, ensure_ascii=False))
                    return
                old = parse_lines(_read())
                if mode == "replace":
                    merged = norm
                    overwritten = 0
                else:
                    old_keys = set(x["orig"] for x in old)
                    overwritten = sum(1 for x in norm if x["orig"] in old_keys)
                    merged, _ = normalize_items(
                        [(x["orig"], x["repl"], x.get("row", 0)) for x in old] +
                        [(x["orig"], x["repl"], x["row"]) for x in norm],
                        source="merge")
                _write(terms_to_lines(merged))
                if mode == "replace":
                    msg = "已用 %d 条替换整份词表" % len(merged)
                elif overwritten:
                    msg = "导入 %d 条，其中 %d 条覆盖了同名词条，现共 %d 条" % (
                        len(norm), overwritten, len(merged))
                else:
                    msg = "导入 %d 条，现共 %d 条" % (len(norm), len(merged))
                self._send(200, json.dumps({
                    "ok": True, "mode": mode, "added": len(norm),
                    "overwritten": overwritten, "total": len(merged),
                    "skipped": skipped[:20], "msg": msg,
                }, ensure_ascii=False))
                return

            if act == "clear":
                # 2026-11-06 用户原话：「我导进去以后还得自己手动一个个删」。
                # 清空前 _write 会自动留一份 .bak，误点还能捞回来。
                n = len(_read())
                _write([])
                self._send(200, json.dumps({
                    "ok": True, "removed": n,
                    "msg": "已清空 %d 条（原词表备份在同目录 敏感词表.txt.bak）" % n,
                }, ensure_ascii=False))
                return

            if act == "template":
                # App 内 WKWebView 不认 Content-Disposition，下载会显示乱码，
                # 所以这里改成「写到词表文件夹 + Finder 定位」，点完就能双击填。
                fmt = (meta.get("fmt") or "xlsx").strip().lower()
                try:
                    from terms_import import build_template
                    data, name, _mime = build_template(fmt)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False,
                                                "msg": "模板生成失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                desk = os.path.join(BASE_DIR, "词表")
                os.makedirs(desk, exist_ok=True)
                fp = os.path.join(desk, name)
                # 同名文件已存在就不覆盖 —— 用户可能已经在里面填了词条，
                # 覆盖等于把他刚干的活删了。改存带时间戳的副本。
                if os.path.exists(fp) and os.path.getsize(fp) > 0:
                    base, ext = os.path.splitext(name)
                    fp = os.path.join(desk, "%s-%s%s" % (base, time.strftime("%m%d-%H%M"), ext))
                try:
                    with open(fp, "wb") as f:
                        f.write(data)
                    subprocess.run(["/usr/bin/open", "-R", fp], capture_output=True)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False,
                                                "msg": "写模板失败：%s" % str(e)[:160]},
                                               ensure_ascii=False))
                    return
                self._send(200, json.dumps({
                    "ok": True, "path": fp, "name": os.path.basename(fp),
                    "msg": "模板已放到「词表」文件夹并已在访达中选中：%s" % os.path.basename(fp),
                }, ensure_ascii=False))
                return

            if act == "pick":
                # 从词表库挑一份导入（覆盖当前词表，先备份）
                script = '''
try
	set f to choose file with prompt "选择词表文件（txt）"
	return POSIX path of f
on error
	return ""
end try'''
                try:
                    r = subprocess.run(["/usr/bin/osascript", "-e", script],
                                       capture_output=True, text=True, timeout=300)
                    src = (r.stdout or "").strip()
                except Exception:
                    src = ""
                if not src or not os.path.exists(src):
                    self._send(200, json.dumps({"ok": False, "msg": "已取消"}, ensure_ascii=False))
                    return
                shutil.copy(src, TERMS_FILE)
                self._send(200, json.dumps({"ok": True, "msg": "已导入 %s" % os.path.basename(src)},
                                           ensure_ascii=False))
                return

            self._send(404, json.dumps({"ok": False, "msg": "未知操作"}, ensure_ascii=False))
            return

        if u.path == "/api/restore/ai-suggest":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                import history_store as HS
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "账本不可用"}, ensure_ascii=False))
                return
            ent = HS.get_entry(str(meta.get("id", "") or ""))
            if not ent:
                self._send(404, json.dumps({"ok": False, "msg": "找不到这条记录"},
                                           ensure_ascii=False))
                return
            src, mp = HS.resolve_input(ent), _map_fallback(ent)
            if not src or not mp:
                self._send(410, json.dumps({"ok": False, "msg": "脱敏件或映射表已丢失"},
                                           ensure_ascii=False))
                return
            conf = ai_config()
            if not conf.get("enabled"):
                self._send(409, json.dumps({"ok": False, "msg": "本地 AI 已关闭"},
                                           ensure_ascii=False))
                return
            try:
                r = restore_ai_suggest(src, mp, conf.get("host"), conf.get("model"))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "AI 判断失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/to-md":
            # 界面与外部脚本共用：传 path 或 paths，可指定 out
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            paths = [str(x) for x in (meta.get("paths") or [])]
            if meta.get("path"):
                paths.append(str(meta["path"]))
            paths = [p2 for p2 in paths if p2]
            if not paths:
                self._send(400, json.dumps({"ok": False, "msg": "请给 paths 或 path"},
                                           ensure_ascii=False))
                return
            ocr = bool(meta.get("ocr", True))
            # 2026-11-12 新增「文件转 MD」独立入口：可以选输出到源文件旁边，
            # 不再只能落到统一 MD 文件夹。agent 老调用不传 out_dir，行为不变。
            out_dir = str(meta.get("out_dir") or "")
            try:
                if len(paths) == 1:
                    out = str(meta.get("out") or "")
                    if not out and out_dir:
                        out = md_out_for(paths[0], out_dir)
                    r = to_md(paths[0], out, ocr=ocr)
                else:
                    r = to_md_batch(paths, ocr=ocr)
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": str(e)[:160]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/to-md/read":
            # 独立入口的「查看」按钮：读回 md 全文。仅限 .md / .markdown，
            # 不开放任意文件读取（本地服务也不该顺手开个洞）。
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            p3 = str(meta.get("path") or "")
            if not (p3 and os.path.isfile(p3) and
                    p3.lower().endswith((".md", ".markdown"))):
                self._send(400, json.dumps({"ok": False, "msg": "文件不是 md 或不存在"},
                                           ensure_ascii=False))
                return
            try:
                with open(p3, encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                self._send(200, json.dumps({"ok": True, "path": p3,
                                            "name": os.path.basename(p3),
                                            "text": txt, "chars": len(txt)},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": str(e)[:140]},
                                           ensure_ascii=False))
            return

        if u.path == "/api/to-md/folder":
            d = md_out_dir()
            subprocess.run(["/usr/bin/open", d], capture_output=True)
            self._send(200, json.dumps({"ok": True, "dir": d}, ensure_ascii=False))
            return

        if u.path == "/api/to-md/list":
            items = []
            d = md_out_dir()
            for n in sorted(os.listdir(d)):
                # 隐藏文件（.DS_Store / .~排版*.md 编辑器残留）不是成品，别列为历史记录
                if n.startswith(".") or not n.endswith(".md"):
                    continue
                p2 = os.path.join(d, n)
                items.append({"name": n, "path": p2, "size": os.path.getsize(p2),
                              "mtime": os.path.getmtime(p2)})
            self._send(200, json.dumps({"ok": True, "dir": d, "items": items},
                                       ensure_ascii=False))
            return

        if u.path == "/api/unredact/log":
            # 这是 POST，参数在 body 里；以前抄了 GET 的写法去读 query，
            # 永远取到空任务号 → 撤销日志恒为空（2026-11-02 实测）
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            self._send(200, json.dumps({"ok": True,
                                        "items": unredact_log(meta.get("task") or "",
                                                             meta.get("file") or "1")},
                                       ensure_ascii=False))
            return

        if u.path == "/api/unredact/one":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                r = unredact_one(meta.get("task"), str(meta.get("ph") or ""),
                                 meta.get("nth") or 1, meta.get("file") or "1")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "还原失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/unredact/redo":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                r = redo_unredact(meta.get("task"), str(meta.get("ph") or ""),
                                   meta.get("file") or "1")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "恢复失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/unredact":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                r = unredact_item(meta.get("task"), str(meta.get("ph") or ""))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "撤销失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/restore/blocks":
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                import history_store as HS
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "账本不可用：%s" % str(e)[:100]},
                                           ensure_ascii=False))
                return
            ent = HS.get_entry(str(meta.get("id", "") or ""))
            if not ent:
                self._send(404, json.dumps({"ok": False, "msg": "找不到这条记录"},
                                           ensure_ascii=False))
                return
            src, mp = HS.resolve_input(ent), _map_fallback(ent)
            if not src or not mp:
                self._send(410, json.dumps({"ok": False, "msg": "脱敏件或映射表已丢失"},
                                           ensure_ascii=False))
                return
            try:
                r = restore_blocks(src, mp)
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "解析失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            r.update({"entry_id": ent.get("id"), "name": ent.get("output_name") or ""})
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path in ("/api/restore/plan", "/api/restore/apply"):
            # 还原预览：先列出每一处占位符 → 人可逐处改 → 再生成还原件
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                import history_store as HS
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "账本不可用：%s" % str(e)[:100]},
                                           ensure_ascii=False))
                return
            ent = HS.get_entry(str(meta.get("id", "") or ""))
            if not ent:
                self._send(404, json.dumps({"ok": False, "msg": "找不到这条记录"},
                                           ensure_ascii=False))
                return
            src = HS.resolve_input(ent)
            mp = _map_fallback(ent)
            if not src:
                self._send(410, json.dumps({"ok": False, "msg": "脱敏件可能被移动或改名了"},
                                           ensure_ascii=False))
                return
            if not mp:
                self._send(409, json.dumps({"ok": False, "msg": "这份记录的映射表已丢失"},
                                           ensure_ascii=False))
                return

            if u.path.endswith("/plan"):
                try:
                    r = restore_plan(src, mp)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "解析失败：%s" % str(e)[:140]},
                                               ensure_ascii=False))
                    return
                r.update({"entry_id": ent.get("id"), "name": ent.get("output_name") or "",
                          "source": os.path.basename(src)})
                self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                return

            try:
                r = restore_apply(src, mp, meta.get("choices") or {}, RESTORE_DIR,
                                  name_hint=str(meta.get("name") or ""))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "还原失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            if r.get("ok"):
                try:
                    HS.update_entry(ent.get("id"), status="restored", restore_path=r["out"],
                                    restored_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
                r["name"] = os.path.basename(r["out"])
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path == "/api/restore/entry":
            # 一键复原：用这条记录导出时冻结的映射表，不需要用户再选
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            eid = str(meta.get("id", "") or "")
            try:
                import history_store as HS
                import restore_helper as RH
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "stage": "module",
                                            "msg": "还原模块不可用：%s" % str(e)[:120]},
                                           ensure_ascii=False))
                return
            ent = HS.get_entry(eid)
            if not ent:
                self._send(404, json.dumps({"ok": False, "stage": "entry",
                                            "msg": "这条记录不存在"}, ensure_ascii=False))
                return
            src = HS.resolve_input(ent)
            if not src:
                self._send(410, json.dumps({"ok": False, "stage": "file",
                                            "msg": "找不到「%s」，可能被移动或改名"
                                                   % (ent.get("output_name") or "脱敏文件")},
                                           ensure_ascii=False))
                return
            mp = HS.resolve_map(ent)
            if not mp:
                self._send(409, json.dumps({"ok": False, "stage": "map",
                                            "msg": "这份记录的映射表已丢失，无法一键复原"},
                                           ensure_ascii=False))
                return
            # 先查冲突：一个占位符对应多个原值，还原只能挑一个，
            # 等于把其余原值悄悄换成它（实测 16 家公司共用一个 [乙方公司]）。
            # 这种情况宁可不还原，也不能给出一个看着对的错答案。
            conf = RH.check_conflicts(mp)
            if conf:
                self._send(409, json.dumps({
                    "ok": False, "stage": "conflict",
                    "conflicts": conf[:20], "conflict_count": len(conf),
                    "msg": "映射表里有 %d 个占位符对应多个原值，无法确定该还原成哪一个"
                           % len(conf)}, ensure_ascii=False))
                return

            ok, out, info = RH.run_restore(src, mp, RESTORE_DIR)
            residual = info.get("residual", []) if isinstance(info, dict) else []
            if ok:
                try:
                    HS.update_entry(eid, status="restored", restore_path=out,
                                    restored_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass
                self._send(200, json.dumps({"ok": True, "out": out,
                                            "map_count": ent.get("map_count", 0),
                                            "name": os.path.basename(out),
                                            "residual": residual,
                                            "residual_count": len(residual)},
                                           ensure_ascii=False))
            else:
                self._send(500, json.dumps({"ok": False, "stage": "run", "msg": out},
                                           ensure_ascii=False))
            return

        if u.path in ("/api/restore/file-plan", "/api/restore/file-apply"):
            # 给定「某个文件 + 某份映射表」直接还原：批注修订后另存的新文件
            # 账本里没有记录，但占位符还是老一套，这条路径专门伺候它。
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            path = str(meta.get("path") or "")
            mp = str(meta.get("map") or "")
            if not (path and os.path.exists(path)):
                self._send(404, json.dumps({"ok": False, "msg": "文件不存在"}, ensure_ascii=False))
                return
            if not (mp and os.path.exists(mp)):
                self._send(400, json.dumps({"ok": False, "msg": "映射表不存在"}, ensure_ascii=False))
                return
            if u.path.endswith("/file-plan"):
                try:
                    r = restore_blocks(path, mp)
                except Exception as e:
                    self._send(500, json.dumps({"ok": False, "msg": "解析失败：%s" % str(e)[:140]},
                                               ensure_ascii=False))
                    return
                r["name"] = os.path.basename(path)
                self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
                return
            try:
                r = restore_apply(path, mp, meta.get("choices") or {}, RESTORE_DIR,
                                  name_hint=str(meta.get("name") or ""))
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "还原失败：%s" % str(e)[:140]},
                                           ensure_ascii=False))
                return
            if r.get("ok"):
                r["name"] = os.path.basename(r["out"])
            self._send(200 if r.get("ok") else 409, json.dumps(r, ensure_ascii=False))
            return

        if u.path.startswith("/api/restore/"):
            act = u.path[len("/api/restore/"):]
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            try:
                import restore_helper as RH
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "还原模块不可用：%s" % str(e)[:120]},
                                           ensure_ascii=False))
                return

            if act == "match":
                path = meta.get("path") or ""
                if not (path and os.path.exists(path)):
                    self._send(404, json.dumps({"ok": False, "msg": "文件不存在"},
                                               ensure_ascii=False))
                    return
                okfmt, why = RH.can_restore(path)
                m = RH.match_map(path, KEYS)
                self._send(200, json.dumps({
                    "ok": okfmt, "msg": why, "path": path,
                    "by": m["by"], "best": m.get("best"),
                    "candidates": m.get("candidates", [])[:60],
                }, ensure_ascii=False))
                return

            if act == "run":
                path = meta.get("path") or ""
                map_csv = meta.get("map") or ""
                if not (path and os.path.exists(path)):
                    self._send(404, json.dumps({"ok": False, "msg": "文件不存在"},
                                               ensure_ascii=False))
                    return
                if not (map_csv and os.path.exists(map_csv)):
                    self._send(400, json.dumps({"ok": False, "msg": "映射表不存在"},
                                               ensure_ascii=False))
                    return
                _conf = RH.check_conflicts(map_csv)
                if _conf:
                    self._send(409, json.dumps({
                        "ok": False, "stage": "conflict",
                        "conflicts": _conf[:20], "conflict_count": len(_conf),
                        "msg": "这份映射表里有 %d 个占位符对应多个原值，无法确定该还原成哪一个"
                               % len(_conf)}, ensure_ascii=False))
                    return
                ok, out, info = RH.run_restore(path, map_csv, RESTORE_DIR)
                residual = info.get("residual", []) if isinstance(info, dict) else []
                self._send(200, json.dumps({"ok": ok, "msg": out if not ok else "已还原",
                                            "out": out if ok else "",
                                            "residual": residual,
                                            "residual_count": len(residual)},
                                           ensure_ascii=False))
                return

            self._send(404, json.dumps({"ok": False, "msg": "未知操作"}, ensure_ascii=False))
            return

        if u.path == "/api/cancel":
            # 真取消：把流水线整个进程组掐断。
            # 只改界面状态是假的 —— 后台还在跑，成品照样落盘。
            proc = _CURRENT.get("proc")
            killed = False
            if proc is not None and proc.poll() is None:
                try:
                    import signal as _sig
                    os.killpg(os.getpgid(proc.pid), _sig.SIGTERM)
                    killed = True
                except Exception:
                    try:
                        proc.terminate()
                        killed = True
                    except Exception:
                        pass

                def _force():
                    time.sleep(3)
                    try:
                        if proc.poll() is None:
                            try:
                                os.killpg(os.getpgid(proc.pid), 9)
                            except Exception:
                                proc.kill()
                    except Exception:
                        pass

                threading.Thread(target=_force, daemon=True).start()
            _state["cancelled"] = True
            _state["stage"] = "正在取消…" if killed else "已取消"
            self._send(200, json.dumps({"ok": True, "killed": killed}, ensure_ascii=False))
            return

        if u.path == "/api/desensitize":
            # 预览模式启动：结果写任务目录，不落成品目录
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            paths = [x for x in (meta.get("paths") or [])
                     if os.path.exists(x) and os.path.splitext(x)[1].lower() in SUPPORTED]
            if not paths:
                # 别只说「没有可用文件」——用户拖进来的东西为什么被拒，得说清楚
                _raw = meta.get("paths") or [] if isinstance(meta, dict) else []
                _bad = sorted({(os.path.splitext(os.path.basename(x))[1] or x) for x in _raw})
                _msg = ("这些格式不支持：%s。支持 doc/docx、PDF、图片、txt/md、xlsx"
                        % "、".join(_bad[:5])) if _bad else "没有可用文件"
                self._send(400, json.dumps({"ok": False, "msg": _msg}, ensure_ascii=False))
                return
            if _state["running"]:
                self._send(409, json.dumps({"ok": False, "msg": "正在处理中"}, ensure_ascii=False))
                return
            task_id = time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)
            task_dir = os.path.join(PREVIEW_ROOT, task_id)
            os.makedirs(os.path.join(task_dir, "output"), exist_ok=True)
            # 同上：有用户词表时默认不做自动识敏，别把他的词表顶掉
            _has_t2 = os.path.exists(TERMS_FILE) and os.path.getsize(TERMS_FILE) > 0
            threading.Thread(target=run_job,
                             args=(paths, bool(meta.get("auto_terms", not _has_t2)),
                                   os.path.join(task_dir, "output"), task_id),
                             daemon=True).start()
            self._send(200, json.dumps({"ok": True, "task_id": task_id, "count": len(paths)},
                                       ensure_ascii=False))
            return

        if u.path == "/api/mark":
            # 手动标记：只存不跑。导出时统一应用，避免每划一下就重跑一遍流水线。
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            task = os.path.basename(str(meta.get("task", "") or ""))
            fno = str(meta.get("file", "1") or "1")
            fdir = os.path.join(PREVIEW_ROOT, task, "files", fno)
            if not (task and os.path.isdir(fdir)):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在或已过期"},
                                           ensure_ascii=False))
                return
            try:
                import mark_apply as MA
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "标记模块不可用：%s" % str(e)[:120]},
                                           ensure_ascii=False))
                return

            mpath = os.path.join(fdir, "marks.json")
            data = {"marks": []}
            if os.path.exists(mpath):
                try:
                    with open(mpath, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {"marks": []}
            marks = data.get("marks", [])
            act = str(meta.get("action") or "add")

            if act == "remove":
                mid = str(meta.get("id", "") or "")
                gone = [m for m in marks if m.get("id") == mid]
                data["marks"] = [m for m in marks if m.get("id") != mid]
                # 软删除：删掉的标记进「已删除」堆，误删能一键装回来
                # （用户要求：2026-11-02「手动脱敏的也加个撤销功能」）
                if gone:
                    trash = data.get("deleted") or []
                    for g2 in gone:
                        g3 = dict(g2)
                        g3["deleted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        trash.append(g3)
                    data["deleted"] = trash[-50:]
                with open(mpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self._send(200, json.dumps({"ok": True, "marks": data["marks"],
                                            "deleted": data.get("deleted") or []},
                                           ensure_ascii=False))
                return

            if act == "restore":
                # 撤销删除：把「已删除」里那条搬回 marks
                mid = str(meta.get("id", "") or "")
                trash = data.get("deleted") or []
                back = None
                for g2 in trash:
                    if g2.get("id") == mid:
                        back = g2
                        break
                trash = [g2 for g2 in trash if g2.get("id") != mid]
                if back:
                    back.pop("deleted_at", None)
                    if not any(m.get("id") == back.get("id") for m in marks):
                        marks.append(back)
                data["marks"] = marks
                data["deleted"] = trash
                with open(mpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self._send(200 if back else 404,
                           json.dumps({"ok": bool(back), "marks": marks,
                                       "deleted": trash,
                                       "msg": "" if back else "找不到这条已删除标记"},
                                      ensure_ascii=False))
                return

            if act == "list":
                self._send(200, json.dumps({"ok": True, "marks": marks,
                                            "deleted": data.get("deleted") or []},
                                           ensure_ascii=False))
                return

            text = str(meta.get("text") or "").strip()
            cat = str(meta.get("category") or "").strip()
            repl = str(meta.get("repl") or "").strip()
            okc, why = MA.check_mark(text, cat)
            if not okc:
                self._send(400, json.dumps({"ok": False, "msg": why}, ensure_ascii=False))
                return
            if not repl:
                repl = MA.default_repl(text, cat)
            # 占位符必须全局唯一：既要避开映射表里已有的，也要避开已标记的
            try:
                taken = {m.get("repl") for m in marks if m.get("repl")}
                mp0, _nm = _map_paths_for_task(task, fno)
                if mp0:
                    import csv as _csv
                    with open(mp0, encoding="utf-8-sig") as f2:
                        for row in _csv.reader(f2):
                            if len(row) >= 2 and row[1].strip():
                                taken.add(row[1].strip())
                repl = _unique_repl(repl, taken)
            except Exception:
                pass

            # 命中数只数「还没脱敏的文本」，占位符里的字不算。
            # ⚡ 2026-11-18：必须容错 —— 用户在预览里选「张某某」，
            # 而预览数据里那一行是「…、张 绪」（排版把字断开了），
            # 精确 count 得 0，于是弹「这份预览里找不到「张某某」」，人明明就在眼前。
            hits = 0
            try:
                _mrx = getattr(MA, "_fuzzy_rx", None)
                _mrx = _mrx(text) if _mrx else None
                _count = getattr(MA, "_count_in", None)

                def _hits_in(plain):
                    if not plain:
                        return 0
                    if _count:
                        return _count(plain, text, _mrx)
                    return plain.count(text)

                pv = os.path.join(fdir, "preview.json")
                with open(pv, encoding="utf-8") as f:
                    pvd = json.load(f)
                for b in pvd.get("blocks", []):
                    if b.get("type") == "p":
                        plain = "".join(r.get("text", "") for r in b.get("runs", [])
                                        if not r.get("mark"))
                        hits += _hits_in(plain)
                    elif b.get("type") == "table":
                        for row in b.get("rows", []):
                            for cell in row:
                                plain = "".join(r.get("text", "") for r in cell
                                                if not r.get("mark"))
                                hits += _hits_in(plain)
            except Exception:
                hits = 0
            if hits <= 0:
                self._send(400, json.dumps({"ok": False,
                                            "msg": "这份预览里找不到「%s」" % text},
                                           ensure_ascii=False))
                return

            mid = "m%d" % int(time.time() * 1000)
            _ids = {m.get("id") for m in marks}
            while mid in _ids:      # 同一毫秒连点两条时 id 不能撞
                mid += "x"
            mark = {"id": mid, "text": text, "repl": repl,
                    "category": cat, "hits": hits}
            if act == "preview":
                # 只试算不落库：前端先给你看一眼"替换成什么、影响几处"，
                # 点确认才真正写进 marks.json
                self._send(200, json.dumps({"ok": True, "mark": mark},
                                           ensure_ascii=False))
                return
            # 同一个词只留一条
            data["marks"] = [m for m in marks if m.get("text") != text] + [mark]
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._send(200, json.dumps({"ok": True, "mark": mark,
                                        "marks": data["marks"]}, ensure_ascii=False))
            return

        if u.path == "/api/export":
            # 用户确认后才把预览任务里的成品复制到成品目录
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            task = os.path.basename(str(meta.get("task", "")))
            tdir = os.path.join(PREVIEW_ROOT, task)
            outd = os.path.join(tdir, "output")
            # 2026-11-07：预览任务被清过 → 按账本重建再导出。
            # 重建后导出的就是同一份成品，内容不受影响。
            if task and not os.path.isdir(outd):
                if revive_task_from_ledger(task):
                    outd = os.path.join(tdir, "output")
            if not (task and os.path.isdir(outd)):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在"}, ensure_ascii=False))
                return
            os.makedirs(OUTBOX, exist_ok=True)
            saved = []
            applied = {}          # 成品名 -> 该文件的手动标记
            idx_map = {}
            try:
                with open(os.path.join(tdir, "index.json"), encoding="utf-8") as f:
                    for it in json.load(f).get("files", []):
                        nm = it.get("output_name")
                        if not nm and it.get("file"):
                            # 旧任务没写 output_name，按「源文件名 + _已脱敏」推导
                            stem, ext = os.path.splitext(it["file"])
                            nm = "%s_已脱敏%s" % (stem, ext or ".docx")
                        if nm:
                            idx_map[nm] = it.get("index")
            except Exception:
                pass
            try:
                import mark_apply as MA
            except Exception:
                MA = None

            for n in sorted(os.listdir(outd)):
                p = os.path.join(outd, n)
                if not os.path.isfile(p) or n.startswith("."):
                    continue
                if n.lower().endswith((".bak", ".tmp")) or ".bak" in n.lower():
                    continue   # 改化名时的备份不是成品，别复制进成品目录
                dst = os.path.join(OUTBOX, n)
                srcp = p
                marks = []
                idx = idx_map.get(n)
                if idx and MA:
                    mp = os.path.join(tdir, "files", str(idx), "marks.json")
                    if os.path.exists(mp):
                        try:
                            with open(mp, encoding="utf-8") as f:
                                marks = json.load(f).get("marks", [])
                        except Exception:
                            marks = []
                if marks and MA:
                    # 在成品副本上替换，不改任务目录里的原样，便于反复导出对比
                    tmp = os.path.join(tdir, "marked_%s" % n)
                    okm, cnt, _detail = MA.apply_marks(p, tmp, marks)
                    if okm and cnt > 0:
                        srcp = tmp
                        applied[n] = marks
                        _state["log"].append("手动标记 %s：%d 处" % (n, cnt))
                try:
                    shutil.copy2(srcp, dst)
                    saved.append(n)
                except Exception:
                    pass
            # 账本：把「这次导出的成品」与「冻结的映射表」绑死。
            # 不绑的话，下次跑同一文件会覆盖对照表里的映射表，
            # 一周后点复原就会拿新表还原旧件 —— 换错名字且不报错。
            try:
                import history_store as HS
                for n in saved:
                    dst = os.path.join(OUTBOX, n)
                    ent = HS.update_by_task(task, n, status="exported", output_path=dst,
                                            exported_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                    if not ent:
                        # 改造前的旧任务没有账本记录，补一条
                        stem = os.path.splitext(n)[0]
                        src_stem = stem[:-len("_已脱敏")] if stem.endswith("_已脱敏") else stem
                        HS.add_entry(task_id=task, index=0, source=src_stem,
                                     output_name=n, output_path=dst,
                                     map_csv=os.path.join(KEYS, "%s_映射表.csv" % src_stem),
                                     status="exported")
                        HS.update_by_task(task, n,
                                          exported_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception as e:
                _state["log"].append("账本更新失败：%s" % str(e)[:100])

            # 手动标记要补进这次导出冻结的映射表，否则复原时
            # [人名]、[地址] 这些换不回来 —— 冻结表必须和成品完全对应。
            if applied:
                try:
                    import history_store as _HS
                    import mark_apply as _MA
                    for _n, _marks in applied.items():
                        _ent = _HS.update_by_task(task, _n)
                        if _ent and _ent.get("map_snapshot"):
                            _added = _MA.merge_mapping(_ent["map_snapshot"], _marks)
                            if _added:
                                _HS.update_entry(_ent["id"],
                                                 map_count=int(_ent.get("map_count", 0)) + _added)
                except Exception as e:
                    _state["log"].append("映射表补充失败：%s" % str(e)[:100])

            # 标记状态
            # 2026-11-05 修：原来只改任务根目录的 meta.json，而实际 meta 在
            # files/<n>/meta.json，路径对不上，导出后 meta 永远停在 preview。
            # 结果凭证闸门拿不到交叉验证信号，只能单点相信账本。
            _mps = [os.path.join(tdir, "meta.json")]
            _fd = os.path.join(tdir, "files")
            try:
                if os.path.isdir(_fd):
                    for _n in sorted(os.listdir(_fd)):
                        _mps.append(os.path.join(_fd, _n, "meta.json"))
            except Exception:
                pass
            for mp in _mps:
                if not os.path.exists(mp):
                    continue
                try:
                    with open(mp, encoding="utf-8") as f:
                        m = json.load(f)
                    # 多文件任务只标本次导出的那几份
                    _on = m.get("output_name") or ""
                    if _on and saved and _on not in saved:
                        continue
                    m["status"] = "exported"
                    m["exported_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    # 路径改成成品位置：历史列表点「在文件夹中显示」直接用它，
                    # 否则还得在字符串里替换预览目录，一改目录名就失效
                    if saved:
                        m["output_path"] = os.path.join(OUTBOX, saved[0])
                    with open(mp, "w", encoding="utf-8") as f:
                        json.dump(m, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            # 手动处理（rej- 任务）导出后，这份就改好了 → 直接放行：
            # 成品在成品区，旧件归档，「不合格」里不再显示
            if task.startswith("rej-"):
                try:
                    accept_rejected(task[4:], "手动处理后导出，放行")
                except Exception:
                    pass
            # 重新打包 zip? 不需要——生成脚本会取单个文件
            _mk = sum(len(v) for v in applied.values())
            self._send(200, json.dumps({"ok": True, "files": saved,
                                        "marks_applied": _mk,
                                        "dir": OUTBOX}, ensure_ascii=False))
            return

        if u.path.startswith("/api/rules/"):
            # 规则配置的全部写操作集中在这一段
            try:
                import rules_store as RS
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "msg": "规则层不可用：%s" % str(e)[:160]},
                                           ensure_ascii=False))
                return
            meta = {}
            try:
                meta = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                meta = {}
            act = u.path[len("/api/rules/"):]

            if act == "toggle":
                ok, msg = RS.set_enabled(str(meta.get("target", "")),
                                         bool(meta.get("enabled", True)))
            elif act == "save":
                ok, msg = RS.upsert_rule(meta)
            elif act == "delete":
                ok, msg = RS.delete_rule(str(meta.get("id", "")))
            elif act == "reset":
                ok, msg = RS.reset_to_builtin()
            elif act == "export":
                ok, msg = RS.export_to_documents()
            elif act == "import":
                ok, msg = RS.pick_and_import()
            elif act == "test":
                r = RS.test_pattern(meta.get("patterns") or [],
                                    meta.get("text") or "",
                                    meta.get("category") or "敏感项")
                self._send(200, json.dumps(r, ensure_ascii=False))
                return
            else:
                ok, msg = False, "未知操作：%s" % act
            self._send(200, json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False))
            return

        if u.path == "/api/setterms":
            script = '''
try
	set f to choose file with prompt "选择你的敏感词表（txt）"
	return POSIX path of f
on error
	return ""
end try
'''
            try:
                r = subprocess.run(["/usr/bin/osascript", "-e", script],
                                   capture_output=True, text=True, timeout=300)
                src = (r.stdout or "").strip()
                if src and os.path.exists(src):
                    shutil.copy(src, TERMS_FILE)
                    self._send(200, json.dumps({"ok": True, "path": TERMS_FILE}, ensure_ascii=False))
                    return
            except Exception:
                pass
            self._send(200, json.dumps({"ok": False}))
            return

        self._send(404, json.dumps({"ok": False}))


def _pids_on_port(port):
    """谁占着这个端口（返回 PID 列表）。"""
    for exe in ("/usr/sbin/lsof", "/usr/bin/lsof"):
        try:
            out = subprocess.run([exe, "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                                 capture_output=True, text=True, timeout=5).stdout
            return [int(x) for x in out.split() if x.strip().isdigit()]
        except Exception:
            continue
    return []


def _is_our_server(port):
    """确认占着端口的是「立丰脱敏」自己的服务。

    不用进程名/路径判断——实测旧实例的 cwd 可能是 `/`，
    lsof 里根本看不到「立丰脱敏」字样，按路径认亲会漏判。
    改成问一句接口：只要 /api/status 返回我们这几个字段，就是自己人。
    （只读字段名，不读内容。）
    """
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/status" % port, timeout=2) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        return isinstance(data, dict) and {"ollama", "has_terms", "log"} <= set(data.keys())
    except Exception:
        return False


def _bind_own_port(port):
    """把端口变成自己的。

    为什么不能「占用就换 8792」：App 窗口是写死连 127.0.0.1:8791 的，
    换端口等于**窗口连到上一个旧进程**上——用户看到的是上一次的进度、
    点「开始」也发给旧进程。这正是「脱敏进度查询不了了」的根因。
    所以这里只做两件事：占用者是自己上一次的实例就杀掉重来；不是自己人就报错。
    """
    for _ in range(4):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError:
            pids = _pids_on_port(port)
            if not pids or not _is_our_server(port):
                raise
            for p in pids:
                try:
                    os.kill(p, signal.SIGKILL)
                except Exception:
                    pass
            time.sleep(0.5)
    raise OSError("端口 %d 被其他程序占用，请关闭后重试" % port)


def main():
    ensure_dirs()
    try:
        srv = _bind_own_port(8791)
    except Exception as e:
        print("立丰脱敏服务启动失败：%s" % e, flush=True)
        return 1
    print("立丰脱敏服务：http://127.0.0.1:8791", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
