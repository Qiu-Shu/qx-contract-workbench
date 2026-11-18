# -*- coding: utf-8 -*-
"""导出账本 —— 每次导出一份文件，就在账本里记一条，并把当时的映射表冻结一份。

为什么非要冻结映射表（2026-10-30 实测）：
    脱敏时写的是 `工作区/对照表/{源文件名}_映射表.csv`，**同一源文件跑第二次会被直接覆盖**。
    实测时间戳：映射表 11:44，成品 11:22——成品比映射表旧 22 分钟。
    两次之间若改过规则或词表，占位符可能整个变掉（某公司从 [甲方公司] 变成 [乙方公司]），
    拿新映射表还原旧成品，会把占位符换成**另一家的真名**，而且不报错。

    「还原错了」比「还原不了」危险得多——看着像对的答案，没人会再去核。

所以账本要解决两件事：
    ① 每条记录绑定一份属于自己的映射表副本（几 KB，攒三年也就几 MB）；
    ② 记录本身要长期存在，不能跟着预览目录一起被清。

目录结构：
    ~/Library/Application Support/立丰脱敏/历史/
        账本.json
        20261030-112233-001/映射表.csv
"""
import csv
import json
import os
import shutil
import threading
import time

APP_SUPPORT = os.path.expanduser("~/Library/Application Support/立丰脱敏")
HIST_DIR = os.path.join(APP_SUPPORT, "历史")
LEDGER = os.path.join(HIST_DIR, "账本.json")

_lock = threading.Lock()


def _ensure():
    os.makedirs(HIST_DIR, exist_ok=True)


def _read_ledger():
    if not os.path.exists(LEDGER):
        return {"schema": 1, "entries": []}
    try:
        with open(LEDGER, "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
            raise ValueError("结构不符")
        return d
    except Exception:
        # 坏了就改名留档，别覆盖 —— 里面是还原钥匙的索引
        try:
            bad = "%s.broken-%s" % (LEDGER, time.strftime("%Y%m%d-%H%M%S"))
            shutil.move(LEDGER, bad)
        except Exception:
            pass
        return {"schema": 1, "entries": []}


def _write_ledger(doc):
    _ensure()
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LEDGER)


def _count_rows(csv_path):
    """映射表有多少条对照（去掉表头）。"""
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
        return max(0, len(rows) - 1)
    except Exception:
        return 0


def _new_id():
    # 时间戳 + 毫秒尾数：同一秒内连续导出多个文件也不会撞号
    return time.strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)


def add_entry(task_id, index, source, output_name, output_path,
              count=0, by_category=None, map_csv="", status="preview",
              preview_path="", outbox_path=""):
    """新增一条导出记录，同时冻结映射表副本。返回记录 dict。

    ⚡ 2026-11-07 新增 outbox_path（成品在成品目录里的位置）：

    起因是「预览任务不存在」这个 bug 的第二次排查。原以为账本的
    output_path 就是成品的位置，实测发现**没导出过的任务，那个字段记的是
    预览任务自己的目录**（…/预览/<task>/output/xxx.docx）。
    预览目录被「清除全部」搬走后，这条路径跟着一起失效 ——
    账本看着有一条记录，实际上什么也指不着，重建预览必然失败。

    所以要单独记一份「成品目录里的位置」：即便预览任务被清，
    只要成品落过盘，就能靠它 + 冻结映射表把预览原样重算出来。
    """
    with _lock:
        doc = _read_ledger()
        entry_id = _new_id()
        snapshot = ""
        map_count = 0
        if map_csv and os.path.exists(map_csv):
            try:
                d = os.path.join(HIST_DIR, entry_id)
                os.makedirs(d, exist_ok=True)
                dst = os.path.join(d, "映射表.csv")
                shutil.copy2(map_csv, dst)
                snapshot = dst
                map_count = _count_rows(dst)
            except Exception:
                snapshot = ""
                map_count = 0

        entry = {
            "id": entry_id,
            "task_id": task_id or "",
            "index": index,
            "source": source or "",
            "output_name": output_name or "",
            "output_path": output_path or "",
            "preview_path": preview_path or "",
            "outbox_path": outbox_path or "",
            "count": int(count or 0),
            "by_category": by_category or {},
            "map_snapshot": snapshot,
            "map_count": map_count,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "exported_at": "",
            "status": status,
            "restore_path": "",
            "restored_at": "",
        }
        doc["entries"].append(entry)
        # 永久保留，不自动清理（2026-10-30 用户确认）：
        # 映射表快照一份几 KB，攒十年也就几十 MB；
        # 相比之下「三年后想复原一份旧件、发现记录没了」才是真麻烦。
        _write_ledger(doc)
        return entry


def _drop_dir(entry_id):
    if not entry_id:
        return
    try:
        shutil.rmtree(os.path.join(HIST_DIR, entry_id), ignore_errors=True)
    except Exception:
        pass


def update_entry(entry_id, **fields):
    with _lock:
        doc = _read_ledger()
        for e in doc["entries"]:
            if e.get("id") == entry_id:
                e.update(fields)
                _write_ledger(doc)
                return e
    return None


def update_by_task(task_id, output_name, **fields):
    """导出时按「任务 + 成品名」回填，不依赖前端传 entry_id。"""
    with _lock:
        doc = _read_ledger()
        hit = None
        for e in doc["entries"]:
            if e.get("task_id") == task_id and e.get("output_name") == output_name:
                e.update(fields)
                hit = e
        if hit:
            _write_ledger(doc)
        return hit


def get_entry(entry_id):
    doc = _read_ledger()
    for e in doc["entries"]:
        if e.get("id") == entry_id:
            return e
    return None


def list_entries(limit=50):
    doc = _read_ledger()
    items = list(doc["entries"])
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items[:limit] if limit else items


def resolve_input(entry):
    """复原要读哪份文件：优先成品目录里那份，其次任务临时副本。

    用户可能导出后又改过成品，改过的版本才是他真正想还原的。
    """
    for k in ("output_path", "preview_path"):
        p = (entry or {}).get(k) or ""
        if p and os.path.exists(p):
            return p
    return ""


def resolve_map(entry):
    p = (entry or {}).get("map_snapshot") or ""
    return p if p and os.path.exists(p) else ""


def stats():
    doc = _read_ledger()
    n = len(doc["entries"])
    exp = sum(1 for e in doc["entries"] if e.get("status") in ("exported", "restored"))
    return {"total": n, "exported": exp}
