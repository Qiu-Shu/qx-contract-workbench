"""Check the supported portable config consumed by installed-runtime.cjs.

Native executable integrity now belongs to the pinned base/source inventory gate
in verify-stage.test.cjs; the old copy_agent_desktop stage helper was removed.
"""
import json
from pathlib import Path


def test_portable_enabled_configuration_and_separate_state():
    rows = json.loads((Path(__file__).with_name('payload-config')/'portable.json').read_text(encoding='utf-8'))
    entry = next(p for r in rows for p in r.get('insert', []) if p['id'] == 'qx-agent-desktop')
    assert entry['disabled'] is False
    assert entry['config']['args'] == ['mcp']
    assert entry['config']['command'] == '@APP@/tools/agent-desktop/1.2.0/agent-desktop.exe'
    assert entry['config']['env']['AGENT_DESKTOP_HOME'] == '@DATA@/.local/agent-desktop'
    assert entry['config']['failOnStartupError'] is False
    assert 'C:/Users/' not in json.dumps(entry)
