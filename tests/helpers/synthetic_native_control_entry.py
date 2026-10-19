"""Test-only provider substitution around the real owned desktop entry.

Never shipped as an entry point. The existing transport enforces a numeric
loopback endpoint; production configuration has no endpoint override.
"""
import sys

from cn_contract.assistant import native_model_control
from cn_contract.assistant.providers.main import DeepSeekProvider


class SyntheticControl(native_model_control.NativeModelControl):
    def __init__(self, database, registry):
        super().__init__(database, registry, provider_factory=lambda config, resolver:
            DeepSeekProvider.for_synthetic_loopback(config, resolver, sys.argv[1]))


if __name__ == '__main__':
    native_model_control.NativeModelControl = SyntheticControl
    from cn_contract.desktop_entry import main
    raise SystemExit(main())
