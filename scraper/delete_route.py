import json
import os
import shutil
from pathlib import Path

ROUTES_DIR = Path("routes")
DATA_DIR = Path("data")


def remove_route_files(route_id):
    removed = []

    route_file = ROUTES_DIR / f"{route_id}.json"
    if route_file.exists():
        route_file.unlink()
        removed.append(str(route_file))

    route_data_dir = DATA_DIR / route_id
    if route_data_dir.exists():
        shutil.rmtree(route_data_dir)
        removed.append(str(route_data_dir))

    return removed


def update_index(route_id):
    index_path = DATA_DIR / "index.json"
    if not index_path.exists():
        return False

    with open(index_path) as f:
        summaries = json.load(f)

    filtered = [s for s in summaries if s.get("id") != route_id]
    if len(filtered) == len(summaries):
        return False

    with open(index_path, "w") as f:
        json.dump(filtered, f, indent=2)
        f.write("\n")

    return True


def main():
    issue_number = os.environ["ISSUE_NUMBER"]
    route_id = f"route-{issue_number}"

    removed = remove_route_files(route_id)
    index_updated = update_index(route_id)

    if not removed and not index_updated:
        print(f"No data found for {route_id}, nothing to delete")
        return

    for path in removed:
        print(f"Removed {path}")
    if index_updated:
        print("Removed entry from data/index.json")


if __name__ == "__main__":
    main()
