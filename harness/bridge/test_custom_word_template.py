from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from docx import Document
from store import MaterialStore
from custom_word_template import inspect_custom_word_template, render_custom_word_template


def template(root, text='委托人：{{ client }}', name='模板.docx'):
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = '合成律所'
    doc.add_paragraph(text, style='Title')
    source = root / name
    doc.save(source)
    return source


def test_render_keeps_format_source_xml_characters_and_existing_output(tmp_path):
    store = MaterialStore(tmp_path)
    source = template(tmp_path)
    before = source.read_bytes()
    view = inspect_custom_word_template(store, source.name)
    assert view['variables'] == ['client']
    first = render_custom_word_template(store, source.name, '结果.docx', {'client':'甲 <乙> & 丙'}, source_sha256=view['source_sha256'])
    second = render_custom_word_template(store, source.name, '结果.docx', {'client':'丁'}, source_sha256=view['source_sha256'])
    assert first['path'] != second['path'] and source.read_bytes() == before
    result = Document(first['path'])
    assert result.paragraphs[0].text == '委托人：甲 <乙> & 丙'
    assert result.paragraphs[0].style.name == 'Title'
    assert result.sections[0].header.paragraphs[0].text == '合成律所'


@pytest.mark.parametrize('text', ['{{ client.__class__ }}', '{{ cycler() }}', '{% for x in client %}{{ x }}{% endfor %}', '{{ client|safe }}', '{{ 9*99999 }}'])
def test_expression_execution_is_rejected(tmp_path,text):
    store = MaterialStore(tmp_path)
    source = template(tmp_path,text)
    with pytest.raises(ValueError): inspect_custom_word_template(store,source.name)
    assert not (tmp_path/'drafts').exists()


def test_core_properties_also_use_restricted_environment(tmp_path):
    store = MaterialStore(tmp_path)
    source = template(tmp_path)
    doc=Document(source);doc.core_properties.title='{{ client.__class__ }}';doc.save(source)
    with pytest.raises(ValueError): inspect_custom_word_template(store,source.name)


def test_split_external_field_and_embedded_object_rejected(tmp_path):
    from docx.oxml import OxmlElement
    store=MaterialStore(tmp_path)
    source=template(tmp_path)
    doc=Document(source)
    for text in ['INCLUDE','TEXT "https://example.invalid/data"']:
        field=OxmlElement('w:instrText');field.text=text
        doc.paragraphs[0].add_run()._r.append(field)
    doc.save(source)
    with pytest.raises(ValueError):inspect_custom_word_template(store,source.name)
    source=template(tmp_path)
    doc=Document(source);doc.paragraphs[0].add_run()._r.append(OxmlElement('w:object'));doc.save(source)
    with pytest.raises(ValueError):inspect_custom_word_template(store,source.name)


def test_missing_stale_extra_fields_and_non_scalar_values_are_rejected(tmp_path):
    store=MaterialStore(tmp_path);source=template(tmp_path)
    view=inspect_custom_word_template(store,source.name)
    for data in ({},{'client':{}},{'client':'甲','unknown':'乙'},{'client':float('nan')}):
        with pytest.raises(ValueError): render_custom_word_template(store,source.name,'草稿.docx',data,source_sha256=view['source_sha256'])
    with pytest.raises(ValueError): render_custom_word_template(store,source.name,'草稿.docx',{'client':'甲'},source_sha256='0'*64)
    assert not (tmp_path/'drafts').exists()


def test_external_relationship_and_zip_expansion_rejected(tmp_path):
    store=MaterialStore(tmp_path);source=template(tmp_path)
    with ZipFile(source) as z: parts={n:z.read(n) for n in z.namelist()}
    name='word/_rels/document.xml.rels'
    parts[name]=parts[name].replace(b'</Relationships>', b'<Relationship Id="evil" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid" TargetMode="External"/></Relationships>')
    with ZipFile(source,'w',ZIP_DEFLATED) as z:
        for name,body in parts.items():z.writestr(name,body)
    with pytest.raises(ValueError):inspect_custom_word_template(store,source.name)
    large=tmp_path/'膨胀.docx'
    with ZipFile(large,'w',ZIP_DEFLATED) as z:z.writestr('word/document.xml',b'0'*(41*1024*1024))
    with pytest.raises(ValueError):inspect_custom_word_template(store,large.name)


def test_paths_cannot_escape_workspace(tmp_path):
    outside=template(tmp_path,name='外部.docx')
    root=tmp_path/'workspace';root.mkdir();store=MaterialStore(root)
    with pytest.raises(ValueError):inspect_custom_word_template(store,str(outside))
    source=template(root);view=inspect_custom_word_template(store,source.name)
    with pytest.raises(ValueError):render_custom_word_template(store,source.name,'../覆盖.docx',{'client':'甲'},source_sha256=view['source_sha256'])
