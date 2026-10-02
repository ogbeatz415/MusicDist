# MusicDist — Azure release preparation v0.2

MusicDist now has a working **owner/admin release-preparation application**: catalog records, scoped uploads, lossless audio checks, private previews, artwork validation, and portable release packages.

**It does not yet submit music to DSPs.** Selected destinations are planning targets. All remain `not_connected`; `/deliveries` returns HTTP 409. The exported manifest is MusicDist JSON, not DDEX and not a recipient-approved format. No false “delivered” or “live” states are emitted.

## Start here

1. Rotate the Azure storage credential included in the original upload/manual. This package contains no old credentials. Rotation must also update any existing Azure host configuration that uses the old key.
2. Start locally to inspect the dashboard and prepare a release from your files.
3. Configure Azure identity, storage and Cosmos using `DEPLOY_AZURE.md`, then test one short track on a staging deployment.
4. Obtain a delivery partner integration or direct DSP onboarding details. Use `DELIVERY_ONBOARDING.md` to collect the exact requirements before implementing the first adapter.

## What's implemented

- Owner/admin dashboard at `/`, protected API using a random admin bearer token. The page shell is public, catalog endpoints are protected. Tokens are not saved in browser storage.
- Release metadata: artist, label, UPC/EAN, ISRCs, credits, language, explicit flag, dates, territories, selected DSPs and rights confirmation.
- SQLite local catalog; Azure Cosmos DB in production, partitioned by `/partitionKey = artist_id`.
- New blob paths: `incoming-tracks/{artist_id}/{release_id}/{asset_id}.wav` (also FLAC/ALAC).
- Managed-identity user-delegation SAS, one randomly named blob, HTTPS, create-only, 15 minutes. No container-wide upload access or account key in the browser. A replacement needs a new upload reservation.
- Worker records duration, codec, bit depth, rate, channels, size and SHA-256 in Cosmos. It preserves original masters, creates 320 kbps MP3 previews in **private** `music-previews`, and re-raises processing errors so Azure can retry.
- Media-aware validation with FFprobe, not regex parsing. Exactly one stereo audio stream; WAV PCM16/24, FLAC or ALAC; 16/24 bits; 44.1/48/88.2/96/176.4/192 kHz. This is a conservative internal baseline, not a guarantee of every DSP's acceptance.
- Artwork baseline: RGB square JPEG/PNG, 3000–6000 pixels, up to 30 MiB.
- Versioned handoff ZIPs containing original master bytes, artwork, metadata and SHA-256 checksums. Existing output filenames are not overwritten. All destination statuses remain blocked pending onboarding.
- Local CLI supports up to 200 tracks in one release. Organize a 200-track catalog into actual releases; tracks are not automatically grouped into albums.

## Quick start — local desktop

Needs Python 3.11+ and FFmpeg/FFprobe available on PATH. This supersedes the original archived virtual environment and static binary; do not copy those environments to another machine.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
export MUSICDIST_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m uvicorn musicdist.api:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080. The token is the value you generated in your shell; keep it private. For a persistent token, generate/store it in your password manager and set the environment variable before starting. `.env.example` lists settings but is **not automatically loaded** by the app.

Local SQLite mode supports the draft catalog without Azure. Browser uploads and packages based on uploaded asset IDs require Azure storage and a configured worker. For a fully local preparation workflow, use the CLI:

```bash
python -m musicdist validate examples/release.json
python -m musicdist package examples/release.json --output dist/my-release-v1.zip
```

The example intentionally contains invalid placeholder codes and missing media. Replace them with your assigned codes and your actual master/artwork paths; set `rights_confirmed` only after your review. Paths are relative to the JSON file (absolute paths are allowed in this trusted-owner CLI). Validation of a code's format/check digit does not establish ownership or confirm its issuance. Keep existing ISRCs for unchanged recordings.

## Dashboard flow

1. Connect with your owner token.
2. Import/edit release JSON, then create a draft. API metadata must not contain `master` or `artwork` local paths.
3. Choose and upload artwork and each master. Allow the worker to finish, then refresh status.
4. Validate and download the package. A successful download means **prepared**, never delivered.

This first dashboard uses a JSON metadata editor. It is not yet a public artist portal. Do not share the owner token with artists. Draft metadata is immutable: create a new draft ID for revisions. Upload reservations and catalog persist, but the current dashboard's file selections and asset choices are in memory: do not refresh during a working session. Existing IDs can be retrieved through the API (`/docs`) for recovery. There is no public player in this version.

## API

Interactive API reference: `/docs`. Use `Authorization: Bearer <owner-token>` for all catalog routes.

| Route | Purpose |
| --- | --- |
| GET /health/live | Liveness only; does not check Azure readiness |
| GET /destinations | Planning targets and connection status |
| POST /releases | Create immutable release draft |
| GET /artists/{artist_id}/releases | List artist's drafts |
| GET /artists/{artist_id}/releases/{release_id} | Draft and associated asset statuses |
| POST /uploads | Create asset reservation and scoped upload URL |
| POST /packages | Validate reserved assets and download handoff ZIP |
| POST /deliveries | Always blocked until an approved adapter exists |

An upload uses one raw HTTP PUT with `x-ms-blob-type: BlockBlob`. The blob name is in the URL **path**, not an appended `&blob=` query parameter. Do not log the signed URL. Single PUT upload has a 1 GiB application limit and no resumability in this release. Azure SAS does not enforce the byte limit; the worker rejects oversized files after upload. Set storage monitoring/quotas before sharing beyond the owner.

Package API downloads assets to temporary disk and validates them again. Default combined asset limit is 2 GiB (`MAX_PACKAGE_BYTES`). Packaging is synchronous, so use local CLI for larger releases and move packaging to a queued worker before operating at public-platform scale. Allow over twice the asset total in temporary disk for the ZIP plus inputs. Downloaded API packages must be retained by the owner; the catalog stores their manifests, not the ZIP bytes.

## Safety and operational limits

- No billing, artist accounts, royalty accounting, takedowns, DSP submissions or reconciliation are implemented yet.
- Artist registration will require tenant-scoped identity/authorization; this admin token grants access to the whole catalog by design.
- No content-recognition, copyright clearance or detection of lossy audio previously converted to WAV is claimed.
- Existing public blobs are not changed or made private by this code. New previews use a separate private container. Review the older public container manually if it includes unreleased music.
- Source code tests use local assets and mocked Azure clients. No claim is made that your Azure environment or an actual DSP has passed end-to-end acceptance.
- Container images must be built and scanned before production. An existing Azure plan may need a container-capable hosting option for the included worker image. Don't deploy this over the existing Function until that is verified.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## File map

- `function_app.py`: durable transcoding worker
- `musicdist/api.py`: admin API and dashboard server
- `musicdist/models.py`: canonical metadata and code checks
- `musicdist/media.py`: FFprobe validation and FFmpeg preview generation
- `musicdist/store.py`: local/Cosmos catalog adapters
- `musicdist/storage.py`: scoped Azure upload grants and downloads
- `musicdist/package.py`: internal handoff ZIP builder
- `musicdist/__main__.py`: local preparation CLI
- `static/`: owner dashboard
- `DEPLOY_AZURE.md`: staged deployment and verification
- `DELIVERY_ONBOARDING.md`: requirements for real multi-DSP delivery
