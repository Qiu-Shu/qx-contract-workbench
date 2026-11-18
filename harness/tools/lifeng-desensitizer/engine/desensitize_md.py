#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md 全库脱敏驱动（2026-10-28 建，配合 legal-desensitize 技能的词表规范）。

与技能自带 desensitize.py 的差异：
  1. 不做「民事/刑事模式」自动判定——本驱动面向知识库/记忆库，固定按词表全量替换；
  2. 统一社会信用代码、手机号、身份证、邮箱一律用固定中文占位符，便于全库一致；
  3. 支持 --dry 只统计不落盘；
  4. 逐文件输出替换计数，便于识别漏词。

用法：
  python3 desensitize_md.py --terms 词表.txt --files targets.txt [--dry]
  targets.txt 每行一个绝对路径。

注意：替换为全库文本级替换，**包括**反引号内的文件路径——脱敏后路径中的字号
      与真实文件名不一致，取件前须按映射表还原（见 MEMORY.md 脱敏段）。
"""
import argparse
import os
import re
import sys

# 内置正则类（与技能第一层「法定标识」对齐）
REGEX_RULES = [
    (re.compile(r'\b[0-9A-HJ-NPQRTUWXY]{18}\b'), '[统一社会信用代码]'),
    (re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'), '[手机号]'),
    (re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'), '[身份证号]'),
    (re.compile(r'[\w.\-+]+@[\w\-]+\.[\w.\-]+'), '[电子邮箱]'),
]


def load_terms(path):
    """读词表：原词=替换词；按原词长度降序，保证长词优先。"""
    pairs = []
    with open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            if '=' not in ln:
                continue
            k, v = ln.split('=', 1)
            k, v = k.strip(), v.strip()
            if k and v and k != v:
                pairs.append((k, v))
    pairs.sort(key=lambda kv: -len(kv[0]))
    return pairs


def apply(text, pairs):
    counts = {}
    for k, v in pairs:
        if k in text:
            n = text.count(k)
            text = text.replace(k, v)
            counts[k] = n
    for rx, ph in REGEX_RULES:
        found = rx.findall(text)
        if found:
            text = rx.sub(ph, text)
            counts[ph] = counts.get(ph, 0) + len(found)
    return text, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--terms', required=True)
    ap.add_argument('--files', required=True)
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    pairs = load_terms(args.terms)
    files = [l.strip() for l in open(args.files, encoding='utf-8') if l.strip()]

    total_hits = 0
    touched = 0
    agg = {}
    for p in files:
        if not os.path.exists(p):
            print('! 缺失 %s' % p, file=sys.stderr)
            continue
        with open(p, encoding='utf-8') as f:
            src = f.read()
        out, counts = apply(src, pairs)
        if counts:
            touched += 1
            total_hits += sum(counts.values())
            for k, v in counts.items():
                agg[k] = agg.get(k, 0) + v
            if not args.dry and out != src:
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(out)

    print('%s：处理 %d 个文件，命中 %d 个，替换 %d 处'
          % ('[演练]' if args.dry else '[已写入]', len(files), touched, total_hits))
    print('\n=== 替换明细（按命中次数）===')
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
        print('%5d  %s' % (v, k))
    return 0


if __name__ == '__main__':
    sys.exit(main())
