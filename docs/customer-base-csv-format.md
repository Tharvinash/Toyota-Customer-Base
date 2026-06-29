# Customer Base CSV Format

The **Upload Customer Base CSV** page accepts a `.csv` file that replaces the existing customer-density records used by the interactive map.

## Required Columns

The CSV must include these six columns:

```csv
state,city,postcode,lat,lon,weight
```

Column names are normalized by the app before validation:

- Leading/trailing spaces are removed.
- Column names are converted to lowercase.
- Example: `State`, ` state `, and `STATE` are accepted as `state`.

## Column Rules

| Column | Required | Type | Example | Notes |
| --- | --- | --- | --- | --- |
| `state` | Yes | Text | `Selangor` | Full Malaysian state or federal territory name used for state filtering. Do not use state codes such as `SGR`, `KUL`, or `JHR`. |
| `city` | Yes | Text | `Ampang` | City, town, district, or location label shown in customer density popups. |
| `postcode` | Yes | Text or number | `68000` | Stored as text in the database. Keep leading zeroes if any by formatting this column as text before saving from Excel. |
| `lat` | Yes | Number | `3.16648` | Latitude in decimal degrees. Must be a valid number. |
| `lon` | Yes | Number | `101.748344` | Longitude in decimal degrees. Must be a valid number. |
| `weight` | Yes | Number | `6265` | Customer density/count for that location. The map uses this value for circle size, color range, legend range, and popup value. |

## Example File

```csv
state,city,postcode,lat,lon,weight
Selangor,Ampang,68000,3.16648,101.748344,6265
Selangor,Bandar Baru Bangi,43600,2.961915,101.75705,2206
Johor,Johor Bahru,80000,1.492659,103.741359,4500
Pulau Pinang,George Town,10000,5.41413,100.32875,3200
```

## Formatting Guidelines

- Save the file as **CSV UTF-8** when exporting from Excel or Google Sheets.
- Prefer plain numbers in numeric fields. The upload can read values like `6,265`, but `6265` is cleaner and safer when exporting from spreadsheets.
- Use full state or federal territory names only. For example, use `Kuala Lumpur` and `Selangor`, not `KUL` or `SGR`.
- Use decimal coordinates, not degrees/minutes/seconds.
- Keep `lat` and `lon` inside Malaysia's approximate coordinate range:
  - Latitude: `0.85` to `7.5`
  - Longitude: `99.5` to `119.5`
- Keep one customer-density row per mapped location. If the same location appears multiple times with the same coordinates, the map may visually combine the density at that coordinate.
- Avoid blank values for `lat`, `lon`, or `weight`; the current upload code converts these to numbers and will fail if they are missing or non-numeric.

## What Happens On Upload

When a valid CSV is uploaded:

1. The app reads the uploaded file with `pandas.read_csv`.
2. The app validates that all six required columns exist.
3. The app deletes all existing records in the `customer_cells` database table.
4. The app inserts every row from the uploaded CSV into `customer_cells`.
5. The interactive map uses the uploaded rows for customer density.

Important: the upload updates the database table, not the `data/customers.csv` source file.

## Common Upload Errors

| Error | Cause | Fix |
| --- | --- | --- |
| `Please upload a CSV file.` | File extension is not `.csv`. | Export or rename the file as `.csv`. |
| `Missing columns in CSV` | One or more required columns are absent. | Add the missing column names from the required list. |
| `Line 2: state must be a full Malaysian state or federal territory name...` | The `state` value is blank, a code, or not recognized by the app. | Use the full state or federal territory name, for example `Kuala Lumpur`, `Selangor`, or `Pulau Pinang`. |
| `Line 2: lat must be numeric...` | `lat`, `lon`, or `weight` contains blank/non-numeric values. | Clean those fields so every row has valid numbers. |
| Search returns no customer density for a state | No uploaded customer row matches that state spelling. | Use full state names that match the app dropdown, especially `Pulau Pinang` instead of `Penang`. |
