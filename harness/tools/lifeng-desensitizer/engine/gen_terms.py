# -*- coding: utf-8 -*-
"""
本地千问「识敏器」—— 读原文，自动挑出需要脱敏的专有名词，生成词表。

定位：模型只负责"找出哪些是敏感词"，绝不让它改写原文。

用法：
  python3 gen_terms.py 案件材料.docx
  python3 gen_terms.py 案件材料.docx --out 词表.txt --max-chars 30000
"""
import os
import re
import sys
import json
import time
import argparse
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from llm_scan import (  # noqa: E402
    read_text, chunk_text, DEFAULT_HOST, DEFAULT_MODEL,
)

SYSTEM_PROMPT = (
    "你是法律文书敏感信息识别助手。找出文本里所有指向真实主体的信息，"
    "为脱敏替换做准备。\n\n"
    "【必须找出】\n"
    "1. 公司/单位全称（含有限公司、集团、厂、店、所、行、社、中心、研究院等）；\n"
    "   包括**非甲乙方**的第三方主体：担保人、监理单位、设计单位、分包商、\n"
    "   保险公司、评估机构、代理机构、关联公司\n"
    "2. 机关全称（公安局、派出所、看守所、法院、检察院、监狱、委员会、仲裁委员会）\n"
    "3. 人名（当事人、法定代表人、代理人、证人、办案民警、经办人、联系人，\n"
    "   含「某某」「张队」这类称呼）\n"
    "4. 地址（精确到省市县区、乡镇、村组、街道、门牌、楼栋、房号、\n"
    "   房屋坐落、宗地位置）\n"
    "5. 主体标识号：统一社会信用代码、营业执照号、身份证号、护照号、车牌号\n"
    "6. 银行与资金：开户银行全称（含支行/分行/分理处）、银行账号、联行号、\n"
    "   银行流水号、回单号、保函编号、保险单号\n"
    "7. 建设工程专用号：建筑业企业资质证书号、安全生产许可证号、施工许可证号、\n"
    "   造价咨询编号、图审编号、竣工验收备案号\n"
    "8. 标的物标识：不动产单元号、不动产权证号、宗地号、地块编号、房屋坐落、\n"
    "   设备序列号/出厂编号、车辆识别代号VIN、集装箱号\n"
    "9. 单据号：提单号、运单号、报关单号、快递单号、发票号\n"
    "10. 知识产权：专利号、商标注册号、软件著作权登记号、著作权（作品）登记号\n"
    "11. 合同/案件编号：合同编号、协议编号、项目编号、案号、文号\n"
    "12. 联系方式：电话、手机、传真、邮箱（含 # ＠ 等变体）、网址、域名、\n"
    "    邮编、QQ/微信/钉钉等社交账号\n"
    "13. 系统账号：招投标平台账号、系统登录名、CA数字证书编号\n"
    "14. 能锁定唯一事件或唯一主体的独特说法（工程名称、项目名称、标段名称、\n"
    "    专项行动名、内部代号）\n"
    "15. 境外主体：Co., Ltd. / Inc. / LLC / GmbH / Pte. Ltd. 等英文公司全称\n\n"
    "【重要】即使这些信息在其他地方公开过（如商标注册人、企业信用公示信息），\n"
    "只要出现在这份文件里，也必须找出来。宁可多报，不要漏报。\n"
    "编号类**不要只报数字**，连前面的栏位名一起报：\n"
    "  报「资质证书编号D142012345」，不要只报「D142012345」。\n\n"
    "【不要输出】\n"
    "日期时间、金额数字、法条名称、《》里的法规名、罪名案由、\n"
    "甲方乙方等文书代称、单独的职业称谓（民警/律师/法官）、\n"
    "单独出现的泛称（公司/集团/医院/酒店/酒楼/经理/局长/人民法院）、\n"
    "「项目所在地人民法院」这类条款用语、印章残字（XX专用章）。\n\n"
    '只输出 JSON 数组，每项 {"term":"原文逐字片段","cat":"公司|机构|人名|地名|编号|联系|其他"}。\n'
    "term 必须逐字照抄，不得改写或拼接。长句要拆成多个专有名词，不要整句照抄。\n"
    "没有则输出 []。\n\n"
    "示例输入：甲方某某公司与某某某签约，开户行某某银行某支行，\n"
    "账号0000000000000000000，施工许可证编号000000000000000000，\n"
    "保险单号000000000000，地址某市某区某镇，案号（0000）0000民初0000号。\n"
    '示例输出：[{"term":"某某公司","cat":"公司"},{"term":"某某某","cat":"人名"},'
    '{"term":"某某银行某支行","cat":"机构"},{"term":"0000000000000000000","cat":"编号"},'
    '{"term":"000000000000000000","cat":"编号"},{"term":"000000000000","cat":"编号"},'
    '{"term":"某市某区某镇","cat":"地名"},'
    '{"term":"（0000）0000民初0000号","cat":"编号"}]'
)

# ===== 刑事卷宗专项提示词（笔录/起诉书/判决书等） =====
# 刑事卷宗与民事合同的敏感位置完全不同：核心是公检法机关全称、办案人员、羁押场所、案号文号。
CRIMINAL_PROMPT = (
    "你是刑事卷宗敏感信息识别助手。这份文件是刑事卷宗或笔录，"
    "找出所有指向真实主体和办案机关的信息。\n\n"
    "【必须找出】\n"
    "1. 公检法机关全称：XX市公安局XX分局、XX派出所、XX县公安局刑侦大队、\n"
    "   XX人民检察院、XX人民法院、XX看守所、XX拘留所、XX监狱\n"
    "2. 办案人员姓名：侦查员、讯问人、记录人、录制人、检察官、公诉人、\n"
    "   审判长、审判员、人民陪审员、书记员、鉴定人、见证人\n"
    "   （「侦查员某某某」只输出「某某某」，不要输出「侦查员」）\n"
    "3. 涉案人员姓名：犯罪嫌疑人、被告人、被害人、证人、法定代理人、近亲属\n"
    "4. 辩护人/代理人姓名 + 律师事务所名称 + 律师执业证号\n"
    "5. 案号文号：X公（刑）诉字〔2024〕1号、X检刑诉〔2024〕12号、\n"
    "   （0000）0000刑初000号、（2024）鄂01刑终456号\n"
    "6. 身份信息：身份证号、现住址、户籍所在地、联系方式\n"
    "7. 羁押场所具体位置：XX看守所第X讯问室、第X监室\n\n"
    "【重要】即使机关名、人名在公开渠道能查到，只要出现在这份文件里也必须找出。\n"
    "宁可多报，不要漏报。\n\n"
    "【扫描件提示】本文可能来自扫描件 OCR，常有识别错误（「讯问」识成「讯间」）\n"
    "和断行。按语义判断实体边界：报完整的机关名、人名、地址，\n"
    "不要报缺首字的半截地名，也不要报跨行拼接出来的假地址。\n\n"
    "【不要输出】\n"
    "罪名、法条（《刑法》第X条）、诉讼程序用语（立案/侦查/起诉/取保候审/认罪认罚）、\n"
    "笔录固定表述（问：/答：/以上笔录我看过/第X页共X页/第X次）、\n"
    "单独的职业称谓（侦查员/检察官/法官/证人）、\n"
    "单独出现的泛称（公安机关/人民检察院/人民法院/看守所）、\n"
    "日期时间、金额、年龄（41岁）、刑期、性别、民族、文化程度。\n\n"
    '只输出 JSON 数组，每项 {"term":"原文逐字片段","cat":"机关|人名|公司|地名|编号|联系|其他"}。\n'
    "term 必须逐字照抄原文，不得改写或拼接。长句拆成多个专有名词。\n"
    "没有则输出 []。\n\n"
    "示例输入：XX县公安局刑侦大队侦查员某某某在XX县看守所第3讯问室讯问\n"
    "犯罪嫌疑人某某某（身份证号000000000000000000，住某县某镇某村00号），\n"
    "案号X公（刑）诉字〔2024〕88号。\n"
    '示例输出：[{"term":"XX县公安局刑侦大队","cat":"机关"},{"term":"某某某","cat":"人名"},'
    '{"term":"XX县看守所第3讯问室","cat":"机关"},{"term":"某某某","cat":"人名"},'
    '{"term":"000000000000000000","cat":"编号"},{"term":"某县某镇某村00号","cat":"地名"},'
    '{"term":"X公（刑）诉字〔2024〕88号","cat":"编号"}]'
)

# 刑事卷宗特征词：命中 3 个以上即判定为刑事卷宗
CRIMINAL_MARKERS = (
    "讯问笔录", "询问笔录", "犯罪嫌疑人", "被告人", "被害人", "证人",
    "侦查员", "检察院", "检察员", "公诉人", "审判长", "审判员", "书记员",
    "看守所", "拘留证", "逮捕证", "起诉意见书", "起诉书", "刑事判决书",
    "立案决定书", "取保候审", "认罪认罚", "刑初", "刑终", "侦查终结",
)

# 标题类强信号：命中任一即可判定刑事卷宗。
# 官方文书标题普遍疏排（「讯 问 笔 录」），必须先归一化再匹配。
CRIMINAL_TITLE = (
    "讯问笔录", "询问笔录", "现场勘验笔录", "检查笔录", "搜查笔录", "辨认笔录",
    "侦查实验笔录", "提取笔录", "扣押笔录", "庭审笔录", "调解笔录",
    "合议庭评议笔录", "审判委员会讨论记录", "审查逮捕意见书",
    "起诉意见书", "起诉书", "刑事判决书", "刑事裁定书", "刑事附带民事判决书",
    "受案登记表", "立案决定书", "拘留证", "逮捕证", "拘传证",
    "取保候审决定书", "监视居住决定书", "批准逮捕决定书",
    "权利义务告知书", "鉴定意见通知书", "抓获经过", "到案经过",
)


def _norm_for_match(s):
    """压缩全部空白，专治官方文书疏排标题（「讯 问 笔 录」→「讯问笔录」）。"""
    return re.sub(r"[\s\u3000\u00a0]+", "", s or "")


def detect_doc_type(text):
    """判断文档类型，返回 'criminal' 或 'general'。"""
    if not text:
        return "general"
    flat = _norm_for_match(text)
    # 强信号：笔录/起诉书/判决书这类标题，命中一个就算刑事卷宗
    if any(t in flat for t in CRIMINAL_TITLE):
        return "criminal"
    hits = sum(1 for m in CRIMINAL_MARKERS if m in flat)
    return "criminal" if hits >= 3 else "general"


def prompt_for(text):
    """按文档类型返回对应提示词。"""
    return CRIMINAL_PROMPT if detect_doc_type(text) == "criminal" else SYSTEM_PROMPT


VALID_CATS = ("公司", "机构", "人名", "地名", "编号", "联系", "其他")

# 模型输出分类时用词不固定（机关/单位/姓名/地址/证件号…），统一映射到白名单。
# 不归一的话，「湖北省…公安局禁毒大队」会被降级成「其他」，替换词变成「敏感1」。
_CAT_ALIAS = {
    "机关": "机构", "机关单位": "机构", "单位": "机构", "单位名称": "机构",
    "组织": "机构", "政府部门": "机构", "机构名": "机构", "机关名称": "机构",
    # 模型经常直接写「政法机关」「公安机关」这类具体类别（提示词里就是这么分的）。
    # 不归一的话会掉进「其他」，占位符变成「敏感1」，比全脱还难读。
    "政法机关": "机构", "司法机关": "机构", "公安机关": "机构",
    "审判机关": "机构", "检察机关": "机构", "政府机关": "机构",
    "羁押场所": "机构", "监管场所": "机构", "办案单位": "机构",
    "事业单位": "机构", "医疗机构": "机构", "学校": "机构",
    "姓名": "人名", "人物": "人名", "人名/姓名": "人名", "当事人姓名": "人名",
    "人名/称谓": "人名", "办案人员": "人名", "办案民警": "人名",
    "地址": "地名", "地点": "地名", "住址": "地名", "地名/地址": "地名",
    "地址/地点": "地名", "籍贯": "地名", "场所": "地名",
    "证件": "编号", "证件号": "编号", "证件号码": "编号", "案号": "编号",
    "文号": "编号", "账号": "编号", "编号/号码": "编号", "号码": "编号",
    "身份证号": "编号", "身份证件号码": "编号", "身份信息": "编号",
    "电话": "联系", "手机": "联系", "手机号": "联系", "联系方式": "联系",
    "邮箱": "联系", "网址": "联系", "电话/邮箱": "联系",
    "公司名": "公司", "公司名称": "公司", "企业": "公司", "企业名称": "公司",
    "机构/公司": "公司", "敏感": "其他", "隐私": "其他", "个人信息": "其他",
}

# 已经化名过的形式（张某、蔡某2、周某3），不能再当作原词化名一次
_ALIAS_PAT = re.compile(r"^[\u4e00-\u9fa5]{1,2}某\d*$")

# 通用代称/泛称，不是专有名词
_GENERIC = {
    "甲方", "乙方", "丙方", "丁方", "第三方", "双方", "对方",
    "原告", "被告", "第三人", "上诉人", "被上诉人", "申请人", "被申请人",
    "当事人", "被告人", "被害人", "证人",
    "酒楼", "酒店", "宾馆", "饭店", "餐厅", "公司", "集团", "工厂", "厂",
    "医院", "学校", "学院", "银行", "法院", "检察院", "公安", "派出所",
    "看守所", "监狱", "事务所", "律所", "中心", "超市", "商店", "门市", "药店",
    "老板", "经理", "主任", "局长", "所长", "队长", "法官", "律师",
    "民警", "协警", "书记", "村长", "镇长", "县长", "市长",
    "科长", "处长", "部长", "董事长", "监事", "会计",
    "工程", "项目", "合同", "协议", "案件", "执行", "诉讼", "判决", "裁定",
}

# 刑事卷宗程序用语/固定表述——脱掉就等于把文书改废了，一律不脱
_CRIMINAL_STOP = {
    "认罪认罚", "取保候审", "监视居住", "刑事拘留", "批准逮捕", "侦查终结",
    "移送审查起诉", "退回补充侦查", "提起公诉", "不批准逮捕", "存疑不捕",
    "一审", "二审", "再审", "发回重审", "开庭审理", "书面审理", "公开审理",
    "量刑建议", "从轻处罚", "减轻处罚", "从重处罚", "免予刑事处罚",
    "坦白", "自首", "立功", "重大立功", "累犯", "初犯", "偶犯", "前科",
    "缓刑", "假释", "暂予监外执行", "羁押", "讯问", "询问", "传唤", "拘传",
    "通缉", "网上追逃", "另案处理", "同案犯", "在逃", "抓获归案", "到案",
    "第一被告", "第二被告", "第三被告", "第一被告人", "第二被告人",
    "被告一人", "嫌疑人", "犯罪嫌疑人", "被讯问人", "被询问人",
    "侦查员", "记录人", "录制人", "讯问人", "询问人", "翻译人",
    "公诉人", "审判长", "审判员", "人民陪审员", "书记员", "检察员",
    "辩护人", "诉讼代理人", "法定代理人", "附带民事诉讼原告人",
    "受案登记", "立案", "破案", "抓获经过", "到案经过", "情况说明",
    "同步录音录像", "讯问室", "询问室", "监室", "提讯室",
    "以上笔录我看过", "和我说的一样", "与我所说一致", "属实",
    # 民族 / 文化程度 / 政治面貌 / 性别年龄 —— 不具识别性，一律不脱
    "汉族", "回族", "满族", "壮族", "苗族", "维吾尔族", "土家族", "彝族",
    "蒙古族", "藏族", "布依族", "侗族", "瑶族", "白族", "朝鲜族", "黎族",
    "高中", "初中", "小学", "大学", "大专", "本科", "硕士", "博士", "研究生",
    "中专", "技校", "职高", "文盲", "半文盲", "高中文化", "初中文化",
    "小学文化", "大学文化", "大专文化", "本科文化", "文盲文化",
    "群众", "党员", "中共党员", "共青团员", "团员", "民主党派",
    "无业", "务农", "务工", "个体经营", "个体户", "农民", "工人", "职员",
    # 笔录/文书类型名（是文档种类，不是主体）
    "现场勘验笔录", "辨认笔录", "搜查笔录", "检查笔录", "提取笔录",
    "扣押笔录", "侦查实验笔录", "庭审笔录", "合议庭评议笔录",
    "讯问笔录", "询问笔录", "权利义务告知书", "鉴定意见通知书",
    # 证据种类（《刑诉法》第50条法定八类），脱掉等于毁掉证据章节
    "证人证言", "被害人陈述", "犯罪嫌疑人供述", "被告人供述", "供述和辩解",
    "物证", "书证", "视听资料", "电子数据", "鉴定意见", "勘验笔录",
    "检查笔录", "侦查实验笔录", "辨认笔录", "情况说明", "抓获经过",
    "户籍证明", "前科材料", "到案经过", "立案决定书", "破案报告",
    # 判决书结构用语
    "公诉机关", "附带民事诉讼", "审理终结", "本院认为", "经审理查明",
    "上述事实", "足以认定", "证据确实充分", "程序合法", "量刑适当",
}

# 罪名一律不脱（盗窃罪/危险驾驶罪/非法经营罪…）
_CRIME_PAT = re.compile(r"^[\u4e00-\u9fa5]{1,12}罪$")

# 模型最爱的错误：把整句证据描述当敏感词
# （「证人王春霞的证言」「被害人陈志刚的陈述」「犯罪嫌疑人王玉梅的供述与辩解」），
# 替换后整句变成「敏感12」，文书直接读不通。
# 判定：以角色词开头 + 含「的」+ 以文书用语结尾 → 不是专有名词，拆词重报即可。
_ROLE_HEAD = ("证人", "被害人", "犯罪嫌疑人", "被告人", "罪犯", "嫌疑人",
              "当事人", "原告", "被告", "第三人", "报案人", "举报人", "扭送人",
              "同案犯", "在逃人员", "被害单位", "被害人家属", "法定代理人",
              # 辩护与代理、审判与检察人员（「辩护人欧阳修」漏剥会把角色词一起涂掉）
              "辩护人", "诉讼代理人", "委托代理人", "代理人", "翻译人",
              "审判长", "审判员", "人民陪审员", "书记员", "公诉人",
              "检察员", "侦查员", "侦查人员", "法医", "鉴定人", "见证人",
              "辨认人", "被辨认人", "持有人", "被讯问人", "被询问人",
              "讯问人", "询问人", "记录人", "录制人")
# 必须长词优先：「被告人」若被「被告」先匹配，会剩「人欧阳修」当成人名
_ROLE_HEAD = tuple(sorted(_ROLE_HEAD, key=len, reverse=True))
_TAIL_WORDS = ("证言", "陈述", "供述", "辩解", "供述与辩解", "户籍证明",
               "身份信息", "基本情况", "常住人口信息", "讯问笔录", "询问笔录")
# 法条引用 + 金额，夹在长串里一并被抓
_LAW_IN = re.compile(r"《[^》]{2,40}》|第[一二三四五六七八九十百千\d]+条")
_MONEY_IN = re.compile(r"(?:人民币|RMB|CNY|美元|欧元|港币)?[¥￥]?\s?\d[\d,]*\.?\d*\s*(?:元|万元|亿元|千元)")
# 物证/书证枚举（「扣押的手表一块等物证」「监控视频、银行交易明细等书证」）
_EVID_IN = re.compile(r"^.{2,30}等(?:物证|书证|证人证言|证据|材料|物品)$")
_ACTION_IN = re.compile(r"的(?:供述|陈述|证言|辩解|供述与辩解|户籍|身份|基本情况)")


def is_sentence_like(term):
    """判断候选是不是「整句/整段描述」而非专有名词。"""
    s = re.sub(r"\s+", "", term or "")
    if not s:
        return False
    # ① 带角色词 + 「的」+ 文书用语收尾
    if s.startswith(_ROLE_HEAD) and _ACTION_IN.search(s):
        return True
    # ② 以文书用语收尾且中间带「的」（不再限开头，覆盖「扣押的…物证」）
    if s.endswith(_TAIL_WORDS) and "的" in s and len(s) >= 6:
        return True
    # ③ 物证/书证枚举
    if _EVID_IN.match(s):
        return True
    return False


def strip_embedded_noise(term):
    """从一个候选里剥掉法条、金额这类不该脱的成分，剩下的才是真专有名词。

    「《中华人民共和国刑法》第268条」→ 整条丢弃（纯法条）
    「人民币105835元」            → 整条丢弃（纯金额）
    返回清洗后的字符串，可能为空。
    """
    s = _LAW_IN.sub("", term or "")
    s = _MONEY_IN.sub("", s)
    return s.strip()


# 复姓（按两字取姓）
COMPOUND_SURNAMES = {
    "欧阳", "司马", "诸葛", "上官", "皇甫", "东方", "独孤", "慕容", "长孙",
    "宇文", "尉迟", "公孙", "端木", "南宫", "西门", "夏侯", "万俟", "呼延",
    "赫连", "澹台", "轩辕", "令狐", "钟离", "闾丘", "仲孙", "鲜于",
}


def http_json(url, payload=None, timeout=300):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ask_model(host, model, chunk, sys_prompt=None):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": "文本如下：\n" + chunk},
        ],
        "stream": False,
        # 注意：绝不能加 format="json"，会让 qwen2.5 输出退化成畸形对象
        "options": {"temperature": 0, "num_predict": 1500, "top_p": 0.9},
    }
    resp = http_json(host + "/api/chat", payload)
    return (resp.get("message") or {}).get("content", "")


def parse_items(content):
    """从模型输出里解析出 [{"term","cat","alias_of"}]，容忍各种格式偏差。"""
    content = (content or "").strip()
    if not content:
        return []
    # 模型常把 JSON 包在 ```json ... ``` 代码块里，先剥掉
    content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content)
    content = content.strip()

    obj = None
    try:
        obj = json.loads(content)
    except Exception:
        m = re.search(r"\[\s*\{.*?\}\s*\]", content, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = None
        if obj is None:
            m2 = re.search(r"\[.*?\]", content, re.S)
            if m2:
                try:
                    obj = json.loads(m2.group(0))
                except Exception:
                    obj = None
    if obj is None:
        return []

    items = []
    if isinstance(obj, list):
        for it in obj:
            alias = ""
            if isinstance(it, dict):
                term = str(it.get("term") or it.get("text") or it.get("word") or "").strip()
                cat = str(it.get("cat") or it.get("category") or it.get("type") or "其他").strip()
                alias = str(it.get("alias_of") or it.get("alias") or it.get("same_as") or "").strip()
            elif isinstance(it, str):
                term, cat = it.strip(), "其他"
            else:
                continue
            if term:
                items.append({"term": term, "cat": cat, "alias_of": alias})
    return items


# 时间表述里的修饰词，笔录/OCR 里极常见（「2024年12月14日晚上2点左右」）
_TIME_WORDS = (
    "上午", "下午", "中午", "晚上", "凌晨", "早晨", "清晨", "傍晚", "深夜",
    "半夜", "夜间", "白天", "上旬", "中旬", "下旬", "左右", "前后", "许",
    "同日", "次日", "当日", "当天", "当时", "此前", "此后", "之间", "时分",
    "时左右", "许分", "钟头", "余", "初", "末", "底",
)


def is_date_like(s):
    """判断候选是不是纯日期/时间（这类不算敏感，要过滤）。"""
    if not s:
        return False
    if re.fullmatch(r"\d{4}[-/.]\d{1,2}([-/.]\d{1,2})?", s):
        return True
    if not re.search(r"[年月日号时分]", s):
        return False
    work = s
    for w in _TIME_WORDS:          # 先剔掉时间修饰词，再判断是否纯时间
        work = work.replace(w, "")
    rest = re.sub(r"[0-9０-９〇零一二三四五六七八九十百千两廿卅"
                  r"年月日号时分秒点刻钟半至到\-—~/～、，,.\s]", "", work)
    return len(rest) == 0


def clean(term, cat, source=""):
    """过滤不合格候选。返回 (term, cat) 或 None。"""
    if not term or len(term) < 2 or len(term) > 60:
        return None
    # 幻觉校验：模型偶尔会把几处片段拼成原文里不存在的词（如把两个地址
    # 揉成「A省B市C区D镇62号附近」）。这种词条一旦进表，替换后正文会出现
    # 原文没有的内容，必须靠「逐字出现在原文中」兜住。
    if source and _norm_for_match(term) not in _norm_for_match(source):
        return None

    # ⚡ 碎片校验（2026-10-28 实测卧式储罐合同）：模型不稳定，同一份文本
    #   两次识敏结果不同。第二次把公司名/固定词的**截断碎片**当人名报上来：
    #     「某发三」←「某某某食品饮料有限公司」的中段
    #     「权代表」←「授权代表」的后半截
    #     「国家现」←「国家现代柑桔产业园」的开头
    #   这些词在原文里**从不是独立词**——左右两侧紧贴其他中文字。
    #   独立实体（人名/公司名/地名）在原文中的出现位置，两侧必有一侧
    #   是分隔符（标点/空白/行首尾/冒号）或非中文；两侧都贴着中文字的，
    #   一定是更长词的碎片，进词表会把正文咬得七零八落。
    #
    #   ⚠ 但**带实体后缀的词一律豁免**：「提交武汉仲裁委员会仲裁」里的
    #   「武汉仲裁委员会」两侧都是中文，可它是完整机构名，不是碎片。
    #   判据：只要以组织形式后缀收尾（公司/委员会/银行/局/院/所/中心/集团…），
    #   就当完整实体放过。碎片永远不会有像样的组织后缀。
    _ENTITY_TAIL = ("有限公司", "有限责任公司", "股份有限公司", "公司", "集团",
                    "集团公司", "委员会", "银行", "支行", "分行", "分理处",
                    "局", "厅", "院", "所", "中心", "站", "厂", "店", "铺",
                    "合作社", "事务所", "工作室", "研究院", "设计院", "产业园",
                    "工业园", "科技园", "街道", "镇", "村", "区", "县", "市", "省")
    _has_tail = any(term.endswith(x) for x in _ENTITY_TAIL)
    if (source and cat in ("人名", "公司", "机构", "地名")
            and len(term) >= 2 and not _has_tail):
        # 分隔符集合：标点/空白/括号/引号/数字/字母都算「断点」。
        # 用 frozenset 而不是字符串字面量，避免 \[ \] 这种无效转义告警。
        _SEP = frozenset(' \t\n\r，。；：、！？（）【】《》「」『』""''—…·'
                         '0123456789abcdefghijklmnopqrstuvwxyz'
                         'ABCDEFGHIJKLMNOPQRSTUVWXYZ[](){}/\\|<>?.,;:!@#$%^&*-_=+~`')
        _frag = False
        for m in re.finditer(re.escape(term), source):
            a, b = m.start(), m.end()
            left = source[a - 1] if a > 0 else ""
            right = source[b] if b < len(source) else ""
            if (not left) or left in _SEP or (not right) or right in _SEP:
                _frag = False
                break
            _frag = True
        if _frag:
            return None
    if _ALIAS_PAT.match(term):
        return None          # 已是化名，避免循环
    # 法规名绝不是敏感项：法律 / 行政法规 / 部门规章 / 地方性法规 / 条例
    # 一律不脱敏（用户 2026-10-26 明确要求）。模型常把
    # 《中华人民共和国民事诉讼法》整条当「机构」吐出来，必须在这里拒掉。
    try:
        import desensitize as _D
        if _D.is_law_name(term):
            return None
    except Exception:
        pass
    if term in _GENERIC:
        return None          # 代称/泛称
    if stripped := re.sub(r"\s+", "", term):
        if stripped in _CRIMINAL_STOP:
            return None      # 刑事程序用语/笔录固定表述
    # 机构/公司/店铺名绝不能当人名（引用姓名库同一份通名表，避免标准不一）
    try:
        import chinese_names as _C
        if cat == "人名":
            if any(w in term for w in _C.ORG_LIKE_WORDS):
                return None
            # 模型常把「地名 + 字号」的公司简称标成人名（武汉某信 → 武某）。
            # 这类改判为「公司」，交给经营类别简写，别把公司写成一个人。
            if len(term) >= 3 and any(term.startswith(p) for p in _C.PLACE_PREFIX):
                return (term, "公司")
    except Exception:
        pass
    if _CRIME_PAT.match(term):
        return None          # 罪名
    # 顿号/逗号相连的文书类型名（「现场勘验笔录、辨认笔录」）—— 文档种类，不是主体
    if re.search(r"[、，,；;]", stripped):
        parts = [p for p in re.split(r"[、，,；;]", stripped) if p]
        if parts and all(p in _CRIMINAL_STOP or p.endswith(("笔录", "通知书", "告知书",
                                                          "决定书", "意见书", "登记表"))
                         for p in parts):
            return None
    # 整句证据描述不是专有名词，脱掉会让文书读不通
    if is_sentence_like(term):
        return None
    # 排除表要在「角色剥离」之前判！否则「代表人」会被「代理」剥出「代人」、
    # 「法定代表人」被「法定代理」剥出「代人」，剥出来的半截恰好首字是姓氏，
    # 就绕过排除表变成「代某」（实测成品出现「法定代某」）。
    try:
        import chinese_names as _C2
        if cat in ("人名", "其他") and stripped in _C2.NON_NAME_WORDS:
            return None
        # 2026-11-05：排除表是精确匹配，挡不住「申辩」的三字延伸词
        # （申辩意 / 申辩意见 / 申辩权），这类被切进词表就是噪声。
        if cat in ("人名", "其他") and hasattr(_C2, "blocked_by_doc_root") \
                and _C2.blocked_by_doc_root(stripped):
            return None
        if cat in ("人名", "其他") and any(
                w in stripped for w in _C2.ORG_LIKE_WORDS):
            return None
    except Exception:
        pass

    # 「被害人陈志刚」这类「角色 + 姓名」：剥掉角色只留姓名，
    # 否则会化名成「被某」——既错又会把角色词一起涂掉。
    for r in _ROLE_HEAD:
        if term.startswith(r):
            rest = term[len(r):].lstrip("：: ")
            if 2 <= len(rest) <= 4 and rest[0] in _SURNAME_SET:
                if not re.search(r"[、，,；;]", rest):     # 顿号相连不是单个人名
                    term = rest
                    cat = "人名"
                    break
    # 模型常把姓名后面紧邻的一个字一起报上来（「某某某性」「某某某工」「某某某工」），
    # 这种粘连条目在图片上会多涂一个字，还和正确条目重复占位。
    # 只从尾部剥离明显的栏目/字段字，不动复姓四字名（欧阳明月之类）。
    if cat == "人名":
        # 只用**明确的栏目字**，别把姓名常用字（月华文明民日年）写进来，
        # 否则「欧阳明月」会被截成「欧阳明」。
        _glue = "性工讯记问签盖职务单位室别龄岁电话式址号族贯"
        while len(term) > 3 and term[-1] in _glue:
            term = term[:-1]
    # 纯法条 / 纯金额（含夹杂在长串里的）
    stripped_noise = strip_embedded_noise(term)
    if not stripped_noise:
        return None
    if stripped_noise != term and len(stripped_noise) < 2:
        return None
    if is_date_like(term):
        return None          # 日期不脱
    if re.fullmatch(r"[¥￥]?\s?\d[\d,]*\.?\d*\s*(元|万元|亿元|千元|万|亿)", term):
        return None          # 纯金额
    if term.startswith("《") and term.endswith("》"):
        return None          # 法规名
    if re.fullmatch(r"第[一二三四五六七八九十百千\d]+条", term):
        return None          # 法条
    if re.search(r"(专用章|公章|合同章|财务章|法人章|签章|印章)", term) and len(term) <= 16:
        return None          # 印章残字
    if re.search(r"(所在地|住所地|签订地|履行地)(的)?(人民法院|仲裁委|仲裁委员会)$", term):
        return None          # 条款通用表述
    if re.fullmatch(r"\d{1,6}", term):
        return None          # 短数字不是编号
    if re.fullmatch(r"\[[^\]]{1,14}\]", term):
        return None          # 占位符
    # 表格/证书上的栏目名，不是敏感信息
    LABELS = ("发证机关", "注册人地址", "注册人", "注册日期", "局长", "申请人",
              "地址", "电话", "传真", "邮编", "备注", "合计", "小计", "序号",
              "名称", "法定代表人", "成立日期", "注册资本", "经营范围",
              "当事人", "案由", "承办人", "审批人", "审核人", "签发人")
    stripped = re.sub(r"\s+", "", term)
    if stripped in LABELS:
        return None
    # 带空格分隔的单字（OCR 常见：「局          长」）
    if re.fullmatch(r"[\u4e00-\u9fa5](\s+[\u4e00-\u9fa5]){1,5}", term):
        if re.sub(r"\s+", "") in LABELS or len(re.sub(r"\s+", "", term)) <= 4:
            return None
    # 类别编号（「第 5 类：」「第3类」）
    if re.fullmatch(r"第\s*\d+\s*类[：:]?", term):
        return None
    # 数量短语（「银行卡三张」「身份证两张」「笔录三份」）—— 不是敏感信息
    if len(stripped) <= 8 and re.search(
            r"[一二三四五六七八九十百千两几数半]+[张个份名人次条只部件台套本页行枚笔]$",
            stripped):
        return None
    # 年龄（41岁 / 41周岁）：不具识别性
    if re.fullmatch(r"\d{1,3}\s*(?:岁|周岁)", stripped):
        return None
    # 第X次 / 标题+次数（OCR 把「讯问笔录」识成「讯间笔录第2次」时模型会整段报上来）
    if re.fullmatch(r"第\s*[\d〇零一二三四五六七八九十百]+\s*次", stripped):
        return None
    if re.search(r"笔录\s*第\s*[\d〇零一二三四五六七八九十百]+\s*次$", stripped):
        return None
    # 残缺省名：OCR 吃掉首字后剩「北省武汉市」（本该是「湖北省武汉市」）。
    # 它比完整名短、比单条片段长，替换时优先生效，结果只涂半截还留一个孤字。
    # 完整名通常另有条目，故丢弃残缺项。
    # 只判「省」这一种：市/区/县残缺难与「南市区」「东城区」这类真实地名区分，
    # 宁可留着由片段兜底，也不要误杀真实地名。
    if cat in ("地名", "机构") and 3 <= len(stripped) <= 30:
        if stripped.startswith("省") and len(stripped) >= 4:
            return None
        if re.match(r"^[\u4e00-\u9fa5]省[\u4e00-\u9fa5]{2,}", stripped):
            return None
    # 模型把非编号标成「编号」时，替换词会退化成 [编号] 占位符，等于没脱。
    # 真编号必须含数字或字母，否则丢弃。
    if cat == "编号" and not re.search(r"[0-9A-Za-z]", term):
        return None

    # ⚡ 2026-10-28：引擎正则有专用占位符的类别，**不进词表**，交给正则。
    #
    # 起因：施工许可证号「000000000000000000」是 18 位纯数字，词表里被标成
    #   「[湖北·2026年·身份证]」，反而盖掉了引擎 REGEX_RULES 里
    #   ［施工许可证号］的正确结果。占位符写错比不脱更误导。
    #
    # 为什么不能靠数字结构判断：该号第 7–14 位恰好是「20260115」，
    #   也是一段合法日期，`_looks_like_id` 分不开。只能靠**上下文锚点**。
    #
    # 判据放宽（第二轮）：不只纯数字，中文编号也要挡——
    #   「安全生产许可证号：（鄂）JZ安许证字〔2020〕001234」含中文括号，
    #   「开户行：某某银行某支行」是中文机构名，
    #   词表若收，会分别退化成 [编号] 和「银行」，都不如正则的
    #   [安全生产许可证号] 和 [开户银行] 准确。
    #
    # 结论：词表只该收**正则认不出**的东西（公司字号、人名、项目名、自由地址）。
    _ANCHOR_CTX = ""
    if source:
        _i = source.find(term)
        if _i > 0:
            _ANCHOR_CTX = source[max(0, _i - 28):_i]
    if _ANCHOR_CTX and re.search(
            r"(?:许可证|资质证书|证书|执照|保函|保单|提单|运单|报关单|"
            r"集装箱|不动产单元|宗地|地块|序列号|出厂编号|车架号|"
            r"车辆识别代号|VIN|联行号|流水号|回单号|凭证号|专利|商标|"
            r"登记号|平台账号|登录名|开户行|开户银行|银行账号|开户账号|"
            r"账号|联行|流水|结算账号)"
            # 锚点词后面常还有「编号/号码/号/证号」等修饰，一并吃掉再找冒号
            r"\s*(?:编号|号码|号|证号)?\s*[：:]?\s*$", _ANCHOR_CTX):
        return None

    cat = _CAT_ALIAS.get(cat, cat)      # 模型常写「机关」「姓名」「地址」，统一归一
    if cat not in VALID_CATS:
        cat = "其他"
    return term, cat


_ORG_NOISE = ("年月日号于在到去是和及与为对向该本此的了他在把被将就才又并由经"
              "送往押解提带引至从自朝给让叫使跟同获抓捕审查诉判立办受移退拘逮"
              "传通缉逃投接处罚据称供述证认案所地")

# 条款用语不是机关名：「项目所在地人民法院」「合同签订地仲裁委员会」绝不能脱
_ORG_STOP_PREFIX = ("所在地", "签订地", "履行地", "住所地", "签约地", "约定地",
                    "本辖区", "有管辖权的", "该", "本", "上述", "前述", "有关")

# 政法机关/羁押场所确定性正则（与 desensitize.py 的 REGEX_RULES 保持同源）
_ORG_RX = [
    re.compile(
        r"(?:(?![%s])[\u4e00-\u9fa5]){2,10}公安局[\u4e00-\u9fa5]{2,6}?分局" % _ORG_NOISE),
    re.compile(
        r"(?:(?![%s])[\u4e00-\u9fa5]){2,10}"
        r"(?:人民检察院|人民法院|公安分局|公安局|看守所|派出所|检察院|法院|监狱|拘留所|戒毒所|管教所)"
        r"(?:[\u4e00-\u9fa5]{2,8}?(?:大队|支队|中队|检察部|检察室|审判庭|刑庭|民庭))?" % _ORG_NOISE),
    # 其他行政机关：地名 + 局/委员会/办公室/管理处/中心
    # 城管局、市场监管局、住建局、卫健委、税务局…这些同样是可识别信息，
    # 且合同/笔录里经常出现（用户要求「其他也同上述规则」）。
    # 前缀限 2-8 字，避免把整句话吞进来；排除动词虚词。
    re.compile(
        r"(?:(?![%s])[\u4e00-\u9fa5]){2,8}"
        r"(?:城市管理执法局|综合行政执法局|市场监督管理局|市场监督局|"
        r"住房和城乡建设局|自然资源和规划局|人力资源和社会保障局|"
        r"生态环境局|交通运输局|农业农村局|文化和旅游局|卫生健康委员会|"
        r"应急管理局|医疗保障局|退役军人事务局|发展和改革委员会|"
        r"城管局|执法局|监管局|住建局|自规局|人社局|生态环境局|交通局|"
        r"农业局|文旅局|卫健委|应急局|医保局|发改委|税务局|财政局|"
        r"审计局|统计局|民政局|教育局|水利局|林业局|商务局|"
        r"管理局|委员会|办公室|管理处|服务中心)" % _ORG_NOISE),
]


def regex_org_terms(text):
    """用确定性正则扫出公检法机关/羁押场所全称。

    7B 模型对同一份文件两次识别结果不一致（看守所时有时无），机关名这类
    有固定形态的实体不能赌模型，正则兜底后统一进词表编号。
    """
    hits = []
    flat = text or ""
    for rx in _ORG_RX:
        for m in rx.finditer(flat):
            t = m.group(0).strip()
            if len(t) < 4:
                continue
            # 条款用语不是机关名：「项目所在地人民法院」里正则只吃到「人民法院」，
            # 必须回看匹配位置的前文才能判断，不能只看 t 的开头。
            before = flat[max(0, m.start() - 8):m.start()]
            if any(before.endswith(p) for p in _ORG_STOP_PREFIX):
                continue
            if any(t.startswith(p) for p in _ORG_STOP_PREFIX):
                continue
            # 「XX省/市/区/县」这类地名前缀至少要有，否则多半是条款裸称
            if not re.search(r"[省市区县旗盟州]", t):
                continue
            if t not in hits:
                hits.append(t)
    # 去掉被更长条目完整包含的短条目（「武汉市公安局」在「武汉市公安局洪山区分局」里）
    return [h for h in hits if not any(h != o and h in o for o in hits)]


# 全国省级行政区白名单——数量有限、形态固定，用白名单零误伤。
# 模型常漏掉整条地址（实测「河南省武汉市西湖区李桥镇134号」整条没识别），
# 省级名一旦漏掉就直接定位到省，必须确定性兜住。
_PROVINCES = (
    "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省",
    "黑龙江省", "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省",
    "山东省", "河南省", "湖北省", "湖南省", "广东省", "广西壮族自治区",
    "海南省", "重庆市", "四川省", "贵州省", "云南省", "西藏自治区",
    "陕西省", "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
    "台湾省", "香港特别行政区", "澳门特别行政区",
)

# 行政区划层级片段：省/市/区/县/镇/乡/街道/村
_FRAG_RX = re.compile(r"[\u4e00-\u9fa5]{2,6}?(?:自治区|自治州|省|市|区|县|镇|乡|街道|村)")


def address_fragments(known_terms, text):
    """兜底扫描地名。

    两路并行：
      ① 从已识别的地址/机关名里拆出**区级以下**的行政区划片段 ——
         模型抓到「…李桥镇62号附近」却漏了「…李桥镇134号」时，
         片段「李桥镇」能把后者一并打散。
      ② 扫描正文里的「XX区/县/街道/镇/乡」片段（跳过省市）。

    **不再把省名、市名当替换目标**（2026-10-25 用户要求「地名参照机构简写」）：
    省市级是层级背景、不指向具体人，没必要脱；
    把它们单独列成规则会把文书里的「湖北省」「武汉市」全替换掉，
    既过度又让读者丢失上下文（用户反馈「涂抹太多会阅读出问题」）。
    真正要藏的是「哪个区、哪条街、几号」。
    """
    import org_short as _OS
    out = []
    flat = text or ""

    def _is_upper_level(frag):
        """片段是不是省/市级（这类不脱）。"""
        return bool(_OS._PROV_PAT.match(frag)) and not re.search(
            r"(?:区|县|旗|街道|镇|乡|村|路|街|巷|号)", frag)

    for t, cat in known_terms:
        if cat not in ("地名", "机构"):
            continue
        for m in _FRAG_RX.finditer(t):
            f = m.group(0)
            if len(f) < 3 or f in out:
                continue
            if _is_upper_level(f):
                continue
            out.append(f)

    # 正文里直接扫「XX区/县/街道/镇/乡」（限定在区级以下，跳省市）
    for m in _FRAG_RX.finditer(flat):
        f = m.group(0)
        if len(f) < 3 or f in out:
            continue
        if not re.search(r"(?:区|县|旗|街道|镇|乡)$", f):
            continue          # 只要区县街道镇乡这一级
        if _is_upper_level(f):
            continue
        out.append(f)

    # 丢掉被更长条目包含的短片段
    return [f for f in out if not any(f != o and f in o for o in out)]


# OCR 常见形近字纠错：真实扫描件的 Vision OCR 会把「讯问」识成「讯同/讯间」，
# 「询问」识成「询间」，栏目名一错，栏目人名兜底就全失效。
_OCR_FIX = (
    ("被讯同人", "被讯问人"), ("被讯间人", "被讯问人"), ("被询间人", "被询问人"),
    ("讯同笔录", "讯问笔录"), ("讯间笔录", "讯问笔录"), ("询间笔录", "询问笔录"),
    ("讯同人", "讯问人"), ("讯间人", "讯问人"), ("询间人", "询问人"),
    ("记隶人", "记录人"), ("记录入", "记录人"),
    ("见证入", "见证人"), ("犯罪嫌疑入", "犯罪嫌疑人"), ("被害入", "被害人"),
    ("口是口否", "□是□否"), ("口是", "□是"), ("口否", "□否"),
)


def fix_ocr_noise(text):
    """修正 OCR 形近字，只用于识敏判断，不改原文。"""
    s = text or ""
    for bad, good in _OCR_FIX:
        s = s.replace(bad, good)
    return s


# 笔录固定栏目后必然是真实姓名，模型对这几个栏目的召回并不稳定
# （实测「被询问人：吴淑珍」「见证人：施雅琴」整片漏掉）。栏目形态固定，
# 用正则确定性补入，不赌模型。
_NAME_FIELDS = (
    "被讯问人", "被询问人", "讯问人", "询问人", "记录人", "录制人",
    "翻译人", "见证人", "辨认人", "被辨认人", "持有人", "当事人",
    "被害人", "犯罪嫌疑人", "被告人", "罪犯", "证人", "报案人",
    "举报人", "扭送人", "投案人", "法定代理人", "辩护人", "诉讼代理人",
    "附带民事诉讼原告人", "申请人", "在场人", "检查人", "勘验人",
    "侦查员", "侦查人员", "办案人", "承办人", "检察员", "审判长",
    "审判员", "人民陪审员", "书记员", "公诉人", "法医", "鉴定人",
    "聘请人", "委托代理人", "见证人员", "签名捺印", "被侵害人",
    # 民事合同/委托书里的姓名栏目，同样要脱
    "法定代表人", "负责人", "联系人", "经办人", "承办律师", "代理律师",
    "开户人", "户名", "收款人", "付款人", "授权代表", "签署人", "签署代表",
    "甲方代表", "乙方代表", "甲方联系人", "乙方联系人", "签约人", "立约人",
    "声明人", "承诺人", "申请人", "填报人", "填报日期", "送达人", "接收人",
)
_FIELD_RX = re.compile(
    r"(?:%s)\s*(?:[（(][^）)]{0,6}[）)])?\s*[：:]\s*"
    r"([\u4e00-\u9fa5]{2,4}(?:[、，,]\s*[\u4e00-\u9fa5]{2,4})*)"
    % "|".join(sorted(_NAME_FIELDS, key=len, reverse=True))
)
# 栏目后常见的非人名（答语、状态描述）
_NOT_NAME = set(_CRIMINAL_STOP) | {
    "本人", "自己", "无", "没有", "同上", "见上", "略", "不详", "未知",
    "签名", "捺印", "盖章", "手印", "指纹", "空白", "如下", "附后",
}
_SURNAME_SET = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍"
    "虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚"
    "程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓"
    "牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙"
    "叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双"
    "闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍卻璩桑桂濮牛寿通边扈燕冀郏浦尚农"
    "温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘"
    "匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空"
    "曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)


def regex_field_names(text):
    """从笔录固定栏目里扫出人名（「被询问人：吴淑珍」）。"""
    hits = []
    for m in _FIELD_RX.finditer(text or ""):
        for n in re.split(r"[、，,]\s*", m.group(1)):
            n = n.strip()
            if len(n) < 2 or len(n) > 4:
                continue
            if n in _NOT_NAME or _ALIAS_PAT.match(n):
                continue
            if n[0] not in _SURNAME_SET:      # 姓氏表兜底，挡住「没有异议」这类
                continue
            if n not in hits:
                hits.append(n)
    return hits


# 叙述句里的人名：不在任何栏目里，7B 模型召回不稳（实测「当时跟某某某在一起，
# 还有钱晓梅也在场」两个名字整片漏掉，成品上原样留着）。
# 这类句式高度固定，用正则确定性兜底；再用姓氏表挡掉「跟他一起」这类代词。
_NT = r"[\u4e00-\u9fa5]{2,3}"          # 一个姓名（2-3 字）
_NARRATIVE_RX = (
    # 跟/和/与/同/随 + 姓名 +（可插入「在」）+ 一起/一同
    # 「跟某某某在一起」中间有个「在」，不允许的话某某某就漏了。
    re.compile(r"(?:跟|和|与|同|随)(%s)(?:在)?(?:一起|一同|共同|合伙|同行)" % _NT),
    # 姓名 + 也在场 / 在场 / 也参与。必须非贪婪 2-3 字，
    # 贪婪版会把「某某某也在场」吃成「某某某在」+「在场」，化名成「孙某在」。
    re.compile(r"(%s)(?:也在场|都在场|也在|均在现场|在场|也参与|也参加)" % _NT),
    # 名叫/叫做/叫 + 姓名
    re.compile(r"(?:名叫|叫做|名字叫|叫)(%s)(?=[，。、；,;\s]|$)" % _NT),
    # 姓名 + 是我(的) + 亲属关系
    re.compile(r"(%s)是我的?(?:表弟|表哥|表姐|表妹|堂弟|堂哥|"
               r"堂姐|堂妹|弟弟|哥哥|姐姐|妹妹|父亲|母亲|儿子|女儿|朋友|同事|邻居|"
               r"亲戚|叔叔|舅舅|姑姑|姨妈)" % _NT),
    # 一起的是/在场的有 + 姓名列表（顿号连接的要全部抓：「某某某、某某某」）
    re.compile(r"(?:一起的?是|在场的有|同行的是|随行的有)(%s(?:、%s)*)"
               % (_NT, _NT)),
)
# 叙述里常见的非人名（代词、泛称），务必挡住
_NARR_STOP = {
    "他", "她", "它", "我", "你", "他们", "她们", "我们", "你们", "对方", "本人",
    "其他", "其它", "别人", "他人", "有人", "某人", "几个", "两个", "三人",
    "朋友", "同事", "邻居", "亲属", "家人", "老乡", "熟人", "同伴", "同行",
    "民警", "警察", "保安", "司机", "老板", "工人", "村民", "群众",
}


def regex_narrative_names(text):
    """从叙述句里扫出人名（「跟某某某在一起」「钱晓梅也在场」）。

    只用于兜底，所以判据从严：首字必须是常见姓氏，且整体不像代词/泛称。
    """
    hits = []
    src = text or ""
    for rx in _NARRATIVE_RX:
        for m in rx.finditer(src):
            raw = next((g for g in m.groups() if g), "") or ""
            # 顿号列表拆成单个名字再逐个校验
            for cand in re.split(r"[、，,]", raw):
                cand = cand.strip()
                if not (2 <= len(cand) <= 4):
                    continue
                if cand in _NARR_STOP or cand in _CRIMINAL_STOP or cand in _GENERIC:
                    continue
                if _ALIAS_PAT.match(cand):
                    continue
                if cand[0] not in _SURNAME_SET:
                    continue
                if cand not in hits:
                    hits.append(cand)
    return hits


def scan_all_names(text, min_score=60):
    """通用中文人名扫描 —— 不依赖模型，靠「姓 + 名」结构 + 上下文打分。

    这是解决「有些人名还是没被识别出来」的主力。4 条模式按置信度加分：

      A 角色词后接姓名（100）：讯问人：某某某 / 法定代表人某某某
      B 签名/捺印/括号（95）：某某某（签名）/ （甲方：某某某）
      C 顿号连排（85）：某某某、某某某 —— 首项像人名则整列都收
      D 全量滑窗（60）：只收 3-4 字候选

    为什么 D 只收 3-4 字：2 字候选与常用词同形太多（「和平」「安全」「万元」），
    靠排除表挡不完，误伤代价高（把「和平」脱成「和某」，文书直接读不通）。
    2 字姓名交给 A/B/C 高置信模式覆盖——文书里 2 字名几乎总在栏目或签名处。

    返回 {姓名: 置信分}。
    """
    import chinese_names as C

    src = text or ""
    if not src:
        return {}
    score = {}

    def _add(name, s):
        name = (name or "").strip()
        if not name:
            return
        # 公司/机构/店铺名绝不能当人名。
        # 「某某商贸有限公司」首字「武」是姓，「某某超市」首字「关」是姓，
        # 早期版本会把它们当人名化成「武某达商贸有限公司」「关某合超市」，
        # 把企业名劈成两半、数据全毁（实测踩过）。
        if re.search(r"(公司|集团|工厂|厂|超市|商场|市场|商店|店铺|门市|酒楼|饭店|"
                     r"餐厅|酒店|宾馆|旅馆|药房|药店|诊所|医院|事务所|合作社|农场|"
                     r"养殖场|加工厂|银行|支行|分行|学院|学校|幼儿园|设计院|研究院|"
                     r"局|院|所|厅|部|队|委|中心)", name):
            return
        if len(name) >= 8:            # 长串基本是机构/地址，不是姓名
            return
        # 低置信（孤立候选）用严格判定：排除「和/与/从/于」这类兼职虚词的姓氏，
        # 否则「以上笔录我看过，和我说的一样」会被识成「和某」。
        if not C.looks_like_name(name, strict=(s < 85)):
            return
        if name in _CRIMINAL_STOP or name in _GENERIC or _ALIAS_PAT.match(name):
            return
        if score.get(name, 0) < s:
            score[name] = s

    # ---- A：角色词后接姓名（可带顿号列表）----
    # 关键：先抓**整段**到标点/空白为止，再在内部分词。
    # 早期用「{2,3}」直接截 3 字，会把「某某商贸有限公司」截成「武汉鑫」
    # 当成人名（化成「武某」），企业名被劈成两半、数据全毁（实测踩过）。
    role_alt = "|".join(sorted(C.ROLE_WORDS, key=len, reverse=True))
    rx_role = re.compile(
        r"(?:%s)\s*(?:[（(][^）)]{0,8}[）)])?\s*[：:是为]?\s*"
        r"([^\s，。；：、（）()\[\]【】\n]{2,40})" % role_alt)
    for m in rx_role.finditer(src):
        seg = m.group(1)
        for part in re.split(r"[、，,]", seg):
            part = part.strip()
            if not part:
                continue
            _add(part, 100)

    # ---- B：签名 / 捺印 / 括号内 ----
    rx_sign = re.compile(
        r"(?:签名|签字|捺印|盖章|手印|指纹)\s*[）)]?\s*[：:]\s*([\u4e00-\u9fa5]{2,3})")
    for m in rx_sign.finditer(src):
        _add(m.group(1), 95)
    rx_paren = re.compile(r"[（(]\s*(?:%s)\s*[：:]\s*([\u4e00-\u9fa5]{2,3})\s*[）)]" % role_alt)
    for m in rx_paren.finditer(src):
        _add(m.group(1), 95)

    # ---- C：顿号连排（首项像人名 → 整列可信）----
    rx_list = re.compile(r"([\u4e00-\u9fa5]{2,3})((?:[、，,][\u4e00-\u9fa5]{2,3}){1,5})")
    for m in rx_list.finditer(src):
        first = m.group(1)
        if not C.looks_like_name(first):
            continue
        _add(first, 85)
        for part in re.split(r"[、，,]", m.group(2)):
            _add(part, 85)

    # ---- D：姓氏驱动的全文扫描（召回最高，不依赖上下文）----
    # 从每个姓氏字起，取 1-2 个「名字用字」组成候选，再用前后字约束定界。
    # 这是解决「人名还是识别不出来」的主力：姓名无法穷举，但姓氏是封闭集合，
    # 名字用字也有明确范围，两者一夹就能把姓名圈出来。
    try:
        by_sur = C.scan_names_by_surname(src, strict=False)
    except Exception:
        by_sur = {}
    for cand, cnt in by_sur.items():
        # 出现 2 次以上给更高分（重复出现的人名几乎必然是真名）
        _add(cand, 70 if cnt >= 2 else 60)

    return {k: v for k, v in score.items() if v >= min_score}


def surname_of(name):
    """取姓氏：复姓取两字，其余取首字。

    必须先剥掉角色前缀，否则「被害人陈志刚」会取到「被」姓 → 变成「被某」，
    这种化名一看就错，还会被当成真人名再脱一次。
    """
    if not name:
        return "某"
    core = name
    for r in _ROLE_HEAD:
        if core.startswith(r) and len(core) > len(r) + 1:
            core = core[len(r):]
            break
    if len(core) >= 3 and core[:2] in COMPOUND_SURNAMES:
        return core[:2]
    return core[0]


def _merge_adjacent_places(text, place_terms, max_span=60):
    """把正文中位置相邻、能首尾相接的地名条目合并成更长的条目。

    为什么需要：「另有一处房产位于洪山区关山街道」里，
    「洪山区」和「关山街道」是两条独立规则，分别替换后成品变成
    「另有一处地名3地名2」——两个占位符挨着，读不通。
    把它们合并成「洪山区关山街道」一条，只替换一次就通顺了。

    做法：在正文里找出「地名A 紧接 地名B」的位置，把两段拼起来。
    最多拼 3 段，避免把整句话当成地名。
    """
    if not text or not place_terms:
        return []
    terms = sorted(set(place_terms), key=len, reverse=True)
    merged = set()
    flat = text
    for a in terms:
        for b in terms:
            if a == b:
                continue
            # 只处理「A 直接跟 B」（允许中间没有空格）
            pair = a + b
            if len(pair) > max_span:
                continue
            if pair in flat:
                merged.add(pair)
    # 再拼第三段
    base = list(merged)
    for p in base:
        for c in terms:
            triple = p + c
            if len(triple) > max_span:
                continue
            if triple in flat and triple not in merged:
                merged.add(triple)
    # 去掉被更长条目包含的
    out = list(merged)
    return [m for m in out if not any(m != o and m in o for o in out)]


def _split_place_safe(name):
    """安全调用 org_short.split_place（失败时退回空前缀）。"""
    try:
        import org_short
        return org_short.split_place(name)
    except Exception:
        return "", name


def make_placeholder(cat, used, term=""):
    """生成占位符。

    人名 → 保留姓 + 某（周军→周某；同姓加序号 周某2；复姓 欧阳某）
    机构 → 保留机构性质与层级（武汉市公安局洪山分局→公安分局，
          洪山区人民检察院→区人民检察院），同简写冲突才加序号
    地名 → 保留行政层级（武汉市洪山区珞南街道→市区街道地名）
    其他 → 类别 + 数字
    编号 → [编号]

    为什么机构不再用「机构1/2」：用户明确反馈「全部变成机构 1234 也让人看不懂」。
    一份笔录里全是机构1机构2，读者分不清哪句是公安、哪句是检察院，文书就废了。
    """
    if cat in ("编号", "案号"):
        # 各类号码用专用格式，保留「能说明这是什么」的部分，
        # 让人一眼看出脱的是什么（用户要求「留前面省份开头」「车牌也要脱」）。
        # 兜底才是 [编号]。
        try:
            import desensitize as _D
            t = term or ""
            # ⚡ 2026-10-28 修：原判据是 `\d{17}[\dXx]` 纯长度匹配，
            #    施工许可证号「000000000000000000」也是 18 位纯数字，
            #    于是被标成「[湖北·2026年·身份证]」——千问词表里就这么写着，
            #    反过来把引擎的正确结果 [施工许可证号] 覆盖掉了。
            #    身份证的 7–14 位必须是合法出生日期（YYYYMMDD），加这道校验就能分开。
            if re.fullmatch(r"\d{17}[\dXx]", t) and _D._looks_like_id(t):
                ph = _D._id_placeholder(t)
                if ph:
                    return ph
            if re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", t):
                ph = _D._uscc_placeholder(t)
                if ph:
                    return ph
            # 车牌：省份简称 + 字母 + 5~6 位
            if re.fullmatch(
                    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]"
                    r"[A-Z][A-Z0-9]{4,6}(?:挂|学|警|港|澳)?", t):
                ph = _D._plate_placeholder(t)
                if ph:
                    return ph
            # 警号：纯 5~7 位数字且上下文提到「警号」时，用 [警号]
            # （单看数字无法区分，交给正则按锚点处理；这里只在词表里
            #  明确带「警号」二字的情况下才走专用格式）
            if "警号" in t or "警 号" in t:
                return "[警号]"
        except Exception:
            pass
        return "[编号]"

    if cat == "人名":
        # 化名规则从简（用户 2026-10-26：「app 里面化名规则也得改简单些」）：
        # 一律「姓 + 某」，同姓不再派 周某2 / 周某3。
        # 原来按人递增序号，一份笔录里会冒出「周某2、吴某3、周某4」，
        # 读起来像编号不像人。代价是同姓的两个人会合并成同一个「周某」，
        # 若某案确实需要区分，把姓名类别改成「编号」即可保留区分度。
        sur = surname_of(term)
        return (sur + "某") if sur else "某"

    # 机构 / 公司 / 地名：全部走简写引擎，保留类别特征、剥离专名。
    # 用户明确要求：机构不能全是「机构1234」，公司商店同理（「xxx超市」也泄露信息）。
    def _dedup(short):
        if not short:
            return ""
        if short not in used:
            return short
        i = 2
        while ("%s%d" % (short, i)) in used:
            i += 1
        return "%s%d" % (short, i)

    # 境外主体（2026-10-28）：英文公司名走 summarize_business 认不出行业，
    # 会掉进兜底变成「敏感1」——读者不知道脱的是公司还是个人。
    # Co., Ltd. / Inc. / LLC / GmbH / Pte. Ltd. 这些后缀是明确的组织形式，直接给中文对应。
    # 注意：_dedup 必须先定义再调用，否则 UnboundLocalError（踩过）。
    _T = (term or "").strip()
    if re.search(r"(?:Co\.,?\s*Ltd\.?|Limited|Inc\.?|LLC|GmbH|Corp\.?|"
                 r"Pte\.?\s*Ltd\.?|S\.A\.|B\.V\.|K\.K\.)\s*$", _T, re.I):
        return _dedup("境外公司")

    if term and cat in ("机构", "公司", "地名"):
        short = ""
        try:
            if cat == "机构":
                from org_short import summarize_org
                short = summarize_org(term)
            elif cat == "公司":
                from org_short import summarize_business
                short = summarize_business(term)
            else:
                # 地名：保留省市前缀 + 「地名」
                # 湖北省武汉市洪山区珞南街道民院路128号 → 湖北省武汉市地名
                # 洪山区关山街道 → 区街道地名（没省市可留时用层级补信息）
                from org_short import summarize_place
                short = summarize_place(term)
                if not short:
                    from org_short import place_display_level
                    short = place_display_level(term) + "地名"
        except Exception:
            short = ""
        got = _dedup(short)
        if got:
            return got
        # 只剩字号、没有经营类别/组织形式的公司简称（武汉某信、深圳某众）：
        # 给一个中性的「某公司」，别退成「公司1」这种编号。
        if cat == "公司":
            try:
                import chinese_names as _C
                if len(term) >= 3 and any(term.startswith(p) for p in _C.PLACE_PREFIX):
                    return "某公司"
            except Exception:
                pass

    base = {"公司": "公司", "地名": "地名", "机构": "机构", "联系": "联系"}.get(cat, "敏感")
    i = 1
    while ("%s%d" % (base, i)) in used:
        i += 1
    return "%s%d" % (base, i)


# ==================== 2026-10-28 词表落地闸门 ====================
# 用户授权「按审合同的经验改」。合同脱敏的真实边界：
#   ① 主体公司全称、证件号、账号、详细地址、案号 —— 必脱
#   ② 法定代表人/负责人/授权代表/签署人/联系人 —— 必脱，化名「姓+某」
#   ③ 正文里其他自然人 —— 不脱（用户 2026-10-28：民事合同正文人名不 x 某化）
#   ④ 法律/商务常用词 —— 绝不可脱（实测「安装」被当人名脱成「安某」，
#      连带「关于交货」→「关于交某」、「单位」→「单某」，整份合同不可读）
# 判据集中在 term_guard.py，与 desensitize.py 共用同一份清单，避免两边漂移。
from term_guard import (is_legal_common, is_alias, near_sign_context,
                        is_civil, looks_like_org)


_ADDR_HINT = re.compile(
    r"(大道|街道|路|街|巷|胡同|号|栋|幢|座|单元|楼|室|村|镇|乡|组|小区|大厦|广场|园区)")

_ORG_TAIL = ("公司", "集团", "银行", "委员会", "医院", "学校", "大学", "学院",
             "法院", "检察院", "公安局", "事务所", "中心", "厂", "酒店", "超市",
             "合作社", "研究院", "设计院", "事务所", "管理局", "局", "院")


def _has_org_tail(s):
    return any((s or "").endswith(t) for t in _ORG_TAIL)


def covered_by_engine(t):
    """这个原值引擎自己的规则能不能认出来？能认就别再进词表。

    为什么必须挡（2026-10-30 实测）：
        词表优先级高于正则，一条词表进去就会盖掉正则的精确占位符。
        本地模型识敏把下面这些全塞进了词表——
            13812345678              → 联系1        （本该是 [手机号]）
            湖北省武汉市…128号3栋502室 → 湖北省武汉市地名
            洪山区文化大道555号…       → 地名2
        成品占位符比纯规则还难读，还有一条碎片「程名称为洪山区=地名4」。

    「词表只收正则认不出的东西」这条原则记忆里写了很久，代码层面一直没落实。
    """
    s = (t or "").strip()
    if not s:
        return True
    # 号码类：有效数字 ≥7 位，除数字外几乎没有别的内容
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 7 and len(re.sub(r"[\d\-\s]", "", s)) <= 2:
        return True
    # 身份证 / 统一社会信用代码
    if re.fullmatch(r"\d{17}[\dXx]", s) or re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", s):
        return True
    # 电子邮箱
    if re.fullmatch(r"[A-Za-z0-9._%+\-]+(?:@|＠|#)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", s):
        return True
    # 地址 / 门牌：含地址特征词，交给地址结构识别。
    # 门槛定在 3 字而不是 6：实测「珞南街道」只有 4 个字、
    # 「民院路」只有 3 个字，都被长度门槛漏过去，进了词表替换成「地名3」。
    # 两字的「街道」「大道」属于泛称，由常用词表挡，这里不必管。
    if len(s) >= 3 and _ADDR_HINT.search(s):
        return True
    # 纯行政区划（省/市/区/县）：按脱敏设计本来就保留，不该进词表。
    # 实测模型把「湖北省武汉市洪山区」当地名收进来，成品变成
    # 「湖北省武汉市洪山区地名3[地址]」——把该留的脱了，还留个半截占位符。
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,8}(?:省|市|区|县)"
                    r"(?:[\u4e00-\u9fa5]{2,8}(?:市|区|县|镇|乡))*", s):
        return True
    # 片段：含虚词说明是从句子里截出来的一截，不是完整实体名。
    # 实测模型报过「程名称为洪山区」（从「工程名称为洪山区…」切歪），
    # 这种词条一旦进表，会把正文咬出莫名其妙的替换。
    # 带机构后缀的豁免：像「湖北和顺商贸有限公司」含「和」但是完整机构名。
    if len(s) >= 4 and re.search(r"[为的了是在与和及或将对把被]", s) and not _has_org_tail(s):
        return True
    return False


def filter_terms(mapping, source_text=""):
    """词表落地前的闸门。返回过滤后的 mapping，并打印被丢弃的条目。"""
    civil = is_civil(source_text)
    out, dropped, reclassed = [], [], []
    for t, ph, cat in mapping:
        if is_legal_common(t) or is_alias(t):
            dropped.append((t, "常用词/已化名"))
            continue
        if covered_by_engine(t):
            dropped.append((t, "引擎可识别"))
            continue
        if cat == "人名" and looks_like_org(t):
            out.append((t, ph, "公司"))
            reclassed.append(t)
            continue
        if civil and cat == "人名" and source_text and not near_sign_context(t, source_text):
            dropped.append((t, "正文人名"))
            continue
        out.append((t, ph, cat))
    if reclassed:
        print("词表闸门：%d 条机构误标为人名，已改判公司（%s）"
              % (len(reclassed), "、".join(reclassed[:5])))
    if dropped:
        print("词表闸门：丢弃 %d 条（%s）"
              % (len(dropped), "、".join("%s·%s" % (t, r) for t, r in dropped[:8])))
    return out
def main():
    ap = argparse.ArgumentParser(description="本地千问识敏器：自动生成脱敏词表")
    ap.add_argument("input")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--out", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-chars", type=int, default=30000,
                    help="长文档只取前 N 字做识敏（人名重复率高，抽样足够），0=不限")
    args = ap.parse_args()

    # 2026-11-05 用户死命令：本地千问不参与脱敏（识敏/补漏/化名），只在 OCR 使用。
    # OCR 走 macOS Vision 框架（ocr_vision），与本地模型无关。
    # 确需应急且使用者本人在场时，显式设 DESENS_ALLOW_LLM=1。
    if os.environ.get("DESENS_ALLOW_LLM") != "1":
        sys.stderr.write(
            "\n[x] 本地模型已禁止参与脱敏。\n"
            "    用户 2026-11-05 死命令：千问只在 OCR 使用，识敏一律不调模型。\n"
            "    OCR 用 ocr_vision（macOS Vision），不需要本脚本。\n"
            "    应急须使用者本人在场并设 DESENS_ALLOW_LLM=1。\n\n")
        return 5

    if not os.path.exists(args.input):
        print("文件不存在：", args.input)
        return 1

    try:
        text = read_text(args.input)
    except SystemExit:
        raise
    except Exception as e:
        print("读取失败：", e)
        return 1

    total_len = len(text)
    sampled = text
    if args.max_chars and total_len > args.max_chars:
        head = int(args.max_chars * 0.7)
        tail = args.max_chars - head
        sampled = text[:head] + "\n" + text[-tail:]
        print("  文档共 %d 字，超过 %d，已抽样 %d 字做识敏（人名重复出现，抽样足够）"
              % (total_len, args.max_chars, len(sampled)), file=sys.stderr)

    chunks = chunk_text(sampled, size=4000, overlap=250)
    if not chunks:
        print("文本为空。")
        return 0

    est = int(len(chunks) * 25)
    _t0 = time.time()
    print("本机模型：%s ｜ 文本 %d 字，分 %d 段 ｜ 预计约 %d 分 %02d 秒 ｜ 仅本地推理"
          % (args.model, len(sampled), len(chunks), est // 60, est % 60), file=sys.stderr)

    _sysp = prompt_for(sampled)
    _dtype = detect_doc_type(sampled)
    print("  文档类型判定：%s（%s）"
          % ("刑事卷宗" if _dtype == "criminal" else "一般文书", _dtype), file=sys.stderr)
    raw = []
    for i, ch in enumerate(chunks, 1):
        try:
            content = ask_model(args.host, args.model, ch, _sysp)
        except urllib.error.URLError as e:
            print("连接本机 Ollama 失败：%s\n请先启动本地模型（双击「本地千问」或跑 local_ai.sh start）" % e,
                  file=sys.stderr)
            return 2
        except Exception as e:
            print("第 %d 段异常：%s" % (i, e), file=sys.stderr)
            continue
        got = parse_items(content)
        elapsed = time.time() - _t0
        avg = elapsed / i
        remain = avg * (len(chunks) - i)
        print("  [%d/%d] 候选 %d 条（已用 %ds，预计还需 %ds）"
              % (i, len(chunks), len(got), int(elapsed), int(remain)), file=sys.stderr)
        raw.extend(got)

    # 确定性兜底：公检法机关/羁押场所有固定形态，不该赌模型每次都抓到
    # （实测同一份讯问笔录，第一次抓到看守所、第二次漏掉）。
    # 正则注入后与模型结果并表，统一编号成「机构N」。
    # 扫描件先过 OCR 形近字纠错，否则「被讯同人」这类噪声会让正则全失效。
    clean_text = fix_ocr_noise(text)
    org_hits = regex_org_terms(clean_text)
    if org_hits:
        print("  正则兜底补入公检法机关/场所 %d 条" % len(org_hits), file=sys.stderr)
        raw.extend({"term": t, "cat": "机构", "alias_of": ""} for t in org_hits)

    # 笔录固定栏目里的人名同样不该赌模型（实测「见证人：施雅琴」整片漏掉）
    name_hits = regex_field_names(clean_text)
    if name_hits:
        print("  正则兜底补入栏目人名 %d 条" % len(name_hits), file=sys.stderr)
        raw.extend({"term": t, "cat": "人名", "alias_of": ""} for t in name_hits)

    # 叙述句里的人名（「当时跟某某某在一起」「钱晓梅也在场」）：
    # 不在任何栏目里，7B 模型实测整片漏，成品上原样留着真名。
    narr_hits = regex_narrative_names(clean_text)
    if narr_hits:
        print("  正则兜底补入叙述人名 %d 条" % len(narr_hits), file=sys.stderr)
        raw.extend({"term": t, "cat": "人名", "alias_of": ""} for t in narr_hits)

    # 通用姓名扫描：这是人名识别的主力，不依赖模型召回。
    # 靠「姓 + 名」结构 + 4 级上下文置信度（角色词 100 / 签名 95 / 顿号 85 / 孤立 60）。
    # 7B 模型对同一份文件两次识敏结果都不一样，人名不能赌它。
    try:
        scanned = scan_all_names(clean_text)
    except Exception as e:
        scanned = {}
        print("  姓名扫描异常（继续用模型结果）：%s" % e, file=sys.stderr)
    if scanned:
        hi = sum(1 for v in scanned.values() if v >= 85)
        print("  姓名结构扫描补入 %d 条（高置信 %d 条）" % (len(scanned), hi),
              file=sys.stderr)
        raw.extend({"term": t, "cat": "人名", "alias_of": ""} for t in scanned)

    # 清洗 + 去重
    seen = set()
    ordered = []
    for it in raw:
        c = clean(it["term"], it["cat"], text)
        if not c:
            continue
        t, k = c
        # 地名条目保留完整地址（含省市），占位符由 summarize_place 生成
        # 「湖北省武汉市地名」——省市在、具体位置没了，读起来通顺。
        # 图片涂抹的「只涂区以下」由 image_redact 单独处理（那里有坐标，
        # 可以精确定位到字符区间；词表阶段拆掉反而会让正文变成「湖北省武汉市区县地名」）。
        #
        # 但要丢掉**纯省/市级**条目：省市是层级背景，不是识别信息。
        # 把它们单独列成规则，会把完整地址里的「武汉市」再替换一次
        # （实测成品出现「湖北省地名地名」），而且过度脱敏。
        if k == "地名":
            _keep, _rest = _split_place_safe(t)
            if not _rest:
                continue
        if t in seen:
            continue
        seen.add(t)
        ordered.append({"term": t, "cat": k, "alias_of": it.get("alias_of", "")})

    # 地名兜底：省级白名单 + 从已识别地址/机关名拆出的区划片段
    frag = address_fragments([(x["term"], x["cat"]) for x in ordered], text)
    exist = {x["term"] for x in ordered}
    new_frag = []
    for f in frag:
        if f in exist:
            continue
        # 兜底片段同样要过滤纯省/市级（与前面清洗阶段一致）
        _keep, _rest = _split_place_safe(f)
        if not _rest:
            continue
        new_frag.append(f)
    if new_frag:
        print("  地名兜底补入 %d 条" % len(new_frag), file=sys.stderr)
        for f in new_frag:
            ordered.append({"term": f, "cat": "地名", "alias_of": ""})

    # 连续地名合并：正文里「洪山区关山街道」会被拆成两个条目分别替换，
    # 成品变成「地名3地名2」，读不通（2026-10-25 实测）。
    # 这里把能连起来的相邻地名拼成一条，作为更长的规则参与替换。
    try:
        _place_terms = [x["term"] for x in ordered if x["cat"] == "地名"]
        _merged = _merge_adjacent_places(text, _place_terms)
        _exist2 = {x["term"] for x in ordered}
        _added = [m for m in _merged if m not in _exist2]
        if _added:
            print("  连续地名合并补入 %d 条" % len(_added), file=sys.stderr)
            for m in _added:
                ordered.append({"term": m, "cat": "地名", "alias_of": ""})
    except Exception:
        pass

    # 冲突消解：机构/公司条目优先于地名条目。
    # 实测踩过：「洪山区城管局隔壁」被模型当地名报上来，它比机关注册抓到的
    # 「洪山区城管局」更长，长词优先后整个被当成地名 → 成品变成「区地名2」，
    # 读者不知道那是城管局。凡是某个地名条目以某机构/公司条目开头，
    # 就把多余的地名条目丢掉，让机构简写生效。
    org_terms = [x["term"] for x in ordered if x["cat"] in ("机构", "公司")]
    if org_terms:
        kept = []
        for x in ordered:
            if x["cat"] == "地名":
                t = x["term"]
                covered = any(t != o and t.startswith(o) for o in org_terms)
                if covered:
                    continue
            kept.append(x)
        ordered = kept

    ordered.sort(key=lambda x: (-text.count(x["term"]), x["term"]))
    all_terms = {x["term"] for x in ordered}

    used = set()
    mapping = []
    ph_by_term = {}

    # 第一轮：主名称分配占位符
    for it in ordered:
        al = it["alias_of"]
        if al and al != it["term"] and al in all_terms:
            continue
        ph = make_placeholder(it["cat"], used, it["term"])
        used.add(ph)
        ph_by_term[it["term"]] = ph
        mapping.append((it["term"], ph, it["cat"]))

    # 第二轮：别名沿用主名称的占位符
    for it in ordered:
        al = it["alias_of"]
        t = it["term"]
        if t in ph_by_term:
            continue
        if al and al in ph_by_term:
            mapping.append((t, ph_by_term[al], it["cat"]))
            ph_by_term[t] = ph_by_term[al]
        else:
            ph = make_placeholder(it["cat"], used, t)
            used.add(ph)
            ph_by_term[t] = ph
            mapping.append((t, ph, it["cat"]))

    # ===== 2026-10-28 修复：词表落地前过两道闸 =====
    # ① 法律/商务常用词一律不得作为敏感项（实测千问把「安装」当人名，
    #    脱成「安某」后整份合同不可读：「关于交货」→「关于交某」、「单位」→「单某」）
    # ② 民事合同正文人名不再化名（用户 2026-10-28 明确要求）——
    #    只保留法定代表人/负责人/授权代表/签署人/联系人这类「签章位人名」
    mapping = filter_terms(mapping, text)

    # ===== ③ 子串消除（2026-10-28，实测卧式储罐合同）=====
    # 千问不稳定，同一文本两次识敏结果不同。第二次把公司名/固定词的截断碎片
    # 当独立实体报上来：「某某三」（「某某某某」中段）、「权代表」（「授权代表」
    # 后半截）、「国家现」（「国家现代柑桔产业园」开头）。
    # 这类碎片有个铁的特征：**同批候选里存在包含它的更长词条**。
    # 长词优先替换本来就会先吃掉长词，短条目不仅冗余，还会把替换后的正文
    # 咬出「国某代柑桔产业园」这种半截货——落地前把真子串全部消除。
    if mapping:
        terms_all = [t for t, _p, _c in mapping]
        keep = []
        for t, ph, cat in mapping:
            covered = any(t != o and t in o for o in terms_all)
            if covered:
                continue
            keep.append((t, ph, cat))
        if len(keep) != len(mapping):
            print("  子串消除：丢弃 %d 条碎片（同批候选中存在包含它的更长词条）"
                  % (len(mapping) - len(keep)), file=sys.stderr)
        mapping = keep

    if args.json:
        print(json.dumps([{"term": t, "placeholder": p, "cat": c} for t, p, c in mapping],
                         ensure_ascii=False, indent=2))
        return 0

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.input)),
                                   "自动识敏词表.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# 本词表由本地千问（%s）自动识别生成\n" % args.model)
        f.write("# 用途：给 desensitize.py 做替换。请人工复核后再使用！\n")
        f.write("# 审核要点：① 该脱的有没有漏 ② 不该脱的有没有误伤 ③ 替换词是否合适\n")
        f.write("# ===== 以下为自动生成的规则（格式：原词=替换词）=====\n")
        for term, ph, cat in mapping:
            f.write("%s=%s\n" % (term, ph))

    print("自动识敏词表：", out)
    print("共识别 %d 条（已按出现频次排序）" % len(mapping))
    if not mapping:
        print("提示：没识别到专有名词。可能文本本身不含具体人名公司名，或模型需更强（可换 14B）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
