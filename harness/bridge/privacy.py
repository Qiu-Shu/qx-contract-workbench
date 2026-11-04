"""Local upload redaction. Only the generated UTF-8 text may leave the vault.

Extraction reuses reader.py and the existing cn_contract local OCR runtime.
See privacy_sources.md for sources, scope and deliberate limitations.
"""
import argparse
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import unicodedata
from uuid import UUID, uuid4

import reader
from store import MaterialStore, SUPPORTED


WARNINGS = [
    '上传的是脱敏文字副本，版式、图片、批注、修订记录、嵌入对象及其他未提取内容不随副本上传；原件另存本机。',
    '本机规则可能漏掉姓名、组织、地址或间接识别信息；可补充自定义敏感词并核对副本，不能保证完全匿名。',
    '金额和日期默认保留；OCR 文字仍需核对数字、日期及否定词。',
]
ERRORS = {
    'INVALID_INPUT': '脱敏参数无效，未生成可上传副本。',
    'VAULT_BOUNDARY': '私有原件目录必须位于模型工作区之外，未生成可上传副本。',
    'UNSUPPORTED_FORMAT': '此格式无法生成脱敏文字副本，未上传原件。',
    'NO_READABLE_TEXT': '未识别到可读文字，未生成可上传副本；请检查材料或换用清晰文件。',
    'RESOURCE_LIMIT': '当前可用内存不足以完成脱敏，未生成可上传副本。',
    'SOURCE_CHANGED': '处理时源文件发生变化，未生成可上传副本，请保存完成后重试。',
    'PARSE_FAILED': '本机解析或脱敏未完成，未生成可上传副本；原件不会自动上传。',
    'DOCUMENT_EXISTS': '此文档标识已使用，请重新上传以生成独立副本。',
}


class PrivacyError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _reject_links(path):
    for current in (path, *path.parents):
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise PrivacyError('INVALID_INPUT')


def _private_child(root, *parts):
    target = root.joinpath(*parts)
    _reject_links(target)
    if not target.resolve().is_relative_to(root):
        raise PrivacyError('VAULT_BOUNDARY')
    return target


def _copy_original(source, destination):
    before = source.stat()
    digest = hashlib.sha256()
    with source.open('rb') as incoming, destination.open('xb') as output:
        while block := incoming.read(1024 * 1024):
            digest.update(block)
            output.write(block)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise PrivacyError('SOURCE_CHANGED')
    return digest.hexdigest()


def _extract(document_dir, original):
    store = MaterialStore(document_dir)
    store.register(original)
    page = 1
    while True:
        result = reader.parse(store, original, start_page=page, page_count=20)
        if result['status'] not in {'ready', 'partial'}:
            raise PrivacyError('NO_READABLE_TEXT')
        following = result.get('next_page')
        if following is None:
            break
        if following <= page:
            raise PrivacyError('PARSE_FAILED')
        page = following
    with store.db() as db:
        count = db.execute('SELECT COALESCE(SUM(length(text)),0) FROM chunks').fetchone()[0]
        if count * 8 > reader.available_memory() // 4:
            raise PrivacyError('RESOURCE_LIMIT')
        chunks = db.execute('SELECT location,text FROM chunks ORDER BY ordinal')
        pieces = []
        plain = original.suffix in {'.txt', '.md', '.csv', '.tsv', '.json'}
        for location, value in chunks:
            # Preserve identifiers split at reader's 4,000-character chunk boundary.
            continuation = plain or not location.endswith(':chars:0-' + str(len(value)))
            pieces.append(('' if continuation or not pieces else '\n') + value)
    text = unicodedata.normalize('NFC', ''.join(pieces))
    if not any(character.isalnum() for character in text) or '\x00' in text:
        raise PrivacyError('NO_READABLE_TEXT')
    return text


_LABEL_NAMES = re.compile(
    r'(?:姓名|联系人|法定代表人|负责人|经办人|签署人|委托代理人|法定代理人|原告|被告|申请人|被申请人|甲方|乙方)'
    r'\s*[:：]\s*(?P<value>[\u3400-\u9fff·]{2,8})(?=$|[\s，。；:：、,;.（(])')
_TITLE_NAMES = re.compile(r'(?<![\u3400-\u9fff])(?P<value>[\u3400-\u9fff]{2,4})(?:先生|女士)')
_ADDRESSES = re.compile(
    r'(?:住所地?|住址|联系地址|送达地址|通讯地址|地址|户籍地|居住地)\s*[:：]\s*'
    r'(?P<value>[^\n\r，,。；;]{3,120})')
_STREET = re.compile(r'[\u3400-\u9fff]{2,30}(?:省|市|区|县)[\u3400-\u9fff0-9]{2,40}'
                     r'(?:路|街|巷|弄)[0-9一二三四五六七八九十百\-]{1,10}号(?:[0-9A-Za-z一二三四五六七八九十栋幢单元室楼层\-]{0,20})')
_ORGANIZATIONS = re.compile(
    r'[\u3400-\u9fffA-Za-z0-9（）()·]{2,80}?'
    r'(?:有限责任公司|股份有限公司|有限公司|合伙企业|律师事务所|会计师事务所|研究院|研究所|医院|学校|银行)')
_LABELED_NUMBERS = re.compile(
    r'(?P<label>银行卡(?:号)?|银行账号|银行账户|收款账号|账户号码|账号|身份证(?:号码|号)?|统一社会信用代码|护照(?:号码|号)?)'
    r'\s*[:：]?\s*(?P<value>[A-Za-z0-9][A-Za-z0-9 \-]{5,35}[A-Za-z0-9])')
_PATTERNS = [
    ('邮箱', re.compile(r'(?<![\w.+\-])[-\w.+]+@[\w\-]+(?:\.[\w\-]+)+')),
    ('身份证', re.compile(r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)')),
    ('电话', re.compile(r'(?<!\d)(?:\+?86[ \-]?)?1[3-9]\d(?:[ \-]?\d){8}(?!\d)')),
    ('电话', re.compile(r'(?<!\d)(?:\+?86[ \-]?)?0\d{2,3}[ \-]\d{7,8}(?:[ \-]\d{1,6})?(?!\d)')),
    ('组织代码', re.compile(r'(?<![A-Za-z0-9])[159Y][1239]\d{6}[0-9A-HJ-NPQRTUWXY]{10}(?![A-Za-z0-9])')),
]

# Only explicit naming contexts establish a brand/product identity. Quotation
# marks alone, and generic technical/organization categories, are not identities.
_GENERIC_VALUES = {'四轮驱动产品体系', '合同', '协议', '技术服务', '服务', '学校', '机构', '企业', '公司', '产品',
                   '品牌', '模型', '系统', '平台', '相关资料', '知名', '自有', '自主', '旗下',
                   '甲方', '乙方', '丙方', '丁方', '双方', '本公司', '该公司', '本合同', '本协议',
                   '本项目', '采购方', '供应方', '买方', '卖方', '委托方', '受托方'}
_GENERIC_ORG = re.compile(
    r'(?:(?:中小|中小学|普通|公办|公立|民办|私立|职业|高等|义务教育|特殊教育|各类|农村|乡村|城市|教育|医疗|金融|商业))*'
    r'(?:学校|中小学|高校|大学|小学|中学|医院|银行|研究院|研究所|机构|公司|企业|单位|律师事务所)')
_GENERIC_ORG_PREFIX = re.compile(
    r'^(?:(?:本合同|本协议|本项目|本公司|该公司|甲方|乙方|合同|企业|公司|我们|主要|累计|现已|已经|已|目前|'
    r'服务|覆盖|面向|提供|对接|合作|约定|涉及|支持|包括|本次|按|应|须|需|将|共计|共|全国|全市|全省|为|向|和|与|及)|'
    r'[0-9一二三四五六七八九十百千万两]+|超过|近|约|余|多|所|家|个)+')
_GENERIC_PRODUCT = re.compile(
    r'(?:(?:AI|人工智能|数字人|通用|智能|测评|心理|训练|教育|教学|学习|语言|大语言|文本|知识|问答|'
    r'行为|认知|情绪|能力|个人|成长|个性化|综合|青少年|学生|技术|信息|数字|自主|自有|基础|管理|数据|服务|原有|现有|既有|相关|产品))*'
    r'(?:引擎|大模型|模型|平台|系统|产品|工具|方案|体系|服务|机器人)', re.I)
_NAMING_LABEL = r'(?:品牌(?:名称|名)?|产品(?:名称|名|体系|系列)|平台名称|系统名称|模型名称|自有模型|(?:以下)?简称|以下简称)'
_NAME_BODY = r'[^\n\r，,。；;：:“”"「」《》（）()]{2,80}'
_NAMED_LABELLED = re.compile(_NAMING_LABEL + r'\s*[:：]\s*[“"「《]?(?P<value>' + _NAME_BODY + r')')
_NAMED_QUOTED = re.compile(_NAMING_LABEL + r'\s*(?:为|是|名为|叫做)?\s*[“"「《](?P<value>' + _NAME_BODY + r')[”"」》]')
_NAMED_AFTER_QUOTE = re.compile(r'[“"「《](?P<value>' + _NAME_BODY + r')[”"」》]\s*'
                                r'(?:品牌|产品(?:体系|系列)?|(?:学习|语言|教育|AI)?大模型|训练体系|测评体系)')
_NAMED_BARE = re.compile(r'(?P<value>[\u3400-\u9fffA-Za-z0-9·._\-]{2,60}?)(?P<suffix>品牌|产品体系|训练体系|测评体系|大模型)'
                         r'(?=$|[\s，,。；;、（）()]|及|和|与|已)')
_ENTITY_PREFIX = re.compile(r'^(?:(?:甲方|乙方|本公司|该公司|公司|其|产品包括|包括|但不限于|不限于|保证|承诺|确保|基于|依托|采用|使用|以及|或|和|与|自主研发|自主开发|自主|自研|研发|开发|推出|打造|保护|维持|旗下|拥有|的))+')
_FILING_NUMBER = re.compile(r'(?:备案编号|备案号|备案编码|备案标识)\s*[:：]?\s*'
                            r'(?P<value>[\u3400-\u9fffA-Za-z0-9][\u3400-\u9fffA-Za-z0-9_\-/]{3,100})')
_COMPETITION = re.compile(r'[《“"](?P<value>[^》”"\n\r]{2,100}(?:大赛|比赛|赛事|竞赛|挑战赛|锦标赛|联赛))[》”"]')
_BARE_COMPETITION = re.compile(r'(?:参加|参与|承办|主办|举办|开展|及|、|：|:)'
    r'(?P<value>[\u3400-\u9fffA-Za-z0-9]{2,60}?(?:大赛|比赛|竞赛|挑战赛|锦标赛|联赛))'
    r'(?=$|[\s，,。；;、（）()]|等|四大板块|四项)')
_GENERIC_COMPETITION = re.compile(
    r'(?:(?:全国|全市|全省|国家级|省级|市级|国际|校园|学校|校内|校际|青少年|中小学|学生|儿童|成人|中学生|小学生|大学生|'
    r'机器人|编程|数学|英语|科学|科技|人工智能|AI|体育|篮球|足球|作文|创新|创业|知识|白名单))*'
    r'(?:大赛|比赛|赛事|竞赛|挑战赛|锦标赛|联赛)', re.I)
_QUALIFICATIONS = re.compile(
    r'(?:国家(?:级)?|省级|市级)?(?:高新技术企业|专精特新(?:小巨人|中小)?企业|科技型中小企业|创新型中小企业|'
    r'瞪羚企业|独角兽企业|企业技术中心|工程技术研究中心)|教育部白名单(?:赛事|项目)?')
_COVERAGE_NUMBER = r'(?:全国|全省|全市)?(?:超过|逾|超|近|约)?[0-9一二三四五六七八九十百千万两,，]+(?:余|多|以上|\+)?(?:所|家|个)'
_COVERAGE_ORG = r'(?:中小学校|中小学|高等学校|公办学校|民办学校|学校|医院|教育机构|医疗机构|机构|企业|单位)'
_COVERAGE = re.compile(r'(?:累计(?:已)?|已累计|现已|目前已|已|先后)(?:服务|覆盖|接入|合作)\s*'
                       r'(?P<value>' + _COVERAGE_NUMBER + _COVERAGE_ORG + r')')
_COVERAGE_LABEL = re.compile(r'(?:累计服务|已服务|覆盖|合作)(?:学校|医院|机构)(?:数量|数|规模)\s*[:：]\s*'
                             r'(?P<value>' + _COVERAGE_NUMBER + r'(?:' + _COVERAGE_ORG + r')?)')
_COVERAGE_POSTFIX = re.compile(r'(?:累计|现已|已|先后)?(?:服务|覆盖|接入|合作)' + _COVERAGE_ORG +
                               r'\s*(?P<value>' + _COVERAGE_NUMBER + r')')
_COVERAGE_REGIONS = re.compile(r'(?:已|现已|累计)?覆盖\s*(?P<value>' + _COVERAGE_NUMBER +
                               r'(?:省区市|省市区|省市|省份|省|自治区|城市|地市|地区))')
_ASSOCIATION_APPOINTMENT = re.compile(
    r'(?P<value>(?:中国|全国|[\u3400-\u9fff]{2,8}(?:省|市|区))[^\n\r，,。；;]{2,50}?'
    r'(?:协会|学会|联合会)[^\n\r，,。；;]{0,65}?(?:实施运营单位|实施单位|运营单位|授权单位|指定单位|会员单位))')
_HONORS = re.compile(r'(?:曾获(?:得)?|获得|获评|荣获|被授予|入选)\s*[“"《]?'
                     r'(?P<value>[^\n\r，,。；;“”"《》]{2,70}?(?:一等奖|二等奖|三等奖|特等奖|金奖|银奖|铜奖|荣誉称号|优秀企业|示范企业))')
_DEEP_KINDS = {'资质头衔', '机构覆盖规模', '荣誉'}


def _generic_organization(value):
    stripped = _GENERIC_ORG_PREFIX.sub('', value)
    quantified_category = re.search(r'[0-9一二三四五六七八九十百千万两]+(?:余|多)?(?:所|家|个)'
                                     + _GENERIC_ORG.pattern + r'$', value)
    return value in _GENERIC_VALUES or bool(_GENERIC_ORG.fullmatch(stripped) or quantified_category)


def _specific_name(value):
    return (len(value) >= 2 and value not in _GENERIC_VALUES
            and not _generic_organization(value) and not _GENERIC_PRODUCT.fullmatch(value)
            and not re.fullmatch(r'[\d\s.\-/]+', value))


def _product_identity(value, known=()):
    value = _ENTITY_PREFIX.sub('', value)
    if not _specific_name(value):
        return None
    # Keep the generic suffix in the sentence, so the full name and a named
    # module share one reversible identity instead of inventing several objects.
    if value.endswith('大模型') and _specific_name(value[:-3]):
        value = value[:-3]
    # Prefer established names over a regex's longer grammatical phrase.
    for identity in sorted(known, key=len, reverse=True):
        if value.endswith(identity):
            return identity
    if re.search(r'不得|不应|不使用|并非|必须|不能|禁止|应当|本项目|该系统', value) or value.startswith(('将', '就')):
        return None
    return value


def _profile_quantity(text, start):
    clause = re.split(r'[。；;\n]', text[max(0, start-200):start])[-1]
    return not re.search(r'本合同|本协议|本项目|本次|本期|约定|交付|履行|验收|应当|必须|计划', clause)


def _candidates(text, custom_terms, privacy_mode='standard'):
    found = {}
    def add(value, kind):
        value = value.strip()
        if value:
            found.setdefault(value, kind)

    for term in custom_terms:
        add(unicodedata.normalize('NFC', term), '自定义')
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            add(match.group(), kind)
    for match in _LABELED_NUMBERS.finditer(text):
        label = match['label']
        kind = '身份证' if '身份证' in label else '组织代码' if '信用代码' in label else '护照' if '护照' in label else '银行账号'
        add(match['value'], kind)
    for match in _ORGANIZATIONS.finditer(text):
        value = re.sub(r'^(?:本合同由|甲方|乙方|原告|被告|申请人|被申请人|与|和|向|由|及)+', '', match.group())
        if not _generic_organization(value):
            add(value, '组织')
    for pattern in (_LABEL_NAMES, _TITLE_NAMES):
        for match in pattern.finditer(text):
            if _specific_name(match['value']):
                add(match['value'], '姓名')
    for pattern in (_NAMED_LABELLED, _NAMED_QUOTED, _NAMED_AFTER_QUOTE):
        for match in pattern.finditer(text):
            value = match['value'].strip()
            identity = _product_identity(value)
            if identity:
                add(identity, '专名')
    for match in sorted(_NAMED_BARE.finditer(text), key=lambda match: len(match['value'])):
        value = _ENTITY_PREFIX.sub('', match['value'])
        value = value if match['suffix'] == '品牌' else value + match['suffix']
        identity = _product_identity(value, [name for name, kind in found.items() if kind == '专名'])
        if identity:
            add(identity, '专名')
    for match in _FILING_NUMBER.finditer(text):
        if re.search(r'\d', match['value']):
            add(match['value'], '备案编号')
    for pattern in (_COMPETITION, _BARE_COMPETITION):
        for match in pattern.finditer(text):
            if not _GENERIC_COMPETITION.fullmatch(match['value']):
                add(match['value'], '赛事')
    if privacy_mode == 'deep':
        for match in _QUALIFICATIONS.finditer(text):
            add(match.group(), '资质头衔')
        for match in _ASSOCIATION_APPOINTMENT.finditer(text):
            add(match['value'], '资质头衔')
        for pattern in (_COVERAGE, _COVERAGE_LABEL, _COVERAGE_POSTFIX, _COVERAGE_REGIONS):
            for match in pattern.finditer(text):
                if _profile_quantity(text, match.start()):
                    add(match['value'], '机构覆盖规模')
        for match in _HONORS.finditer(text):
            # A leading award year/date is still a date, not a name to conceal.
            value = re.sub(r'^\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?(?:度)?\s*', '', match['value'])
            if not re.search(r'\d{4}[-/年]\d{1,2}', value):
                add(value, '荣誉')
    for match in _ADDRESSES.finditer(text):
        value = re.split(r'\s+(?:电话|手机|邮箱|联系人|身份证|邮编)\s*[:：]', match['value'])[0]
        add(value, '地址')
    for match in _STREET.finditer(text):
        add(match.group(), '地址')
    # Unlabelled long numbers: Luhn filters obvious dates/amounts; labeled account
    # numbers above deliberately need no checksum so OCR errors are still masked.
    for match in re.finditer(r'(?<!\d)[3-6]\d{15,18}(?!\d)', text):
        if re.match(r'\s*(?:元|万元|亿元)', text[match.end():]):
            continue
        digits = [int(c) for c in match.group()]
        total = sum((n * 2 - 9 if n * 2 > 9 else n * 2) if i % 2 else n
                    for i, n in enumerate(reversed(digits)))
        if total % 10 == 0:
            add(match.group(), '银行账号')
    return found


def _redact(text, custom_terms, mapping_path, privacy_mode='standard'):
    candidates = _candidates(text, custom_terms, privacy_mode)
    with sqlite3.connect(mapping_path, timeout=60) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS replacements(original TEXT PRIMARY KEY,kind TEXT NOT NULL,token TEXT UNIQUE NOT NULL)')
        prefix_row = db.execute("SELECT value FROM metadata WHERE key='prefix'").fetchone()
        prefix = prefix_row[0] if prefix_row else uuid4().hex[:12]
        if '【脱敏-' + prefix + '-' in text:
            # Existing placeholders in a source would make local restoration ambiguous.
            raise PrivacyError('INVALID_INPUT')
        db.execute("INSERT OR IGNORE INTO metadata VALUES('prefix',?)", (prefix,))
        rows = db.execute('SELECT original,kind,token FROM replacements').fetchall()
        mapping = {original: token for original, _, token in rows}
        kinds = {original: kind for original, kind, _ in rows}
        for original, kind in candidates.items():
            if original not in mapping:
                token = '【脱敏-' + prefix + '-' + kind + '-' + str(len(mapping) + 1) + '】'
                db.execute('INSERT INTO replacements VALUES(?,?,?)', (original, kind, token))
                mapping[original] = token
                kinds[original] = kind
        def active(original):
            if original in candidates:
                return True
            kind = kinds[original]
            # Keep the dictionary for restoration/token stability, but never let
            # old generic errors, removed custom terms or a deep run change this
            # upload's mode. Confirmed names still carry across case documents.
            if kind in _DEEP_KINDS or kind == '自定义':
                return False
            if kind == '组织':
                return not _generic_organization(original)
            if kind == '专名':
                known = [name for name, category in candidates.items() if category == '专名' and name != original]
                return _product_identity(original, known) == original
            if kind == '姓名':
                return _specific_name(original)
            return True
        relevant = [original for original in mapping if original in text and active(original)]
        if not relevant:
            return text, 0
        pattern = re.compile('|'.join(re.escape(value) for value in sorted(relevant, key=lambda value: (-len(value), value))))
        count = 0
        custom = {unicodedata.normalize('NFC', term.strip()) for term in custom_terms}
        def replace(match):
            nonlocal count
            original = match.group()
            # The same count can describe a company profile and a contractual
            # obligation. A global dictionary must not erase the latter.
            if (original not in custom and candidates.get(original, kinds[original]) == '机构覆盖规模'
                    and not _profile_quantity(text, match.start())):
                return original
            if (original not in custom and kinds[original] in {'身份证', '电话', '银行账号'}
                    and (re.match(r'\s*(?:元|万元|亿元)', text[match.end():])
                         or re.search(r'(?:金额|价款|人民币|RMB|CNY|[￥¥])\s*[:：]?\s*$', text[max(0, match.start()-16):match.start()]))):
                return original
            count += 1
            return mapping[original]
        return pattern.sub(replace, text), count


def prepare_upload(source_path, vault_dir, document_id=None, custom_terms=None, context_id=None, workspace_dir=None,
                   privacy_mode='standard', review=False):
    """Return only safe-copy metadata. Original, mapping and index stay private.

    The caller must keep the vault and upload staging outside every model-accessible
    directory, and copy ONLY safe_path to its attachment store after status=ready.
    A context_id is an explicit per-case/batch boundary, never an automatic history.
    """
    safe_path = None
    try:
        if not isinstance(source_path, str) or not isinstance(vault_dir, str):
            raise PrivacyError('INVALID_INPUT')
        if privacy_mode not in ('standard', 'deep') or not isinstance(review, bool):
            raise PrivacyError('INVALID_INPUT')
        source, vault = Path(source_path), Path(vault_dir)
        if not source.is_absolute() or not vault.is_absolute():
            raise PrivacyError('INVALID_INPUT')
        _reject_links(source)
        _reject_links(vault)
        source, vault = source.resolve(), vault.resolve()
        workspace = Path(workspace_dir).resolve() if workspace_dir else Path(__file__).resolve().parents[1] / 'workspace'
        if vault.is_relative_to(workspace) or workspace.is_relative_to(vault):
            raise PrivacyError('VAULT_BOUNDARY')
        if not source.is_file():
            raise PrivacyError('INVALID_INPUT')
        if source.suffix.lower() not in SUPPORTED:
            raise PrivacyError('UNSUPPORTED_FORMAT')
        if custom_terms is None:
            custom_terms = []
        if not isinstance(custom_terms, list) or any(not isinstance(term, str) or not term.strip() for term in custom_terms):
            raise PrivacyError('INVALID_INPUT')
        if context_id is not None and (not isinstance(context_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', context_id)):
            raise PrivacyError('INVALID_INPUT')
        identifier = str(UUID(document_id)) if document_id is not None else str(uuid4())
        vault.mkdir(parents=True, exist_ok=True)
        documents = _private_child(vault, 'documents')
        documents.mkdir(exist_ok=True)
        document_dir = _private_child(vault, 'documents', identifier)
        try:
            document_dir.mkdir()
        except FileExistsError:
            raise PrivacyError('DOCUMENT_EXISTS') from None
        original = document_dir / ('original' + source.suffix.lower())
        digest = _copy_original(source, original)
        manifest = {
            'document_id': identifier, 'original_path': str(source), 'sha256': digest,
            'context_hash': hashlib.sha256(context_id.encode()).hexdigest() if context_id else None,
            'privacy_mode': privacy_mode,
        }
        manifest_path = document_dir / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        text = _extract(document_dir, original)
        mapping_path = document_dir / 'mapping.sqlite'
        if context_id:
            contexts = _private_child(vault, 'contexts')
            contexts.mkdir(exist_ok=True)
            context_dir = _private_child(vault, 'contexts', hashlib.sha256(context_id.encode()).hexdigest())
            context_dir.mkdir(exist_ok=True)
            mapping_path = _private_child(vault, 'contexts', context_dir.name, 'mapping.sqlite')
        safe, count = _redact(text, custom_terms, mapping_path, privacy_mode)
        safe_dir = _private_child(vault, 'safe')
        safe_dir.mkdir(exist_ok=True)
        # The output name never incorporates a source name, case name or supplied id.
        display_name = ('深度脱敏文字-' if privacy_mode == 'deep' else '脱敏文字-') + uuid4().hex[:16] + '.txt'
        safe_path = _private_child(vault, 'safe', display_name)
        with safe_path.open('x', encoding='utf-8', newline='\n') as output:
            output.write(safe)
        manifest.update(safe_file=safe_path.relative_to(vault).as_posix(),
                        mapping_file=mapping_path.relative_to(vault).as_posix(), replacement_count=count)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        warnings = list(WARNINGS)
        if privacy_mode == 'deep':
            warnings.append('深度脱敏另隐去资质头衔、机构覆盖规模与荣誉等间接标识；副本不能用于判断这些业务事实，请回看本机原件。')
        result = {'status': 'ready', 'safe_path': str(safe_path), 'display_name': display_name,
                  'privacy_mode': privacy_mode, 'replacement_count': count, 'warnings': warnings}
        if review:
            with sqlite3.connect(mapping_path) as db:
                replacements = [{'original': value, 'token': token} for value, token in
                                db.execute('SELECT original,token FROM replacements') if token in safe]
            preview = {'document_id': identifier, 'review_token': uuid4().hex,
                       'original_text': text, 'safe_text': safe, 'display_name': display_name,
                       'privacy_mode': privacy_mode, 'replacement_count': count,
                       'replacements': replacements, 'warnings': warnings}
            review_path = document_dir / 'review.json'
            review_path.write_text(json.dumps(preview, ensure_ascii=False), encoding='utf-8')
            result['review_path'] = str(review_path)
        return result
    except Exception as error:
        if safe_path is not None and safe_path.exists():
            safe_path.unlink(missing_ok=True)
        code = error.code if isinstance(error, PrivacyError) else 'PARSE_FAILED'
        return {'status': 'failed', 'error_code': code, 'error': ERRORS[code], 'warnings': []}


def finalize_review(vault_dir, document_id, review_token, text, manual_replacements=None, workspace_dir=None):
    """Store a new immutable reviewed copy; never rewrite the original or auto copy."""
    try:
        vault = Path(vault_dir)
        _reject_links(vault)
        vault = vault.resolve()
        workspace = Path(workspace_dir).resolve() if workspace_dir else Path(__file__).resolve().parents[1] / 'workspace'
        if vault.is_relative_to(workspace) or workspace.is_relative_to(vault):
            raise PrivacyError('VAULT_BOUNDARY')
        identifier = str(UUID(document_id))
        document = _private_child(vault, 'documents', identifier)
        review_path = _private_child(vault, 'documents', identifier, 'review.json')
        preview = json.loads(review_path.read_text(encoding='utf-8'))
        if not isinstance(review_token, str) or not hmac.compare_digest(review_token, preview['review_token']):
            raise PrivacyError('INVALID_INPUT')
        if not isinstance(text, str) or not text.strip() or '\x00' in text:
            raise PrivacyError('INVALID_INPUT')
        manual = manual_replacements if manual_replacements is not None else []
        if not isinstance(manual, list) or any(not isinstance(item, dict) or
                set(item) != {'original', 'token'} or not all(isinstance(v, str) and v for v in item.values())
                for item in manual):
            raise PrivacyError('INVALID_INPUT')
        revision = uuid4().hex
        name = '已复核脱敏文字-' + revision[:16] + '.txt'
        safe = _private_child(vault, 'safe', name)
        record = {'document_id': identifier, 'revision': revision, 'safe_file': 'safe/' + name,
                  'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                  'manual_replacements': manual, 'privacy_mode': preview['privacy_mode']}
        with safe.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        try:
            with (document / ('reviewed-' + revision + '.json')).open('x', encoding='utf-8') as stream:
                json.dump(record, stream, ensure_ascii=False)
        except Exception:
            safe.unlink(missing_ok=True)
            raise
        return {'status': 'ready', 'safe_path': str(safe), 'display_name': name,
                'privacy_mode': preview['privacy_mode'], 'revision': revision}
    except Exception as error:
        code = error.code if isinstance(error, PrivacyError) else 'INVALID_INPUT'
        return {'status': 'failed', 'error_code': code, 'error': ERRORS[code], 'warnings': []}


@contextmanager
def _quiet_libraries():
    # Native OCR/PDF libraries may write to file descriptors, not Python streams.
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, 'w') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            yield
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            for target, descriptor in zip((1, 2), saved):
                os.dup2(descriptor, target)
                os.close(descriptor)


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        if len(sys.argv) > 1:
            parser = argparse.ArgumentParser(description='生成本机脱敏文字副本')
            parser.add_argument('--source', required=True)
            parser.add_argument('--vault', required=True)
            parser.add_argument('--workspace')
            parser.add_argument('--context-id')
            parser.add_argument('--privacy-mode', choices=('standard', 'deep'), default='standard')
            parser.add_argument('--term', action='append', default=[])
            arguments = parser.parse_args()
            payload = {'source_path': arguments.source, 'vault_dir': arguments.vault,
                       'workspace_dir': arguments.workspace, 'context_id': arguments.context_id,
                       'custom_terms': arguments.term, 'privacy_mode': arguments.privacy_mode}
        else:
            payload = json.load(sys.stdin)
        with _quiet_libraries():
            action = payload.pop('action', 'prepare')
            if action not in {'prepare', 'confirm'}:
                raise PrivacyError('INVALID_INPUT')
            result = finalize_review(**payload) if action == 'confirm' else prepare_upload(**payload)
    except Exception:
        result = {'status': 'failed', 'error_code': 'INVALID_INPUT', 'error': ERRORS['INVALID_INPUT'], 'warnings': []}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
