"""Generate only synthetic opinion/comment samples; never open a real client file."""
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bridge'))
from contract_opinion import write_contract_opinion
from docx_delivery import inspect_docx, write_review_docx
from docx import Document

out = Path(__file__).resolve().parent
sections = [
    {'heading': '一 审查结论与处理顺序', 'paragraphs': [
        '本文件全部内容为合成排版样稿。建议先把服务范围、验收方式与付款条件对应起来，再形成双方可以确认的修改清单。',
        '意见应逐项说明原条款在哪里、可能产生什么分歧，以及建议怎样写清。缺少附件或事实依据的部分，应保留待核问题，避免把假设直接写成结论。']},
    {'heading': '二 重点条款意见', 'paragraphs': ['下表展示四列风险表的阅读与打印效果，所有条款和意见均为合成内容。'],
     'table': {'headers': ['处理顺序', '对应条款', '审阅意见', '建议调整'], 'rows': [
         ['优先确认', '服务范围与附件', '正文仅写“提供技术服务”，未说明交付物、排除事项和客户配合义务。', '将交付物清单、提供方式、交付期限和双方配合事项列为附件，并写明附件与正文的对应关系。'],
         ['优先确认', '验收方式', '现有合成条款允许一方自行认定验收是否完成，缺少异议提交方式。', '约定可核对的验收标准和反馈期限；异议应写明具体不符事项，双方按照约定路径处理。'],
         ['结合事实', '需求变更', '需求变化可能影响费用和交付安排，当前材料尚不足以判断实际工作量。', '变更以双方书面确认的记录为依据，同时说明新增工作、费用和进度影响；未确定部分列为待协商事项。'],
         ['结合事实', '付款节点', '付款与验收之间的关系需要结合实际服务流程核对。', '把每个付款节点对应的提交材料、确认条件和金额写清，并与费用附件逐项对应。'],
         ['后续完善', '通知与联系人', '合同履行中的通知渠道、联系人变化和送达记录需要保持一致。', '补充双方确认的联系信息、变更通知方式及记录保存方式。']]}},
    {'heading': '三 建议替换文字', 'paragraphs': ['以下仅演示替换条款的标题与正文层级，不构成针对真实交易的法律结论。'],
     'subsections': [
         {'heading': '服务范围条款', 'paragraphs': ['本项目的服务内容、交付成果、交付方式及各方配合事项，以双方书面确认的服务清单为准。未列入清单的新增事项，由双方另行确认工作内容、费用和履行安排。']},
         {'heading': '需求变更条款', 'paragraphs': ['任何一方提出需求变更时，应说明变更内容及预期目标。双方确认变更对工作量、费用和期限的影响后，再据此调整履行安排。']} ]},
    {'heading': '四 待核材料与后续沟通', 'paragraphs': ['请核对服务清单、报价附件、需求确认记录和现有验收流程。沟通时优先确认影响履行与付款的事项，再整理可直接接受和需要进一步协商的文字。'],
     'references': [{'label': '示例来源链接 仅测试链接样式', 'url': 'https://example.org/reference?section=1&version=2'}]},
]
opinion = write_contract_opinion(out, 'synthetic-opinion', '合成技术服务合同审查意见', 'HTML 与 Word 版式核对样稿', sections)
long_text = '这是连续的合成长意见，用于验证跨页时正文完整保留，且不会为每项意见强制插入新页。'*35
long_opinion = write_contract_opinion(out, 'long-flow', '合成长意见连续排版测试', '仅验证跨页流动与内容完整性', [
    {'heading': '连续长段落', 'paragraphs': [long_text]},
    {'heading': '长表格意见', 'table': {'headers': ['级别', '条款', '风险说明', '完整建议'], 'rows': [
        ['短项', '条款甲', '短行应尽量留在同一页。', '这是短行示例。'],
        ['长项', '条款乙', '长行应允许跨页。', long_text],
        ['末项', '条款丙', '核对最后一项仍存在。', '最后一项完整保留。']]}}
])
source = out / 'default-comments-source.docx'
if not source.exists():
    doc = Document(); doc.add_paragraph('合成技术服务合同 仅供批注功能核对')
    doc.add_paragraph('乙方应在收到需求后立即交付，甲方可单方确认验收。')
    doc.add_paragraph('服务费用由双方另行确认。'); doc.save(source)
before = source.read_bytes(); inspected = inspect_docx(out, source.name); ps = inspected['paragraphs']
comments = write_review_docx(out, source.name, 'default-comments.docx', [
    {'paragraph_id': ps[1]['paragraph_id'], 'old': '立即交付', 'new': '在双方约定的交付期限内完成交付', 'comment': '建议把期限写清，便于双方履行和核对。'},
    {'paragraph_id': ps[2]['paragraph_id'], 'old': '另行确认', 'new': '按双方书面确认的费用清单执行', 'comment': '请将费用清单与正文对应。'}
], source_sha256=inspected['source_sha256'])
assert source.read_bytes() == before
assert [p.text for p in Document(source).paragraphs] == [p.text for p in Document(comments['path']).paragraphs]
manifest = {'opinion': opinion, 'long_opinion': long_opinion, 'comments': comments,
            'source_sha256': sha256(before).hexdigest(), 'source_unchanged': True, 'visible_body_unchanged': True}
(out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'opinion': opinion['word_path'], 'long_opinion': long_opinion['word_path'], 'comments': comments['path']}, ensure_ascii=True))
