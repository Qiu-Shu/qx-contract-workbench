"""Offline checks of method loading, source provenance and deployable Skill files."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import workflows


class WorkflowTests(unittest.TestCase):
    def test_release_registers_only_approved_practice_method(self):
        self.assertEqual(set(workflows._WORKFLOWS), {'reception', 'contract', 'case', 'hearing', 'evidence'})
        for name in ('litigation', 'employment', 'corporate', 'compliance', 'ip',
                     'qx-litigation-drafting', 'qx-employment-review', 'qx-corporate-records',
                     'qx-compliance-work', 'qx-ip-register'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                workflows.workflow(name)

    def test_all_four_methods_load_as_natural_text_with_provenance(self):
        for name, (skill, _title, _suggested) in workflows._WORKFLOWS.items():
            with self.subTest(name=name):
                result = workflows.workflow(name)
                directory = workflows.SKILLS / skill
                body = (directory / 'references' / 'method.md').read_text(encoding='utf8')
                self.assertEqual(result['method'], body)
                self.assertEqual(result['method_sha256'], hashlib.sha256(body.encode()).hexdigest())
                self.assertEqual(result['output_protocol'], 'natural_language')
                self.assertTrue(body.strip())
                self.assertTrue(result['sources'])
                # Old transport directives must not leak back into model method text.
                self.assertNotRegex(body, r'(?:只|仅)输出\s*JSON|每项严格为|start/end[是为]')
                self.assertTrue(result['suggested_skills'])
                json.dumps(result, ensure_ascii=False)

    def test_aliases_unknown_names_and_returned_values_are_isolated(self):
        for alias, expected in workflows._ALIASES.items():
            self.assertEqual(workflows.workflow(alias)['name'], expected)
        for name in ('', '../../workspace', 'unknown', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                workflows.workflow(name)
        result = workflows.workflow('contract')
        result['suggested_skills'].clear()
        result['sources'].clear()
        self.assertTrue(workflows.workflow('contract')['suggested_skills'])
        self.assertTrue(workflows.workflow('contract')['sources'])

    def test_portable_skill_copy_needs_no_legacy_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            for skill, _title, _suggested in workflows._WORKFLOWS.values():
                shutil.copytree(workflows.SKILLS / skill, target / skill)
            with patch.object(workflows, 'SKILLS', target):
                self.assertEqual(workflows.workflow('case')['name'], 'case')
                (target / 'qx-case-work/references/method.md').unlink()
                with self.assertRaisesRegex(ValueError, '保留已完成的回答'):
                    workflows.workflow('case')

    def test_skill_frontmatter_and_relative_references_are_loadable(self):
        for skill, _title, _suggested in workflows._WORKFLOWS.values():
            directory = workflows.SKILLS / skill
            text = (directory / 'SKILL.md').read_text(encoding='utf8')
            self.assertRegex(text, rf'\A---\r?\nname: {re.escape(skill)}\r?\n')
            self.assertIn('description:', text.split('---', 2)[1])
            for relative in re.findall(r'\]\((references/[^)#]+)(?:#[^)]*)?\)', text):
                path = (directory / relative).resolve()
                self.assertTrue(path.is_relative_to(directory.resolve()))
                self.assertTrue(path.is_file(), relative)
            for name in workflows.workflow(skill)['suggested_skills']:
                self.assertTrue((workflows.PACKAGED_SKILLS / name / 'SKILL.md').is_file(), name)

    def test_recorded_old_source_hashes_match_used_bytes(self):
        old = Path('D:/qx-contract-workbench-20261102')
        if not old.is_dir():
            self.skipTest('Original source checkout is not required to run the deployed methods')
        for name in ('reception', 'contract', 'case'):
            for source in workflows.workflow(name)['sources']:
                with self.subTest(source=source['path']):
                    raw = (old / source['path']).read_bytes()
                    self.assertRegex(source['git_head'], r'^[0-9a-f]{40}$')
                    self.assertEqual(source['bytes'], len(raw))
                    self.assertEqual(source['sha256'], hashlib.sha256(raw).hexdigest())
                    section = source['sections']
                    chosen = b''.join(raw.splitlines(keepends=True)[section['start_line']-1:section['end_line']])
                    self.assertEqual(section['sha256'], hashlib.sha256(chosen).hexdigest())


if __name__ == '__main__':
    unittest.main()
