"""Download a pinned public site artifact for Pages; never call the law API."""
import argparse,hashlib,json,tarfile,tempfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from scripts.validate_static_galaxies import validate

RELEASE_PREFIX='https://github.com/gschamisle/tax-amendment-assistant/releases/download/'

def fetch(metadata,destination):
    spec=json.loads(metadata.read_text(encoding='utf-8'))
    if not spec['url'].startswith(RELEASE_PREFIX):raise ValueError('Unexpected release host or repository')
    if destination.exists():raise ValueError('Destination must be new')
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'site.tar.gz';digest=hashlib.sha256();size=0
        with urlopen(spec['url'],timeout=120) as source,archive.open('wb') as output:
            while chunk:=source.read(1024*1024):
                size+=len(chunk)
                if size>250*1024*1024:raise ValueError('Archive too large')
                digest.update(chunk);output.write(chunk)
        if digest.hexdigest()!=spec['sha256']:raise ValueError('Release checksum mismatch')
        with tarfile.open(archive,'r:gz') as tar:
            members=tar.getmembers()
            if len(members)>20000 or sum(m.size for m in members)>1024**3:raise ValueError('Unsafe archive size')
            for m in members:
                name=PurePosixPath(m.name)
                if not m.isfile() or name.is_absolute() or '..' in name.parts or '\\' in m.name:raise ValueError('Unsafe archive member')
            destination.mkdir(parents=True)
            tar.extractall(destination,filter='data')
    result=validate(destination)
    if result['version']!=spec['data_version']:raise ValueError('Unexpected data version')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--metadata',type=Path,default=Path('static-web-release.json'));p.add_argument('--destination',type=Path,default=Path('_site'));a=p.parse_args()
    print(json.dumps(fetch(a.metadata,a.destination),indent=2))
