"""Explicit fixed-release preparation; application requests never download assets."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

from cn_contract.documents import pdfjs_assets as gate


def verified_members(raw, manifest):
    if len(raw) != manifest['tarball_bytes'] or sha256(raw).hexdigest() != manifest['tarball_sha256']:
        raise ValueError('release digest mismatch')
    expected = {row['path']: row for row in manifest['files']}
    found, names, total = {}, set(), 0
    with tarfile.open(fileobj=BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or name.as_posix() != member.name
                    or '\\' in member.name or ':' in member.name or name.parts[0] != 'package'):
                raise ValueError('unsafe member')
            if member.isdir(): continue
            total += member.size
            if (not member.isfile() or member.name in names or member.size > 20_000_000
                    or total > 250_000_000 or len(names) >= 2000):
                raise ValueError('invalid archive')
            names.add(member.name)
            relative = PurePosixPath(*name.parts[1:]).as_posix()
            if relative in expected:
                row = expected[relative]
                data = archive.extractfile(member).read(row['bytes'] + 1)
                if len(data) != row['bytes'] or sha256(data).hexdigest() != row['sha256']:
                    raise ValueError('asset mismatch')
                found[relative] = data
    if found.keys() != expected.keys(): raise ValueError('missing assets')
    return found


def main():
    raw_lock = gate.MANIFEST_PATH.read_bytes()
    if sha256(raw_lock).hexdigest() != gate.MANIFEST_SHA256: raise ValueError('lock mismatch')
    manifest = json.loads(raw_lock)
    if gate.ASSET_ROOT.exists():
        gate._inventory()
        print('LOCAL_ASSETS_VERIFIED files=' + str(len(manifest['files'])))
        return
    url = 'https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.4.299.tgz'
    if manifest['tarball_url'] != url: raise ValueError('source mismatch')
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read(manifest['tarball_bytes'] + 1)
    files = verified_members(raw, manifest)
    gate.ASSET_ROOT.parent.mkdir(parents=True, exist_ok=True)
    gate._regular(gate.ASSET_ROOT.parent, directory=True)
    gate.ASSET_ROOT.mkdir(exist_ok=False)
    # A interrupted preparation remains unavailable; never overwrite an existing set.
    for relative, data in files.items():
        path = gate.ASSET_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        gate._regular(path.parent, directory=True)
        with path.open('xb') as output: output.write(data)
    gate._inventory()
    print('LOCAL_ASSETS_PREPARED files=' + str(len(files)))


if __name__ == '__main__': main()
