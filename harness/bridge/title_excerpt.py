"""Read short local excerpts for session naming; reuse the material parser."""
import json
import sys
from pathlib import Path
from store import MaterialStore
from reader import parse, text_encoding


def excerpts(workspace, paths, image_paths=()):
    store = MaterialStore(workspace)
    results = []
    for value in paths[:3]:
        text = ''
        try:
            source = store.safe(value)
            if value in image_paths:
                # Harness image objects use a digest filename with no extension.
                from PIL import Image
                from cn_contract.documents.material_ocr import recognize
                with Image.open(source) as image:
                    text = '\n'.join(block[1] for block in recognize(image.convert('RGB')))[:6000]
            elif source.suffix.lower() in {'.txt', '.md', '.csv', '.tsv', '.json'}:
                with source.open(encoding=text_encoding(source)) as stream:
                    text = stream.read(6000)
            else:
                record = store.register(str(source))
                # Parsing is local; PDF naming needs only the opening pages.
                if record.get('status') not in {'ready', 'partial', 'no_text'}:
                    parse(store, str(source), page_count=2)
                text = '\n'.join(row['text'] for row in store.read(str(source), limit=2)['chunks'])[:6000]
        except Exception:
            # An unreadable upload must not stop the conversation; its name remains available.
            pass
        results.append({'text': text})
    return results


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(excerpts(request['workspace'], request['paths'], request.get('image_paths', [])), ensure_ascii=False))
