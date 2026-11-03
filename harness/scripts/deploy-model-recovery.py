"""Enable the official provider's request recovery without replacing the profile."""
from datetime import datetime
from pathlib import Path
import json
import os
import shutil
from tempfile import NamedTemporaryFile
import yaml

MARKER = '# qunxing-model-recovery-v1'


def deploy(root):
    root = Path(root)
    rows = yaml.safe_load((root / 'config/cordis.patch.yml').read_text(encoding='utf-8-sig'))
    entry = next(row for row in rows if row.get('id') == 'llm-deepseek'
                 and 'retryPolicy' in row.get('config', {}))
    patch = {'id': entry['id'], 'config': {'retryPolicy': entry['config']['retryPolicy']}}
    target = root / '.local/dsh-home/profiles/web/cordis.patch.yml'
    original = target.read_bytes()
    if MARKER.encode() in original:
        return False
    text = original.decode('utf-8')
    document = yaml.compose(text)
    if document is not None and not isinstance(document, yaml.SequenceNode):
        raise ValueError('The existing profile must be a YAML sequence; it was not changed.')
    value = json.dumps(patch, ensure_ascii=False)
    if document is not None and document.flow_style:
        position = document.end_mark.index - 1
        insertion = (',' if document.value else '') + '\n' + MARKER + '\n' + value + '\n'
    else:
        position = document.end_mark.index if document is not None else len(text)
        insertion = '\n' + MARKER + '\n- ' + value + '\n'
    updated = text[:position] + insertion + text[position:]
    yaml.compose(updated)
    backup = root / '.local/backups' / ('model-recovery-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.yml')
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    if target.read_bytes() != original:
        raise RuntimeError('Profile changed concurrently; retry against its current contents.')
    temporary = None
    try:
        with NamedTemporaryFile(dir=target.parent, prefix='.qx-recovery-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


if __name__ == '__main__':
    changed = deploy(Path(__file__).resolve().parents[1])
    print('Model request recovery enabled; existing profile preserved.' if changed else 'Model recovery already configured.')
