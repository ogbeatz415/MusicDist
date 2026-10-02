"""Catalog adapters: SQLite for local development, Cosmos for Azure deployment."""
from functools import lru_cache
import json
import os
import sqlite3
from pathlib import Path

class NotFound(Exception):
    pass

class Conflict(Exception):
    pass

class LocalStore:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS items (artist TEXT, id TEXT, body TEXT, PRIMARY KEY(artist,id))')
    def connect(self):
        return sqlite3.connect(self.path, timeout=30)
    def get(self, artist, id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM items WHERE artist=? AND id=?', (artist, id)).fetchone()
        if not row:
            raise NotFound()
        return json.loads(row[0])
    def put(self, item, create=False):
        with self.connect() as db:
            try:
                verb = 'INSERT' if create else 'INSERT OR REPLACE'
                db.execute(f'{verb} INTO items VALUES (?,?,?)', (item['partitionKey'], item['id'], json.dumps(item)))
            except sqlite3.IntegrityError:
                raise Conflict() from None
        return item
    def list(self, artist, kind):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM items WHERE artist=?', (artist,)).fetchall()
        return [i for row in rows if (i := json.loads(row[0]))['type'] == kind]

class CosmosStore:
    def __init__(self):
        from azure.identity import DefaultAzureCredential
        from azure.cosmos import CosmosClient
        self.client = CosmosClient(os.environ['COSMOS_ENDPOINT'], credential=DefaultAzureCredential())
        self.container = self.client.get_database_client(os.getenv('COSMOS_DATABASE', 'MusicCatalog')).get_container_client(os.getenv('COSMOS_CONTAINER', 'CatalogItems'))
    def get(self, artist, id):
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        try:
            return self.container.read_item(item=id, partition_key=artist)
        except CosmosResourceNotFoundError:
            raise NotFound() from None
    def put(self, item, create=False):
        from azure.cosmos.exceptions import CosmosResourceExistsError
        try:
            return (self.container.create_item if create else self.container.upsert_item)(body=item)
        except CosmosResourceExistsError:
            raise Conflict() from None
    def list(self, artist, kind):
        return list(self.container.query_items(query='SELECT * FROM c WHERE c.type = @kind',
            parameters=[{'name': '@kind', 'value': kind}], partition_key=artist))

@lru_cache
def get_store():
    mode = os.getenv('CATALOG_BACKEND', 'sqlite')
    if mode == 'cosmos':
        return CosmosStore()
    if mode != 'sqlite':
        raise RuntimeError('CATALOG_BACKEND must be sqlite or cosmos')
    if os.getenv('WEBSITE_INSTANCE_ID') or os.getenv('MUSICDIST_ENV') == 'production':
        raise RuntimeError('Production requires Cosmos DB; SQLite is local-only')
    return LocalStore(os.getenv('SQLITE_PATH', 'data/catalog.sqlite'))
