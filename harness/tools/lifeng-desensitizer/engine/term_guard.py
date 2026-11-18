#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脱敏词条闸门（2026-10-28 建，gen_terms 与 desensitize 共用）。

为什么要有这个模块：
    合同脱敏最容易出的不是漏脱，是**脱过头**。实测本地千问把「安装」当成人名，
    词表里写了 `安装=安某`，于是全文「安装」变「安某」、「关于交货」变
    「关于交某」、「单位」变「单某」——合同条款直接读不懂，审查无法进行。

两条底线（用户 2026-10-28 确认）：
    1. 法律/商务常用词永不作为敏感项——不论哪个环节、哪张词表带进来。
    2. 民事合同正文人名不化名；法定代表人/授权代表/联系人等**签章位人名仍脱**
       （化名规则：保留姓氏 + 某）。

用法：
    from term_guard import is_legal_common, near_sign_context
    if is_legal_common(term):
        continue                      # 直接丢弃该词条
    if is_civil and not near_sign_context(term, text):
        continue                      # 正文人名，放行
"""
import os
import re

# 应急开关：置环境变量 DESENSITIZE_NO_GUARD=1 即整体停用本闸门（回到旧行为）。
# 用途：万一某类文书被误挡，不必改代码即可先跑通。
_NO_GUARD = os.environ.get("DESENSITIZE_NO_GUARD", "") not in ("", "0")

# 法律/商务高频词：出现即判定「不是敏感主体」
LEGAL_COMMON = frozenset("""
安装 单位 关于 双方 协议 附件 签署 盖章 支付 付款 通过 实际 共同 确定 确保
材料 代表 生产 制作 管理 交货 验收 结算 发票 违约 解除 争议 管辖 保密 知识产权
补充 变更 履行 交付 质量 价格 金额 数量 期限 责任 甲方 乙方 丙方 丁方 合同 条款
约定 协商 通知 送达 生效 终止 转让 担保 抵押 保证 赔偿 损失 不可抗力 授权 委托
签字 联系人 地址 电话 开户 账号 税号 采购 供货 运输 保险 税费 质保 售后 培训
承包 发包 施工 工期 竣工 监理 设计 图纸 审计 决算 服务费 咨询 股权 出资 分红
章程 董事 监事 设备 工程 项目 技术 标准 规格 型号 单价 总价 报价 结算方式
提供 负责 承担 享有 完成 提交 确认 审核 批准 备案 报送 开具 收取 退还 支付方式
以上 以下 其中 其他 备注 合计 小计 大写 小写 人民币 元整 甲方代表 乙方代表
违约金 保证金 预付款 进度款 尾款 含税 不含税 增值税 专用发票 普通发票 开户行
""".split())

# 签章位上下文：命中即认为该人名属于「必须脱」的一类
SIGN_CONTEXT = ("法定代表人", "负责人", "授权代表", "委托代理人", "委托代表",
                "签署", "签字", "签章", "盖章", "联系人", "经办人",
                "甲方代表", "乙方代表", "甲方（", "乙方（", "法定代表人（")

# 明显是机构而非人名（模型常把公司简称标成人名）
ORG_TAIL = ("公司", "集团", "厂", "店", "中心", "事务所", "研究院", "设计院",
            "合作社", "银行", "学校", "医院", "电站", "仓库", "基地", "工程处")

# 民事文书特征（判断走「正文人名不脱」这条规则）
CIVIL_MARKERS = ("甲方", "乙方", "本协议", "本合同", "发包", "承包", "承租", "供货")

_ALIAS = re.compile(r'(某|X|x){1,2}\d*$')


def is_legal_common(term):
    if _NO_GUARD:
        return False
    if not term:
        return False
    t = term.strip()
    if t in LEGAL_COMMON:
        return True
    # 「安装费」「合同价」这类由常用词 + 单字后缀构成的，也一并挡掉
    for w in LEGAL_COMMON:
        if len(w) >= 2 and t.startswith(w) and len(t) - len(w) <= 1:
            return True
    return False


def is_alias(term):
    """已经是化名（张某/某1/X某）的，不要再脱一次。"""
    return bool(term and _ALIAS.search(term))


def near_sign_context(term, text, span=16):
    """term 是否出现在签章位上下文附近（前后 span 字内）。"""
    if not text or not term:
        return False
    start = 0
    while True:
        i = text.find(term, start)
        if i < 0:
            return False
        seg = text[max(0, i - span): i + len(term) + span]
        if any(c in seg for c in SIGN_CONTEXT):
            return True
        start = i + 1


def is_civil(text):
    return any(k in (text or "") for k in CIVIL_MARKERS)


def looks_like_org(term):
    return bool(term) and any(term.endswith(x) for x in ORG_TAIL)
