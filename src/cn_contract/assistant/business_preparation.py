"""Source-bound local preparation, deliberately not a model or legal prediction."""
import re
from datetime import date
from uuid import UUID
import json

from sqlalchemy import text

from .. import domain as d
from ..persistence import configured_database
from ..record_codec import sha
from ..task_drafts import service as tasks
from . import attachment_records as materials, attachment_files, evidence_worksheet, service


def evidence_ref(actor, cid, view, rows, db):
    if not rows:
        return None
    snapshot = evidence_worksheet.historical(actor, cid, view.revision, db)
    ids = tuple(row.id for row in rows)
    return d.BusinessEvidenceRef(revision=view.revision, snapshot_sha256=sha(snapshot.model_dump(mode='json')),
        fact_ids=ids, historical_ids=tuple(identifier for identifier in view.historical_ids if identifier in ids))


def validate_evidence(result, db):
    from . import evidence_records
    ref = result.evidence
    found = next((snapshot for _, _, snapshot in evidence_records.history(db, result.scope.conversation_id)
                  if snapshot.revision == ref.revision), None)
    if (found is None or found.created_at > result.created_at or sha(found.model_dump(mode='json')) != ref.snapshot_sha256
            or len(set(ref.fact_ids)) != len(ref.fact_ids) or not set(ref.fact_ids) <= {row.id for row in found.rows}
            or not set(ref.historical_ids) <= set(ref.fact_ids)):
        raise ValueError('BUSINESS_EVIDENCE_INVALID')
    expected = tuple(row.id for row in found.rows if row.event_date)[:40] if result.workflow == 'case' else tuple(row.id for row in found.rows[:8])
    selection = db.scalar(text('SELECT items_json FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
        {'cid':str(result.scope.conversation_id), 'rev':result.scope.materials_revision})
    selected = {UUID(item['attachment_id']):item['parse_revision'] for item in json.loads(selection or '[]')}
    revision = db.scalar(text('SELECT MAX(revision) FROM assistant_profile_revisions WHERE conversation_id=:cid AND created_at<=:at'),
        {'cid':str(result.scope.conversation_id), 'at':result.created_at.isoformat()})
    _, statement = evidence_records.statement(result.scope.conversation_id, db, revision) if revision else (0, None)
    historical = []
    for fact in found.rows:
        if fact.id not in expected:
            continue
        source = fact.source
        current = (statement is not None and statement[source.start:source.end] == source.quote) if source.kind == 'statement' else (
            source.attachment_id in selected and (source.kind != 'document' or selected[source.attachment_id] == source.parse_revision))
        if not current:
            historical.append(fact.id)
    if ref.fact_ids != expected or ref.historical_ids != tuple(historical):
        raise ValueError('BUSINESS_EVIDENCE_INVALID')


def sources(actor, cid, db):
    conversation = service._owned(actor, cid, db)
    refs, files, directory = [], [], []
    for item in materials.items(conversation, db):
        row = materials.owned_attachment(actor, cid, item.attachment_id, db)
        attachment_files.read_checked(row, configured_database(db))
        parsed = materials.parse_view(materials.parse_row(cid, item.attachment_id, item.parse_revision, db)) if item.parse_revision else None
        readable = parsed and parsed.result is not None
        state = 'ready' if readable else 'pending'
        files.append(d.TaskMediaInput(media_id=str(item.attachment_id), name=row['original_name'], mime=row['mime'],
            attachment_id=item.attachment_id, sha256=row['sha256'], parse_revision=item.parse_revision, status=state))
        directory.append(row['original_name'] + ' · ' + ('可读原文，内容待核' if parsed and parsed.reading_status == 'readable'
            else '部分可读，存在未读内容' if readable else '尚未读取，请在本对话材料区核对'))
        if readable:
            for anchor in parsed.result.anchors:
                if anchor.quote and len(refs) < 100:
                    refs.append(d.ProfileDocumentRef(kind='document', conversation_id=UUID(str(cid)),
                        attachment_id=item.attachment_id, original_sha256=row['sha256'],
                        parse_revision=item.parse_revision, result_sha256=parsed.result_sha256, anchor=anchor))
    return tuple(refs), tuple(files), directory


def contract(actor, run, request, previous, media, db, *, personal_draft_id=None):
    if personal_draft_id is not None:
        from ..security import ServiceError
        draft = tasks.read_draft(actor, personal_draft_id, db)
        manifest, _ = tasks._manifest(actor, tasks._draft(actor, personal_draft_id, db), db)
        if draft.conversation_id != run.scope.conversation_id or manifest.synthetic or draft.state != 'collecting':
            raise ServiceError('CROSS_MATTER_DENIED', 403)
    else:
        binding = tasks.create_binding(actor, run.scope.conversation_id, db)
        target = previous.contract_draft_id if previous else None
        receipt = tasks.receive_batch(actor, binding.id, d.TaskInboxBatchInput(expected_cursor=binding.cursor,
            next_cursor=binding.cursor + 1, events=(d.TaskInboxEventInput(event_id=str(request.request_id),
                text=request.content, task_id=target, start_new=target is None, media=media),)), db)
        if not receipt.drafts:
            return '存在多个可能的合同任务，请先在当前聊天的任务记录中选择归属。', None
        draft = receipt.drafts[0]
    notes = {'main_contract_required':'请上传主合同，可随后继续补附件。',
        'main_contract_selection_required':'有多份材料，请明确哪一份是主合同。',
        'instruction_required':'请补充审查要求。', 'media_pending':'材料已关联，请在本对话读取原文。',
        'media_not_readable':'存在未完整读取的材料，请核对读取范围。',
        'media_unsupported':'包含暂不支持解析的材料，请补充可读版本。'}
    if any(code.startswith('media_') for code in draft.blockers):
        notes['main_contract_required'] = '已收到材料，但主合同尚未完整读取；请在材料区核对读取状态与未读范围。'
    reasons = [notes.get(code, '请核对材料版本与读取状态。') for code in draft.blockers]
    return ('合同任务已关联本次指令和材料。\n' + '\n'.join(dict.fromkeys(reasons)) +
        '\n\n这是材料归集记录。模型分析将按当前设置使用选定材料，结果保存在本对话。'
        '材料陈述仍为待核信息；原件和已有执行结果保留。'), draft.id


def case_text(actor, cid, refs, directory, db):
    evidence = evidence_worksheet.read(actor, cid, db)
    lines = ['材料目录', *('• ' + item for item in directory)]
    if not directory:
        lines.append('尚无选中的材料。可在当前聊天分次上传。')
    lines.extend(['', '初步事实时间线（原文线索，不代表事实认定）'])
    dated = []
    for index, ref in enumerate(refs, 1):
        for match in re.finditer(r'(?<!\d)(20\d{2}|19\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})日?', ref.anchor.quote):
            try:
                when = date(*(int(part) for part in match.groups()))
            except ValueError:
                continue
            dated.append((when, f'材料引文 {index}：{ref.anchor.quote[:180]}'))
    used = tuple(fact for fact in evidence.rows if fact.event_date)[:40]
    for fact in used:
        if fact.event_date:
            dated.append((fact.event_date, ('历史来源 · ' if fact.id in evidence.historical_ids else '') + '已登记底稿（' + {'pending':'待核','reviewed':'律师登记已核','disputed':'有争议'}[fact.review_state] + '）：' + fact.content[:180]))
    lines.extend(str(when) + ' · ' + content for when, content in sorted(dated)[:40])
    if not dated:
        lines.append('未找到可明确排序的日期，不推断时间或先后关系。')
    lines.extend(['', '待整理争点与证据缺口', '• 双方各自主张什么，哪些陈述相互冲突？',
        '• 约定、履行与损失分别由哪份原始材料支持？', '• 原件是否完整，是否存在未读页、补充协议或相反证据？',
        '', '文书准备提纲', '请求事项：待律师确定。', '事实与理由：按上述时间线逐项核对后填写。',
        '证据目录：沿用本次材料目录，标注证明目的及争议。', '',
        '本机规则整理；问题为通用核对清单，尚未进行模型争点分析。'])
    return '\n'.join(lines), evidence_ref(actor, cid, evidence, used, db)


def court_text(actor, cid, refs, directory, db):
    evidence = evidence_worksheet.read(actor, cid, db)
    lines = ['庭审通用准备提纲（未调用模型，不预测裁判）', '', '复用材料', *('• ' + item for item in directory)]
    used = evidence.rows[:8]
    subjects = [('历史来源 · ' if fact.id in evidence.historical_ids else '') + fact.content[:1000] for fact in used] or [ref.anchor.quote[:180] for ref in refs[:8]]
    if not subjects:
        lines.append('尚无可用事实或已读取材料，请先补充案件材料。')
    for number, subject in enumerate(subjects, 1):
        lines.extend(['', f'待核材料线索 {number}：{subject}',
            '对方律师质疑：这项陈述由谁提出，原件是否完整，是否有相反材料？',
            '法官追问：这项材料要证明哪一项主张，与其他证据能否相互印证？',
            '己方准备：核对原件及来源，列明能证明与暂不能证明的事项；缺失处明确承认待补。'])
    lines.extend(['', '庭前准备清单', '• 核对诉请、答辩、举证期限及证据编号。',
        '• 对有争议的事实分别准备双方说法、原件位置和待补证明。',
        '• 将通用追问交律师结合案情改写；当前结果不代表已完成个案策略推演。'])
    return '\n'.join(lines), evidence_ref(actor, cid, evidence, used, db)
