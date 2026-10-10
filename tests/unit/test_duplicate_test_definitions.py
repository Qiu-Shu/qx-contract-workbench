"""A later test definition must never silently replace an earlier scenario."""
import ast
from pathlib import Path
from collections import Counter


def test_no_duplicate_test_definitions_in_module_or_class():
    duplicates=[]
    for path in Path(__file__).resolve().parents[1].rglob('test_*.py'):
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for scope in (tree, *(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef))):
            names=Counter(n.name for n in scope.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_'))
            duplicates.extend((str(path),name) for name,count in names.items() if count>1)
    assert duplicates==[]
