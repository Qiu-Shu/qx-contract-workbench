"""CLI routing and zero-side-effect rejection; real suite owned by root."""
from pathlib import Path
import subprocess,sys

ROOT=Path(__file__).resolve().parents[2]


def test_evaluate_command_is_an_actual_cli_entry():
    response=subprocess.run([sys.executable,'-X','utf8','-m','cn_contract.cli','--help'],capture_output=True,text=True)
    assert response.returncode==0 and 'evaluate' in response.stdout


def test_evaluate_rejects_unregistered_suite_before_artifact(tmp_path):
    other=tmp_path/'cases.json';other.write_text('[{"entrypoint":"os.system"}]')
    output=tmp_path/'evaluation.json'
    response=subprocess.run([sys.executable,'-X','utf8','-m','cn_contract.cli','evaluate','--suite',str(other),
        '--offline','--output',str(output)],capture_output=True,text=True)
    assert response.returncode==1 and 'EVALUATION_INVALID' in response.stderr
    assert not output.exists()


def test_without_offline_has_no_approved_real_provider(tmp_path):
    output=tmp_path/'evaluation.json'
    response=subprocess.run([sys.executable,'-X','utf8','-m','cn_contract.cli','evaluate',
        '--suite','tests/acceptance/cases.json','--output',str(output)],cwd=ROOT,capture_output=True,text=True)
    assert response.returncode==1 and 'EVALUATION_INVALID' in response.stderr
    assert not output.exists()
