"""Portable internal handoff packages, deliberately not advertised as DDEX."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from .media import validate_master, validate_artwork
from .models import Release


def validate_release(release: Release, base: Path):
    errors = []
    assets = []
    if not release.rights_confirmed:
        errors.append('Confirm you control the rights for the selected territories')
    if not release.artwork:
        errors.append('Artwork is missing')
    else:
        try:
            p = (base / release.artwork).resolve()
            assets.append({'source': p, 'path': 'artwork/cover' + p.suffix.lower(), 'kind': 'artwork', **validate_artwork(p)})
        except (ValueError, OSError) as exc:
            errors.append(f'Artwork: {exc}')
    for i, track in enumerate(release.tracks, 1):
        if not track.master:
            errors.append(f'{track.id}: master is missing')
            continue
        try:
            p = (base / track.master).resolve()
            assets.append({'source': p, 'path': f'audio/{i:03d}_{track.isrc}{p.suffix.lower()}',
                           'kind': 'audio', 'track_id': track.id, **validate_master(p)})
        except Exception as exc:
            errors.append(f'{track.id}: {type(exc).__name__}: {exc}' if isinstance(exc, ValueError) else f'{track.id}: audio inspection failed ({type(exc).__name__})')
    return errors, assets


def build_package(release: Release, base: Path, output: Path):
    errors, assets = validate_release(release, base)
    if errors:
        raise ValueError('\n'.join(errors))
    metadata = release.model_dump(mode='json')
    metadata.pop('artwork', None)
    for t in metadata['tracks']:
        t.pop('master', None)
    manifest = {
        'schema': 'musicdist.internal-handoff.v1', 'status': 'prepared_not_delivered',
        'created_at': datetime.now(timezone.utc).isoformat(), 'release': metadata,
        'assets': [{k: v for k, v in a.items() if k != 'source'} for a in assets],
        'deliveries': [{'destination': d, 'status': 'blocked',
                        'reason': 'Approved delivery connection and recipient-specific validation required'} for d in release.destinations],
        'notice': 'Internal handoff package. Not a DDEX message or proof of DSP acceptance.'}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / 'release.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
            z.writestr('manifest.json', json.dumps(manifest, indent=2))
            z.writestr('README.txt', manifest['notice'] + '\nAudio files are unchanged original masters.\n')
            for asset in assets:
                z.write(asset['source'], asset['path'])
        # Exclusive creation prevents accidental replacement of a previous delivery package.
        try:
            with output.open('xb') as dst, staged.open('rb') as src:
                shutil.copyfileobj(src, dst)
        except FileExistsError:
            raise ValueError('Output already exists. Choose a new versioned filename.') from None
    return manifest
