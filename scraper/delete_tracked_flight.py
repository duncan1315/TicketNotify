import os
import shutil
from pathlib import Path

FLIGHTS_DIR = Path("flights")
DATA_DIR = Path("data")


def remove_tracked_flight_files(tracked_id):
    removed = []

    flight_file = FLIGHTS_DIR / f"{tracked_id}.json"
    if flight_file.exists():
        flight_file.unlink()
        removed.append(str(flight_file))

    flight_data_dir = DATA_DIR / tracked_id
    if flight_data_dir.exists():
        shutil.rmtree(flight_data_dir)
        removed.append(str(flight_data_dir))

    return removed


def main():
    issue_number = os.environ["ISSUE_NUMBER"]
    tracked_id = f"flight-{issue_number}"

    removed = remove_tracked_flight_files(tracked_id)

    if not removed:
        print(f"No data found for {tracked_id}, nothing to delete")
        return

    for path in removed:
        print(f"Removed {path}")


if __name__ == "__main__":
    main()
