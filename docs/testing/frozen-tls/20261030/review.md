# Frozen TLS packaging repair — scoped independent review

2026-10-30. Workspace: `D:/Documents/ChatGPT/律所项目`. Reviewed the complete supplied `frozen-network-review.diff` once, covering `5915cda..b999455`, against `frozen-network-brief.md` and the project instructions. This review makes no product edits or Git mutations.

## Spec — PASS

No scoped findings. `desktop/backend.spec` derives `codex-rejected-cas.pem` from the active build runtime's `ssl.__file__`, conditionally adds that precise file with destination `.`, and leaves its bytes untouched. This meets the requested adjacent-resource contract and preserves ordinary Python compatibility when the resource is absent. There is no client, receipt, budget, certificate-store, or TLS-verification behavior change.

The new test executes the actual spec with the requested PyInstaller boundary stubs and inspects the assets reaching `COLLECT`. It covers present/absent resource cases, the exact destination, binary preservation, and a decoy in a different Python prefix. The 0.5.3 metadata follow-up updates the package and lockfile root versions together with the current-version upgrade assertion, providing a distinct release artifact name within the agreed repair scope.

## Quality — PASS

No scoped findings. The implementation is a small resource-selection change consistent with the existing explicit-asset spec; it introduces no dependency or unnecessary abstraction. The regression test exercises the spec rather than matching source text and checks that resource selection follows the actual `ssl` module.

The independently inspected `red.json`, `green.json`, and `installed-green.json` support the root-cause diagnosis: without the resource, both frozen client initializations fail at `ssl.py:440`, Weixin pauses, and the model path reaches `sent_unknown` with zero requests. With the resource, both clients initialize, Weixin reaches `waiting_scan`, and the loopback model fixture reaches `received` with one request (4/4 checks in both green evidence files). These are local diagnostic boundary checks, not proof of a newly rebuilt installer's acceptance or of a successful external model call.

## Verification boundary

Reviewed the implementation report's recorded targeted results: packaging pytest 2 passed; desktop regression 409 passed; metadata packaging tests 3 passed; syntax and whitespace checks exit 0. Tests were not rerun, per the single scoped review/no repeated suites instruction. No build, external request, credentials, installation operation, broad repository crawl, or unrelated working-tree inspection was performed. The new candidate build and its acceptance remain the root agent's separate responsibility.

Spec: 0 findings. Quality: 0 findings. Dual PASS for this scoped patch.
