# -*- coding: utf-8 -*-
"""
脱敏规则配置存储层 —— 把硬编码的正则规则变成可勾选、可增改的配置。

设计三原则：

1. **配置与数据分离**：配置文件单独一份，删掉它等于恢复出厂设置，
   不碰记忆库、映射表、词表。用户改坏规则不该丢案件数据。

2. **逐条隔离**：一条正则写错只跳过它自己，绝不能让整个脱敏功能瘫掉。
   编译失败要记下是哪一条、错在哪，界面上能看见。

3. **顺序即优先级**：内置规则的 order 沿用源码原始顺序（锚点规则天然在前），
   自定义规则默认排在最后（order 从 10000 起）。
   理由是一条真事故：施工许可证号 000000000000000000 是 18 位，
   通用身份证规则若先跑会把它吃成「[湖北·2026年·身份证]」——
   占位符标错比不脱更误导。

配置文件位置：~/Library/Application Support/立丰脱敏/脱敏规则.json
"""
import os
import json
import time
import shutil

HOME = os.path.expanduser("~")
APP_SUPPORT = os.path.join(HOME, "Library", "Application Support", "立丰脱敏")
CONFIG_PATH = os.path.join(APP_SUPPORT, "脱敏规则.json")

SCHEMA_VERSION = 1

# 分组定义（顺序即界面显示顺序）
GROUPS = [
    ("id", "证件证照", ["身份证号", "护照号", "港澳通行证号", "台湾通行证号", "军官证号",
                     "驾驶证号", "行驶证号", "社保号", "医保卡号", "公积金号",
                     "学号工号", "警号", "统一社会信用代码", "组织机构代码", "车牌号"]),
    ("credential", "执业与资质", ["律师执业证号", "法律职业资格证号", "资质证书号", "安全生产许可证号",
                             "施工许可证号", "营业执照号", "税务登记号", "专利号",
                             "商标注册号", "不动产权证号"]),
    ("contact", "联系方式", ["手机号", "固定电话", "客服电话", "电子邮箱", "社交账号", "网址", "邮编"]),
    ("finance", "金融账号", ["银行卡号", "银行账号", "开户银行", "联行号", "银行流水号",
                          "数字证书号", "平台账号", "发票号", "保函号", "保险单号"]),
    ("contract", "合同与工程", ["合同编号", "运输单据号", "快递单号", "设备序列号", "车辆识别代号",
                             "不动产单元号", "宗地号", "房屋坐落", "软件著作权登记号", "著作权登记号"]),
    ("judicial", "司法办案", ["刑事文号", "检察文号", "公文文号", "文书编号", "刑事案号",
                           "民事案号", "羁押场所", "政法机关", "仲裁机构", "提讯证号",
                           "看守所在押人员编号", "监室编号"]),
    ("entity", "主体与位置", ["人名", "企业名", "学校", "字号", "项目名", "地址", "境外主体"]),
    ("misc", "时间与金额", ["日期", "金额"]),
]

CAT2GROUP = {c: gid for gid, _n, cats in GROUPS for c in cats}
GROUP_NAME = {gid: name for gid, name, _c in GROUPS}

# 结构识别类：靠算法，不靠正则，只允许开关
STRUCTURE_CATS = {
    "人名": "姓名结构识别 + 本地模型识敏",
    "企业名": "企业全称结构识别（行政区+字号+行业+组织形式）",
    # 2026-11-07 用户要求：「学校名也需要脱敏，自动识别里面加入学校」
    "学校": "学校/教育机构结构识别（大学、学院、中学、小学、幼儿园）",
    "字号": "字号提取（企业名中的识别性词）",
    "项目名": "工程/项目名称结构识别",
    "地址": "地址片段结构识别（只脱区县以下街道门牌村组）",
}

# 禁用时需要二次确认的高风险项
HIGH_RISK = {"身份证号", "护照号", "手机号", "银行卡号", "银行账号", "统一社会信用代码",
             "人名", "企业名", "学校", "地址", "车牌号"}

# 默认关闭的（按脱敏惯例保留，需按需开启）
DEFAULT_OFF = {"日期", "金额"}

# 示例文本（界面提示用）
SAMPLES = {
    "身份证号": "000000000000000000", "手机号": "138 1234 5678", "固定电话": "027-87654321",
    "银行卡号": "0000000000000000000", "统一社会信用代码": "000000000000000000",
    "车牌号": "某A00000", "企业名": "某某公司", "人名": "张三",
    "学校": "某某大学附属中学",
    "地址": "某市某区某路000号", "合同编号": "0000-0000-0000",
    "开户银行": "中国银行某支行", "电子邮箱": "a@b.com", "网址": "https://example.com/about",
    "刑事案号": "（0000）0000刑初000号", "民事案号": "（0000）0000民初0000号",
    "施工许可证号": "000000000000000000", "日期": "2026年10月30日", "金额": "￥000,000元",
    "护照号": "00000000", "律师执业证号": "00000000000000000",
}


def _ensure_dir():
    os.makedirs(APP_SUPPORT, exist_ok=True)


def config_exists():
    return os.path.exists(CONFIG_PATH)


# 进程内缓存：Redactor 每处理一段文本都要问「这个类别开着吗」，
# 一次文档几千段就是几万次读盘。用 mtime 判断是否失效，改配置后自动重读。
_cache = {"doc": None, "mtime": None}

# 内置规则快照：恢复默认时用它立即重建，不必等下次启动或回头去 import 引擎
_builtin_snapshot = ()


def load():
    """读配置。不存在或损坏返回 None（调用方决定是否用默认值）。"""
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        mt = os.path.getmtime(CONFIG_PATH)
        if _cache["doc"] is not None and _cache["mtime"] == mt:
            return _cache["doc"]
    except Exception:
        mt = None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or not isinstance(d.get("rules"), list):
            raise ValueError("结构不符")
        # 老配置补齐后来新增的内置类别（学校等），否则界面看不见、也关不掉。
        # migrate_builtin 内部按 `have` 判重，没有缺失就什么都不做，零成本。
        d, _added = migrate_builtin(d)
        if _added:
            try:
                mt = os.path.getmtime(CONFIG_PATH)
            except Exception:
                mt = None
        _cache["doc"] = d
        _cache["mtime"] = mt
        return d
    except Exception:
        # 损坏就改名留档，别直接覆盖用户可能想抢救的内容
        try:
            bad = "%s.broken-%s" % (CONFIG_PATH, time.strftime("%Y%m%d-%H%M%S"))
            shutil.move(CONFIG_PATH, bad)
        except Exception:
            pass
        _cache["doc"] = None
        _cache["mtime"] = None
        return None


def save(doc):
    """原子写：先写临时文件再替换，避免写一半断电留下半截 JSON。"""
    _ensure_dir()
    doc["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)
    # 写完要让缓存失效，否则同一进程里读到的还是旧值
    _cache["doc"] = doc
    try:
        _cache["mtime"] = os.path.getmtime(CONFIG_PATH)
    except Exception:
        _cache["mtime"] = None


def ensure_config(builtin_rules):
    """首次运行：用内置规则生成初始配置。

    builtin_rules：[(类别, 已编译正则), ...]，由 desensitize 传入。
    一类可挂多条正则，这里聚合到 patterns 数组。
    """
    global _builtin_snapshot
    _builtin_snapshot = tuple(builtin_rules)
    if config_exists():
        return load()
    order_cats, pats = [], {}
    for cat, rx in builtin_rules:
        if cat in STRUCTURE_CATS:
            continue
        if cat not in pats:
            pats[cat] = []
            order_cats.append(cat)
        p = getattr(rx, "pattern", None)
        if p and p not in pats[cat]:
            pats[cat].append(p)

    rules = []
    for i, cat in enumerate(order_cats, 1):
        off = cat in DEFAULT_OFF
        rules.append({
            "id": cat, "category": cat, "group": CAT2GROUP.get(cat, "misc"),
            "engine": "regex", "patterns": pats[cat],
            "enabled": not off, "builtin": True, "order": i * 10,
            "risk": "high" if cat in HIGH_RISK else ("low" if off else "medium"),
            "sample": SAMPLES.get(cat, ""),
            "note": "默认关闭：脱敏惯例保留日期与金额" if off else "",
        })
    base = len(rules)
    for j, (cat, desc) in enumerate(STRUCTURE_CATS.items(), 1):
        rules.append({
            "id": cat, "category": cat, "group": "entity", "engine": "structure",
            "patterns": [], "enabled": True, "builtin": True, "order": (base + j) * 10,
            "risk": "high" if cat in HIGH_RISK else "medium",
            "sample": SAMPLES.get(cat, ""), "note": desc,
        })

    doc = {
        "schema_version": SCHEMA_VERSION,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "内置规则初始配置",
        "groups": [{"id": g, "name": n, "order": k + 1} for k, (g, n, _c) in enumerate(GROUPS)],
        "rules": rules,
    }
    save(doc)
    return doc


def _compile(patterns):
    """编译一组正则，坏的那条跳过并记录。返回 (编译好的列表, 问题列表)。"""
    import re as _re
    ok, bad = [], []
    for p in (patterns or []):
        if not isinstance(p, str) or not p.strip():
            continue
        try:
            ok.append(_re.compile(p))
        except Exception as e:
            bad.append({"pattern": p[:120], "error": str(e)[:160]})
    return ok, bad


def filter_rules(builtin_rules):
    """按配置过滤内置规则，并把自定义规则补齐。

    返回 [(类别, 编译好的正则), ...]，按 order 升序 —— 顺序即优先级。

    任何异常都返回原始内置规则：宁可多脱，不能让脱敏功能整个不可用。
    """
    doc = load()
    if not doc:
        return list(builtin_rules)

    try:
        ids = _config_ids(doc)
        enabled_ids = set()
        custom = []
        for r in doc.get("rules", []):
            rid = r.get("id") or r.get("category")
            if not rid:
                continue
            if r.get("enabled", True):
                enabled_ids.add(rid)
            if not r.get("builtin", False):
                custom.append(r)

        out = []
        # 内置：顺序完全沿用源码原序，不重排（重排会破坏锚点优先）
        for cat, rx in builtin_rules:
            if cat in STRUCTURE_CATS:
                continue
            # 配置里明确禁用才剔除；配置里没有的（新版新增规则）默认启用
            if cat in ids and cat not in enabled_ids:
                continue
            out.append((cat, rx))

        # 自定义：排在最后，按 order
        custom.sort(key=lambda x: x.get("order", 10000))
        for r in custom:
            cat = r.get("category") or r.get("id")
            if r.get("id") not in enabled_ids:
                continue
            compiled, bad = _compile(r.get("patterns"))
            if bad:
                # 记录坏规则，不阻断
                _log_bad(cat, bad)
            for rx in compiled:
                out.append((cat, rx))
        return out
    except Exception:
        return list(builtin_rules)


def _config_ids(doc):
    """配置里出现过的 id 集合。用于判断某内置类别是否已被配置接管。

    为什么需要：老版本升级时配置里可能没有新增的内置类别，
    这时不能因为"配置里没有"就把它当成禁用 —— 新规则应当默认启用。
    """
    s = set()
    for r in doc.get("rules", []):
        s.add(r.get("id") or r.get("category"))
    return s


def migrate_builtin(doc):
    """给**存量配置**补齐后来新增的内置规则，返回 (doc, 新增条数)。

    ⚡ 为什么必须有这一步（2026-11-07 学校名踩的坑）：
    用户机器上 `脱敏规则.json` 是几个月前首次运行时生成的快照，
    后来代码里新增了「学校」这个结构识别类别，但磁盘那份 rules 数组里
    没有它。后果是 twofold：
      1. `list_for_ui()` 遍历的是磁盘 rules，面板上压根没有「学校」开关，
         用户看不到、也关不掉 —— 他会以为「你没加进来」；
      2. `set_enabled("学校", False)` 命中 0 项，开关点了没反应。
    而 `is_enabled()` 对查不到的类别返回 True，所以脱敏其实一直是生效的，
    只有界面是瞎的。这种「功能对、界面空」最难被用户理解。
    """
    if not doc:
        return doc, 0
    have = _config_ids(doc)
    max_order = 0
    for r in doc.get("rules", []):
        try:
            max_order = max(max_order, int(r.get("order") or 0))
        except Exception:
            pass
    added = 0
    # 1) 结构识别类（学校、字号、项目名、地址……）
    for cat, desc in STRUCTURE_CATS.items():
        if cat in have:
            continue
        added += 1
        max_order += 10
        doc["rules"].append({
            "id": cat, "category": cat, "group": CAT2GROUP.get(cat, "entity"),
            "engine": "structure", "patterns": [], "enabled": True,
            "builtin": True, "order": max_order,
            "risk": "high" if cat in HIGH_RISK else "medium",
            "sample": SAMPLES.get(cat, ""), "note": desc,
        })
    # 2) 正则类（后续新增的证件号、案号之类）
    #    patterns 从 _builtin_snapshot 里取真身，别留空数组：
    #    active_rules() 对内置类不看配置 patterns（直接用源码 rx），功能不受影响，
    #    但界面上会显示一条「没有任何正则」的规则，用户点了测试发现测不出东西。
    snap_pats = {}
    for _c, _rx in (_builtin_snapshot or ()):
        _p = getattr(_rx, "pattern", None)
        if _c and _p:
            snap_pats.setdefault(_c, [])
            if _p not in snap_pats[_c]:
                snap_pats[_c].append(_p)
    for gid, _gname, cats in GROUPS:
        for cat in cats:
            if cat in have or cat in STRUCTURE_CATS:
                continue
            added += 1
            max_order += 10
            off = cat in DEFAULT_OFF
            doc["rules"].append({
                "id": cat, "category": cat, "group": gid,
                "engine": "regex", "patterns": snap_pats.get(cat, []),
                "enabled": not off, "builtin": True, "order": max_order,
                "risk": "high" if cat in HIGH_RISK else ("low" if off else "medium"),
                "sample": SAMPLES.get(cat, ""),
                "note": "默认关闭：脱敏惯例保留日期与金额" if off else "",
            })
    if added:
        doc["schema_version"] = SCHEMA_VERSION
        save(doc)
    return doc, added


def _log_bad(cat, bad):
    try:
        _ensure_dir()
        p = os.path.join(APP_SUPPORT, "规则错误.log")
        with open(p, "a", encoding="utf-8") as f:
            f.write("[%s] %s: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), cat,
                                       json.dumps(bad, ensure_ascii=False)))
    except Exception:
        pass


def is_enabled(cat):
    """某类别是否启用。配置不存在时返回 True（保持原行为）。"""
    doc = load()
    if not doc:
        return True
    for r in doc.get("rules", []):
        if (r.get("id") or r.get("category")) == cat:
            return bool(r.get("enabled", True))
    return True


def enabled_map():
    """一次性取出全部开关，供 Redactor 在构造时缓存。

    为什么不在 Redactor 里反复调 is_enabled：一份文档几千段，
    每段都要问「人名开着吗、企业名开着吗」，逐次查表会把性能拖垮。
    """
    doc = load()
    if not doc:
        return {}
    m = {}
    for r in doc.get("rules", []):
        k = r.get("id") or r.get("category")
        if k:
            m[k] = bool(r.get("enabled", True))
    return m


def set_enabled(target, enabled):
    """切换单个类别或整组。target 可以是类别名，也可以是组 id。"""
    doc = load()
    if not doc:
        return False, "配置不存在"
    hit = 0
    for r in doc.get("rules", []):
        if r.get("id") == target or r.get("category") == target or r.get("group") == target:
            r["enabled"] = bool(enabled)
            hit += 1
    if hit:
        save(doc)
    return bool(hit), ("已更新 %d 项" % hit if hit else "未找到目标")


def upsert_rule(rule):
    """新增或修改一条自定义规则。

    rule: {id?, category, group?, patterns[], enabled?, sample?, note?}
    内置规则（builtin=true）不允许改内容，只能改 enabled。
    """
    doc = load()
    if not doc:
        return False, "配置不存在"
    cat = (rule.get("category") or "").strip()
    if not cat:
        return False, "类别名不能为空"
    pats = rule.get("patterns") or []
    if not isinstance(pats, list) or not pats:
        return False, "至少要有一条正则"
    # 先验编译
    compiled, bad = _compile(pats)
    if bad:
        return False, "正则语法错误：%s" % bad[0]["error"]
    if not compiled:
        return False, "正则为空"

    rid = rule.get("id") or ("custom-" + cat)
    for r in doc["rules"]:
        if r.get("id") == rid:
            if r.get("builtin"):
                return False, "内置规则不可修改内容（可停用）"
            r.update({"category": cat, "patterns": pats,
                      "enabled": bool(rule.get("enabled", True)),
                      "sample": rule.get("sample", ""), "note": rule.get("note", "")})
            save(doc)
            return True, "已更新"
    max_order = max([r.get("order", 0) for r in doc["rules"]] + [10000])
    doc["rules"].append({
        "id": rid, "category": cat, "group": rule.get("group") or CAT2GROUP.get(cat, "misc"),
        "engine": "regex", "patterns": pats,
        "enabled": bool(rule.get("enabled", True)), "builtin": False,
        "order": max_order + 10,
        "risk": rule.get("risk") or ("high" if cat in HIGH_RISK else "medium"),
        "sample": rule.get("sample", ""), "note": rule.get("note", ""),
    })
    save(doc)
    return True, "已新增"


def delete_rule(rid):
    doc = load()
    if not doc:
        return False, "配置不存在"
    for r in doc["rules"]:
        if r.get("id") == rid:
            if r.get("builtin"):
                return False, "内置规则不可删除（可停用）"
            doc["rules"].remove(r)
            save(doc)
            return True, "已删除"
    return False, "未找到该规则"


def reset_to_builtin():
    """恢复出厂：备份现有配置后删除，下次读取时重新按内置规则生成。

    必须同时清缓存：server 是长驻进程，不清的话恢复默认之后
    接口返回的仍是旧配置，用户会以为按钮没生效。
    """
    try:
        if os.path.exists(CONFIG_PATH):
            bak = "%s.bak-%s" % (CONFIG_PATH, time.strftime("%Y%m%d-%H%M%S"))
            shutil.move(CONFIG_PATH, bak)
        _cache["doc"] = None
        _cache["mtime"] = None
        # 立刻用内置快照重建，别让用户看到「配置不存在」的空配置页
        if _builtin_snapshot:
            ensure_config(_builtin_snapshot)
            return True, "已恢复默认（原配置已备份）"
        return True, "已恢复默认（下次启动重新生成）"
    except Exception as e:
        return False, str(e)


def export_config(out_path):
    doc = load()
    if not doc:
        return False, "配置不存在"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        return True, out_path
    except Exception as e:
        return False, str(e)


def import_config(in_path):
    """导入配置。导入的自定义规则保留；内置规则只吸收 enabled 状态。"""
    try:
        with open(in_path, "r", encoding="utf-8") as f:
            new = json.load(f)
        if not isinstance(new, dict) or not isinstance(new.get("rules"), list):
            return False, "文件格式不符"
    except Exception as e:
        return False, "无法读取：%s" % e

    doc = load()
    if not doc:
        return False, "本机配置不存在"
    # 内置只同步启用状态，绝不被外来文件覆盖内容
    in_enabled = {(r.get("id") or r.get("category")): bool(r.get("enabled", True))
                  for r in new["rules"]}
    for r in doc["rules"]:
        k = r.get("id")
        if r.get("builtin") and k in in_enabled:
            r["enabled"] = in_enabled[k]
    # 自定义：整体替换
    doc["rules"] = [r for r in doc["rules"] if r.get("builtin")]
    for r in new["rules"]:
        if r.get("builtin"):
            continue
        r["builtin"] = False
        doc["rules"].append(r)
    save(doc)
    return True, "已导入"


def list_for_ui():
    """给前端用的完整快照（含分组统计）。"""
    doc = load()
    if not doc and _builtin_snapshot:
        doc = ensure_config(_builtin_snapshot)
    if not doc:
        return {"ok": False, "msg": "配置不存在"}
    groups = []
    for gid, gname, cats in GROUPS:
        items = [r for r in doc["rules"] if r.get("group") == gid]
        groups.append({
            "id": gid, "name": gname,
            "total": len(items),
            "enabled": sum(1 for r in items if r.get("enabled", True)),
        })
    return {
        "ok": True,
        "groups": groups,
        "rules": doc["rules"],
        "stats": {
            "total": len(doc["rules"]),
            "enabled": sum(1 for r in doc["rules"] if r.get("enabled", True)),
            "structure": sum(1 for r in doc["rules"] if r.get("engine") == "structure"),
            "custom": sum(1 for r in doc["rules"] if not r.get("builtin")),
        },
    }


def test_pattern(patterns, text, category="敏感项", limit=200):
    """正则测试器：返回命中片段与替换预览。

    为什么必须走 Python 后端：前端 JS 的正则方言与 Python 有差异
    （命名组、\\d 对全角数字的处理、零宽断言支持度都不同），
    前端测通过了真脱敏却不认——那种测试器比没有更误导。
    """
    import re as _re
    if not isinstance(patterns, list):
        patterns = [patterns]
    compiled, bad = _compile(patterns)
    if bad:
        return {"ok": False, "error": bad[0]["error"], "hits": [], "preview": ""}
    if not compiled:
        return {"ok": False, "error": "没有可用的正则", "hits": [], "preview": ""}

    hits = []
    for pi, rx in enumerate(compiled):
        for m in rx.finditer(text or ""):
            hits.append({"match": m.group(0), "start": m.start(), "end": m.end(),
                         "pattern_index": pi})
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    hits.sort(key=lambda x: (x["start"], x["end"]))

    # 替换预览：从后往前替换，避免前面的替换改变后面的索引
    out = text or ""
    for h in sorted(hits, key=lambda x: -x["start"]):
        out = out[:h["start"]] + ("[%s]" % category) + out[h["end"]:]

    return {"ok": True, "error": "", "hits": hits, "preview": out,
            "count": len(hits)}


def export_to_documents():
    """导出配置到文稿目录，文件名带时间戳。返回 (ok, 路径/错误)。"""
    out = os.path.join(os.path.expanduser("~/Documents"),
                       "脱敏规则-导出-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    ok, msg = export_config(out)
    return ok, (out if ok else msg)


def pick_and_import():
    """用系统文件对话框选一份配置导入。返回 (ok, 消息)。"""
    import subprocess
    script = '''
try
	set f to choose file with prompt "选择要导入的脱敏规则配置（json）"
	return POSIX path of f
on error
	return ""
end try
'''
    try:
        r = subprocess.run(["/usr/bin/osascript", "-e", script],
                           capture_output=True, text=True, timeout=300)
        src = (r.stdout or "").strip()
    except Exception:
        src = ""
    if not src:
        return False, "已取消"
    return import_config(src)


def disabled_patterns():
    """返回被禁用字段的正则列表，供「禁用即保护」使用。

    为什么需要它：禁用一个字段，不能允许其它规则冒名顶替。
    实测（2026-10-30）：关掉「身份证号」后，18 位号码被
    「统一社会信用代码」规则 `[0-9A-HJ-NPQRTUWXY]{18}` 接走，
    成品出现「[01·文化·统一代码]」——把身份证标成文化类代码，
    比原样保留更误导。

    做法：把这些字段的命中片段先换成哨兵，正则阶段碰不到，末尾原样还原。
    注意排除日期/金额：它们的「禁用」含义是不参与脱敏，
    但不至于被别的规则吃掉，无需保护（保护反而可能干扰金额识别）。
    """
    doc = load()
    if not doc:
        return []
    out = []
    for r in doc.get("rules", []):
        if r.get("enabled", True):
            continue
        if r.get("engine") == "structure":
            continue
        if r.get("category") in ("日期", "金额"):
            continue
        for p in (r.get("patterns") or []):
            if p and p not in out:
                out.append(p)
    return out
