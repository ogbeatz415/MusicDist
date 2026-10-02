# Validation record

Tested October 2, 2026 UTC using Python 3.12 and the resolved runtime dependency versions in requirements-lock.txt.

- 15 pytest cases passed.
- Real FFmpeg generation/transcoding and FFprobe inspection of synthetic stereo audio.
- Local CLI generated a handoff ZIP; original master bytes and SHA-256 matched.
- API package workflow exercised with real audio/artwork and mocked Azure storage.
- Rejected malformed UPC, duplicate ISRC/track IDs, unknown destinations/territories, missing rights confirmation, lossy masters and inadequate artwork.
- Verified API authentication, fail-closed missing admin secret, immutable drafts, partition lookup isolation, local-path rejection and blocked delivery.
- Verified blob-level create-only HTTPS upload-grant arguments with a mocked Azure SDK.
- Verified worker re-raises processing failures and records failed status.
- Verified package size limit and refusal to overwrite existing local package files.
- Python compilation and JavaScript syntax validation passed.

Not tested: live Azure credentials/RBAC/CORS, container image builds, actual Azure trigger/retry behavior, public-host load testing, browser upload end-to-end against Azure, or DSP acceptance. These require the staging acceptance steps in DEPLOY_AZURE.md. One dependency deprecation warning appeared in the test client; no test failed.
