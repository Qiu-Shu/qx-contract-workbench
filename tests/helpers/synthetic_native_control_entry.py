"""Test-only provider substitution around the real owned desktop entry.

Never shipped as an entry point. The existing transport enforces a numeric
loopback endpoint; production configuration has no endpoint override.
"""
import sys

from cn_contract.assistant import native_model_control
from cn_contract.assistant.providers.main import DeepSeekProvider


def install_judge(endpoint, report_path):
    """Only this test entry can substitute both exact loopback destinations."""
    import json
    from pathlib import Path
    import httpx
    import httpx2
    from cn_contract.assistant import native_judge_control
    from cn_contract.assistant.providers.jev import JevProvider

    class SyntheticJudgeControl(native_judge_control.NativeJudgeControl):
        def __init__(self, runtime, *, database=None):
            super().__init__(runtime, database=database, provider_factory=lambda config, resolver:
                JevProvider.for_synthetic_loopback(config, resolver, endpoint))

    native_judge_control.NativeJudgeControl = SyntheticJudgeControl
    allowed = {sys.argv[1]: 'main', endpoint: 'judge'}
    target = Path(report_path)
    counts = {'main': 0, 'judge': 0, 'blocked_other_httpx_requests': 0}

    def save():
        target.write_text(json.dumps(counts), encoding='utf-8')

    def check(request):
        provider = allowed.get(str(request.url))
        if provider is None or request.method != 'POST':
            counts['blocked_other_httpx_requests'] += 1
            save()
            raise RuntimeError('TEST_NON_LOOPBACK_PROVIDER_REQUEST_BLOCKED')
        counts[provider] += 1
        save()

    def wrap_sync(original):
        def send(self, request, *args, **kwargs):
            check(request)
            return original(self, request, *args, **kwargs)
        return send

    def wrap_async(original):
        async def send(self, request, *args, **kwargs):
            check(request)
            return await original(self, request, *args, **kwargs)
        return send

    save()
    for module in (httpx, httpx2):
        module.Client.send = wrap_sync(module.Client.send)
        module.AsyncClient.send = wrap_async(module.AsyncClient.send)


class SyntheticControl(native_model_control.NativeModelControl):
    def __init__(self, database, registry):
        super().__init__(database, registry, provider_factory=lambda config, resolver:
            DeepSeekProvider.for_synthetic_loopback(config, resolver, sys.argv[1]))


if __name__ == '__main__':
    if len(sys.argv) > 2:
        if len(sys.argv) != 5 or sys.argv[2] != '--judge':
            raise SystemExit('invalid synthetic judge entry arguments')
        install_judge(sys.argv[3], sys.argv[4])
    native_model_control.NativeModelControl = SyntheticControl
    from cn_contract.desktop_entry import main
    raise SystemExit(main())
