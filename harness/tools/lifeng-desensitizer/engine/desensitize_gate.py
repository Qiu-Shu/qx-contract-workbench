#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脱敏件质量闸门（2026-10-28 建，配合「立丰脱敏」及 legal-desensitize）。

为什么需要它：
    2026-10-28 实测「立丰脱敏」产出的合同脱敏件，人名识别在词中间切出假姓名，
    把「安装→安某」「单位→单某」「关于交货→关于交(某)」「双方友好→双方友(某)」
    「补充协议→充协议(某)」全部打碎。这种脱敏件**已无法用于条款审查**——
    条款含义、数量、责任主体都可能读错。

本闸门做四件事：
    1. 结构体检：段落数、表格数、字数与原件的偏差（防止脱敏破坏文档）
    2. 误伤体检：统计「某」密度，并检测一批高频法律词是否被打断
    3. 金额体检：检测「元」前的数字是否被占位符吃掉（2026-10-28 新增）
    4. 结论：PASS 才允许进入审查；FAIL 一律退回，不得审查

为什么加第 3 项（2026-10-28 血泪）：
    旧版引擎把「（￥8180000元）」脱成「（￥[编号]元）」，五个金额全失，
    只剩大写金额，导致「金额三向核对（大写↔合计↔单价×数量）」退化为单向。
    引擎已于同日修复，但**闸门不查这一项，同类事故仍会静默放行**。
    金额是审查判断的地基，丢一个数字就可能让违约金、尾款、差额全部算错。

用法：
    python3 desensitize_gate.py 原件.docx 脱敏件.docx
    python3 desensitize_gate.py 脱敏件.docx          # 只做误伤 + 金额体检

退出码：0=PASS，1=FAIL（不可审），2=参数/读取错误。
"""
import json
import os
import re
import sys

# 合同/文书高频词——一旦在脱敏件里被打断（含「某」或缺失），即判误伤。
# 只放通用法律与商务词，不含任何客户信息。
COMMON_WORDS = [
    '安装', '单位', '关于', '双方', '协议', '附件', '签署', '盖章', '支付', '付款',
    '通过', '实际', '共同', '确定', '确保', '材料', '代表', '生产', '制作', '管理',
    '交货', '验收', '结算', '发票', '违约', '解除', '争议', '管辖', '保密', '知识产权',
    '补充', '变更', '履行', '交付', '质量', '价格', '金额', '数量', '期限', '责任',
    '甲方', '乙方', '丙方', '合同', '条款', '约定', '协商', '通知', '送达', '生效',
    '终止', '转让', '担保', '抵押', '保证', '赔偿', '损失', '不可抗力', '法定代表',
    '授权', '签字', '盖章', '联系人', '地址', '电话', '开户', '账号', '税号',
    '采购', '供货', '运输', '保险', '税费', '验收合格', '质保', '售后', '培训',
    '承包', '发包', '施工', '工期', '竣工', '监理', '设计', '图纸', '审计', '决算',
    '服务费', '咨询', '尽职调查', '股权', '出资', '分红', '章程', '董事', '监事',
]

# 常用字被单字替换的高危姓氏（合同里几乎不会单独成人名）
RISKY_SINGLE = '于过价位清章装管关于单方安通签盖充双'

# 金额位被占位符吃掉：「元」前面不是数字而是 [编号]/[金额]/[占位符] 之类。
# 2026-10-28：旧引擎把「（￥8180000元）」脱成「（￥[编号]元）」，五个金额全失。
# 判据只认「右括号/页边 + 元」紧邻的占位符，避免误伤「合同编号：[编号]　，」这类真编号。
MONEY_LOST_RE = re.compile(r'[\[［【]\s*[^\]］】\n]{1,12}\s*[\]］】]\s*元')
# 中文大写金额（捌佰壹拾捌万元整），用于与阿拉伯数字配对核对
CN_AMOUNT_RE = re.compile(r'[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]{2,}元整?')
# 阿拉伯金额的三种形态（2026-10-28 补第三种）：
#   ① 8180000元 / 1,174,250.00元 / 815.75万元 —— 数字直接跟「元」
#   ② ¥13,000.00 —— 货币符号+数字，常见于「人民币壹万叁仟元整（¥13,000.00）」
#      这种写法数字后面跟的是右括号不是「元」，原正则匹配 0 处，
#      闸门误判「疑似金额被整体脱除」把成品拦进不合格（实测卧式储罐合同）。
AR_AMOUNT_RE = re.compile(
    r'(?:[￥¥$€£]\s?\d[\d,，]*(?:\.\d+)?|\d[\d,，]*(?:\.\d+)?\s*(?:亿元|万元|元))')

# 项目名栏位：工程名称/项目名称 后面若还是原文，说明项目识别信息没脱（2026-10-28）
PROJ_FIELD_RE = re.compile(
    r'(?:工程名称|项目名称|标段名称|工程全称|项目全称|建设项目名称)\s*[：:]\s*([^\n。；;]{2,40})')


def read_docx(path):
    from docx import Document
    d = Document(path)
    paras = [p.text for p in d.paragraphs]
    cells = []
    for t in d.tables:
        for r in t.rows:
            for c in r.cells:
                cells.append(c.text)
    return paras, cells


def stats(paras, cells):
    body = '\n'.join(paras)
    table = '\n'.join(cells)
    return {
        'paras': len(paras),
        # 非空段落数：判断「整段被吞」靠它，不靠字数。
        # 脱敏只会把词换短（地址 17 字 → [地址] 4 字），不会让整段消失；
        # 一旦非空段落变少，才是真事故。
        'nonempty': sum(1 for x in paras if x.strip()),
        'tables_text_len': len(table),
        'chars': len(body) + len(table),
        'body': body,
        'all': body + '\n' + table,
    }


class Unsupported(Exception):
    """闸门读不了的格式。注意：读不了 ≠ 成品不合格。"""


def read_doc(path):
    """按格式取文本与结构量。

    2026-10-31 血泪：本函数原来只会 read_docx，于是 PDF 成品一进来就抛
    「Package not found」，闸门返回 2，dropbox_run 把「非 0」一律当不合格，
    结果**所有 PDF 成品都被拦进「不合格」**——用户看到文件凭空消失，
    却连原因都不知道（原因只印在控制台）。三卷.pdf 130 页就是这么被误杀的。
    现在按扩展名分派；真读不了就抛 Unsupported，由调用方判「未体检、放行」。
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in ('.docx', '.docm'):
        paras, cells = read_docx(path)
        d = stats(paras, cells)
        d['unit'] = '段落'
        d['units'] = d['paras']
        return d

    if ext == '.pdf':
        import pymupdf
        doc = pymupdf.open(path)
        pages = [doc[i].get_text() for i in range(len(doc))]
        # 是不是整页扫描件：抽样 10 页，看有没有铺满整页的图。
        # 版面判断用图框面积占比，比「有没有字」可靠——OCR 层也会有字。
        scanned = False
        try:
            n_probe = min(10, len(doc))
            cover = 0
            for i in range(n_probe):
                pg = doc[i]
                pr = pg.rect
                area = max(pr.width * pr.height, 1)
                for b in pg.get_image_info():
                    w = abs(b['bbox'][2] - b['bbox'][0])
                    h = abs(b['bbox'][3] - b['bbox'][1])
                    if (w * h) / area > 0.6:
                        cover += 1
                        break
            scanned = bool(n_probe) and cover >= max(1, int(n_probe * 0.8))
        except Exception:
            scanned = False
        doc.close()
        body = '\n'.join(pages)
        return {
            'paras': len(pages),
            'nonempty': sum(1 for p in pages if p.strip()),
            'tables_text_len': 0,
            'chars': len(body),
            'body': body,
            'all': body,
            'unit': '页',
            'units': len(pages),
            'scanned': scanned,
            'note': '' if body.strip() else '该 PDF 无文本层（扫描件），只做页数核对',
        }

    if ext in ('.xlsx', '.xlsm'):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        cells = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    if v is not None and str(v).strip():
                        cells.append(str(v))
        try:
            wb.close()
        except Exception:
            pass
        body = '\n'.join(cells)
        return {'paras': 0, 'nonempty': 0, 'tables_text_len': len(body),
                'chars': len(body), 'body': body, 'all': body,
                'unit': '单元格', 'units': len(cells)}

    if ext in ('.txt', '.md', '.csv'):
        with open(path, encoding='utf-8', errors='replace') as f:
            body = f.read()
        lines = body.splitlines()
        return {'paras': len(lines), 'nonempty': sum(1 for l in lines if l.strip()),
                'tables_text_len': 0, 'chars': len(body), 'body': body, 'all': body,
                'unit': '行', 'units': len(lines)}

    raise Unsupported(ext or '无扩展名')


def scan_terms(text, terms_path):
    """按本次词表回查残留：词表里明明有，成品里还在，就是漏脱。

    为什么加这一条（2026-10-31）：结构体检管不了「该脱的没脱」。
    实测 130 页的刑事卷宗扫描件，原件 87 处当事人姓名，成品里还剩 27 处，
    闸门却因为只核页数而判「通过」——这种成品流出去比拦错更危险。
    """
    hits = []
    if not terms_path or not os.path.exists(terms_path):
        return hits
    seen = set()
    try:
        with open(terms_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                src = line.split('=', 1)[0].strip()
                if len(src) < 2 or src in seen:
                    continue
                seen.add(src)
                n = text.count(src)
                if n:
                    hits.append((src, n))
    except Exception:
        return hits
    return hits


def check(orig_path, red_path, terms_path=""):
    red = read_doc(red_path)
    problems = []
    info = []
    issues = []          # 结构化问题：[{code, text, fix}]，供「不合格」后续处理分诊

    def _issue(code, text, fix):
        """记一条问题。

        fix 决定拦截之后还能不能救——这是「不合格」闭环的依据，不是装饰：
          auto   重跑一次大概率就好（判据误杀、阈值问题）
          rule   得先改规则/词表再重跑，直接重跑结果不变
          engine 引擎本身的缺陷，重跑一百次也一样，必须改代码或人工核对
        """
        problems.append(text)
        issues.append({"code": code, "text": text, "fix": fix})

    if red.get('note'):
        info.append(red['note'])

    # 扫描件（整页图片 + OCR 文字层）单独对待：
    # OCR 会把「8」认成「6」、把字吞掉，字数与金额计数天然对不上——
    # 拿它当判据只会把好成品判死。这类件只核对页数，文字靠人工抽查。
    scanned = bool(red.get('scanned'))
    if scanned:
        info.append('扫描件：文字层来自 OCR，字数/金额只作参考，判据改为页数核对')

    # 1. 结构
    if orig_path:
        o = read_doc(orig_path)
        info.append('%s %d → %d' % (red['unit'], o['units'], red['units']))

        info.append('字数 %d → %d' % (o['chars'], red['chars']))
        if red['units'] != o['units']:
            _issue('STRUCT_UNITS', '%s数不一致（%d→%d），脱敏可能改动了文档结构'
                   % (red['unit'], o['units'], red['units']), 'engine')
        # 字数判据（2026-10-28 收口）：原先是「偏差 >5% 就判死」，方向写错了。
        # 脱敏天生是**变短**的——长公司名换成 [甲方公司]、工程名称换成 [项目名称]，
        # 一份合同掉 10% 字是正常现象（实测 517→465 字被误判成「损伤条款表述」）。
        # 真正该抓的是：掉太多（整段被吞）或反而变长（注入了东西）。
        ratio = (red['chars'] - o['chars']) / max(o['chars'], 1)
        # 「整段被吞」的判据换成非空段落数（2026-10-30 二次修正）：
        # 地址粒度细化到「室」之后，`湖北省武汉市洪山区珞南街道民院路128号3栋502室`
        # 变成 `湖北省武汉市洪山区[地址]`，一字减少 25 字——短文书整体掉 30% 以上很正常。
        # 实测一份 200 字的测试件因此被拦，可成品内容是完整的。
        # 真正该抓的是「段落变空」，字数只留一个很宽的上限兜底。
        if not scanned and red['nonempty'] < o['nonempty']:
            _issue('STRUCT_EMPTY', '有 %d 个段落脱敏后变空，疑似整段被吞'
                   % (o['nonempty'] - red['nonempty']), 'engine')
        if not scanned and ratio < -0.55:
            _issue('CHAR_SHRINK', '字数减少 %.1f%%（超过 55%%），疑似整段被吞' % (-ratio * 100), 'engine')
        elif ratio > 0.10:
            _issue('CHAR_GROW', '字数增加 %.1f%%（超过 10%%），疑似占位符注入异常' % (ratio * 100), 'engine')

    # 2. 「某」密度
    mou = red['all'].count('某')
    density = mou / max(red['chars'], 1)
    info.append('「某」%d 个，密度 %.2f%%' % (mou, density * 100))
    # 阈值配一个绝对数量门槛（2026-10-30 修）：
    # 密度判据是为长文档设计的，短文本样本量太小——一份 40 字的材料
    # 只要有 1 个「张某」，密度就 2.5%，直接被判「大面积误伤」拦掉。
    # 实测：一句「被告人张三，身份证号…」的测试件，脱敏完全正确，
    # 却因 1 个「某」被闸门退回，用户完全看不懂原因。
    # 改为「至少 3 个某 且 密度超阈值」才算误伤：单个姓氏化名属正常。
    # 2026-11-02 第三次修正：阈值从 1.2% 提到 3.5%。
    # 判决书、讯问笔录这类文书天生人名密集，一页里「张某甲」出现十几次很正常；
    # 1.2% 会把正常的刑事文书全部拦下（实测一份 600 字的判决片段 1.8% 就被判"误伤"）。
    # 真正的误伤有另一个更准的信号：高频法律词被打断（安装→安某），那条始终生效；
    # 这里只兜"极端密度"这种明显失控的情况。
    if not scanned and mou >= 3 and density > 0.035:
        _issue('MOU_DENSITY', '「某」密度 %.2f%% 偏高（阈值 3.5%%，且需 ≥3 个），疑似大面积误伤'
               % (density * 100), 'auto')

    # 3. 高频词被打断
    broken = []
    for w in COMMON_WORDS:
        if len(w) < 2:
            continue
        pattern = '(%s)某|某(%s)' % (w[:-1], w[1:])
        if re.search(pattern, red['all']):
            broken.append(w)
    if broken:
        _issue('WORD_BROKEN', '高频词被打断 %d 个：%s' % (len(broken), '、'.join(broken[:12])), 'rule')

    # 4. 单字姓氏被替换
    singles = []
    for ch in RISKY_SINGLE:
        if re.search(r'(?<![某])%s某' % ch, red['all']) and not re.search(r'%s某[一二三四五六七八九十]' % ch, red['all']):
            singles.append(ch)
    if singles:
        _issue('SINGLE_NAME', '疑单字被当成人名（%s某）：%s' % ('/'.join(singles[:6]), '这些字多为虚词或常用字'), 'rule')

    # 5. 金额完整性（2026-10-28 新增）
    #    (a) 「元」前是占位符 → 金额被脱，直接判死
    lost = []
    for m in MONEY_LOST_RE.finditer(red['all']):
        a, b = max(0, m.start() - 12), min(len(red['all']), m.end() + 6)
        lost.append(red['all'][a:b].replace('\n', ' '))
    if lost:
        _issue('MONEY_LOST', '金额被脱成占位符 %d 处：%s（「元」前必须是数字，见 2026-10-28 事故）'
               % (len(lost), ' | '.join(lost[:5])), 'engine')

    #    (b) 金额完整性核对分两种场景（2026-10-28 修，实测卧式储罐合同被误拦）：
    #        ① 有原件 → 逐类比对数量，少了就是脱敏吃了，直接 FAIL；
    #        ② 没原件 → 只能看脱敏件自身形态。「大写有/阿拉伯无」**不能判死**：
    #           甲方给的合同可能只写大写、不写阿拉伯，金额留空待定，
    #           甚至整段金额都没填——这是合同本身的不完整，不是脱敏的错。
    cn_cnt = len(CN_AMOUNT_RE.findall(red['all']))
    ar_cnt = len(AR_AMOUNT_RE.findall(red['all']))
    info.append('金额：大写 %d 处、阿拉伯 %d 处' % (cn_cnt, ar_cnt))
    if scanned:
        # 扫描件的数字来自 OCR，少几个多半是认错字，不是脱敏吃掉的
        info.append('扫描件不比对金额数量（OCR 会认错数字），金额请抽查原件对照')
    elif orig_path:
        o_ar = len(AR_AMOUNT_RE.findall(o['all']))
        o_cn = len(CN_AMOUNT_RE.findall(o['all']))
        if not lost and o_ar > 0 and ar_cnt == 0:
            _issue('MONEY_AR_ALL', '原件有阿拉伯金额 %d 处，脱敏件一处不剩——金额被整体脱除' % o_ar, 'engine')
        if o_ar > ar_cnt:
            _issue('MONEY_AR_LOST', '阿拉伯金额数量减少（原件 %d → 脱敏件 %d），脱敏吃掉了金额'
                   % (o_ar, ar_cnt), 'engine')
        if o_cn > cn_cnt:
            _issue('MONEY_CN_LOST', '大写金额数量减少（原件 %d → 脱敏件 %d），脱敏吃掉了金额'
                   % (o_cn, cn_cnt), 'engine')
    else:
        if cn_cnt > 0 and ar_cnt == 0:
            # 只提示不拦：合同本来就可能只写大写（金额待定/留空同样如此）
            info.append('提示：只有大写金额、无阿拉伯金额——合同本就可能只写大写，不算异常')

    # 6. 项目识别信息（2026-10-28 新增）
    #    合同最容易被认出来的不是公司名，是「工程名称/项目名称」——公司名换个马甲，
    #    同一页写着「远景科技园三期土建工程」，等于没脱。
    #    判据：栏位名后面若还是原文（不含 [,说明整段没动）→ 判死。
    for m in PROJ_FIELD_RE.finditer(red['all']):
        val = m.group(1).strip(' 　:：')
        if len(val) < 2:
            continue
        if '[' in val or '某' in val:
            continue          # 已占位/已化名
        _issue('PROJ_NAME', '项目名未脱：%s%s（工程名称/项目名称必须占位，'
               '否则公司名脱了也白搭）' % (m.group(0).split('：')[0], val[:20]), 'rule')
        break                 # 同类问题报一次就够，别刷屏

    # 7. 必备要素仍在
    for kw, name in [('甲方', '甲方'), ('乙方', '乙方')]:
        if kw not in red['all']:
            info.append('提示：脱敏件未见「%s」字样，请确认是否已被替换' % name)

    # 8. 词表回查：该脱的有没有真脱掉
    resid = scan_terms(red['all'], terms_path)
    if resid:
        total = sum(n for _, n in resid)
        sample = '、'.join('%s%s（%d 处）' % (t[0], '＊' * (len(t) - 1), n)
                           for t, n in [(a, b) for a, b in resid[:5]])
        _issue('RESIDUAL_TERMS', '成品仍残留词表里的敏感词 %d 个、共 %d 处：%s'
               % (len(resid), total, sample), 'rule')
    elif terms_path and os.path.exists(terms_path):
        info.append('词表回查：未发现残留')

    return problems, info, {'mou': mou, 'density': density, 'broken': broken,
                            'money_lost': len(lost), 'ar_amounts': ar_cnt}, issues


def main():
    argv = []
    as_json = False
    terms_path = ""
    it = iter(sys.argv[1:])
    for a in it:
        if a == '--json':
            as_json = True
        elif a == '--terms':
            terms_path = next(it, '')
        elif a.startswith('--terms='):
            terms_path = a.split('=', 1)[1]
        else:
            argv.append(a)
    if not argv:
        print(__doc__)
        return 2
    red_path = argv[-1]
    orig_path = argv[0] if len(argv) >= 2 else None
    for p in [x for x in (orig_path, red_path) if x]:
        if not os.path.exists(p):
            if as_json:
                print(json.dumps({'ok': False, 'error': '文件不存在：%s' % p}, ensure_ascii=False))
            else:
                print('文件不存在：%s' % p)
            return 2
    try:
        problems, info, raw, issues = check(orig_path, red_path, terms_path)
    except Unsupported as e:
        # 读不了 ≠ 不合格。宁可放行后提示人工抽查，也不能把用户的成品塞进「不合格」。
        msg = '该格式（%s）本闸门不做体检，已放行；请人工抽查成品' % e
        if as_json:
            print(json.dumps({'ok': True, 'skipped': True, 'note': msg}, ensure_ascii=False))
        else:
            print(msg)
        return 3
    except Exception as e:
        if as_json:
            print(json.dumps({'ok': False, 'error': '读取失败：%s' % e}, ensure_ascii=False))
        else:
            print('读取失败：%s' % e)
        return 2

    if as_json:
        # 结构化输出给「不合格」闭环用：谁拦截、为什么拦、还能不能救，一目了然。
        print(json.dumps({'ok': not problems,
                          'file': os.path.basename(red_path),
                          'orig': os.path.basename(orig_path) if orig_path else '',
                          'issues': issues,
                          'info': info,
                          'stats': raw}, ensure_ascii=False))
        return 1 if problems else 0

    print('=' * 56)
    print('脱敏件质量闸门：%s' % os.path.basename(red_path))
    print('-' * 56)
    for i in info:
        print('  · ' + i)
    if problems:
        print('-' * 56)
        for p in problems:
            print('  [FAIL] ' + p)
        print('-' * 56)
        print('结论：不通过 —— 脱敏件已损伤条款表述，不得据此审查')
        print('处置：退回重脱（换词表/指定本案词表/修人名规则），或由用户提供可读版本')
        return 1
    print('-' * 56)
    print('结论：通过 —— 可用于审查')
    return 0


if __name__ == '__main__':
    sys.exit(main())
