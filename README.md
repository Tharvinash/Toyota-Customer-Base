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

3. Run the migration script once to load existing CSV data into the DB:

```bash
python migrate_from_csv.py
```

4. Start the FastAPI app:

```bash
uvicorn main:app --reload
```

5. Open the admin dashboard:

- Admin UI: `http://127.0.0.1:8000/`
- Map view: `http://127.0.0.1:8000/map`

### Environment variables

- `DATABASE_URL`: SQLAlchemy URL for the database.
  - For local development, the default is `sqlite:///./selangor_map.db`.
  - For production, use a managed PostgreSQL URL, e.g.:
    - `postgresql://user:password@host:5432/selangor_map`

### Deployment notes

- The included `Procfile` assumes a platform like Render, Railway, or Heroku-style hosting:
  - `web: uvicorn main:app --host 0.0.0.0 --port 8000`
- On your cloud platform:
  - Provision a PostgreSQL instance.
  - Set `DATABASE_URL` in the environment.
  - Deploy the code and let the platform run the `web` process.


