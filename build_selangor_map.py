from map_utils import DATA_DIR, OUTPUT_HTML, log, load_csv
from map_builder import build_map


# ----------------- MAIN -----------------
def main():
    log(f"Running from folder: {DATA_DIR}")
    log(f"CSV files present: {[p.name for p in DATA_DIR.glob('*.csv')]}")

    customers = load_csv("customers.csv")
    service = load_csv("toyota_service_outlets.csv")
    bp = load_csv("toyota_bp_outlets.csv")
    traffic_police = load_csv("traffic_police_stations.csv")

    m = build_map(customers, service, bp, traffic_police)

    m.save(str(OUTPUT_HTML))
    log(f"✅ Map saved to: {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
