## Selangor Map Backend

This project serves an interactive Google Maps experience for Selangor, showing:

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

4. Provide your Google Maps API key (Maps JavaScript + Geocoding enabled):

- Set an environment variable before starting the app:

```bash
$env:GOOGLE_MAPS_API_KEY="YOUR_KEY_HERE"   # PowerShell
# or
export GOOGLE_MAPS_API_KEY="YOUR_KEY_HERE" # bash/zsh
```

5. Start the FastAPI app:

```bash
.\.venv\Scripts\activate
uvicorn main:app --reload
```

6. Open the admin dashboard:

- Admin UI: `http://127.0.0.1:8000/`
- Interactive search map: `http://127.0.0.1:8000/interactive-map`

All CSV inputs, the generated `selangor_map.html`, and the default SQLite DB live under the `data/` folder (created automatically).

### Environment variables

- `DATABASE_URL`: SQLAlchemy URL for the database.
  - For local development, the default is `sqlite:///./data/selangor_map.db`.
  - For production, use a managed PostgreSQL URL, e.g.:
    - `postgresql://user:password@host:5432/selangor_map`
- `GOOGLE_MAPS_API_KEY`: Required for Google Maps JavaScript + Geocoding. Enable both APIs for the key and restrict it to your domains/origins where possible.

### Deployment notes

- The included `Procfile` assumes a platform like Render, Railway, or Heroku-style hosting:
  - `web: uvicorn main:app --host 0.0.0.0 --port 8000`
- On your cloud platform:
  - Provision a PostgreSQL instance.
  - Set `DATABASE_URL` in the environment.
  - Deploy the code and let the platform run the `web` process.
