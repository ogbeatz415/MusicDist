from datetime import datetime, timedelta, timezone
from functools import lru_cache
import os
from azure.identity import DefaultAzureCredential
from azure.core import MatchConditions
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
from .media import MAX_ASSET_BYTES

INCOMING = 'incoming-tracks'
ARTWORK = 'release-artwork'
PREVIEWS = 'music-previews'  # Private; never publishes unreleased music anonymously.

@lru_cache
def service():
    return BlobServiceClient(account_url=os.environ['STORAGE_ACCOUNT_URL'], credential=DefaultAzureCredential())

def upload_url(container, name):
    client = service()
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
    key = client.get_user_delegation_key(start, expiry)
    sas = generate_blob_sas(account_name=client.account_name, container_name=container, blob_name=name,
        user_delegation_key=key, permission=BlobSasPermissions(create=True), start=start, expiry=expiry, protocol='https')
    return {'upload_url': client.get_blob_client(container, name).url + '?' + sas,
            'expires_at': expiry.isoformat(), 'method': 'PUT', 'headers': {'x-ms-blob-type': 'BlockBlob'}}

def download(container, name, path):
    blob = service().get_blob_client(container, name)
    props = blob.get_blob_properties()
    if props.size > MAX_ASSET_BYTES:
        raise ValueError('Asset exceeds 1 GiB limit')
    with open(path, 'wb') as f:
        blob.download_blob(etag=props.etag, match_condition=MatchConditions.IfNotModified).readinto(f)
    return props
