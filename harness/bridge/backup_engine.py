"""Extract exactly the pinned restic executable; never interpret archive member paths."""
import hashlib
from pathlib import Path
import sys
import zipfile

def main():
    source, target = map(Path, sys.argv[1:])
    with zipfile.ZipFile(source) as archive:
        expected = 'restic_0.19.1_windows_amd64.exe'
        if archive.namelist() != [expected] or archive.getinfo(expected).file_size > 64 * 1024**2:
            raise ValueError('BACKUP_ENGINE_UNVERIFIED')
        content = archive.read(expected)
    if hashlib.sha256(content).hexdigest() != 'b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830':
        raise ValueError('BACKUP_ENGINE_UNVERIFIED')
    with target.open('xb') as stream:
        stream.write(content)

if __name__ == '__main__':
    main()
