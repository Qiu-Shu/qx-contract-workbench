"""Confirm the baseline defaults match specification 2.0."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cn_contract.config import DEFAULTS_PATH, SPEC_DEFAULTS_SHA256, load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, default=DEFAULTS_PATH)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.file)
    except (OSError, ValueError) as exc:
        print(f'CONFIG_INVALID: {type(exc).__name__}', file=sys.stderr)
        return 1
    print(settings.config_sha256)
    if settings.config_sha256 != SPEC_DEFAULTS_SHA256:
        print('DEFAULTS_HASH_MISMATCH', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
