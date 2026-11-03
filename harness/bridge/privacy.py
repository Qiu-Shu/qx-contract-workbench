"""Local upload redaction. Only the generated UTF-8 text may leave the vault.

Extraction reuses reader.py and the existing cn_contract local OCR runtime.
See privacy_sources.md for sources, scope and deliberate limitations.
"""
import argparse
from contextlib import contextmanager
import hashlib
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


def _candidates(text, custom_terms):
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
        add(value, '组织')
    for pattern in (_LABEL_NAMES, _TITLE_NAMES):
        for match in pattern.finditer(text):
            add(match['value'], '姓名')
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


def _redact(text, custom_terms, mapping_path):
    candidates = _candidates(text, custom_terms)
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
        relevant = [original for original in mapping if original in text]
        if not relevant:
            return text, 0
        pattern = re.compile('|'.join(re.escape(value) for value in sorted(relevant, key=lambda value: (-len(value), value))))
        count = 0
        custom = {unicodedata.normalize('NFC', term.strip()) for term in custom_terms}
        def replace(match):
            nonlocal count
            original = match.group()
            if (original not in custom and kinds[original] in {'身份证', '电话', '银行账号'}
                    and (re.match(r'\s*(?:元|万元|亿元)', text[match.end():])
                         or re.search(r'(?:金额|价款|人民币|RMB|CNY|[￥¥])\s*[:：]?\s*$', text[max(0, match.start()-16):match.start()]))):
                return original
            count += 1
            return mapping[original]
        return pattern.sub(replace, text), count


def prepare_upload(source_path, vault_dir, document_id=None, custom_terms=None, context_id=None, workspace_dir=None):
    """Return only safe-copy metadata. Original, mapping and index stay private.

    The caller must keep the vault and upload staging outside every model-accessible
    directory, and copy ONLY safe_path to its attachment store after status=ready.
    A context_id is an explicit per-case/batch boundary, never an automatic history.
    """
    safe_path = None
    try:
        if not isinstance(source_path, str) or not isinstance(vault_dir, str):
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
        safe, count = _redact(text, custom_terms, mapping_path)
        safe_dir = _private_child(vault, 'safe')
        safe_dir.mkdir(exist_ok=True)
        # The output name never incorporates a source name, case name or supplied id.
        display_name = '脱敏文字-' + uuid4().hex[:16] + '.txt'
        safe_path = _private_child(vault, 'safe', display_name)
        with safe_path.open('x', encoding='utf-8', newline='\n') as output:
            output.write(safe)
        manifest.update(safe_file=safe_path.relative_to(vault).as_posix(),
                        mapping_file=mapping_path.relative_to(vault).as_posix(), replacement_count=count)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        return {'status': 'ready', 'safe_path': str(safe_path), 'display_name': display_name,
                'replacement_count': count, 'warnings': list(WARNINGS)}
    except Exception as error:
        if safe_path is not None and safe_path.exists():
            safe_path.unlink(missing_ok=True)
        code = error.code if isinstance(error, PrivacyError) else 'PARSE_FAILED'
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
            parser.add_argument('--term', action='append', default=[])
            arguments = parser.parse_args()
            payload = {'source_path': arguments.source, 'vault_dir': arguments.vault,
                       'workspace_dir': arguments.workspace, 'context_id': arguments.context_id,
                       'custom_terms': arguments.term}
        else:
            payload = json.load(sys.stdin)
        with _quiet_libraries():
            result = prepare_upload(**payload)
    except Exception:
        result = {'status': 'failed', 'error_code': 'INVALID_INPUT', 'error': ERRORS['INVALID_INPUT'], 'warnings': []}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
