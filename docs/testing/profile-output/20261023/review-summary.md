# Independent reviews and disposition

Fixed baseline: `1a7072bb905568a24292a53f3f3133c7c9fbb4f6`. Reviews used only synthetic text and random loopback ports; no active database or desktop backend interaction.

- Architecture preflight required empty wire citations, server-owned source identities, refusal of received/checked materials, and post-response revocation handling with retained usage. Implemented and covered by codec/provider probes.
- Spec first run: 9 assertion groups pass, plus observations of accepted integer money and numeric date strings. Those observations were findings, not successful legal parsing. P2 numeric date coercion and P3 non-string money accepted range were fixed solely in the new wire DTO. Final 13 groups pass (original 9 + new 4), exit 0. [Original report](spec-review/report.json), [final report](spec-review/final/report.json).
- Standards first run: 5 passed / 3 failed, exit 1; all three failures exposed numeric dates interpreted as epoch timestamps. Final original 8 probes pass, exit 0; separate 4 compatibility probes pass, exit 0. Both source snapshots and original failures are retained. [Original log](standards-review/output.log), [final log](standards-review/final/output.log).
- No remaining required finding in the reviewed C1 scope. Exact quoting proves location, not whether a proposed fact is supported in substance. C2 must reconstruct the source under current permission and bind protocol purpose/wire bytes before adoption and atomic saving.

Commands are recorded in the reviewer artifacts. For Spec: `.venv/Scripts/python.exe -X utf8 .local/profile-output-20261023/spec-review/final/probe.py`. For Standards: the same interpreter with `-m pytest`, running the independent `test_review_probe.py` and `test_compatibility.py` separately. These results overlap with the root regression and are not added into a project-wide test total.
