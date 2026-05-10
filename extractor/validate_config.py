"""Lee config.json desde Drive y valida que tenga repos.

Es la primera tarea del DAG. Si esto falla, no tiene sentido seguir
con la extracción.
"""

import os

from dotenv import load_dotenv

from drive_client import DriveClient


def main():
    load_dotenv()

    drive = DriveClient(
        credentials_path=os.environ["GOOGLE_CREDENTIALS_PATH"],
        folder_id=os.environ["GOOGLE_DRIVE_FOLDER_ID"],
    )
    config = drive.read_json_config(
        os.environ.get("DRIVE_CONFIG_FILENAME", "config.json")
    )

    repos = config.get("repositories", [])
    if not repos:
        raise RuntimeError("config.json no tiene repos configurados")

    print(f"Config OK: {len(repos)} repos a procesar")
    for r in repos:
        print(f"  - {r['owner']}/{r['name']}")


if __name__ == "__main__":
    main()