#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不合格件台账 —— 被闸门拦下的成品，从这里开始有下文。

为什么要有这个模块（2026-10-31）：
    原来的做法是「闸门判不合格 → 把成品挪进 不合格/ → 打印一行字 → 完」。
    这条路径有三个洞：
      1. 原因只在控制台滚过去，刷新页面就没了，用户事后完全不知道为什么被拦；
      2. 界面里根本看不到这份文件（它既不在成品列表，也不在失败列表）；
      3. 原件留在待处理区，下一批开始时被整体清空——想重脱都没原件了。
    结果就是「不合格」变成一个只进不出的黑洞：文件躺在那儿，没人知道该干什么。

    本模块负责把黑洞变成闭环：
      落盘留证（记录 + 人读原因 + 原件留底）→ 分诊（能不能救、怎么救）
      → 重脱 / 忽略 → 有终局（已重脱 / 已放弃），不再无限堆积。

目录结构（都在成品目录下的「不合格」里）：
    不合格/
      xxx_已脱敏.docx          成品本体（保留，便于人工比对）
      xxx_原因.txt             人读的拦截说明
      原件/xxx.docx            原件留底（重脱的原料）
      历史/<时间戳>/           同一文件被再次拦截时，旧的那份挪到这里
      _拦截记录.jsonl          机读台账，只追加不改写

台账设计：只追加事件，读的时候折叠成当前状态。
    这样做的好处是「谁在什么时候重脱过、结果如何」永久可查（对齐账本永久保留的规矩），
    也不会因为并发写入把别人的记录覆盖掉。
"""
import json
import os
import shutil
import time

BAD = "不合格"
ORIG = "原件"
HIST = "历史"
LOG = "_拦截记录.jsonl"

FIX_LABEL = {
    "auto": "可直接重脱（判据误杀，重跑一次即可）",
    "rule": "需先改规则或词表，再重脱",
    "engine": "重脱无效，须改引擎或人工核对",
}


def dirs(outdir, bad_dir=None):
    """bad_dir 可直接指定「不合格」目录。

    为什么需要：预览模式下成品目录是 `预览/{任务}/output`（藏在 App Support 里，
    用户根本翻不到），拦截件如果跟着落在那儿，等于凭空消失。
    所以服务端会显式把 bad_dir 指到文稿的「立丰脱敏成品/不合格」，
    不管这次跑的是预览还是批量，不合格件都落在同一个用户找得到的地方。
    """
    bad = bad_dir or os.path.join(outdir, BAD)
    return {
        "bad": bad,
        "orig": os.path.join(bad, ORIG),
        "hist": os.path.join(bad, HIST),
        "log": os.path.join(bad, LOG),
    }


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _rid():
    return time.strftime("%Y%m%d-%H%M%S") + "-%03d" % int((time.time() % 1) * 1000)


def _append(d, rec):
    os.makedirs(d["bad"], exist_ok=True)
    with open(d["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def overall_fix(issues):
    """整份文件该怎么救：有一条 engine 级问题，重脱就没意义。"""
    fixes = [i.get("fix", "rule") for i in (issues or [])]
    if "engine" in fixes:
        return "engine"
    if "rule" in fixes:
        return "rule"
    return "auto"


def record_reject(outdir, out_path, src_path, issues, why="", bad_dir=None,
                  keep_in_place=False):
    """成品被闸门拦下时调用：留原件、写记录、写人读原因。

    keep_in_place=True（2026-11-05 用户死命令）：成品**不移动**，与合格件同目录，
    只在台账留一条质检记录、界面标红提示。用户原话：「合格和不合格都丢到一个路径，
    只是不合格标红提示一下就行……分开搞麻烦了，意义不大」。

    返回记录 dict。任何一步失败都不抛——拦截本身不能让整个批次崩掉。
    """
    d = dirs(outdir, bad_dir)
    for k in ("bad", "orig", "hist"):
        try:
            os.makedirs(d[k], exist_ok=True)
        except Exception:
            pass

    out_name = os.path.basename(out_path)
    src_name = os.path.basename(src_path) if src_path else ""
    stem = os.path.splitext(src_name)[0] if src_name else os.path.splitext(out_name)[0]

    # 1. 成品去向：默认挪进留底目录；keep_in_place=True 时原地不动，
    #    与合格件同目录，界面靠台账标红提示（2026-11-05 用户死命令）。
    target = os.path.join(d["bad"], out_name)
    if not keep_in_place:
        if os.path.exists(target):
            try:
                sub = os.path.join(d["hist"], time.strftime("%Y%m%d-%H%M%S"))
                os.makedirs(sub, exist_ok=True)
                shutil.move(target, os.path.join(sub, out_name))
            except Exception:
                pass
        try:
            if os.path.exists(out_path):
                shutil.move(out_path, target)
        except Exception:
            pass

    # 2. 原件留底：这是「还能不能重脱」的命门。
    #    不复制的话，原件会在下一批清空待处理区时被删，用户想重脱都无从下手。
    orig_rel = ""
    if src_path and os.path.exists(src_path):
        try:
            dst = os.path.join(d["orig"], src_name)
            shutil.copy2(src_path, dst)
            orig_rel = os.path.join(ORIG, src_name)
        except Exception:
            orig_rel = ""

    rec = {
        "event": "reject",
        "id": _rid(),
        "ts": _now(),
        "source": src_name,
        "output": out_name,
        "output_rel": out_name,
        "orig_rel": orig_rel,
        "stem": stem,
        "issues": issues or [],
        "fix": overall_fix(issues),
        "why": (why or "")[:400],
        "attempts": 0,
        "status": "pending",
    }
    _append(d, rec)

    # 3. 人读原因：给不看日志的人（也包括三天后的自己）一个交代
    try:
        lines = ["文件：%s" % out_name,
                 "原件：%s" % (src_name or "（未记录）"),
                 "时间：%s" % rec["ts"],
                 "结论：未通过质量闸门，成品未进入成品区。",
                 "处置：%s" % FIX_LABEL.get(rec["fix"], ""),
                 "", "具体问题："]
        for i, it in enumerate(rec["issues"], 1):
            lines.append("  %d. [%s] %s" % (i, it.get("code", ""), it.get("text", "")))
        if rec["fix"] == "engine":
            lines += ["", "说明：这类问题重跑结果不会改变，要么修引擎，要么人工核对原件后另存一份可用版本。"]
        elif rec["fix"] == "rule":
            lines += ["", "说明：先到「规则设置」里调整相关字段（或换用本案词表），再点「重新脱敏」。"]
        else:
            lines += ["", "说明：判据误伤，直接点「重新脱敏」通常就能通过。"]
        with open(os.path.join(d["bad"], "%s_原因.txt" % stem), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass

    return rec


def load_records(outdir, bad_dir=None):
    """读台账并折叠成当前状态。返回按时间倒序的列表。"""
    d = dirs(outdir, bad_dir)
    if not os.path.exists(d["log"]):
        return []
    cur = {}
    order = []
    try:
        with open(d["log"], encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                rid = e.get("id")
                if not rid:
                    continue
                if e.get("event") == "reject":
                    e["history"] = []
                    e["status"] = "pending"
                    cur[rid] = e
                    order.append(rid)
                elif rid in cur:
                    r = cur[rid]
                    if e.get("event") == "retry":
                        r["attempts"] = r.get("attempts", 0) + 1
                        r["last_try"] = e.get("ts", "")
                        r["status"] = "retried" if e.get("ok") else "pending"
                        if not e.get("ok"):
                            r["last_fail"] = e.get("note", "")
                    elif e.get("event") == "ignore":
                        r["status"] = "ignored"
                        r["ignored_at"] = e.get("ts", "")
                    elif e.get("event") == "accept":
                        # 人工改完放行：这份从此算合格，界面里不再出现在"不合格"
                        r["status"] = "accepted"
                        r["accepted_at"] = e.get("ts", "")
                    elif e.get("event") == "undo":
                        # 忽略了又想处理：退回待办，不算一次重脱尝试
                        r["status"] = "pending"
                        r.pop("ignored_at", None)
                    r.setdefault("history", []).append(e)
    except Exception:
        return []

    items = [cur[i] for i in order]
    # 同一原件只留最新一条：老记录进历史，界面别刷屏
    latest = {}
    for it in items:
        latest[it.get("source") or it.get("id")] = it
    res = list(latest.values())
    # 原件是否还在，直接决定「重新脱敏」能不能点
    for it in res:
        it["has_orig"] = bool(it.get("orig_rel")) and os.path.exists(
            os.path.join(d["bad"], it["orig_rel"]))
        it["fix_label"] = FIX_LABEL.get(it.get("fix"), "")
        # 自愈判定：成品区里已经有同名且比拦截时间更新的文件，说明后来重脱成功了，
        # 不用再让用户手动点一次「我处理完了」——状态自己走。
        try:
            op = os.path.join(outdir, it.get("output") or "")
            if it.get("status") in ("pending", "ignored") and it.get("output") and os.path.exists(op):
                ts = time.mktime(time.strptime(it.get("ts", ""), "%Y-%m-%d %H:%M:%S"))
                if os.path.getmtime(op) >= ts:
                    it["status"] = "retried"
                    it["auto_retried"] = True
        except Exception:
            pass
    res.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return res


def update(outdir, rid, event, bad_dir=None, **kw):
    rec = {"event": event, "id": rid, "ts": _now()}
    rec.update(kw)
    _append(dirs(outdir, bad_dir), rec)
    return rec


if __name__ == "__main__":
    import sys
    box = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Documents/立丰脱敏成品")
    for it in load_records(box):
        print("%s  %-10s %-28s %s" % (it["ts"], it["status"],
                                      it.get("output", ""), it.get("fix_label", "")))
