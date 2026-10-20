"""Read-only evidence check; does not execute tests or alter resource budgets."""
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
BASE = "13f53bf986fb672834d2952c0276b52ea41b3d9c"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


full = json.loads((EVIDENCE / "full-verification.json").read_text(encoding="utf-8"))
before, after = full["inputs_before"], full["inputs_after"]
current = {name: digest(ROOT / name) for name in before}
xml = ET.parse(EVIDENCE / "full.xml")
cases = xml.findall(".//testcase")
failed = [case for case in cases if case.find("failure") is not None]
budget = "src/cn_contract/library/budget.py"
baseline = subprocess.check_output(["git", "show", f"{BASE}:{budget}"], cwd=ROOT)
now = (ROOT / budget).read_bytes()
result = {
    "full_counts": {"tests": len(cases), "failed": len(failed),
        "errors": sum(c.find("error") is not None for c in cases),
        "skipped": sum(c.find("skipped") is not None for c in cases)},
    "failure_groups": dict(Counter(case.attrib["classname"] for case in failed)),
    "failure_mentions_disk_budget": sum("LIBRARY_DISK_BUDGET" in str(case.find("failure").text) for case in failed),
    "failure_without_disk_budget_text": [case.attrib for case in failed
        if "LIBRARY_DISK_BUDGET" not in str(case.find("failure").text)],
    "inputs": {"count": len(before), "before_after_equal": before == after,
        "before_current_equal": before == current,
        "differences": [name for name in before if before[name] != current[name]]},
    "budget": {"baseline": BASE, "file": budget,
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "current_sha256": digest(ROOT / budget), "byte_equal": baseline == now,
        "newline_normalized_equal": baseline.replace(b"\r\n", b"\n") == now.replace(b"\r\n", b"\n"),
        "git_diff": subprocess.check_output(["git", "diff", BASE, "--", budget], cwd=ROOT).decode("utf-8"),
        "threshold_bytes": 40 * 1024 ** 3},
    "gates": [{"name": value["name"], "exit_code": value["exit_code"]}
        for value in full["results"] if value["name"].startswith("gate-")],
    "scope": "Artifact/source audit only; no test execution or product mutation.",
}
recovery_path = EVIDENCE / "recovery-verification.json"
if recovery_path.exists():
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    recovered = ET.parse(EVIDENCE / "environment-recovery.xml").findall(".//testcase")
    def node(case):
        return case.attrib["classname"].replace(".", "/") + ".py::" + case.attrib["name"]
    original_nodes = [node(case) for case in failed]
    recovered_nodes = [node(case) for case in recovered]
    command_nodes = [arg for arg in recovery["command"] if arg.startswith("tests/")]
    result["recovery"] = {
        "exit_code": recovery["exit_code"],
        "counts": {"tests": len(recovered),
            "failed": sum(c.find("failure") is not None for c in recovered),
            "errors": sum(c.find("error") is not None for c in recovered),
            "skipped": sum(c.find("skipped") is not None for c in recovered)},
        "exact_failed_node_set": set(original_nodes) == set(recovered_nodes),
        "no_duplicate_nodes": len(recovered_nodes) == len(set(recovered_nodes)),
        "command_exact_failed_node_order": command_nodes == original_nodes,
        "record_exact_failed_node_order": recovery["failed_full_nodes"] == original_nodes,
        "basetemp": next(arg for arg in recovery["command"] if arg.startswith("--basetemp=")),
        "inputs_equal_to_full_reported": recovery["inputs_equal_to_full"],
        "inputs_equal_to_full_independently_recomputed": after == current,
        "combined_distinct_passing_cases": len(cases) - len(failed) + len(recovered),
        "single_full_run_green": False,
    }
(EVIDENCE / "environment-source-check.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
