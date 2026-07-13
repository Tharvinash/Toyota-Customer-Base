## Selangor Map Backend

This project generates an interactive Folium map for Selangor, showing:

- Toyota service outlets
- Toyota body & paint outlets
- Traffic police stations
- Customer density heatmap (from an uploaded CSV)

### Local setup

1. Create a virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Ensure PostgreSQL is running and the local database exists:

```text
postgresql://postgres:<password>@localhost:5432/toyota_customer_base
```

For a different database, set `DATABASE_URL` before starting the app.

4. Start the FastAPI app:

```bash
.\.venv\Scripts\activate
uvicorn main:app --reload
```

5. Open the admin dashboard:

- Admin UI: `http://127.0.0.1:8000/`
- Interactive search map: `http://127.0.0.1:8000/interactive-map`

Runtime map assets live under the `data/` folder. Uploaded business data is stored in PostgreSQL.

### Environment variables

- `DATABASE_URL`: SQLAlchemy URL for the database.
  - For local development, create a local `.env` with `DATABASE_URL`.
  - For production, use a managed PostgreSQL URL, e.g.:
    - `postgresql://user:password@host:5432/selangor_map`

### Local PostgreSQL with Docker

This repo includes a Docker Compose setup for a local PostgreSQL database.

1. Copy the example environment file:

```bash
copy .env.example .env
```

2. Start PostgreSQL:

```bash
docker compose up -d postgres
```

3. Use this local database URL for the app:

```bash
postgresql://postgres:<password>@localhost:5432/toyota_customer_base
```

In PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

4. Connect from DBeaver:

- Host: `localhost`
- Port: `5432`
- Database: `toyota_customer_base`
- Username: `postgres`
- Password: use the value from your local `.env`

To stop the database:

```bash
docker compose down
```

To delete the local PostgreSQL data volume and start fresh:

```bash
docker compose down -v
```

### Deployment notes

- The included `Procfile` assumes a platform like Render, Railway, or Heroku-style hosting:
  - `web: uvicorn main:app --host 0.0.0.0 --port 8000`
- On your cloud platform:
  - Provision a PostgreSQL instance.
  - Set `DATABASE_URL` in the environment.
  - Deploy the code and let the platform run the `web` process.

### PostgreSQL migration

Use `docs/postgres-migration-plan.md` for the cautious SQLite-to-PostgreSQL
migration runbook. The key scripts are:

```bash
python scripts/export_db_csv_backup.py
python scripts/migrate_sqlite_to_postgres.py --target-database-url "$POSTGRES_DATABASE_URL"
```

The old SQLite and source CSV files should remain in local `backups/` only. They
are no longer runtime inputs after the PostgreSQL migration.
