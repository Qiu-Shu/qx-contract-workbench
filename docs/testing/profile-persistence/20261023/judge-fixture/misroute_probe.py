"""Negative control: deliberately misroute only synthetic in-process handlers."""
from pathlib import Path
import sys

import pytest
from cn_contract import desktop_control as control

target = sys.argv[1]
assert target in ('main', 'context')
original = control.NativeControlHandler.__init__


def misroute(self, main, judge):
    original(self, main, judge)
    self.authorize_judge = self.authorize if target == 'main' else self.authorize_context


control.NativeControlHandler.__init__ = misroute
raise SystemExit(pytest.main([
    'tests/unit/test_judge_authorization_protocol.py::test_dual_dispatch_routes_authorization_without_touching_main',
    '-q', '--junitxml='+str(Path(__file__).parent/f'negative-{target}.xml')]))
