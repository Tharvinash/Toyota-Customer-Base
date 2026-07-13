# PostgreSQL Migration Plan

This runbook moves the app from the local SQLite database at `data/selangor_map.db`
to a shared PostgreSQL database.

## Current Database Tables

The migration scripts cover these app tables:

| Table | Purpose |
| --- | --- |
| `toyota_service_outlets` | Toyota service outlet markers |
| `toyota_bp_outlets` | Toyota body and paint markers |
| `non_dealer_workshops` | Non-dealer workshop markers |
| `competitor_bp_outlets` | Competitor body and paint markers |
| `traffic_police_stations` | Traffic police station markers |
| `customer_cells` | Customer density heatmap cells |

## 1. Create a CSV Backup

Run this before any migration:

```powershell
.\.venv\Scripts\python.exe scripts\export_db_csv_backup.py
```

The command writes timestamped CSV files under `backups/`.

## 2. Prepare PostgreSQL

Create or identify the PostgreSQL database, then keep its connection string out of
Git. Use an environment variable:

```powershell
$env:POSTGRES_DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DBNAME"
```

Render may show the URL as `postgres://...`; the app and migration scripts normalize
that to `postgresql://...`.

## 3. Migrate SQLite to PostgreSQL

For a new empty PostgreSQL database:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --target-database-url "$env:POSTGRES_DATABASE_URL"
```

If the target already has rows and you intentionally want to replace them:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_postgres.py --target-database-url "$env:POSTGRES_DATABASE_URL" --replace-target
```

The migration script:

1. Creates a fresh source CSV backup.
2. Creates missing PostgreSQL tables from the SQLAlchemy models.
3. Refuses to overwrite non-empty target tables unless `--replace-target` is used.
4. Copies rows from SQLite into PostgreSQL.
5. Validates source and target row counts table-by-table.
6. Resets PostgreSQL `id` sequences after inserting explicit IDs.

## 4. Run Locally Against PostgreSQL

After migration:

```powershell
$env:DATABASE_URL = $env:POSTGRES_DATABASE_URL
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Verify:

- Admin list pages load.
- Interactive map shows all marker layers.
- CSV upload writes to PostgreSQL.
- Refreshing from another browser/device shows the uploaded data.

## 5. Deploy on Render

In Render:

1. Provision or select the PostgreSQL database.
2. Set the web service environment variable `DATABASE_URL` to the PostgreSQL
   connection string.
3. Redeploy the app.
4. Open the deployed admin and map pages from two devices to confirm shared data.

## 6. Data Folder Cleanup

Only clean files after PostgreSQL is verified locally and on Render.

| File | Action After Verification | Reason |
| --- | --- | --- |
| `data/selangor_map.db` | Remove | SQLite DB is replaced by PostgreSQL |
| `data/customers.csv` | Move to backup or remove | DB is the source of truth after migration |
| `data/toyota_service_outlets.csv` | Move to backup or remove | DB is the source of truth after migration |
| `data/toyota_bp_outlets.csv` | Move to backup or remove | DB is the source of truth after migration |
| `data/traffic_police_stations.csv` | Move to backup or remove | DB is the source of truth after migration |
| `data/selangor_map.html` | Remove if unused | Legacy generated static map |
| `data/malaysia_admin1.geojson` | Keep | Required for state boundary rendering |
| `data/geoboundaries_mys_adm1_metadata.json` | Keep | Boundary source metadata |
| `data/master.json` | Keep | Used by `/api/master-data` |
| `data/data_completion_sources.md` | Keep or move to `docs/` | Source/audit notes |

Do not delete `data/malaysia_admin1.geojson` or `data/master.json`; the app still
reads them at runtime.
