"""HTTP helpers and route modules can be imported without the application factory."""
from pathlib import Path
import subprocess
import sys
import textwrap


def test_request_helpers_and_routes_do_not_import_application():
    root = Path(__file__).resolve().parents[2]
    code = textwrap.dedent('''
        import importlib
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(sys.argv[1]) / 'src'))
        for name in ('case_bridge', 'library', 'recovery', 'intake',
                     'draft_confirmation', 'pdf_review', 'request_context'):
            importlib.import_module('cn_contract.web.' + name)
            assert 'cn_contract.web.app' not in sys.modules, name
        from cn_contract.web import app, request_context
        for name in ('same_origin', 'actor_in', 'bounded_body', 'unique', 'body_input'):
            assert getattr(app, name) is getattr(request_context, name), name
    ''')
    result = subprocess.run(
        [sys.executable, '-I', '-X', 'utf8', '-c', code, str(root)],
        cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
