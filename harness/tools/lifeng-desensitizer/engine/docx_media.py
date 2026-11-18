# -*- coding: utf-8 -*-
"""
docx 内嵌图片脱敏 —— 把 Word 里插入的扫描件/照片也涂黑。

为什么需要：文字脱敏只处理段落和表格，**Word 里插的图片（案卷扫描页、现场照片）
完全不会被处理**，而这些图里往往正是最敏感的内容（身份证、笔录、人脸）。

做法：把 docx 当 zip 拆开 → 逐个 `word/media/*` 图片做 OCR + 涂黑 →
用新字节写回原位置 → 重新打包。文档里图片的引用关系不变，版式不受影响。

用法：
  python3 docx_media.py 文档.docx --terms 敏感词表.txt
  python3 docx_media.py 文档.docx --terms 敏感词表.txt --out 新文档.docx
"""
import os
import sys
import io
import csv
import time
import zipfile
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from image_redact import redact_bytes, find_sensitive  # noqa: E402
from desensitize import load_terms  # noqa: E402

MEDIA_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif")


def redact_docx_media(path, terms, precise=False, out_path=None):
    """处理 docx 内所有图片。返回 (记录列表, 处理的图片数)。

    识别不到敏感内容的图片原样保留，不会二次压缩损失画质。
    """
    out_path = out_path or path
    records = []
    touched = 0
    total = 0
    final = []

    zin = zipfile.ZipFile(path, "r")
    for info in zin.infolist():
        data = zin.read(info.filename)
        name = info.filename
        is_media = (name.startswith("word/media/")
                    and not name.endswith("/")
                    and name.lower().endswith(MEDIA_EXT))
        if is_media:
            total += 1
            try:
                nb, recs = redact_bytes(data, terms, precise)
                if recs:
                    touched += 1
                    for r in recs:
                        r["file"] = name
                        records.append(r)
                    data = nb
            except Exception:
                pass
        final.append((info, data))
    zin.close()

    tmp = out_path + ".tmp"
    zout = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
    for info, data in final:
        zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = info.external_attr
        zout.writestr(zi, data)
    zout.close()
    os.replace(tmp, out_path)

    return records, total, touched


def main():
    ap = argparse.ArgumentParser(description="docx 内嵌图片脱敏（OCR 涂黑）")
    ap.add_argument("input")
    ap.add_argument("--terms", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--map", default="")
    ap.add_argument("--precise", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print("文件不存在：", args.input)
        return 1
    if not args.input.lower().endswith(".docx"):
        print("只支持 .docx")
        return 1

    terms = load_terms(args.terms) if args.terms else []
    outp = args.out or args.input
    records, total, touched = redact_docx_media(args.input, terms, args.precise, outp)

    mapf = args.map
    if mapf:
        with open(mapf, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["图片", "被涂黑的原文", "类别"])
            for r in records:
                w.writerow([r["file"], r["text"], r["category"]])

    print("文档图片总数：%d，涂黑处理：%d 张，涂黑 %d 处" % (total, touched, len(records)))
    if total and not touched:
        print("提示：图片里没识别到词表内的敏感内容。若图中有真名，请确认词表是否覆盖。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
