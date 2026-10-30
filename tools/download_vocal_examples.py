"""Download the provider's public research excerpts into an empty directory.

See MUSDB's terms before other uses. Audio is not part of the application package.
"""
import argparse
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen
import zipfile

URL = 'https://github.com/sigsep/sigsep-mus-db/releases/download/v0.4.0/MUSDB18-7-STEMS.zip'
SHA256 = '365f66acffc57282e474a4c24b32afec3678258c50b8d45646ac849b0a287df3'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    if root.exists() and any(root.iterdir()):
        parser.error('Use an empty destination; existing research files are preserved')
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rated-rip-music-') as temporary:
        archive = Path(temporary) / 'musdb7.zip'
        digest = hashlib.sha256()
        with urlopen(URL, timeout=60) as response, archive.open('wb') as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise ValueError('Archive checksum mismatch; nothing was extracted')
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if not (root / member.filename).resolve().is_relative_to(root):
                    raise ValueError('Unsafe archive path')
            bundle.extractall(root)
    print(f'Verified and extracted {len(list(root.glob("*/*.stem.mp4")))} excerpts into {root}')


if __name__ == '__main__':
    main()
