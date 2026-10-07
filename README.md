# Geospatial File Measurement

A small full-stack application: upload a **KML** file or a **zipped Shapefile** in a React UI and
get the **area of every polygon** and the **length of every line in metres**, calculated by a
FastAPI backend in a suitable projected CRS (never in degrees).

Built as the Software Development Intern assignment for AEREO.

```
geospatial-measurement-api/
├── backend/    FastAPI + GeoPandas + SQLAlchemy/SQLite  (REST API, 108 pytest tests)
├── frontend/   React + TypeScript + Vite                (single-page UI)
├── docker-compose.yml
└── README.md   (this file)
```

The two applications are independent: the backend can be used alone through Swagger (`/docs`),
and the frontend only needs a backend URL.

## 1. Problem statement

Survey files store coordinates in many coordinate reference systems (CRS). The most common one,
EPSG:4326 (WGS84 latitude/longitude), uses **degrees**. Calling `polygon.area` on such a geometry
returns "square degrees" — meaningless, because a degree of longitude is ~111 km at the equator
and shrinks to 0 at the poles. The system must detect the CRS, convert to a metric CRS when
needed, measure there, and handle untrusted uploads safely.

## 2. Features

**Backend**
- Upload `.kml` or `.zip` (one Shapefile) via `POST /api/files/`, processed synchronously
- Extracts feature index, geometry type, geometry (GeoJSON), CRS and properties
- Area (m²) for `Polygon`/`MultiPolygon`, length (m) for `LineString`/`MultiLineString`, no
  measurement for `Point`/`MultiPoint`; unsupported or invalid features are reported per feature
  and never fail the whole file
- CRS chosen **per feature** (UTM zone of the feature's centre); `calculation_crs` is stored per
  feature; missing/invalid CRS fails safely with no misleading numbers
- Upload security (size limit, content checks, ZIP Slip/ZIP bomb protection, safe KML parsing with
  `defusedxml`, UUID file names), consistent JSON errors, configurable CORS
- Swagger UI (`/docs`) and ReDoc (`/redoc`)

**Frontend**
- Drag-and-drop or file picker, client-side validation (type, empty, size)
- Loading state ("Processing geospatial file..."), success view, friendly error messages
- File information card, measurements table with status per feature, "Upload another file" reset
- Responsive layout, API URL from an environment variable

## 3. Tech stack

| Layer | Tools |
|---|---|
| Backend | Python 3.11+ (tested on 3.12), FastAPI, Pydantic, SQLAlchemy 2, SQLite, GeoPandas (+pyogrio/GDAL), Shapely, PyProj, defusedxml, Uvicorn |
| Backend tests | pytest, httpx (FastAPI TestClient) |
| Frontend | React 19, TypeScript, Vite, plain CSS (no UI/state libraries) |
| Packaging | Docker, Docker Compose (optional) |

## 4. Architecture

```
Browser
   ↓
React Frontend              frontend/src  (validates the file, calls the API, renders state)
   ↓  HTTP + multipart, CORS-restricted
FastAPI                     backend/app/api/routes/files.py
   ↓
Validation                  extension, size, content (ZIP structure / safe XML parse)
   ↓
File Storage                backend/uploads/<uuid>.<ext>
   ↓
GeoPandas / Shapely         geospatial/reader.py, processor.py
   ↓
CRS Transformation (PyProj) geospatial/crs.py  → UTM zone per feature
   ↓
Measurements                area in m², length in m, status per feature
   ↓
SQLAlchemy / SQLite         files + features tables
   ↓
FastAPI Response            JSON (Pydantic models)
   ↓
React UI                    file info + measurements table
```

### Backend architecture

```
backend/app/
├── main.py                  app factory: routes, error handling, CORS, startup
├── api/routes/files.py      HTTP only: parse request, call a service, shape the response
├── services/file_service.py upload pipeline: validate → store → process → save
├── services/measurement_service.py   ORM rows ↔ response schemas
├── geospatial/
│   ├── archive.py           safe ZIP validation + extraction
│   ├── reader.py            KML (safe XML check) / Shapefile → GeoDataFrame
│   ├── crs.py               CRS detection, UTM selection, projection for measuring
│   ├── processor.py         per-feature validation + measuring → structured results
│   └── errors.py
├── db/                      SQLAlchemy engine/session and models
├── schemas/file.py          Pydantic response models
└── core/                    config (env variables) and consistent JSON errors
```

Rule: **no geospatial code in route functions**; the geospatial package knows nothing about HTTP
or the database; services connect the two.

### Frontend architecture

```
frontend/src/
├── main.tsx, App.tsx        entry point; App renders the current state
├── hooks/useFileProcessing.ts   upload → measurements flow and the state machine
│                                (idle | uploading | success | error)
├── services/api.ts          the ONLY code that calls the backend; maps errors to friendly text
├── components/              Header, FileUpload, FileInfo, MeasurementTable, StatusMessage
├── types/api.ts             TypeScript types of the API responses
├── utils/                   file validation and number/date formatting
└── config.ts                the ONLY place that reads environment variables
```

## 5. File-processing flow

1. The browser checks the file (`.kml`/`.zip`, not empty, ≤ size limit) and posts it to `POST /api/files/`.
2. The backend sanitises the display name, checks the extension, reads the body in chunks (413 over the limit, 400 if empty).
3. Content is checked: ZIP signature and Shapefile structure, or a safe `defusedxml` parse of the KML.
4. The bytes are stored as `<uuid>.<ext>`; a `files` row (`PROCESSING`) is created.
5. The processor reads the data (KML layers/Folders are combined; Shapefile is extracted into a temporary directory that is always deleted), drops Z values and builds per-feature results.
6. Results are saved; the file becomes `COMPLETED` or `FAILED`; the response is returned.
7. The frontend fetches `/measurements/` for a `COMPLETED` file and renders the tables.

Per feature: no geometry → `INVALID`; unsupported type (e.g. `GeometryCollection`) →
`UNSUPPORTED`; invalid geometry (e.g. self-intersecting polygon) → `INVALID` with the reason;
points → `NOT_APPLICABLE`; no usable CRS → `SKIPPED`; otherwise `MEASURED`.

## 6. CRS strategy

Implemented in `backend/app/geospatial/crs.py` and applied to **every feature**:

1. **Detect** the CRS (KML → EPSG:4326; Shapefile → `.prj`).
2. **Suitable projected CRS** (UTM, national grids, State Plane…): measure directly in it; non-metre
   units (e.g. US survey foot) are converted.
3. **Geographic CRS** (EPSG:4326, NAD83, any lat/lon): take the centre of the feature's bounding
   box, convert it to WGS84 lon/lat, select the **UTM zone** containing it (`EPSG:326xx` north,
   `EPSG:327xx` south; polar UPS beyond 84°N/80°S), transform the geometry and measure.
4. **Projected but distorting CRS** (Web Mercator and other Mercator variants): treated like step 3.
5. **Missing, unparseable or non-geodetic CRS**: the file is `FAILED` with a clear message. Features
   are still extracted (`/features/`), but **no area or length is calculated**.
6. Coordinates outside the valid range of the declared geographic CRS mark that feature `INVALID`.

The CRS is selected **per feature, not per file**: two features in one file can be measured in
different UTM zones. The CRS used is stored on every feature row (`features.calculation_crs`) and
returned in every measurement; the file-level `crs` is only the *source* CRS. A feature that itself
spans several UTM zones is measured using the zone containing its centre (reduced accuracy).
Tests compare results with an independent ellipsoidal calculation (`pyproj.Geod`) within 0.5 %.

## 7. Security considerations

- Extension whitelist (`.kml`, `.zip`) **and** content checks; the extension alone is not trusted.
- Size limit (`MAX_UPLOAD_SIZE_MB`, default 20): early `Content-Length` check plus a chunked read that aborts at the limit. Empty files are rejected.
- The client filename is never used as a path: files are stored as `<uuid4>.<ext>` in `UPLOAD_DIR` (outside the application package), created with exclusive-create mode.
- **ZIP Slip**: names with absolute paths, `..`, drive letters or backslash tricks are rejected; extraction ignores archive names and writes fixed names (`layer.shp`…) into a temporary directory. There is no `extractall`.
- **ZIP bombs**: caps on entry count and on uncompressed size (declared and actually copied); symlinks and encrypted members rejected; exactly one Shapefile with `.shp`, `.shx`, `.dbf` required.
- **KML** is parsed with `defusedxml`: must be well-formed XML with a `<kml>` root (any namespace); DOCTYPE and entities are refused (XXE, "billion laughs").
- Temporary extraction directories are always removed.
- Unexpected errors return a generic message; details are only logged. Error responses also carry CORS headers so the UI can show them.
- **CORS** allows only the origins in `CORS_ORIGINS` (default: the local Vite dev server), never `*`.

## 8. Database design

```
files                              features
─────                              ────────
id (PK, uuid hex)                  id (PK)
filename (display name)            file_id (FK → files.id, indexed)
stored_filename (uuid.ext)         feature_index   (unique together with file_id)
original_extension                 geometry_type
crs (source CRS of the file)       geometry (JSON, GeoJSON in the source CRS)
feature_count                      properties (JSON)
status (PROCESSING/COMPLETED/      area_m2, length_m
        FAILED)                    calculation_crs (CRS used for this feature)
error_message                      status, note
created_at, updated_at (UTC)
```

## 9. API endpoints

| Method & path | Purpose | Success |
|---|---|---|
| `POST /api/files/` | Upload `.kml` / `.zip` (form field `file`) | 201 |
| `GET /api/files/{id}/` | File metadata and status | 200 |
| `GET /api/files/{id}/measurements/` | Area/length per feature | 200 |
| `GET /api/files/{id}/features/` | Extracted geometry (GeoJSON) and properties | 200 |

Errors use `{"error": {"code": "...", "message": "..."}}`: `400` invalid input (extension, empty,
malformed/unsafe KML, bad archive), `404` unknown id, `413` too large, `422` validation (e.g. no
`file` field), `409` measurements not available (file `FAILED`), `500` unexpected.

- A file that passes validation always gets an id and HTTP **201**, even if its *content* cannot be
  processed (corrupt data, missing CRS): then `status` is `FAILED` and `error_message` explains why.
  The frontend turns that into an error message.
- `/measurements/` lists **every** feature with a `status`; `area` (m²) and `length` (m) are
  separate nullable fields next to `unit`, `calculation_crs` and `note`.

Example (`curl.exe` on PowerShell):

```powershell
curl.exe -F "file=@backend/sample_data/survey.kml" http://localhost:8000/api/files/
curl.exe http://localhost:8000/api/files/<id>/measurements/
```

```json
{
  "file_id": "4637ef9d7db24a2ca4ab0a10dc41d69f",
  "crs": "EPSG:4326",
  "measurements": [
    {"feature_id": 0, "geometry_type": "Polygon", "area": 48067.8227, "length": null,
     "unit": "m²", "calculation_crs": "EPSG:32643", "status": "MEASURED", "note": null},
    {"feature_id": 1, "geometry_type": "LineString", "area": null, "length": 1129.0133,
     "unit": "m", "calculation_crs": "EPSG:32643", "status": "MEASURED", "note": null},
    {"feature_id": 2, "geometry_type": "Point", "area": null, "length": null,
     "unit": null, "calculation_crs": null, "status": "NOT_APPLICABLE",
     "note": "Points have no area or length."}
  ]
}
```

## 10. Frontend usage

1. Open <http://localhost:5173>.
2. Drag a `.kml` or `.zip` onto the drop area, or click to browse (try `backend/sample_data/survey.kml` and `parcels_utm43n.zip`).
3. Invalid files (wrong type, empty, too large) are flagged immediately and cannot be uploaded.
4. Click **Upload and measure**; while the server works you see "Processing geospatial file...".
5. On success you get the file information (name, ID, feature count, source CRS, status, timestamps) and the measurements table (feature ID, geometry type, measurement, unit, CRS used, status).
6. On failure a clear message explains what went wrong (unsupported file, too large, corrupt file, invalid ZIP, missing Shapefile components, missing CRS, server or network error). Raw backend errors and stack traces are never shown.
7. **Upload another file** clears the result.

## 11. Windows setup (PowerShell)

Prerequisites: Python 3.11+ and Node.js 20+.

Backend (terminal 1):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Backend runs at <http://localhost:8000> (Swagger: `/docs`, ReDoc: `/redoc`). The SQLite database and
`backend/uploads/` are created automatically. If PowerShell blocks the activation script:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

Frontend (terminal 2):

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend runs at <http://localhost:5173>.

## 12. Environment variables

**Backend** (`backend/.env`, see `backend/.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<backend>/geospatial.db` | SQLAlchemy database URL |
| `UPLOAD_DIR` | `<backend>/uploads` | Where original uploads are stored |
| `MAX_UPLOAD_SIZE_MB` | `20` | Upload size limit |
| `MAX_ZIP_ENTRIES` / `MAX_ZIP_UNCOMPRESSED_MB` | `100` / `200` | ZIP bomb limits |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API |
| `LOG_LEVEL` | `INFO` | Logging level |

**Frontend** (`frontend/.env`, see `frontend/.env.example`; read at build/start time)

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL |
| `VITE_MAX_UPLOAD_MB` | `20` | Limit shown/checked in the UI; keep equal to the backend's `MAX_UPLOAD_SIZE_MB` |

## 13. Testing

```powershell
cd backend
pytest
```

108 backend tests build all geodata programmatically. They cover uploads (valid, invalid
extension, empty, missing, corrupt, oversized), polygon/line/point measurements, CRS selection
(EPSG:4326, other geographic CRS, projected, feet, Web Mercator, missing, invalid, non-geodetic),
KML XML validation (malformed, namespaced, DOCTYPE/entity payloads, wrong root), ZIP Slip and ZIP
bombs, filename safety, per-feature failure isolation, leak-free errors, CORS, and 404/409/500.

Frontend checks:

```powershell
cd frontend
npm run typecheck
npm run build
```

The frontend has no automated unit tests; its API layer was exercised against a live backend
during development (see Limitations).

Optional lint: `pip install ruff`, then `ruff check .` in `backend`.

## 14. Docker

```powershell
docker compose up --build
```

Frontend: <http://localhost:3000>, backend: <http://localhost:8000>. The database and uploads
persist in the `backend_data` volume. The API URL is baked into the frontend at build time
(`VITE_API_BASE_URL` build argument in `docker-compose.yml`) and the backend allows the frontend's
origin through `CORS_ORIGINS`. The application also runs without Docker.

## 15. Design decisions

- **Per-feature UTM zone** (deliberate): more accurate for datasets spanning several zones; the CRS used is stored and reported per feature.
- **Synchronous processing**: fine for files ≤ 20 MB and simpler than a job queue.
- **A second `features` table** (JSON geometry/properties) instead of PostGIS: keeps setup trivial.
- **Failed content ≠ rejected upload**: unsafe or structurally invalid uploads are rejected before storage (400/413); valid uploads whose content fails get a record with status `FAILED`.
- **Errors handled in a middleware** (not an `Exception` handler) so that even 500 responses pass through CORS and the browser can read them.
- **Frontend: no extra libraries**; one hook owns the state machine, one module talks to the API.

## 16. Limitations

- One Shapefile per ZIP; only `.kml` and `.zip` (no KMZ, GeoJSON, GeoPackage).
- A feature spanning several UTM zones, or crossing the antimeridian, is measured using the zone containing its centre (reduced accuracy). Measurements are planimetric; elevation is ignored.
- The upload is held in memory during validation (bounded by the size limit) and Starlette spools multipart bodies before the route runs; use a body-size limit on a reverse proxy in production.
- No authentication, rate limiting or pagination; SQLite is single-writer.
- A crash between the two commits of an upload could leave a file in `PROCESSING`.
- The frontend's size limit must be kept in sync with the backend manually (`VITE_MAX_UPLOAD_MB`).
- Development was done on Linux. The UI was verified by type-checking, building, serving the build, and running its real API service code against a live backend; it was **not** opened in a browser here. The PowerShell commands and the Docker files were **not** run on Windows/Docker.

## 17. What was learned

- Why degrees are not a unit of length and how to choose a projected CRS (UTM zone arithmetic); that "projected" does not mean "suitable for measuring" (Web Mercator).
- Defensive handling of untrusted uploads: ZIP Slip, ZIP bombs, XXE, never trusting file names.
- Isolating failures per feature so one bad record does not fail a file.
- CORS in practice: preflight requests, and why error responses need CORS headers too.
- Keeping HTTP, services and domain logic separate in the backend, and state, API access and presentation separate in the frontend.

## 18. Future scope

Not implemented, possible next steps: PostgreSQL/PostGIS (spatial indexes, server-side geodesic
area), asynchronous processing with background jobs, authentication and per-user files, cloud
object storage, streaming uploads for larger files, pagination of measurements, more geometry
types and formats (GeoJSON, GeoPackage, KMZ), a map preview of the features, frontend unit tests.
