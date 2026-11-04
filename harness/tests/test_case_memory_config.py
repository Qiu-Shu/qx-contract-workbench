"""Distribution wiring must expose management and retrieval together."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_template_contains_both_case_memory_plugins_and_no_credentials():
    patch = yaml.safe_load((ROOT / 'config/cordis.patch.yml').read_text(encoding='utf-8-sig'))
    entries = [entry for group in patch for entry in group.get('insert', [])]
    plugins = {entry['id']: entry for entry in entries}
    ui = plugins['qx-case-memory-ui']
    assert ui.get('disabled') is not True
    assert ui['config']['workspace'].replace('\\', '/').endswith('/workspace')
    assert Path(ui['name']).is_file()
    mcp = plugins['qx-case-memory']
    assert mcp['config']['serverName'] == 'qx_case_memory'
    assert Path(mcp['config']['args'][0]).name == 'case_memory_server.py'
    assert mcp['config']['env']['QX_HINDSIGHT_TOKEN'] == {'__jsExpr': "process.env.QX_HINDSIGHT_TOKEN || ''"}
    assert 'DEEPSEEK_API_KEY' not in mcp['config']['env']


def test_seed_has_case_scope_and_no_history_backfill():
    instructions = (ROOT / 'config/workspace-AGENTS.md').read_text(encoding='utf-8')
    assert instructions.count('## 案件记忆') == 1
    section = instructions.split('## 案件记忆', 1)[1].split('\n## ', 1)[0]
    for text in ('默认开启', 'case_id', '不自动导入历史聊天', 'read_case_memory'):
        assert text in section
