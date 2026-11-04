"""Restricted local DOCX field filling; preserves templates and existing drafts."""
from hashlib import sha256
from io import BytesIO
import math
import re
from zipfile import BadZipFile, ZipFile

from jinja2 import StrictUndefined, TemplateError, nodes
from jinja2.sandbox import SandboxedEnvironment
from lxml.etree import XMLSyntaxError
from docx_delivery import _filename, _publish, _store, _string, _xml

MAX_ARCHIVE = 10 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024


class FieldEnvironment(SandboxedEnvironment):
    """Only literal text and scalar variable names, in every rendered DOCX part."""
    def __init__(self):
        super().__init__(undefined=StrictUndefined, autoescape=True)
        self.globals.clear()
        self.filters.clear()
        self.tests.clear()
        self.variables = set()

    def _parse(self, source, name, filename):
        if '{%' in source or '{#' in source:
            raise ValueError('模板只支持 {{ 字段名 }}，不执行循环、语句或模板注释。')
        tree = super()._parse(source, name, filename)
        for node in tree.find_all(nodes.Node):
            if type(node) not in (nodes.Output, nodes.TemplateData, nodes.Name):
                raise ValueError('模板只支持字段名，不支持属性、调用、运算或过滤器。')
            if isinstance(node, nodes.Name):
                if not node.name.isidentifier() or node.name.startswith('_'):
                    raise ValueError('请使用不以下划线开头的简单字段名。')
                self.variables.add(node.name)
        return tree


def _package(data):
    if len(data) > MAX_ARCHIVE:
        raise ValueError('模板超过10MB，请精简图片后重试。')
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) > 2000 or len(entries) != len({e.filename for e in entries})
                    or sum(e.file_size for e in entries) > MAX_EXPANDED):
                raise ValueError('模板部件重复、过多或解压后超过40MB。')
            parts = {e.filename: archive.read(e) for e in entries}
        if 'word/document.xml' not in parts:
            raise ValueError('不是完整的Word模板。')
        for name, body in parts.items():
            lower = name.lower()
            if ('vbaproject' in lower or '/embeddings/' in lower or '/activex/' in lower
                    or lower.endswith(('.htm', '.html'))):
                raise ValueError('模板不能包含宏、嵌入对象或外部格式部件。')
            if lower.endswith(('.xml', '.rels')):
                tree = _xml(body)
                if lower.endswith('.rels') and any(
                    e.get('TargetMode', '').lower() == 'external' or
                    re.match(r'^(?:[a-z][a-z0-9+.-]*:|[/\\]{2})', e.get('Target', ''), re.I)
                    for e in tree.iter()):
                    raise ValueError('模板含外部链接，请移除外部链接后另存空白模板。')
                if lower == '[content_types].xml' and any(token in body.lower() for token in
                        (b'macroenabled', b'vbaproject', b'oleobject', b'activex')):
                    raise ValueError('模板不能包含宏或嵌入对象。')
                instructions = []
                for element in tree.iter():
                    if element.tag.endswith(('}object', '}OLEObject', '}control', '}altChunk')):
                        raise ValueError('模板不能包含嵌入对象、控件或外部格式部件。')
                    if element.tag.endswith(('}instrText', '}fldSimple')):
                        instructions.append(''.join(element.itertext()) + ''.join(element.attrib.values()))
                if re.search(r'DDE|INCLUDETEXT|INCLUDEPICTURE|LINK', ''.join(instructions), re.I):
                    raise ValueError('模板含外部数据域，请转为普通文字后重试。')
        return parts
    except (BadZipFile, KeyError, RuntimeError, UnicodeError, XMLSyntaxError, NotImplementedError) as error:
        raise ValueError('Word模板损坏或包含不支持的部件，原件未修改。') from error


def _prepare(workspace, path):
    store = _store(workspace)
    source = store.safe(path)
    if source.suffix.lower() != '.docx' or source.stat().st_size > MAX_ARCHIVE:
        raise ValueError('请选择工作区内不超过10MB的 .docx 空白模板。')
    data = source.read_bytes()
    parts = _package(data)
    try:
        from docxtpl import DocxTemplate
    except ImportError:
        raise ValueError('本机未安装docxtpl，请安装项目候选依赖后重试。') from None
    template = DocxTemplate(BytesIO(data))
    env = FieldEnvironment()
    try:
        for name, body in parts.items():
            if name.endswith(('.xml', '.rels')):
                text = body.decode('utf-8')
                if any(token in text for token in ('{{', '{%', '{#')):
                    if not re.fullmatch(r'word/(?:document|header\d*|footer\d*|footnotes)\.xml|docProps/core\.xml', name):
                        raise ValueError('模板变量只能放在正文、页眉页脚、脚注或文档属性中。')
                    env.parse(template.patch_xml(text))
    except TemplateError:
        raise ValueError('模板字段语法无效，请使用 {{ 字段名 }}。') from None
    if not 1 <= len(env.variables) <= 100:
        raise ValueError('空白模板须包含1至100个字段名。')
    return store, source, data, template, env


def inspect_custom_word_template(store, path):
    store, source, data, _, env = _prepare(store, path)
    return {'variables': sorted(env.variables), 'source_sha256': sha256(data).hexdigest(),
            'source_path': str(source), 'relative_path': source.relative_to(store.root).as_posix(),
            'notice': '先核对模板固定正文中的姓名、金额、案情；固定文字不会自动清除。仅支持简单字段填充。'}


def render_custom_word_template(store, path, filename, data, *, source_sha256):
    _filename(filename)
    store, source, original, template, env = _prepare(store, path)
    digest = sha256(original).hexdigest()
    if source_sha256 != digest:
        raise ValueError('模板版本变化，请重新检查模板字段和正文。')
    if not isinstance(data, dict) or set(data) != env.variables:
        raise ValueError('填写字段必须与模板变量一致；缺失或多余字段请核对，不自动猜测。')
    for value in data.values():
        if type(value) not in (str, int, float, bool) or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError('字段只支持文字、有限数字或布尔值，不支持对象和列表。')
        _string(str(value), '字段')
        if len(str(value)) > 50000:
            raise ValueError('单字段超过50000字，请拆分文档。')
    if sum(len(str(value)) for value in data.values()) > 200000:
        raise ValueError('本次填写内容过多，请拆分文档。')
    try:
        template.render(data, jinja_env=env, autoescape=True)
        output = BytesIO()
        template.save(output)
        result = output.getvalue()
        _package(result)
    except TemplateError:
        raise ValueError('模板渲染未完成，请检查字段语法和值；原件未修改。') from None
    if sha256(store.safe(path).read_bytes()).hexdigest() != digest:
        raise ValueError('生成期间模板变化，本次未发布草稿，请重新检查。')
    return {**_publish(store, filename, result), 'source_path': str(source),
            'source_sha256': digest, 'status': 'draft',
            'notice': '已另存Word草稿。固定模板文字会保留，请复核事实、金额与格式。'}
