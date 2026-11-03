"""Small persistent legal workflows on the existing local material transport."""
import argparse
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from store import MaterialStore
from business_store import CaseStore
from hearing import HearingStore
from workflows import workflow
import server as material_server
from server import friendly_errors

mcp = MCPServer('qx_legal', instructions=(
    '按需求读取业务方法。持续办理时明确案件ID，把本轮材料关联到该案再读取；'
    '原话、内部分析与客户回复分别追加保存，更正保留原记录。庭审发言是模拟记录，不是证据。'
    '工具保存失败时保留可用正文并说明，不能称保存成功。'), log_level='WARNING')
cases = None
hearings = None


@mcp.tool()
@friendly_errors
def get_workflow(name: str) -> dict:
    """按需读取接待reception、合同contract、办案case、庭审hearing方法与实际来源；不调用模型。"""
    return workflow(name)


@mcp.tool()
@friendly_errors
def list_cases(query: str = '', offset: int = 0, limit: int = 20) -> dict:
    """按题名查找案件。不要仅按最近时间猜案件归属，同名结果需结合当前会话或询问。"""
    return cases.list(query, offset, limit)


@mcp.tool()
@friendly_errors
def create_case(title: str, our_role: str = '', request_id: str = '') -> dict:
    """用户需要持续办理或保存时建案；our_role只录入已明确立场。request_id用于重复请求找回。"""
    return cases.create(title, our_role, request_id)


@mcp.tool()
@friendly_errors
def get_case(case_id: str, offset: int = 0, limit: int = 30, include_history: bool = False) -> dict:
    """读取指定案件材料、笔记和变更提示；长笔记按返回next_start调用read_case_note。"""
    return cases.get(case_id, offset, limit, include_history)


@mcp.tool()
@friendly_errors
def link_case_materials(case_id: str, paths: list[str]) -> dict:
    """把明确用于本案的材料按当前版本登记；先使用qx_materials导入和解析，不覆盖旧版关联。"""
    return cases.link_materials(case_id, paths)


@mcp.tool()
@friendly_errors
def record_case_note(case_id: str, kind: str, content: str, source: str = '',
                     supersedes: str = '', citations: list[dict] | None = None,
                     request_id: str = '') -> dict:
    """追加consultation/fact/inference/timeline/stance/todo/contract_review/client_reply/internal_note等记录。

    content为自然语言，不限制回答格式或业务篇幅。更正用supersedes指向当前同类别笔记；只有用户明确更正才使用。
    citations每项path、quote，可选sha256、chunk；程序核对原文，不要让模型计算字符偏移。
    未匹配引用保留正文并标待核，材料陈述不等于事实已证实。客户正文与内部分析必须分两条保存。
    """
    return cases.add_note(case_id, kind, content, source, supersedes, citations, request_id)


@mcp.tool()
@friendly_errors
def record_reception(case_id: str, client_reply: str, internal_note: str,
                     source: str = '', request_id: str = '') -> dict:
    """一次事务分别保存客户可转发正文与内部底稿；失败不留下单独半条，重试沿用request_id。"""
    return cases.record_reception(case_id, client_reply, internal_note, source, request_id)


@mcp.tool()
@friendly_errors
def read_case_note(case_id: str, note_id: str, start: int = 0, limit: int = 8000) -> dict:
    """分段读取本案一条完整笔记，按next_start继续；不会把旧笔记改成最新事实。"""
    return cases.read_note(case_id, note_id, start, limit)


@mcp.tool()
@friendly_errors
def read_case_material(case_id: str, path: str, start: int = 0, limit: int = 6,
                       page: int | None = None, version: int | None = None) -> dict:
    """读取本案关联材料；默认核对当前原件，指定version可回读已保存的历史解析文字快照。"""
    return cases.read_material(case_id, path, start, limit, page, version)


@mcp.tool()
@friendly_errors
def search_case_materials(case_id: str, query: str, offset: int = 0, limit: int = 10) -> dict:
    """仅搜索本案已关联材料及笔记，kind区分二者。笔记是陈述/分析，不因命中变为原始证据。"""
    return cases.search(case_id, query, offset, limit)


@mcp.tool()
@friendly_errors
def export_case(case_id: str, filename: str = '案件工作稿.docx', audience: str = 'internal',
                note_ids: list[str] | None = None) -> dict:
    """从已保存当前记录生成真实Word。internal含来源；client仅客户回复，默认最新一条，不夹内部底稿。

    note_ids可指定当前笔记；更正后的旧记录可get_case(include_history=True)回查，但不默认导出。
    导出不发送到微信，文件同名另存。工具成功后再提供真实路径。
    """
    if audience not in {'internal', 'client'}:
        raise ValueError('audience只能为internal或client。')
    page = cases.export_snapshot(case_id)
    notes = page['notes']
    if note_ids is not None:
        by_id = {note['id']: note for note in notes}
        if any(identifier not in by_id for identifier in note_ids):
            raise ValueError('所选笔记不在本案当前记录中，请回读后选择。')
        notes = [by_id[identifier] for identifier in dict.fromkeys(note_ids)]
    if audience == 'client':
        if note_ids is not None and any(note['kind'] != 'client_reply' for note in notes):
            raise ValueError('客户版只能导出client_reply，内部底稿不会夹入。')
        if note_ids is None:
            notes = [note for note in notes if note['kind'] == 'client_reply'][-1:]
    if not notes:
        raise ValueError('尚无所选范围的已保存内容，请先保存回复或工作稿。')
    sections = []
    for note in notes:
        if audience == 'internal':
            sections.append(f"## {note['kind']} · {note['id']}")
        sections.append(note['content'])
        if audience == 'internal':
            if note.get('source'):
                sections.append('记录来源：' + note['source'])
            for citation in note.get('citations', []):
                sections.append(f"出处：{citation.get('path', '')}；{citation.get('location', '')}；"
                                f"引用版本：{citation.get('version', '未记录')}；"
                                f"SHA-256 {citation.get('sha256', '未记录')}；片段：{citation.get('chunk', '未记录')}；"
                                f"记录时原文匹配：{citation.get('status', 'unverified')}\n{citation.get('quote', '')}")
            sections.extend('待核：' + str(warning) for warning in note.get('warnings', []))
    if audience == 'internal':
        sections.append('## 当前关联材料版本（引用自身版本见各条出处）')
        for item in page.get('materials', []):
            sections.append(f"{item['path']} · 版本 {item.get('version', '未记录')} · SHA-256 {item['sha256']}")
            if item.get('changed'):
                sections.append('待核：文件内容已变化，当前文件与登记版本不同。')
            if item.get('missing'):
                sections.append('待核：登记的材料文件当前不可读取。')
            sections.extend('待核：' + str(warning) for warning in item.get('warnings', []))
    title = '客户回复' if audience == 'client' else page['case']['title'] + ' · 工作稿'
    result = material_server.write_word_draft(filename, title, '\n\n'.join(sections))
    return {**result, 'case_id': case_id, 'audience': audience, 'note_ids': [note['id'] for note in notes]}


@mcp.tool()
@friendly_errors
def start_hearing(case_id: str, our_role: str, focus: str = '', request_id: str = '', previous_id: str = '') -> dict:
    """开始五阶段民事庭审演练，明确我方plaintiff/defendant。补件重开用previous_id关联，保留旧回合。"""
    return hearings.start(case_id, our_role, focus, request_id, previous_id)


@mcp.tool()
@friendly_errors
def get_hearing(hearing_id: str, offset: int = 0, limit: int = 30) -> dict:
    """回读演练与下一阶段/角色；长发言按next_start调用read_hearing_turn，页末按next_offset续读。"""
    return hearings.get(hearing_id, offset, limit)


@mcp.tool()
@friendly_errors
def list_hearings(case_id: str, offset: int = 0, limit: int = 20) -> dict:
    """按明确案件找回演练ID与已保存进度；多个演练结合当前任务选择，不自动按最近记录续接。"""
    return hearings.list(case_id, offset, limit)


@mcp.tool()
@friendly_errors
def read_hearing_turn(hearing_id: str, turn_id: str, start: int = 0, limit: int = 8000) -> dict:
    """逐段回读本次演练已保存发言，按next_start读取全文；不会改变发言或推进阶段。"""
    return hearings.read_turn(hearing_id, turn_id, start, limit)


@mcp.tool()
@friendly_errors
def record_hearing_turn(hearing_id: str, stage: str, role: str, text: str,
                        citations: list[dict] | None = None, unresolved: str = '', request_id: str = '') -> dict:
    """保存一次真实生成的角色发言；按get_hearing给出的顺序推进。不要预先填充未执行阶段。"""
    return hearings.append_turn(hearing_id, stage, role, text, citations, unresolved, request_id)


@mcp.tool()
@friendly_errors
def get_hearing_role_context(hearing_id: str, role: str) -> dict:
    """生成指定角色的目标、材料版本与已发生发言摘要；供定向追问，不声称同模型角色上下文独立。"""
    return hearings.role_context(hearing_id, role)


def main():
    global cases, hearings
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', default=str(Path(__file__).resolve().parents[1] / 'workspace'))
    args = parser.parse_args()
    materials = MaterialStore(args.workspace)
    cases = CaseStore(materials)
    hearings = HearingStore(cases)
    # Reuse the existing non-overwriting Word writer in this workspace-bound process.
    material_server.store = materials
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
