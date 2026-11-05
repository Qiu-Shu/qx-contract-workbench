import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from stage import bundle_node,portable_config,verify_office_engine

class StageTests(unittest.TestCase):
    def test_missing_or_corrupt_office_engine_cannot_be_packaged(self):
        with tempfile.TemporaryDirectory(prefix='qx-office-package-') as folder:
            payload=Path(folder)
            with self.assertRaisesRegex(RuntimeError,'Office'):verify_office_engine(payload)
            engine=payload/'node_modules/@deepseek-ai/libreoffice-kit-win32-x64'
            engine.mkdir(parents=True)
            (engine/'package.json').write_text(json.dumps({'name':'@deepseek-ai/libreoffice-kit-win32-x64','version':'0.1.5'}))
            (engine/'bin').mkdir();(engine/'bin/helper.exe').write_bytes(b'synthetic engine')
            digest=hashlib.sha256(b'synthetic engine').hexdigest()
            (engine/'prebuilds.json').write_text(json.dumps({'version':'0.1.5','platform':'win32-x64','status':'built','files':{'bin/helper.exe':digest}}))
            verify_office_engine(payload)
            (engine/'bin/helper.exe').write_bytes(b'broken')
            with self.assertRaisesRegex(RuntimeError,'Office'):verify_office_engine(payload)
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
    def test_verified_delivery_uses_the_data_workspace(self):
        plugins=[p for block in portable_config() for p in block.get('insert',[])
                 if p.get('id')=='qx-verified-delivery']
        self.assertEqual(len(plugins),1)
        self.assertEqual(plugins[0]['name'],'@APP@/plugins/verified-delivery/index.mjs')
        self.assertEqual(plugins[0]['config']['workspace'],'@DATA@/workspace')

if __name__=='__main__':unittest.main()
