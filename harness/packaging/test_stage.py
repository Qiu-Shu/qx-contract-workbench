import json
from pathlib import Path
import tempfile
import unittest
from stage import bundle_node,portable_config

class StageTests(unittest.TestCase):
    def test_nearer_other_version_cannot_shadow_required_dependency(self):
        with tempfile.TemporaryDirectory(prefix='qx-stage-') as folder:
            root=Path(folder)
            def package(directory,name,version,deps=None):
                directory.mkdir(parents=True)
                (directory/'package.json').write_text(json.dumps({'name':name,'version':version,'dependencies':deps or {}}))
                return directory
            a=package(root/'a','a','1.0.0')
            q=package(root/'q','q','1.0.0')
            p=package(root/'p','p','1.0.0',{'a':'2.0.0','q':'2.0.0'})
            package(p/'node_modules/a','a','2.0.0')
            q2=package(p/'node_modules/q','q','2.0.0',{'a':'1.0.0'})
            package(q2/'node_modules/a','a','1.0.0')
            bundle_node([(a,'a'),(q,'q'),(p,'p')],root/'out')
            nested=root/'out/node_modules/p/node_modules/q/node_modules/a/package.json'
            self.assertEqual(json.loads(nested.read_text())['version'],'1.0.0')
    def test_portable_config_has_no_development_paths(self):
        config=json.dumps(portable_config())
        self.assertNotIn('C:/Users/Lenovo',config)
        self.assertNotIn('D:/qx-',config)
        self.assertIn('@DATA@/workspace',config)
        self.assertIn('@APP@/runtime/windows/python.exe',config)

if __name__=='__main__':unittest.main()
