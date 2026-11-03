import unittest
from unittest.mock import patch
from subprocess import CompletedProcess, TimeoutExpired
import browser


class BrowserTests(unittest.TestCase):
    def setUp(self):
        browser.SNAPSHOTS.clear()

    def test_missing_or_duplicate_target_never_dispatches(self):
        with patch('browser.execute') as run:
            for arguments in [['snap', '-i'], ['fill', '@3', 'value'], ['reload', '--tab', 'a', '--tab', 'b']]:
                with self.assertRaises(browser.ToolError):
                    browser.browser(arguments)
            run.assert_not_called()

    def test_failed_mutation_or_observation_cannot_reuse_old_snapshot(self):
        for action in ['fill', 'type', 'hover', 'scroll', 'snap', 'goto']:
            browser.SNAPSHOTS['tab'] = 'old-token'
            with patch('browser.execute', side_effect=browser.ToolError('synthetic failure')):
                with self.assertRaises(browser.ToolError):
                    browser.browser([action, '--tab', 'tab'])
            self.assertNotIn('tab', browser.SNAPSHOTS, action)

    def test_click_has_one_dispatch_and_consumes_the_snapshot_on_failure(self):
        browser.SNAPSHOTS['tab'] = 'observed-token'
        with patch('browser.evaluate', side_effect=browser.ToolError('synthetic failure')) as evaluate:
            with self.assertRaises(browser.ToolError):
                browser.browser(['click', '@3', '--tab', 'tab'])
            evaluate.assert_called_once()
        self.assertNotIn('tab', browser.SNAPSHOTS)

    def test_arguments_are_not_shell_code(self):
        with patch('browser.subprocess.run', return_value=CompletedProcess([], 0, '{"ok":true}', '')) as run:
            result = browser.browser(['fill', '@3', 'hello; $(echo secret)', '--tab', '123'])
        self.assertTrue(result['ok'])
        self.assertIn('hello; $(echo secret)', run.call_args.args[0])
        self.assertFalse(run.call_args.kwargs.get('shell', False))

    def test_rejects_unrelated_commands(self):
        for args in [['site', 'recommend'], ['daemon', 'stop'], ['cookies'], ['site', 'update'], []]:
            with self.assertRaises(ValueError):
                browser.validate_arguments(args)

    def test_reports_cli_failure(self):
        with patch('browser.subprocess.run', return_value=CompletedProcess([], 1, '', 'Cannot find browser')):
            with self.assertRaisesRegex(browser.ToolError, 'Cannot find browser'):
                browser.browser(['status'])

    def test_timeout_is_not_success(self):
        with patch('browser.subprocess.run', side_effect=TimeoutExpired('node', 90)):
            with self.assertRaisesRegex(browser.ToolError, '超时'):
                browser.browser(['status'])


if __name__ == '__main__':
    unittest.main()
