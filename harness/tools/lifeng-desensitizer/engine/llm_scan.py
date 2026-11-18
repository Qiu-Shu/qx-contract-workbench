# -*- coding: utf-8 -*-
"""
本地 LLM 补漏扫描器（配合 desensitize.py 使用）—— 只连本机 Ollama，不联外网。

定位：脱敏的"第二道巡检"。规则脚本（desensitize.py）负责确定性替换；
本脚本用本地小模型扫一遍【已脱敏】的成品，找出规则漏掉的隐性可识别信息
（独特事实组合、未入词表的第三方姓名、可反查的地点/时间/编号等），
输出候选片段供律师确认后补进敏感词表。

**只让模型"报告"，不让它"改写"**——避免模型幻觉改动法律原文。

用法：
  python3 llm_scan.py 脱敏文档.docx
  python3 llm_scan.py 脱敏文档.docx --model qwen2.5:7b
  python3 llm_scan.py 脱敏文档.docx --append-terms 敏感词表.txt   # 候选以注释形式追加，人工确认后去掉 #
  python3 llm_scan.py --list-models
"""
import os
import re
import sys
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "你是法律文书脱敏复核助手。用户会给你一段已经做过部分脱敏的文本，"
    "其中姓名、身份证号、手机号等已被替换为形如 [手机号]、[当事人甲] 的占位符。\n"
    "你的唯一任务：找出文本中【仍然可能反向识别到具体自然人、具体单位、具体案件或具体地点】的原文片段。\n\n"
    "必须逐句扫描、宁多勿漏，不要保守。以下每一类都要检查：\n"
    "1. 人名及称呼：实名，以及“某某”“小李”“某警官”“张队”这类可指向特定人的称呼；\n"
    "2. 单位：公司/工厂/学校/医院/物流公司等全称或特定简称；\n"
    "3. 政法机关具体名称：某看守所、某派出所、某公安局、某法院、某检察院、某监狱、某拘留所；\n"
    "4. 时间：精确到月或日的日期，以及“去年冬天”“去年底”“上个月”这类可锁定事件的表述；\n"
    "5. 编号：车牌号、统一社会信用代码、营业执照号、合同编号、案号、文号、其他证照编号；\n"
    "6. 地址：具体到街道、门牌、楼栋、小区、村组的地址；\n"
    "7. 独特事实组合：地点＋时间＋人物＋行为叠加后能锁定唯一事件的信息。\n\n"
    "只输出一个 JSON 数组；每个元素必须是原文中真实出现的原样片段，逐字照抄，不得改写、不得概括、不得解释。\n"
    "不要输出任何已经是占位符的内容（如 [手机号]、[身份证号]、[当事人甲]）。\n"
    "不要输出罪名、法条名称；单独出现的“民警”“律师”“法官”等通用称谓不算。\n"
    "没有发现则输出 []。数组可以有很多元素，不要只给一两个。\n\n"
    "示例：\n"
    "输入：2023年4月，某某县公安局副局长某某带队到某镇某小学检查，涉案车辆车牌 某A00000。\n"
    '输出：["2023年4月","某某县公安局","某某","某镇某小学","某A00000"]'
)


# 显式禁用代理：urllib 默认读 HTTP_PROXY/HTTPS_PROXY，会把 127.0.0.1 的请求也交给代理，
# 既可能被代理改写结果，也破坏"请求只在本机直连"的保证。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(url, payload=None, timeout=180):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with _OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def list_models(host):
    try:
        info = http_json(host + "/api/tags", timeout=10)
        names = [m.get("name") for m in info.get("models", [])]
        if not names:
            print("Ollama 已运行，但尚未拉取任何模型。请先执行：ollama pull qwen2.5:7b")
        else:
            print("本机已有模型：")
            for n in names:
                print("  -", n)
        return names
    except Exception as e:
        print("连接本机 Ollama 失败：", e)
        print("请确认已安装并启动：ollama serve")
        return []


def read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        from docx import Document
        d = Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                for c in row.cells:
                    parts.append(c.text)
        return "\n".join(parts)
    if ext in (".txt", ".md", ".markdown"):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise SystemExit("仅支持 .docx / .txt / .md，当前：" + ext)


def chunk_text(text, size=1800, overlap=200):
    text = text.strip()
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        if i + size >= len(text):
            break
        i += size - overlap
    return chunks


def scan_chunk(host, model, chunk):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "文本如下：\n" + chunk},
        ],
        "stream": False,
        # 注意：切勿设置 format="json"。实测该参数会强制语法约束，使 qwen2.5 退化成
        # {"鄂A88888":["车牌 鄂A88888"]} 这类畸形对象，导致候选全部丢失（返回 0 条）。
        # 去掉后模型能正常输出完整数组。
        "options": {"temperature": 0, "num_predict": 1024, "top_p": 0.9},
    }
    resp = http_json(host + "/api/chat", payload)
    content = (resp.get("message") or {}).get("content", "")
    return parse_candidates(content)


def parse_candidates(content):
    content = (content or "").strip()
    if not content:
        return []
    # 优先整体 JSON 解析
    try:
        obj = json.loads(content)
        if isinstance(obj, list):
            return [str(x) for x in obj]
        if isinstance(obj, dict):
            for k in ("candidates", "items", "list", "result", "data"):
                if isinstance(obj.get(k), list):
                    return [str(x) for x in obj[k]]
            # 兜底：模型可能输出 {"某片段": ["某片段"]} 这类畸形对象，把键和值里的字符串都捞出来
            salvaged = []
            for k, v in obj.items():
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, str):
                            salvaged.append(x)
                if isinstance(k, str) and len(k) >= 2:
                    salvaged.append(k)
            if salvaged:
                return salvaged
    except Exception:
        pass
    # 退而求其次：抓第一个数组
    m = re.search(r"\[.*?\]", content, re.S)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return [str(x) for x in arr]
        except Exception:
            pass
    return []


def is_noise(s, placeholder_labels=None):
    if not s or not s.strip():
        return True
    s = s.strip()
    if len(s) < 2 or len(s) > 60:
        return True
    if re.fullmatch(r"[\[\]（）()\s\W]+", s):
        return True
    # 已是占位符本体（含 [xxx] 形式）
    if re.fullmatch(r"\[[^\]]{1,14}\]", s):
        return True
    # 模型常把占位符内部的标签词单独报出来（如“政法机关”“当事人甲”“手机号”），需排除
    if placeholder_labels and s in placeholder_labels:
        return True
    if re.fullmatch(r"脱敏\d+", s):
        return True
    return False


def collect_placeholder_labels(text):
    """收集文中已存在的占位符标签，用于过滤模型误报。"""
    return set(m.strip() for m in re.findall(r"\[([^\[\]]{1,14})\]", text) if m.strip())


def main():
    ap = argparse.ArgumentParser(description="本地 LLM 补漏扫描（只连本机 Ollama）")
    ap.add_argument("input", nargs="?", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--append-terms", default="")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # 2026-11-05 用户死命令：本地千问不参与脱敏，补漏扫描一律不跑。
    # 应急须使用者本人在场并设置 DESENS_ALLOW_LLM=1。
    if os.environ.get("DESENS_ALLOW_LLM") != "1":
        sys.stderr.write(
            "\n[x] 本地模型已禁止参与脱敏（含补漏扫描）。\n"
            "    用户 2026-11-05 死命令：千问只在 OCR 使用。\n"
            "    应急须使用者本人在场并设 DESENS_ALLOW_LLM=1。\n\n")
        return 5

    if args.list_models:
        list_models(args.host)
        return
    if not args.input:
        print("请提供待扫描文件。用法：python3 llm_scan.py 脱敏文档.docx")
        sys.exit(1)
    if not os.path.exists(args.input):
        print("文件不存在：", args.input)
        sys.exit(1)

    try:
        text = read_text(args.input)
    except SystemExit:
        raise
    except Exception as e:
        print("读取失败：", e)
        sys.exit(1)

    chunks = chunk_text(text)
    if not chunks:
        print("文本为空，无需扫描。")
        return
    placeholder_labels = collect_placeholder_labels(text)

    print("本机模型：%s ｜ 分块：%d 段 ｜ 仅本地推理" % (args.model, len(chunks)))
    found = []
    for idx, ch in enumerate(chunks, 1):
        try:
            cands = scan_chunk(args.host, args.model, ch)
        except urllib.error.URLError as e:
            print("连接本机 Ollama 失败（第 %d 段）：%s" % (idx, e))
            print("请先启动服务：ollama serve")
            sys.exit(1)
        except Exception as e:
            print("第 %d 段推理异常：%s" % (idx, e))
            continue
        for c in cands:
            if not is_noise(c, placeholder_labels) and c.strip() not in found:
                found.append(c.strip())
        print("  [%d/%d] 候选 %d 条" % (idx, len(chunks), len(cands)))

    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        print("\n===== 候选补漏片段（%d 条，需人工确认）=====" % len(found))
        if not found:
            print("未发现明显残留。")
        for i, s in enumerate(found, 1):
            print("%2d. %s" % (i, s))

    if args.append_terms and found:
        with open(args.append_terms, "a", encoding="utf-8") as f:
            f.write("\n# ===== 以下为本地模型补漏候选（%s 生成，确认后再去掉 # ）=====\n" % args.model)
            for s in found:
                f.write("# %s\n" % s)
        print("\n已以注释形式追加到：%s（确认后手动去掉行首 # 生效）" % args.append_terms)

    print("\n提示：候选仅供人工复核，模型可能误报/漏报，最终以律师判断为准。")


if __name__ == "__main__":
    # 2026-11-05：必须带退出码，否则闸门的 return 5 被吞，调用方以为跑成功了
    sys.exit(main())
