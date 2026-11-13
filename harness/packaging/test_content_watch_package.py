import json
from pathlib import Path
import unittest


class ContentWatchPackageTests(unittest.TestCase):
    def test_portable_watcher_uses_current_user_data_and_bundled_component_preparer(self):
        source = Path(__file__).with_name('payload-config') / 'portable.json'
        patches = json.loads(source.read_text(encoding='utf-8'))
        watchers = [plugin for patch in patches for plugin in patch.get('insert', [])
                    if plugin.get('id') == 'qx-content-watch']
        self.assertEqual(len(watchers), 1)
        value = watchers[0]
        self.assertEqual(value['name'], '@APP@/plugins/content-watch/index.mjs')
        self.assertEqual(value['config']['workspace'], '@DATA@/workspace')
        self.assertEqual(value['config']['stateDir'], '@DATA@/.local/content-watch')
        self.assertEqual(set(value['config']), {'workspace', 'stateDir'})


if __name__ == '__main__':
    unittest.main()
