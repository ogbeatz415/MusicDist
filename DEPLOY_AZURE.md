# Azure staging deployment

This archive does not deploy anything or change your Azure resources. Your original worker continues to run until you deploy a replacement. No access to your Azure subscription was available during this build.

## 1. Credentials and staging

Rotate the exposed storage credential from the old manual/local settings. Coordinate the rotation with the existing Function's `AzureWebJobsStorage` setting so the running host is not accidentally disconnected. Prefer managed identity for the new application's SDK operations. Do not put real credentials into local.settings.json files that are committed or shared.

Create/use a staging environment first. Confirm the Azure Function hosting plan supports custom Linux containers; `Dockerfile.worker` installs FFmpeg and FFprobe inside the image. The old archive has no usable FFprobe binary. This package deliberately does not claim that a plain `func publish` to your old plan will be enough.

The API and the blob-triggered worker are **two services**, sharing Cosmos and storage. Deploy the API image to your chosen Azure container web host with HTTPS; deploy the worker image to a container-capable Azure Functions host. Resource provisioning and pricing choices are not automated in this archive.

## 2. Storage

Keep `incoming-tracks` private. Create private `release-artwork` and private `music-previews` containers. Do not enable anonymous access for new containers. Existing `public-streams` is no longer a destination for new previews and is not modified automatically.

Both service identities need Storage Blob Data Contributor at an appropriately reviewed storage scope. The identity issuing upload grants additionally needs the user-delegation key action at storage-account scope (included in the corresponding built-in contributor role at that scope). For tighter separation, use scoped data roles plus Storage Blob Delegator at account scope. Verify effective role permissions in staging.

Configure Blob service CORS for the **exact API/dashboard HTTPS origin**:
- Allowed methods: PUT (Azure handles the browser's preflight).
- Allowed headers: content-type, x-ms-blob-type and any Azure headers needed by your client.
- Exposed headers: ETag, x-ms-request-id.
- Short max-age, e.g. 600 seconds.

Only add http://127.0.0.1:8080 if local browser uploads are needed. Avoid wildcard origins. The server-side CLI does not need browser CORS.

## 3. Cosmos catalog

Use `MusicCatalog` / `CatalogItems`, partition key `/partitionKey`. This key is case-sensitive and must already exist with this definition. Assign both identities Cosmos DB **data-plane** access sufficient to read/create/upsert/query documents (for example, the Cosmos DB Built-in Data Contributor role on the database/container). Azure resource management Contributor alone does not grant Cosmos data access.

The app creates records but deliberately does not provision or delete databases or containers.

## 4. Settings

Both services:

```text
MUSICDIST_ENV=production
CATALOG_BACKEND=cosmos
STORAGE_ACCOUNT_URL=https://mystoragemusicvault.blob.core.windows.net
COSMOS_ENDPOINT=https://music-catalog-db.documents.azure.com:443/
COSMOS_DATABASE=MusicCatalog
COSMOS_CONTAINER=CatalogItems
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
TRANSCODE_TIMEOUT_SECONDS=480
```

API only: `MUSICDIST_ADMIN_TOKEN` as a newly generated random secret of at least 32 characters; `MAX_PACKAGE_BYTES=2147483648` unless deliberately adjusted with enough temporary disk. Store the token in Azure secret settings/Key Vault, never a frontend build.

Worker: configure the Azure Functions host's `AzureWebJobsStorage` identity-based connection or a securely held replacement connection string using Microsoft's host-storage guidance. Host storage has its own blob/queue permissions and is separate from the application's DefaultAzureCredential SDK configuration. `host.json` requests a 10-minute function timeout and one blob invocation at a time. Check that these settings fit the actual hosting plan. Monitor the blob-trigger poison queue and failed invocations.

## 5. Build images

From the project directory, in an environment with Docker:

```bash
docker build -f Dockerfile -t musicdist-api:0.2 .
docker build -f Dockerfile.worker -t musicdist-worker:0.2 .
```

Push images to your Azure Container Registry and configure the two hosts to pull them using your normal Azure deployment process. Do not run a second worker against the production incoming container during testing; use a staging storage account or disable one trigger.

## 6. Acceptance test before production

1. Confirm `/health/live` responds, then authenticate to `/destinations`.
2. Create one draft with real metadata and assigned codes.
3. Request one upload grant and PUT a short lossless stereo test file. Reusing that create-only grant to overwrite the blob must fail.
4. Check the asset transitions from awaiting_upload to processing to processed in Cosmos.
5. Confirm duration/checksum exist, original master is unchanged, preview is private, and no new public-streams file appeared.
6. Upload valid artwork and download the package; compare original master bytes/checksum.
7. Upload invalid media and confirm failed state, retried invocation, and eventually poison handling.
8. Confirm `/deliveries` returns 409 and nothing is sent externally.

Only then migrate the production API/worker. Legacy flat uploads (e.g. `incoming-tracks/song.wav`) are intentionally skipped by the new worker: re-upload them through a reservation to establish their artist/release ownership. Existing files are not deleted.

## Verified documentation

- User delegation SAS: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-user-delegation-sas-create-python
- Blob triggers and poison handling: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-blob-trigger
- Identity-based Functions connections: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference#configure-an-identity-based-connection
- Cosmos data access: https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/how-to-connect-role-based-access-control
