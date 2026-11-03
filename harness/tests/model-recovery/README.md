# Model recovery regression

Run with the installed Node 24 runtime:

```powershell
& 'C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' tests/model-recovery/run.mjs
```

The test reads only the `llm-deepseek` provider retry policy from `config/cordis.patch.yml`. It starts a separate official Harness web host with a temporary DSH_HOME, workspace, dependency-free profile and a loopback simulated DeepSeek Messages SSE endpoint. The actual installed DeepSeek adapter, agent loop, retry executor and MCP transport run unchanged. All text/files are synthetic; no production host, user session, WeChat, secret store or real provider is used. Temporary processes and files are cleaned up, and the compact report goes to `docs/checks/model-recovery/green.json`.

The synthetic MCP tools record their side effects. A successful first step writes a file, presents it and records a note. The next response includes partial text and malformed tool JSON. Assertions verify that recovery occurs within that same failed step, the previous results enter retry context, the failed stream remains an `assistant/attempt`, the incomplete attempt does not enter successful model history, user input appears once, and each previous side effect runs exactly once with unchanged output bytes. Additional cases cover an SSE stream ending without `message_stop`, user cancellation during retry delay, authentication and quota errors without retries, and a persistent format failure stopping after the configured retry budget.

`--expect-red` was run **before** the provider configuration change and requires a policy without MALFORMED_RESPONSE. Its preserved `red.json` records the original reproducible stop after the prior tools succeeded. It is not meant to be rerun against the fixed configuration. Early fixture setup attempts (profile bootstrap and provider identifiers) were corrected before that recorded red result; they are not product regressions.

Scope: this proves that Harness does not replay previous tool batches when retrying the failed model request. It does not claim arbitrary externally interrupted side effects are exactly-once, or that a future model cannot independently request a repeated business operation. Existing request IDs and recorded results remain relevant. No live provider pricing or legal-content quality is tested.
