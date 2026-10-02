"""Owner/admin-only API. Do not expose this shared admin token as artist login."""
from datetime import datetime, timezone
import hmac
import logging
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.background import BackgroundTask
from .models import Release, StrictModel, ID, DESTINATIONS
from .store import get_store, NotFound, Conflict
from . import storage
from .package import build_package
from .media import validate_artwork
from typing import Literal

app = FastAPI(title='MusicDist Admin', version='0.2.0')
security = HTTPBearer(auto_error=False)

def admin(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    expected = os.getenv('MUSICDIST_ADMIN_TOKEN', '')
    if len(expected) < 32:
        raise HTTPException(503, 'Admin access is not configured')
    if not credentials or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, 'Invalid admin token', headers={'WWW-Authenticate': 'Bearer'})

@app.exception_handler(NotFound)
async def missing(request, exc):
    return JSONResponse({'detail': 'Catalog item not found'}, status_code=404)

@app.exception_handler(Conflict)
async def conflict(request, exc):
    return JSONResponse({'detail': 'ID already exists; create a new draft version'}, status_code=409)

@app.exception_handler(Exception)
async def unexpected(request, exc):
    logging.error('API operation failed (%s)', type(exc).__name__)
    return JSONResponse({'detail': 'Operation failed. Check server configuration and asset processing status.'}, status_code=500)

@app.middleware('http')
async def headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://*.blob.core.windows.net; frame-ancestors 'none'"
    if request.url.path in {'/docs', '/redoc'}:
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' https://fastapi.tiangolo.com data:; frame-ancestors 'none'"
    return response

@app.get('/health/live')
def health():
    return {'status': 'ok', 'delivery_enabled': False}

@app.get('/')
def dashboard():
    return FileResponse(Path(__file__).parent.parent / 'static/index.html')

@app.get('/app.js')
def script():
    return FileResponse(Path(__file__).parent.parent / 'static/app.js', media_type='text/javascript')

@app.get('/style.css')
def style():
    return FileResponse(Path(__file__).parent.parent / 'static/style.css', media_type='text/css')

@app.get('/destinations', dependencies=[Depends(admin)])
def destinations():
    return [{'id': d, 'status': 'not_connected', 'delivery_enabled': False} for d in DESTINATIONS]

@app.post('/releases', status_code=201, dependencies=[Depends(admin)])
def create_release(release: Release):
    if release.artwork or any(t.master for t in release.tracks):
        raise HTTPException(422, 'Use Azure asset IDs in the API; local file paths are only supported by the CLI')
    item = {'id': 'release_' + release.id, 'partitionKey': release.artist_id, 'type': 'release',
            'state': 'draft', 'release': release.model_dump(mode='json')}
    get_store().put(item, create=True)
    return item

@app.get('/artists/{artist_id}/releases', dependencies=[Depends(admin)])
def releases(artist_id: str):
    return get_store().list(artist_id, 'release')

@app.get('/artists/{artist_id}/releases/{release_id}', dependencies=[Depends(admin)])
def release_detail(artist_id: str, release_id: str):
    item = get_store().get(artist_id, 'release_' + release_id)
    item['assets'] = [a for a in get_store().list(artist_id, 'asset') if a['release_id'] == release_id]
    return item

class Upload(StrictModel):
    artist_id: ID
    release_id: ID
    kind: Literal['master', 'artwork']
    track_id: ID | None = None
    extension: Literal['.wav', '.flac', '.m4a', '.jpg', '.jpeg', '.png']

@app.post('/uploads', dependencies=[Depends(admin)])
def upload(request: Upload):
    store = get_store()
    release = Release.model_validate(store.get(request.artist_id, 'release_' + request.release_id)['release'])
    if request.kind == 'master':
        if request.track_id not in {t.id for t in release.tracks} or request.extension not in {'.wav', '.flac', '.m4a'}:
            raise HTTPException(422, 'Select an existing track and a lossless audio extension')
    elif request.extension not in {'.jpg', '.jpeg', '.png'} or request.track_id is not None:
        raise HTTPException(422, 'Artwork requires JPEG/PNG and no track ID')
    asset_id = uuid.uuid4().hex
    container = storage.INCOMING if request.kind == 'master' else storage.ARTWORK
    blob = f'{request.artist_id}/{request.release_id}/{asset_id}{request.extension}'
    grant = storage.upload_url(container, blob)
    item = {'id': 'asset_' + asset_id, 'asset_id': asset_id, 'partitionKey': request.artist_id, 'type': 'asset',
        'release_id': request.release_id, 'track_id': request.track_id, 'kind': request.kind,
        'container': container, 'blob': blob, 'state': 'awaiting_upload'}
    store.put(item, create=True)
    return {'asset_id': asset_id, **grant, 'instruction': 'PUT the raw file bytes once. Request a new asset ID for a replacement.'}

class Selection(StrictModel):
    artist_id: ID
    release_id: ID
    artwork_asset_id: ID
    track_assets: dict[str, str]

@app.post('/packages', dependencies=[Depends(admin)])
def package(selection: Selection):
    store = get_store()
    release = Release.model_validate(store.get(selection.artist_id, 'release_' + selection.release_id)['release'])
    if set(selection.track_assets) != {t.id for t in release.tracks}:
        raise HTTPException(422, 'Supply exactly one asset for every track')
    temp = Path(tempfile.mkdtemp(prefix='musicdist-package-'))
    try:
        total_bytes = 0
        def fetch_asset(id, kind, track_id=None):
            nonlocal total_bytes
            asset = store.get(selection.artist_id, 'asset_' + id)
            if asset['release_id'] != selection.release_id or asset['kind'] != kind or asset['track_id'] != track_id:
                raise HTTPException(422, 'Asset does not belong to this release/track')
            if kind == 'master' and asset['state'] != 'processed':
                raise HTTPException(409, 'A selected master is not processed yet')
            path = temp / (asset['asset_id'] + Path(asset['blob']).suffix)
            props = storage.service().get_blob_client(asset['container'], asset['blob']).get_blob_properties()
            total_bytes += props.size
            if total_bytes > int(os.getenv('MAX_PACKAGE_BYTES', str(2 * 1024**3))):
                raise HTTPException(413, 'Release exceeds the server package limit; use local CLI preparation or a smaller release')
            storage.download(asset['container'], asset['blob'], path)
            if kind == 'artwork':
                validate_artwork(path)
            return path
        release.artwork = str(fetch_asset(selection.artwork_asset_id, 'artwork'))
        release.artwork_asset_id = selection.artwork_asset_id
        for track in release.tracks:
            track.asset_id = selection.track_assets[track.id]
            track.master = str(fetch_asset(track.asset_id, 'master', track.id))
        filename = f'{release.upc}-{uuid.uuid4().hex[:12]}.zip'
        target = temp / filename
        manifest = build_package(release, temp, target)
        store.put({'id': 'package_' + uuid.uuid4().hex, 'partitionKey': release.artist_id, 'type': 'package',
                   'release_id': release.id, 'state': 'prepared_not_delivered', 'manifest': manifest})
        return FileResponse(target, filename=filename, media_type='application/zip', background=BackgroundTask(shutil.rmtree, temp))
    except Exception as exc:
        shutil.rmtree(temp, ignore_errors=True)
        if isinstance(exc, ValueError):
            raise HTTPException(422, str(exc)) from None
        raise

@app.post('/deliveries', dependencies=[Depends(admin)])
def delivery():
    raise HTTPException(409, 'No approved DSP/partner adapter is configured. No release has been sent.')
