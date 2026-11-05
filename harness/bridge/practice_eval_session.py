"""Development-only JSONL relay to real MCP servers in a synthetic workspace."""
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from docx import Document
from check_business_mcp import client, call

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'read_case_material','ground_case_extractions','save_evidence_analysis',
           'save_employment_review','calculate_employment_amount','generate_litigation_document',
           'record_case_note','read_case_note','get_case','export_case','write_word_draft',
           'build_source_bound_litigation','assess_employment_termination','save_source_bound_register'}


def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)


async def run():
    if len(sys.argv)!=3 or any(not re.fullmatch('[a-z0-9-]+',v) for v in sys.argv[1:]):
        raise ValueError('Expected explicit run and synthetic scenario IDs')
    run_id, scenario_id = sys.argv[1:]
    case_file = ('docs/checks/skill-resume-20261105/e2e-cases.json'
                 if os.environ.get('QX_SKILL_EVAL_CAMPAIGN') == 'skill-resume-20261105'
                 else 'docs/checks/practice-gaps/e2e-cases.json')
    if (os.environ.get('QX_SKILL_EVAL_CAMPAIGN') == 'skill-resume-20261105'
            and os.environ.get('QX_SKILL_EVAL_SNAPSHOT') in ('v4','v5','v6')):
        case_file = 'docs/checks/skill-resume-20261105/e2e-'+os.environ['QX_SKILL_EVAL_SNAPSHOT']+'-cases.json'
    rows=json.loads((ROOT/case_file).read_text(encoding='utf-8'))
    scenario=next(row for row in rows if row['id']==scenario_id)
    workspace=ROOT/'docs/checks/practice-gaps/e2e'/run_id/scenario_id/'workspace'
    if not workspace.resolve().is_relative_to(ROOT.resolve()/'docs/checks/practice-gaps/e2e'):
        raise ValueError('Synthetic workspace resolves outside evaluation directory')
    workspace.mkdir(parents=True,exist_ok=False)
    source=workspace/'合成材料.txt'
    source.write_text(scenario['material'],encoding='utf-8')
    source_digest=sha256(source.read_bytes()).hexdigest()
    async with client('server.py',workspace) as materials, client('business_server.py',workspace) as legal:
        await call(materials,'import_material',path=source.name)
        await call(materials,'parse_material',path=source.name)
        case=await call(legal,'create_case',title='合成实测-'+scenario_id)
        cid=case['id']
        await call(legal,'link_case_materials',case_id=cid,paths=[source.name])
        tools=[]
        for session in (legal,materials):
            for tool in (await session.list_tools()).tools:
                if tool.name in ALLOWED and tool.name in scenario['tools']:
                    tools.append({'type':'function','function':{'name':tool.name,
                        'description':tool.description or '', 'parameters':tool.input_schema}})
        emit({'ready':True,'case_id':cid,'workspace':str(workspace),'material_path':source.name,'tools':tools,'scenario':scenario})
        while True:
            line=await asyncio.to_thread(sys.stdin.readline)
            if not line:break
            request=json.loads(line)
            if request.get('op')=='finalize':
                view=await call(legal,'get_case',case_id=cid,limit=100)
                while view.get('next_offset') is not None:
                    page=await call(legal,'get_case',case_id=cid,offset=view['next_offset'],limit=100)
                    view['notes'].extend(page['notes']);view['next_offset']=page.get('next_offset')
                for note in view['notes']:
                    while note.get('next_start') is not None:
                        page=await call(legal,'read_case_note',case_id=cid,note_id=note['id'],start=note['next_start'],limit=16000)
                        note['content']+=page['content'];note['next_start']=page.get('next_start')
                notes_complete=(len(view['notes'])==view['total_notes'] and
                                all(len(n['content'])==n['content_chars'] for n in view['notes']))
                drafts=[]
                for path in (workspace/'drafts').glob('*.docx'):
                    if not path.resolve().is_relative_to(workspace.resolve()):
                        raise ValueError('Draft resolves outside synthetic workspace')
                    doc=Document(path)
                    text='\n'.join([p.text for p in doc.paragraphs]+[cell.text for table in doc.tables for row in table.rows for cell in row.cells])
                    drafts.append({'path':str(path),'text':text,'bytes':path.stat().st_size,
                                   'sha256':sha256(path.read_bytes()).hexdigest()})
                emit({'finalized':True,'case':view,'drafts':drafts,'notes_complete':notes_complete,
                      'source_sha256':source_digest,'source_unchanged':sha256(source.read_bytes()).hexdigest()==source_digest})
                break
            name=request.get('name');args=request.get('arguments',{})
            if name not in {t['function']['name'] for t in tools} or not isinstance(args,dict):
                emit({'executed':False,'is_error':True,'error':'Tool outside this synthetic scenario'});continue
            if 'case_id' in args and args['case_id']!=cid:
                emit({'executed':False,'is_error':True,'error':'Only the declared synthetic case is allowed'});continue
            session=materials if name=='write_word_draft' else legal
            result=await session.call_tool(name,args,read_timeout_seconds=60)
            content=result.structured_content
            if content is None:
                text='\n'.join(c.text for c in result.content if c.type=='text')
                try:content=json.loads(text)
                except ValueError:content={'text':text}
            emit({'executed':True,'is_error':result.is_error,'result':content})


if __name__=='__main__':asyncio.run(run())
