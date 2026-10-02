"""Azure processor. Managed uploads only; durable processing status and retryable errors."""
import logging
import os
from pathlib import Path
import tempfile
import azure.functions as func
from azure.storage.blob import ContentSettings
from musicdist.media import MAX_ASSET_BYTES, validate_master, transcode
from musicdist.store import get_store, NotFound
from musicdist.storage import service, PREVIEWS

app = func.FunctionApp()

@app.blob_trigger(arg_name='myblob', path='incoming-tracks/{name}', connection='AzureWebJobsStorage')
def audio_transcoder_trigger(myblob: func.InputStream):
    # Fail closed if deployed with a non-durable catalog.
    if os.getenv('CATALOG_BACKEND') != 'cosmos':
        raise RuntimeError('Azure worker requires CATALOG_BACKEND=cosmos')
    name = myblob.name.removeprefix('incoming-tracks/')
    parts = name.split('/')
    if len(parts) != 3:
        logging.warning('Legacy upload skipped: create an upload request in MusicDist first')
        return
    artist, release_id, filename = parts
    store = get_store()
    try:
        asset = store.get(artist, 'asset_' + Path(filename).stem)
    except NotFound:
        # Unknown blobs never become public; transient catalog races should retry.
        raise RuntimeError('Missing upload reservation') from None
    if asset['blob'] != name or asset['release_id'] != release_id or asset['kind'] != 'master':
        raise ValueError('Upload reservation mismatch')
    if asset['state'] == 'processed':
        return
    try:
        asset['state'] = 'processing'
        store.put(asset)
        with tempfile.TemporaryDirectory(prefix='musicdist-') as tmp:
            source = Path(tmp) / ('master' + Path(filename).suffix)
            count = 0
            with source.open('wb') as f:
                while chunk := myblob.read(1024 * 1024):
                    count += len(chunk)
                    if count > MAX_ASSET_BYTES:
                        raise ValueError('Master exceeds 1 GiB limit')
                    f.write(chunk)
            metadata = validate_master(source)
            preview = Path(tmp) / 'preview.mp3'
            transcode(source, preview)
            preview_name = f'{artist}/{release_id}/{asset["asset_id"]}.mp3'
            with preview.open('rb') as f:
                service().get_blob_client(PREVIEWS, preview_name).upload_blob(f, overwrite=True,
                    content_settings=ContentSettings(content_type='audio/mpeg'))
            asset.update(state='processed', metadata=metadata, preview_blob=preview_name, preview_container=PREVIEWS)
            asset.pop('error', None)
            store.put(asset)
    except Exception as exc:
        asset.update(state='failed', error=type(exc).__name__)
        try:
            store.put(asset)
        except Exception:
            logging.error('Could not record failed asset state')
        logging.error('Processing failed (%s); invocation will fail for retry', type(exc).__name__)
        raise
