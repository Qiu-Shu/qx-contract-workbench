import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import stage

class AgentDesktopTests(unittest.TestCase):
    def test_portable_enabled_configuration_and_separate_state(self):
        rows=stage.portable_config()
        entry=next(p for r in rows for p in r.get('insert',[]) if p['id']=='qx-agent-desktop')
        self.assertFalse(entry['disabled'])
        self.assertEqual(entry['config']['args'],['mcp'])
        self.assertEqual(entry['config']['command'],'@APP@/tools/agent-desktop/1.2.0/agent-desktop.exe')
        self.assertEqual(entry['config']['env']['AGENT_DESKTOP_HOME'],'@DATA@/.local/agent-desktop')
        self.assertFalse(entry['config']['failOnStartupError'])
        self.assertNotIn('C:/Users/',json.dumps(entry))

    def test_copy_is_allowlisted_and_validates_executable(self):
        with tempfile.TemporaryDirectory(prefix='qx-ad-stage-') as directory:
            root=Path(directory);source=root/'source';source.mkdir();target=root/'target'
            content=b'synthetic executable'
            (source/'agent-desktop.exe').write_bytes(content)
            (source/'LICENSE').write_text('synthetic license')
            (source/'provenance.json').write_text(json.dumps({'version':'1.2.0','binarySha256':hashlib.sha256(content).hexdigest()}))
            (source/'private-state.json').write_text('must never ship')
            stage.copy_agent_desktop(target,source=source)
            self.assertEqual({p.name for p in target.iterdir()},{'agent-desktop.exe','LICENSE','provenance.json'})
            (source/'agent-desktop.exe').write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError,'agent-desktop'):
                stage.copy_agent_desktop(root/'broken',source=source)
            self.assertFalse((root/'broken').exists())

if __name__=='__main__':unittest.main()
