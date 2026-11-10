"""MCP stdio bridge; use the existing project Python runtime."""
import argparse
from pathlib import Path
import json
import os
import subprocess
import sys
import sqlite3
from functools import wraps
from tempfile import NamedTemporaryFile
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from store import MaterialStore

DEFAULT_WORKSPACE=Path(__file__).resolve().parents[1]/'workspace'
mcp=MCPServer('qx_materials',instructions='材料只在工作区内处理。先列文件/导入，解析后分批读取或搜索，不一次塞入全文。PDF按next_page继续解析。生成的Word是待核草稿。',log_level='WARNING')
store=None


def friendly_errors(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        try:
            result=function(*args,**kwargs)
            # Reader failures are recoverable, but must not appear as successful
            # MCP calls. Keep the original hint and metadata for the next attempt.
            if isinstance(result,dict) and result.get('error'):
                raise ToolError(json.dumps(result,ensure_ascii=False))
            return result
        except ValueError as error:raise ToolError(str(error)) from None
        except (OSError,sqlite3.Error):
            raise ToolError('本机文件或索引操作未完成，请检查磁盘空间、权限和文件是否仍存在。') from None
    return wrapped


@mcp.tool()
@friendly_errors
def list_materials(offset:int=0,limit:int=50)->dict:
    """列出工作区文档和图片，包含尚未导入的上传文件；分页不限制总数量。"""
    return store.list(offset,limit)


@mcp.tool()
@friendly_errors
def import_material(path:str)->dict:
    """注册工作区内材料，保留原路径与摘要。上传图片的 objects/哈希 路径没有扩展名也可直接导入，无需复制/改名或调用Windows工具；随后parse_material。文件改变后重新导入。"""
    return store.register(path)


@mcp.tool()
@friendly_errors
def parse_material(path:str,start_page:int=1,page_count:int=20,force_ocr:bool=False,revision_mode:str='original')->dict:
    """解析已导入材料。PDF、图片及多帧扫描件按next_page逐批读取；failed_pages可用start_page及page_count=1单独重试，其余已提取内容先用。本机OCR保留文字框和置信信息，DOCX表格保留行列与合并范围。修订视图original或accepted_view。"""
    if revision_mode not in {'original','accepted_view'}:raise ValueError('revision_mode 只能为 original 或 accepted_view。')
    with store.db() as db:store.current(path,db)
    request={'workspace':str(store.root),'path':path,'start_page':start_page,'page_count':page_count,
             'force_ocr':force_ocr,'revision_mode':revision_mode}
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('reader.py'))],
            input=json.dumps(request,ensure_ascii=False),text=True,encoding='utf-8',capture_output=True,
            timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
            env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    except subprocess.TimeoutExpired:
        return {'error':'本批处理超过十分钟，原件保留。PDF请减小page_count继续；其他格式可转PDF逐页处理。'}
    if result.returncode:return {'error':'解析进程未完成，原件保留；可能内存不足或文件损坏。','exit_code':result.returncode}
    try:response=json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):return {'error':'解析进程返回异常，原件保留。'}
    return response['result'] if response['ok'] else {'error':response['error']}


@mcp.tool()
@friendly_errors
def read_material(path:str,start:int=0,limit:int=6,page:int|None=None)->dict:
    """分页读取已解析材料的原文片段，返回位置、文件摘要和next_start；PDF可指定page。"""
    return store.read(path,start,limit,page)


@mcp.tool()
@friendly_errors
def search_materials(query:str,path:str|None=None,offset:int=0,limit:int=10)->dict:
    """检索所有已解析内容中的原词/短语（支持中文），返回位置和短摘录；更多结果按next_offset继续。"""
    return store.search(query,path,offset,limit)


@mcp.tool()
@friendly_errors
def write_word_draft(filename:str,title:str,content:str)->dict:
    """把拟好的文字生成工作区drafts目录内的真实Word草稿。不会覆盖原文件；filename须为.docx文件名。"""
    from docx import Document
    from docx.shared import Pt
    if Path(filename).name!=filename or any(c in filename for c in '/\\:') or not filename.lower().endswith('.docx'):
        raise ValueError('filename 必须为简单的 .docx 文件名。')
    directory=store.root/'drafts';directory.mkdir(exist_ok=True)
    store.safe(directory,internal=True)
    target=store.safe(directory/filename,must_exist=False)
    if target.exists():target=store.safe(directory/(target.stem+'-'+uuid4().hex[:8]+'.docx'),must_exist=False)
    from word_render import document_from_text
    document=document_from_text(title,content)
    temporary=None
    try:
        with NamedTemporaryFile(dir=directory,prefix='.qx-word-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);document.save(stream)
        # Windows rename fails if the destination appeared concurrently; no overwrite.
        if target.exists():raise OSError('destination exists')
        os.rename(temporary,target)
    except OSError:
        raise ValueError('Word 写入未完成，请检查磁盘空间和目录权限。') from None
    finally:
        if temporary is not None and temporary.exists():
            store.safe(temporary).unlink()
    return {'path':str(target),'relative_path':target.relative_to(store.root).as_posix(),
            'bytes':target.stat().st_size,'status':'draft','notice':'已生成Word草稿，请核对事实、引文与金额。'}


@mcp.tool()
@friendly_errors
def inspect_word_document(path:str,offset:int=0,limit:int=100)->dict:
    """准备修改Word原件前，读取带稳定段落编号的正文与表格。返回source_sha256，用于修订时核对版本；按next_offset继续。"""
    from docx_delivery import inspect_docx
    return inspect_docx(store,path,offset,limit)


@mcp.tool()
@friendly_errors
def write_review_word(path:str,filename:str,edits:list[dict],source_sha256:str,author:str='律师',mode:str='comments')->dict:
    """默认生成批注版Word，保留正文：先inspect_word_document定位。edits每项paragraph_id、old、comment（理由）及new（可选建议文本），new默认也只写入批注。仅用户明确要修订正文时传mode=tracked_changes。原件与已有批注保留；检查逐项results，不把失败项称为已应用。"""
    from docx_delivery import write_review_docx
    if not source_sha256:raise ValueError('请先 inspect_word_document 获取原件版本 source_sha256。')
    return write_review_docx(store,path,filename,edits,author,source_sha256,mode)


@mcp.tool()
@friendly_errors
def write_contract_opinion(filename:str,title:str,sections:list[dict],subtitle:str='')->dict:
    """生成同内容的合同审查意见书HTML与Word，不覆盖原件。filename可为简单文件基名/.html/.docx。sections每项heading、paragraphs文字列表，可选table{headers,rows}、subsections、references[{label,url}]。推荐结论、事实、四列风险表、条款建议与补件等章节，不强制章节数量；普通文字会转义。先保存本案审查记录，再展示返回文件。"""
    from contract_opinion import write_contract_opinion as generate
    return generate(store,filename,title,subtitle,sections)


@mcp.tool()
@friendly_errors
def list_document_templates()->dict:
    """列出诉状和证据目录模板、template_id及填写字段。根据业务需要选择，不强制用户先填表。"""
    from docx_delivery import list_templates
    return list_templates()


@mcp.tool()
@friendly_errors
def generate_document_from_template(template_id:str,filename:str,data:dict,author:str='')->dict:
    """根据模板生成独立Word。诉状data: parties/claims/facts字符串列表、court/signature/date；证据目录data: evidence[{name,content,purpose,page_range,source}]、title/submitter/date。未知事实写待补，不编造证据页码。"""
    from docx_delivery import generate_template_document
    return generate_template_document(store,template_id,filename,data,author)


@mcp.tool()
@friendly_errors
def inspect_custom_word_template(path:str)->dict:
    """读取用户工作区DOCX空白模板的变量名及source_sha256；保留页眉、样式。仅支持{{ 字段名 }}。
    模板固定正文也会保留，应先核对不是其他案件样例；拒绝外链、宏与可执行模板表达式。
    """
    from custom_word_template import inspect_custom_word_template as inspect
    return inspect(store,path)


@mcp.tool()
@friendly_errors
def render_custom_word_template(path:str,filename:str,data:dict,source_sha256:str)->dict:
    """用已确认字段另存律所Word模板。先inspect获取版本；只填字符串、数字或布尔值，缺失不猜。
    不覆盖原模板；静态正文不会自动清除，须先核对其中姓名/金额/事实。产物仍是待核草稿。
    """
    from custom_word_template import render_custom_word_template as render
    return render(store,path,filename,data,source_sha256=source_sha256)


def main():
    global store
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',default=str(DEFAULT_WORKSPACE))
    args=parser.parse_args();store=MaterialStore(args.workspace)
    mcp.run(transport='stdio')


if __name__=='__main__':main()
