"""Download all available Oura data into data/<endpoint>.json.

Usage:
    python3 export.py              # everything since 2015-01-01
    python3 export.py 2023-01-01   # everything since the given date
"""
import json
import sys
import urllib.error
from datetime import date, datetime, timedelta

from oura import ROOT, api_get, get_access_token, load_env

DATA_DIR = ROOT / "data"

DATE_ENDPOINTS = [
    "daily_activity",
    "daily_cardiovascular_age",
    "daily_readiness",
    "daily_resilience",
    "daily_sleep",
    "daily_spo2",
    "daily_stress",
    "enhanced_tag",
    "rest_mode_period",
    "session",
    "sleep",
    "sleep_time",
    "tag",
    "vO2_max",
    "workout",
]
DATETIME_ENDPOINTS = ["heartrate", "ring_battery_level"]


def date_chunks(start, end, days):
    while start <= end:
        chunk_end = min(start + timedelta(days=days - 1), end)
        yield start, chunk_end
        start = chunk_end + timedelta(days=1)


def fetch_all(token, endpoint, **params):
    """Fetch every page of an endpoint, following next_token."""
    items = []
    while True:
        page = api_get(token, endpoint, **params)
        items.extend(page.get("data", []))
        if not page.get("next_token"):
            return items
        params["next_token"] = page["next_token"]


def export(name, fetch):
    print(f"{name}...", end=" ", flush=True)
    try:
        items = fetch()
    except urllib.error.HTTPError as e:
        print(f"hoppet over (HTTP {e.code})")
        return
    (DATA_DIR / f"{name}.json").write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"{len(items)} poster")


def main():
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2015, 1, 1)
    end = date.today()
    token = get_access_token(load_env())
    DATA_DIR.mkdir(exist_ok=True)

    export("personal_info", lambda: [api_get(token, "personal_info")])
    export("ring_configuration", lambda: fetch_all(token, "ring_configuration"))

    for endpoint in DATE_ENDPOINTS:
        export(endpoint, lambda: [
            item
            for a, b in date_chunks(start, end, 365)
            for item in fetch_all(token, endpoint, start_date=a.isoformat(), end_date=b.isoformat())
        ])

    # Time series are large, so request them in 30-day windows.
    for endpoint in DATETIME_ENDPOINTS:
        export(endpoint, lambda: [
            item
            for a, b in date_chunks(start, end, 30)
            for item in fetch_all(
                token, endpoint,
                start_datetime=datetime.combine(a, datetime.min.time()).isoformat(),
                end_datetime=datetime.combine(b + timedelta(days=1), datetime.min.time()).isoformat(),
            )
        ])

    print(f"\nFerdig, dataene er lagret i {DATA_DIR}")


if __name__ == "__main__":
    main()
