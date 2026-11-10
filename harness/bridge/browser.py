"""Expose the installed bb-browser CLI to Harness without a shell."""
import json
import os
import re
import subprocess
from pathlib import Path
from threading import RLock
from uuid import uuid4

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer('bb_browser', log_level='WARNING')
APP_ROOT = Path(__file__).resolve().parent.parent
NODE = os.environ.get('BB_BROWSER_NODE', str(APP_ROOT / 'runtime' / 'node.exe'))
CLI = os.environ.get('BB_BROWSER_CLI', str(APP_ROOT / 'browser' / 'node_modules' / 'bb-browser' / 'dist' / 'cli.js'))
SNAPSHOTS = {}
LOCK = RLock()
ACTIONS = {'status', 'open', 'goto', 'snap', 'snapshot', 'click', 'hover', 'fill', 'type',
           'check', 'uncheck', 'select', 'press', 'scroll', 'get', 'eval', 'close',
           'back', 'forward', 'reload', 'site'}


def validate_arguments(arguments: list[str]) -> list[str]:
    if not arguments or not all(isinstance(v, str) and '\0' not in v for v in arguments):
        raise ValueError('请提供非空命令参数数组。')
    if arguments[0] not in ACTIONS:
        raise ValueError('仅支持当前任务的网页读取和交互，不支持浏览历史、Cookie 导出或服务管理。')
    if arguments[0] == 'site' and (len(arguments) < 2 or not (
        arguments[1] in {'list', 'info'} or re.fullmatch(r'[a-z0-9-]+/[a-z0-9-]+', arguments[1])
    )):
        raise ValueError('site 仅支持 list、info 或明确的 平台/操作，不读取浏览习惯或更新全局适配器。')
    if any(v in {'--port', '--openclaw', '--domain'} or v.startswith(('--port=', '--domain=')) for v in arguments):
        raise ValueError('使用既定浏览器连接和明确 tab，不切换连接或跨标签页自动发现。')
    return [NODE, CLI, *arguments, '--json']


def execute(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=90,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (ValueError, OSError) as error:
        raise ToolError(str(error)) from None
    except subprocess.TimeoutExpired:
        raise ToolError('浏览器操作超时；请先观察页面状态，不要直接重复提交。') from None
    if result.returncode:
        raise ToolError((result.stderr or result.stdout or 'bb-browser 执行失败').strip())
    try:
        response = json.loads(result.stdout)
        if isinstance(response, dict) and (response.get('error') or response.get('success') is False):
            raise ToolError(str(response.get('error') or '浏览器操作失败。'))
        return response
    except json.JSONDecodeError:
        return {'text': result.stdout, 'warning': result.stderr.strip()}


def tab_argument(arguments):
    try:
        if arguments.count('--tab')!=1:raise ValueError('tab')
        tab=arguments[arguments.index('--tab')+1]
        if not tab or tab.startswith('-'):raise ValueError('tab')
        return tab
    except (ValueError,IndexError):
        raise ToolError('请使用 open 返回的完整 tabId，并显式提供 --tab ID。') from None


def evaluate(tab, expression):
    return execute(validate_arguments(['eval', expression, '--tab', tab]))


@mcp.tool()
def browser(arguments: list[str]) -> dict:
    """操作 bb-browser，传字符串数组。open 返回 tabId 后，用 snap -i --tab ID 观察。
    fill @3 内容 --tab ID；click @5 --tab ID；press Enter --tab ID。
    click 使用最近快照保留的真实 DOM 节点进行一次程序化激活，非可信鼠标事件。
    press 使用完整键码的 CDP 事件。结果仅表示动作已发出，不等于业务成功。
    页面改变/超时后先观察，禁止自动补点；只操作获授权页面。先加载 bb-browser Skill。
    """
    try:
        command = validate_arguments(arguments)
    except ValueError as error:
        raise ToolError(str(error)) from None
    with LOCK:
        action=arguments[0]
        if action not in {'open','status','site'}:
            # Reject an unspecified target before the CLI can touch its current tab.
            tab_argument(arguments)
        if action in {'goto','close','back','forward','reload','eval','site','check','uncheck','select',
                      'fill','type','hover','scroll','snap','snapshot'}:
            # Discard before dispatch: an error/timeout can still follow a page mutation.
            if action=='site':SNAPSHOTS.clear()
            else:SNAPSHOTS.pop(tab_argument(arguments),None)
        if action=='click':
            tab=tab_argument(arguments)
            if len(arguments)!=4 or arguments[2]!='--tab' or not re.fullmatch(r'@?\d+',arguments[1]):
                raise ToolError('点击格式：click @实际ref --tab 完整ID。')
            token=SNAPSHOTS.get(tab)
            if token is None:raise ToolError('请先对这个 tab 调用 snap -i，不能猜测引用。')
            ref=arguments[1].lstrip('@')
            script='''(() => {
              const snapshot=window.__qxBbSnapshot;
              if(!snapshot || snapshot.token!==TOKEN) throw new Error('快照已失效，请重新观察');
              const node=snapshot.nodes[REF];
              if(!(node instanceof HTMLElement)||!node.isConnected) throw new Error('节点已改变，请重新观察');
              if(node.matches(':disabled,[aria-disabled="true"]')) throw new Error('目标不可用');
              node.scrollIntoView({block:'center',inline:'center',behavior:'instant'});
              const rect=node.getBoundingClientRect();
              const style=getComputedStyle(node);
              if(rect.width<=0||rect.height<=0||style.visibility==='hidden'||style.display==='none') throw new Error('目标不可见');
              const hit=document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2);
              if(!hit||(hit!==node&&!node.contains(hit))) throw new Error('目标被遮挡，请重新观察');
              node.focus({preventScroll:true});
              HTMLElement.prototype.click.call(node);
              return {activation:'dom',action_dispatched:true,business_outcome:'not_checked'};
            })()'''.replace('TOKEN',json.dumps(token)).replace('REF',json.dumps(ref))
            # One deliberate activation, never native-click followed by a blind retry.
            SNAPSHOTS.pop(tab,None)
            return evaluate(tab,script)
        if action=='press':
            tab=tab_argument(arguments)
            if len(arguments)!=4 or arguments[2]!='--tab' or not re.fullmatch(r'[0-9a-fA-F]{32}',tab):
                raise ToolError('按键格式：press Enter --tab open返回的完整tabId。')
            SNAPSHOTS.pop(tab,None)
            return execute([NODE,str(Path(__file__).with_name('browser-keyboard.mjs')),tab,arguments[1]])
        result=execute(command)
        if action in {'snap','snapshot'}:
            tab=tab_argument(arguments)
            refs=result.get('result',{}).get('snapshotData',{}).get('refs',{})
            token=uuid4().hex
            # Keep actual node identity: a later replacement at the same XPath is stale.
            script='''(() => {
              const refs=REFS,nodes={};
              for(const [ref,info] of Object.entries(refs)){
                if(!info.xpath)continue;
                try { nodes[ref]=document.evaluate(info.xpath,document,null,XPathResult.FIRST_ORDERED_NODE_TYPE,null).singleNodeValue; } catch {}
              }
              window.__qxBbSnapshot={token:TOKEN,nodes};return {snapshot_saved:true};
            })()'''.replace('TOKEN',json.dumps(token)).replace('REFS',json.dumps(refs,ensure_ascii=False))
            evaluate(tab,script)
            SNAPSHOTS[tab]=token
        return result


if __name__ == '__main__':
    mcp.run(transport='stdio')
