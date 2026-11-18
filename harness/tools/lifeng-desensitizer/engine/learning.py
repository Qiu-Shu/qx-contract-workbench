#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""立丰脱敏 · 自适应学习引擎 —— 把每次办案的经验归纳成规则。

【必须先说清一件事】
本地千问（qwen2.5:7b）的**模型权重不会自己变化**。它不会"越用越懂"，
也不会自己扩展。任何声称模型会自我进化的说法都是骗人的。

那"越用越聪明"靠什么？靠**规则库的自我扩展**：

    每次处理完 → 观察这次遇到的新东西 → 归纳成候选规则 → 验证后入库
              → 下次处理时规则库更大 → 同样的活干得更准更快

这就是人能"越干越熟练"的真实机制——不是大脑长新细胞，
而是把经验沉淀成可复用的判断规则。本模块做的就是这个。

【学什么、怎么学、怎么防止学脏】
只学**结构可验证**的东西，绝不从"没脱掉"反推"不敏感"（那可能只是漏了）。

  1. 新姓氏：映射表里某真名被化名为「X某」→ 说明引擎已认定它是人名
     → 取首字为新姓氏。**验证条件**：该字不能是已有排除词、不能是常见虚词。
  2. 新名字用字：真名的名字部分出现未知字 → 候选为新名字用字。
  3. 机构类型：原文含「局/院/所/厅/部/队/委」且化名保留同类后缀 → 提取类型词。
  4. 误脱纠正：用户明确标注"这个词不该脱" → 进排除表（**只能人给，不自动学**）。

所有候选先进 pending 区，满足下列任一条件才转正：
  · 出现次数 ≥ 2（同一现象重复出现，是规律不是偶然）
  · 用户手动 confirm

【命令】
  python3 learning.py observe --map 映射表.csv --text 原文.txt --case 案名
  python3 learning.py review                    # 看候选，人工审核
  python3 learning.py confirm 赫               # 确认某条候选
  python3 learning.py reject 赫                # 否决某条候选
  python3 learning.py teach --word 和我说 --as non_name   # 直接教一条
  python3 learning.py stats                    # 学习成果
  python3 learning.py export                   # 导出学习库（备份/迁移）
"""
import os
import re
import sys
import csv
import json
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "Library", "Application Support", "立丰脱敏", "记忆库")
LEARNED = os.path.join(BASE, "learned.json")
# 学习库同时回写到技能目录，方便随技能一起备份/迁移
LEARNED_MIRROR = os.path.join(HERE, "learned.json")

# 晋升阈值：同一候选出现这么多次就自动转正
PROMOTE_AT = 2


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


EMPTY = {
    "version": 1,
    "updated": "",
    # 已生效
    "surnames": {},          # {"赫": {"来源":..., "次数":n, "确认":bool}}
    "compound_surnames": {},
    "name_chars": {},
    "non_names": {},
    "org_types": {},         # {"城管局": {"简写":"城管局", "次数":n}}
    "number_anchors": {},    # {"警号": {...}} 编号类锚点词（警号/执业证号/文书编号…）
    # 待审
    "pending": {},           # {"surnames|赫": {...}}
    # 被否决的（记住别再学）
    "rejected": {},
    # 观察日志（可追溯）
    "log": [],
}


def load_learned():
    d = _load(LEARNED, None)
    if not d:
        d = json.loads(json.dumps(EMPTY))
    for k, v in EMPTY.items():
        d.setdefault(k, json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else v)
    return d


def save_learned(d):
    d["updated"] = _now()
    _save(LEARNED, d)
    try:
        _save(LEARNED_MIRROR, d)
    except Exception:
        pass


# ============================================================
# 一、观察：从一次处理的结果里归纳候选
# ============================================================
_ALIAS_PAT = re.compile(r"^[\u4e00-\u9fa5]{1,2}某\d*$")
# 机构后缀（用于识别机构类型）
_ORG_SUFFIX = ("公安局", "公安分局", "分局", "派出所", "警务室", "检察院", "人民检察院",
               "检察分院", "检察部", "法院", "人民法院", "中级法院", "高级法院",
               "司法局", "司法所", "司法厅", "看守所", "拘留所", "监狱", "戒毒所",
               "管教所", "监狱医院", "法律援助中心", "公证处", "鉴定中心", "鉴定所",
               "司法鉴定中心", "司法鉴定所", "大队", "支队", "中队", "审判庭",
               "刑庭", "民庭", "执行局", "国安局", "国家安全局", "委员会", "管理处",
               "管理局", "服务中心", "办公室", "指挥部")


def _strip_level(name):
    """剥掉机构化名开头的层级字，返回机构类型。

    「区城管局」→「城管局」，「市中级人民法院」→「中级人民法院」，
    「公安分局」→「公安分局」（没有层级字，原样返回）。
    """
    s = (name or "").strip()
    for lv in ("街道", "区", "市", "省"):
        if s.startswith(lv) and len(s) > len(lv) + 1:
            return s[len(lv):]
    return s


def _looks_org(word):
    """看起来是不是机构类型名（以机构通名结尾）。"""
    if len(word) < 2:
        return False
    return word.endswith(("局", "院", "所", "厅", "部", "队", "委", "中心",
                          "办公室", "管理处", "管理局", "委员会", "指挥部",
                          "检察部", "检察室", "审判庭", "法庭", "监狱"))


def _number_anchor(orig):
    """从「锚点词 + 号码」里提取锚点词。

    「警号012345」   → 警号
    「律师执业证号11010120100123456」→ 律师执业证号
    「不动产权证号鄂（2020）…」 → 不动产权证号
    「受案登记表编号2024-0118」→ 受案登记表编号

    只认「以号/编号/号码/证号/代码结尾，且前面至少 2 个汉字」的形态，
    避免把任意含数字的串都当编号。
    """
    s = (orig or "").strip()
    if len(s) < 4:
        return ""
    # 在第一个数字出现的位置切开，前半部分就是锚点
    m = re.match(r"^([\u4e00-\u9fa5]{2,14}?(?:号|编号|号码|证号|代码|证|卡号|账号))", s)
    if m:
        anchor = m.group(1)
        # 锚点本身不能是纯泛称
        if anchor in ("号码", "编号", "号码是", "编号是"):
            return ""
        return anchor
    return ""


def _looks_business(word):
    """看起来是不是公司/商店的经营类别名。

    「商贸公司」「综合超市」「包子铺」「大酒店」「律师事务所」都算。
    判据：以企业/门店通名结尾。
    """
    if not word or len(word) < 2:
        return False
    return word.endswith((
        "公司", "厂", "店", "铺", "馆", "厅", "部", "行", "社", "场",
        "超市", "商场", "市场", "药房", "大药房", "诊所", "医院", "卫生院",
        "事务所", "设计院", "研究院", "学院", "学校", "幼儿园",
        "酒店", "宾馆", "旅馆", "招待所", "民宿", "酒楼", "饭店", "餐厅",
        "加油站", "修理厂", "汽修厂", "物流", "快递", "仓储",
    ))


def _read_map(path):
    """读映射表 CSV，返回 [(原文, 化名)]。"""
    rows = []
    if not path or not os.path.exists(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            rd = csv.reader(f)
            header = next(rd, None)
            for r in rd:
                if len(r) >= 2 and r[0].strip():
                    rows.append((r[0].strip(), r[1].strip()))
    except Exception as e:
        print("  读取映射表失败：%s" % e, file=sys.stderr)
    return rows


def _known(res):
    """把基础库 + 已学库合成"当前已知道的东西"。"""
    import chinese_names as C
    singles = set(C.SINGLE_SURNAMES)
    comps = set(C.COMPOUND_SURNAMES)
    non_names = set(C.NON_NAME_WORDS)
    name_chars = set(C.NAME_CHARS)
    for k in res.get("surnames", {}):
        singles.add(k)
    for k in res.get("compound_surnames", {}):
        comps.add(k)
    for k in res.get("non_names", {}):
        non_names.add(k)
    for k in res.get("name_chars", {}):
        name_chars.add(k)
    return singles, comps, non_names, name_chars


def _add_pending(res, kind, word, meta):
    """把候选放进 pending 区；已达阈值直接转正。"""
    key = "%s|%s" % (kind, word)
    if key in res["rejected"]:
        return None
    bucket = res["pending"].setdefault(key, {
        "kind": kind, "word": word, "次数": 0, "来源": [], "首次": _now(),
    })
    bucket["次数"] += 1
    for s in meta.get("来源", []):
        if s and s not in bucket["来源"]:
            bucket["来源"].append(s)
    if bucket["次数"] >= PROMOTE_AT:
        _promote(res, key, bucket)
        return "promoted"
    return "pending"


def _promote(res, key, item):
    kind, word = item["kind"], item["word"]
    target = {
        "surname": "surnames", "compound": "compound_surnames",
        "name_char": "name_chars", "non_name": "non_names",
        "org_type": "org_types",
        "number_anchor": "number_anchors",
    }.get(kind)
    if not target:
        return
    entry = {"来源": item.get("来源", []), "次数": item.get("次数", 1),
             "确认": False, "时间": _now()}
    if kind == "org_type":
        entry["简写"] = item.get("简写", word)
    res[target][word] = entry
    res["pending"].pop(key, None)


def observe(map_path, text_path, case=""):
    """从一次处理结果里归纳候选规则。"""
    import chinese_names as C

    res = load_learned()
    singles, comps, non_names, name_chars = _known(res)
    rows = _read_map(map_path)
    if not rows:
        print("映射表为空或读不到，跳过学习。")
        return 0

    text = ""
    if text_path and os.path.exists(text_path):
        try:
            with open(text_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            text = ""

    found = {"surname": [], "compound": [], "name_char": [],
             "org_type": [], "number_anchor": [], "skipped": 0}

    for orig, alias in rows:
        if not orig or len(orig) < 2:
            continue

        # ---- 1. 人名：化名形如「X某」→ 反推姓氏 ----
        if _ALIAS_PAT.match(alias):
            # 复姓判断（化名两字姓 + 某）
            m2 = re.match(r"^([\u4e00-\u9fa5]{2})某\d*$", alias)
            m1 = re.match(r"^([\u4e00-\u9fa5])某\d*$", alias)
            if m2:
                sur = m2.group(1)
                if sur not in comps:
                    found["compound"].append(sur)
            elif m1:
                sur = m1.group(1)
                # 名字部分
                given = orig[len(sur):] if orig.startswith(sur) else orig[1:]
                # 单字姓氏判定：真名首字应等于化名姓氏字
                if orig[0] == sur:
                    if sur not in singles:
                        # 验证：不能是排除词的首字、不能是常见虚词
                        if orig not in non_names and sur not in "的了在是我你他她它和与及":
                            found["surname"].append(sur)
                    for ch in given:
                        if ch not in name_chars and "\u4e00" <= ch <= "\u9fa5":
                            found["name_char"].append(ch)
            continue

        # ---- 2. 机构：从化名反推机构类型 ----
        # 化名的格式固定是「层级字 + 机构类型」（区城管局、公安分局、市中级人民法院），
        # 剥离开头的层级字剩下的就是机构类型。这比从原文猜后缀准得多：
        # 原文「洪山区城管局」用后缀表只能匹配到「分局」这种通用词，
        # 而化名「区城管局」直接给出「城管局」。
        plain = _strip_level(alias)
        if plain and plain != alias and _looks_org(plain) and plain in orig:
            found["org_type"].append({"word": plain, "简写": plain})
            continue
        # 退化：化名原样就是机构名（派出所、看守所这类没有层级前缀的）
        if plain and _looks_org(plain) and plain in orig and plain not in ("分局", "大队"):
            found["org_type"].append({"word": plain, "简写": plain})
            continue

        # ---- 2.5 公司 / 商店：化名是经营类别（商贸公司/综合超市/包子铺）----
        # 用户要求「xxx 超市也会泄露信息，其他同上规则」。
        # 判据：化名以企业通名结尾，且不等于原文（说明字号已被剥掉）。
        if _looks_business(plain) and plain != orig and plain not in _ORG_SUFFIX:
            found["org_type"].append({"word": plain, "简写": plain})
            continue

        # ---- 3. 编号类：观察哪些「锚点词 + 号码」被脱掉了 ----
        # 用户要求「警号、车牌号、律师证、各种文书编号也得脱敏，同理可得，继续展开，类比学习」。
        # 做法：从映射表原文里提取「XX号：值」的锚点词，学进锚点词库；
        # 下次遇到同类「新锚点 + 号码」就能自动识别，不用等我们硬编码规则。
        # 例如学到「警号」，以后「警号 123456」「警号：123456」都能抓住。
        num_anchor = _number_anchor(orig)
        if num_anchor and re.search(r"\d", orig):
            found["number_anchor"].append(num_anchor)
            continue

        # 兜底：按已知后缀匹配
        for suf in _ORG_SUFFIX:
            if suf in orig and suf in alias:
                found["org_type"].append({"word": suf, "简写": suf})
                break

    # ---- 入库 ----
    n_new = 0
    for sur in found["surname"]:
        r = _add_pending(res, "surname", sur, {"来源": [case or os.path.basename(map_path or "")]})
        n_new += (r == "promoted")
    for sur in found["compound"]:
        r = _add_pending(res, "compound", sur, {"来源": [case or os.path.basename(map_path or "")]})
        n_new += (r == "promoted")
    for ch in found["name_char"]:
        r = _add_pending(res, "name_char", ch, {"来源": [case or os.path.basename(map_path or "")]})
        n_new += (r == "promoted")
    for it in found["org_type"]:
        r = _add_pending(res, "org_type", it["word"],
                         {"来源": [case or os.path.basename(map_path or "")],
                          "简写": it["简写"]})
        n_new += (r == "promoted")
    for anc in found["number_anchor"]:
        r = _add_pending(res, "number_anchor", anc,
                         {"来源": [case or os.path.basename(map_path or "")]})
        n_new += (r == "promoted")

    res["log"].append({
        "时间": _now(), "案件": case, "映射条数": len(rows),
        "候选": {k: len(v) for k, v in found.items() if isinstance(v, list)},
    })
    res["log"] = res["log"][-200:]
    save_learned(res)

    print("观察完成（%d 条映射）" % len(rows))
    print("  新姓氏候选 %d 个、复姓 %d 个、名字用字 %d 个、机构类型 %d 个、编号锚点 %d 个"
          % (len(found["surname"]), len(found["compound"]),
             len(found["name_char"]), len(found["org_type"]),
             len(found["number_anchor"])))
    if found["number_anchor"]:
        print("  编号锚点：%s" % " ".join(found["number_anchor"][:10]))
    if found["surname"]:
        print("  新姓氏：%s" % " ".join(found["surname"][:20]))
    if found["compound"]:
        print("  新复姓：%s" % " ".join(found["compound"][:10]))
    if found["org_type"]:
        print("  机构类型：%s" % " ".join(x["word"] for x in found["org_type"][:10]))
    if n_new:
        print("  → %d 项已达阈值自动转正，下次脱敏即生效" % n_new)
    return 0


# ============================================================
# 二、审核：看候选、确认、否决
# ============================================================
KIND_LABEL = {"surname": "姓氏", "compound": "复姓", "name_char": "名字用字",
              "non_name": "排除词", "org_type": "机构类型"}


def review():
    res = load_learned()
    pend = res.get("pending", {})
    if not pend:
        print("没有待审候选。")
    else:
        print("待审候选 %d 条（出现 %d 次自动转正）：\n" % (len(pend), PROMOTE_AT))
        by_kind = {}
        for key, it in pend.items():
            by_kind.setdefault(it["kind"], []).append(it)
        for kind, items in by_kind.items():
            print("【%s】%d 条" % (KIND_LABEL.get(kind, kind), len(items)))
            for it in items[:40]:
                print("   %-6s 出现 %d 次  来源：%s"
                      % (it["word"], it["次数"], "、".join(it.get("来源", [])[:2])))
            if len(items) > 40:
                print("   …还有 %d 条" % (len(items) - 40))
            print()

    print("=" * 56)
    print("已生效规则：")
    for k, label in (("surnames", "姓氏"), ("compound_surnames", "复姓"),
                     ("name_chars", "名字用字"), ("non_names", "排除词"),
                     ("org_types", "机构类型")):
        n = len(res.get(k, {}))
        print("   %-8s %d 条" % (label, n))
    rej = len(res.get("rejected", {}))
    if rej:
        print("   已否决   %d 条（不会再学）" % rej)
    if res.get("log"):
        last = res["log"][-1]
        print("\n最近一次观察：%s ｜ 案件 %s ｜ 映射 %s 条"
              % (last.get("时间"), last.get("案件") or "（未标）", last.get("映射条数")))
    return 0


def _resolve_key(res, word):
    """按词找到 pending 或已生效的键。"""
    for key, it in res.get("pending", {}).items():
        if it["word"] == word:
            return key, it, "pending"
    for bucket, kind in (("surnames", "surname"), ("compound_surnames", "compound"),
                         ("name_chars", "name_char"), ("non_names", "non_name"),
                         ("org_types", "org_type")):
        if word in res.get(bucket, {}):
            return "%s|%s" % (kind, word), {"kind": kind, "word": word}, bucket
    return None, None, None


def confirm(word):
    res = load_learned()
    key, it, where = _resolve_key(res, word)
    if not it:
        print("找不到「%s」，先用 review 看看候选有什么。" % word)
        return 1
    if where == "pending":
        it["次数"] = PROMOTE_AT
        _promote(res, key, it)
        save_learned(res)
        print("已确认「%s」→ 立即生效" % word)
    else:
        res[where][word]["确认"] = True
        save_learned(res)
        print("已标记「%s」为人工确认" % word)
    return 0


def reject(word):
    res = load_learned()
    key, it, where = _resolve_key(res, word)
    if not it:
        print("找不到「%s」" % word)
        return 1
    res["pending"].pop(key, None)
    for bucket in ("surnames", "compound_surnames", "name_chars", "non_names", "org_types"):
        res[bucket].pop(word, None)
    res.setdefault("rejected", {})["%s|%s" % (it.get("kind", "?"), word)] = {
        "时间": _now(), "原因": "人工否决"}
    save_learned(res)
    print("已否决「%s」，以后不会再学。" % word)
    return 0


def teach(word, as_kind):
    """直接教一条规则（人工给，不过 pending）。"""
    mapping = {"surname": "surnames", "compound": "compound_surnames",
               "name_char": "name_chars", "non_name": "non_names",
               "org_type": "org_types"}
    bucket = mapping.get(as_kind)
    if not bucket:
        print("as 只能是：surname / compound / name_char / non_name / org_type")
        return 1
    res = load_learned()
    res.setdefault(bucket, {})[word] = {
        "来源": ["人工教授"], "次数": 99, "确认": True, "时间": _now()}
    if as_kind == "org_type":
        res[bucket][word]["简写"] = word
    res.get("pending", {}).pop("%s|%s" % (as_kind, word), None)
    save_learned(res)
    print("已教会：「%s」→ %s（立即生效）" % (word, KIND_LABEL.get(as_kind, as_kind)))
    return 0


def stats():
    res = load_learned()
    print("学习库：", LEARNED)
    print("更新时间：", res.get("updated") or "（还没学过）")
    print()
    import chinese_names as C
    print("%-12s %8s %8s" % ("类别", "基础库", "已学习"))
    print("-" * 32)
    print("%-12s %8d %8d" % ("单姓", len(C.SINGLE_SURNAMES), len(res.get("surnames", {}))))
    print("%-12s %8d %8d" % ("复姓", len(C.COMPOUND_SURNAMES), len(res.get("compound_surnames", {}))))
    print("%-12s %8d %8d" % ("名字用字", len(C.NAME_CHARS), len(res.get("name_chars", {}))))
    print("%-12s %8d %8d" % ("排除词", len(C.NON_NAME_WORDS), len(res.get("non_names", {}))))
    try:
        import org_short as O
        print("%-12s %8d %8d" % ("机构类型", len(O.ORG_TYPES), len(res.get("org_types", {}))))
    except Exception:
        print("%-12s %8s %8d" % ("机构类型", "-", len(res.get("org_types", {}))))
    print()
    print("待审候选：%d 条 ｜ 已否决：%d 条 ｜ 观察记录：%d 次"
          % (len(res.get("pending", {})), len(res.get("rejected", {})),
             len(res.get("log", []))))
    if res.get("pending"):
        print("\n提示：跑 review 看候选，confirm 确认，reject 否决。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="立丰脱敏 · 自适应学习引擎")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("observe", help="从映射表归纳候选规则")
    p.add_argument("--map", required=True)
    p.add_argument("--text", default="")
    p.add_argument("--case", default="")

    sub.add_parser("review", help="查看候选与已生效规则")
    p = sub.add_parser("confirm", help="确认一条候选")
    p.add_argument("word")
    p = sub.add_parser("reject", help="否决一条候选")
    p.add_argument("word")
    p = sub.add_parser("teach", help="直接教一条规则")
    p.add_argument("--word", required=True)
    p.add_argument("--as", dest="as_kind", required=True)
    sub.add_parser("stats", help="学习成果统计")

    args = ap.parse_args()
    if args.cmd == "observe":
        return observe(args.map, args.text, args.case)
    if args.cmd == "review":
        return review()
    if args.cmd == "confirm":
        return confirm(args.word)
    if args.cmd == "reject":
        return reject(args.word)
    if args.cmd == "teach":
        return teach(args.word, args.as_kind)
    if args.cmd == "stats":
        return stats()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
