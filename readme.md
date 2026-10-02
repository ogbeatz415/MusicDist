markdown
# 🎼 MusicDist

Automated serverless music distribution and audio transcoding pipeline built on **Microsoft Azure**. This repository houses the core automation logic for managing raw audio uploads, extracting track metadata, and downsampling assets into web-optimized streaming formats.

---

## 🧭 Global System Architecture

Use code with caution.
[ Developer Mac Terminal ] ──(Pushes Code Engine via CLI)──► [ GitHub Source Control ]
│
(Generates Upload SAS Tokens)
│
▼
[ Artist Client App / Frontend Request Portal ]
│
(Direct 15-Min Secure Binary Push)
│
▼
[ Azure Blob Storage Account ]
├── incoming-tracks/  (Private Vault: Hot Tier)  ───► [ Serverless Cloud Robot ]
│                                                          (Wakes Up Instantly)
│                                                                   │
│                                                       (Calculates Track Metrics)
│                                                       (Downsamples via FFmpeg)
│                                                                   │
└── public-streams/   (Streaming Room: Cool Tier) ◄─────────────────┘
│
(Global Edge Delivery)
│
▼
[ Azure Front Door / CDN ] ──► [ Global Listener Audio Playback Streaming ]

---

## 🗂️ Infrastructure Blueprint

### 1. Storage Topology (`mystoragemusicvault`)
* **Type:** Azure Blob Storage (General Purpose v2)
* **Performance:** Standard / Locally-redundant storage (LRS)
* **Containers:**
  * `incoming-tracks`: Private access container optimized on a **Hot Tier** to handle incoming raw `.wav` or `.flac` studio masters.
  * `public-streams`: Public anonymous **Blob access** container optimized on a **Cool Tier** to serve globally cached `.mp3` compression blocks supporting range byte queries.

### 2. Database Cabinet (`music-catalog-db`)
* **Type:** Azure Cosmos DB (NoSQL API)
* **Capacity Mode:** Serverless (Consumption-based)
* **Database ID:** `MusicCatalog`
* **Container ID:** `CatalogItems`
* **Partition Key:** `/partitionKey` (Mapped directly to structural strings like `artistId` to optimize cross-partition compute query overhead).

---

## 📂 Core Repository Ecosystem

This project relies on the following file map:

```text
├── bin/
│   └── ffmpeg            # Static 64-bit Linux media compilation binary
├── .gitignore            # Security firewall filtering runtime attributes
├── function_app.py       # Main serverless backend robot transaction script
├── host.json             # Global Azure application engine metadata settings
├── local.settings.json   # Local credentials deployment mapping matrix
└── requirements.txt      # System dependency manifests
```

---

## 🚀 Execution Routines

### Local Service Simulation
To boot up the processing engine and bind it to watch your active live storage container streams on your development computer, run:
```bash
func start
```

### Direct Cloud Deployment
To compile your application layout, bundle the static media compilation binaries, and deploy them live to your active Azure infrastructure slot:
```bash
func azure functionapp publish music-robot-app
```

---

## 🧪 Terminal Integration Testing Routine

### 1. Extract Secure Temporary Upload Key
Run the local key management script to query your account infrastructure and yield a 15-minute secure access wrapper:
```bash
python3 generator.py
```

### 2. Stream Audio Binary Assets into the Cloud Vault
Use your terminal to simulate a user or frontend application pushing a track directly into your storage architecture:
```bash
curl -X PUT -H "x-ms-blob-type: BlockBlob" \
     --data-binary "@/path/to/local/studio_master.wav" \
     "PASTE_YOUR_GENERATED_SAS_URL_HERE&blob=studio_master.wav"
```

---
*Disclaimer: System manifests are configured to match production Azure deployment infrastructure policies. Repository architecture is locked for maintenance verification.*