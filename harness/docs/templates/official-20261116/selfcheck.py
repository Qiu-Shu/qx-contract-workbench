"""Offline checks using synthetic links and Office XML only."""
import io
import zipfile
from scrapling.parser import Selector
from collect import official, links_from_page
from inspect_collection import inspect_bytes

assert official('https://www.court.gov.cn/a')
assert not official('http://www.court.gov.cn/a')
assert not official('https://www.court.gov.cn.evil.example/a')
links=links_from_page(Selector('<a href="/download/42.html">诉状.docx</a><a href="/download/42.html">下载</a><a href="/test.pdf">PDF</a><a href="/script.exe">run</a>'),'https://www.court.gov.cn/a')
assert len(links)==2
assert links[0]['extension']=='.docx'
payload=io.BytesIO()
with zipfile.ZipFile(payload,'w') as archive:
    archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>虚构样式 姓名：___</w:t></w:r></w:p></w:body></w:document>')
result,text=inspect_bytes(payload.getvalue(),'.docx')
assert result['zip_crc_ok']
assert result['blank_markers_present']
assert result['macro_payloads']==[]
assert text=='虚构样式 姓名：___'
archive_bytes=io.BytesIO()
with zipfile.ZipFile(archive_bytes,'w') as archive:
    archive.writestr('example.docx',payload.getvalue())
    archive.writestr('../outside.txt','untrusted')
info,_=inspect_bytes(archive_bytes.getvalue(),'.zip')
assert info['members'][0]['parse_status']=='parsed_ooxml'
assert not info['members'][1]['safe_path']
try:
    inspect_bytes(b'<html>not word</html>','.doc')
    raise AssertionError('wrong signature accepted')
except ValueError:
    pass
print('collector/inspector self-check: 12 assertions/checks passed')
