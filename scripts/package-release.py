"""Create the GitHub update asset and manifest; signing is a separate private-key step."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import tarfile

root = Path(__file__).resolve().parent.parent
output = Path(sys.argv[1] if len(sys.argv) > 1 else 'dist')
output.mkdir(parents=True, exist_ok=True)
tree = ast.parse((root / 'airnode/__init__.py').read_text())
version = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))
if len(sys.argv) > 2 and sys.argv[2] != 'v' + version: raise SystemExit('Tag must match the application version')
archive = output / 'airnode-update.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    for folder in ('airnode', 'web', 'deploy', 'scripts', 'docs'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                tar.add(path, arcname='AirNode/' + path.relative_to(root).as_posix(), recursive=False)
    for name in ('README.md', 'LICENSE', 'THIRD_PARTY.md'):
        tar.add(root / name, arcname='AirNode/' + name)
manifest = {'format': 1, 'repository': 'TaxiwayBravo/airnode', 'version': version,
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'readsb_commit': (root / 'deploy/readsb.commit').read_text().strip()}
(output / 'airnode-release.json').write_text(json.dumps(manifest, sort_keys=True) + '\n', encoding='utf-8')
print('Packaged AirNode ' + version)
