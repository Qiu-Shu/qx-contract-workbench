"""Shared editable Word rendering for ordinary drafts and media packages."""
from docx import Document
from docx.shared import Pt


def document_from_text(title,content):
    document=Document()
    document.styles['Normal'].font.name='Microsoft YaHei'
    document.styles['Normal'].font.size=Pt(11)
    document.add_heading(title,0)
    for line in content.splitlines():
        if line.startswith('### '): document.add_heading(line[4:],3)
        elif line.startswith('## '): document.add_heading(line[3:],2)
        elif line.startswith('# '): document.add_heading(line[2:],1)
        else: document.add_paragraph(line)
    return document
