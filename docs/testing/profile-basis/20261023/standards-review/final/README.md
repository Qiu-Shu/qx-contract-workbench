# CH-07C2a Standards review

Base: `37773d92f08e0b3bc2fed27064ceb011e8a72cd6`.

No actionable documented-standard violation or Fowler heuristic finding remains in this slice. All added DTOs are in domain.py. The helper shares C1 wire construction, does not access storage/secrets/network, and does not enable any grant or application entry. The future trusted assembler must establish saved database relations, current permissions, actual selected attachments and current profile/intake versions; offline consistency does not establish those facts.

Independent command (workspace root):

```
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-basis-20261023/standards-review/test_review_probe.py -q --tb=short --junitxml=.local/profile-basis-20261023/standards-review/final/results.xml
```

Exit 0: 9 passed, 1.01 seconds. Coverage: unchanged prior DTO definitions; four C1 byte comparisons including Unicode, escaping and long text; hostile Decimal precision/traps; coherent forged wire hash/length rejected; default provider permission still denied before secret resolution; preparation imports without HTTP/SQLAlchemy/FastAPI/PDF dependencies.

The initial independent run was 8 passed / 2 setup-teardown errors, exit 1: pytest used a 16,000-character parameter as its test ID, exceeding Windows' 32,767-character environment variable limit before that case executed. Only local probe IDs were shortened; original logs/XML remain in the parent directory. This was a review harness error, not a product failure or functional RED.

Five review input hashes remained stable across the checks (input-stability.json). The subsequently added service integration test was read separately and fingerprinted in integration-supplement.json, not independently rerun. No src or existing test edits, active data, desktop process, network calls or full-suite run occurred.
