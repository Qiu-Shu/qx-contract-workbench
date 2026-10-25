"""Import supplied DOCX references privately, without installing plugin instructions."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cn_contract.reception.knowledge import import_plugin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    manifest = import_plugin(args.archive, args.destination)
    print(f"Imported {manifest['original_documents']} original documents; {len(manifest['sources'])} unique sources.")
    print('References remain user-supplied and unverified; model calls: 0.')


if __name__ == '__main__':
    main()
