"""Genera un CSV con el conteo de issues y commits por repo, y lo
sube a Google Drive.

Se corre después del extractor. Usa las mismas variables de entorno.
"""

import os
import tempfile

import pandas as pd
from dotenv import load_dotenv

from drive_client import DriveClient
from db_loader import DBLoader


REPORT_FILENAME = "reporte_resumen.csv"


def load_env():
    load_dotenv()
    required = [
        "GOOGLE_CREDENTIALS_PATH",
        "GOOGLE_DRIVE_FOLDER_ID",
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
    ]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Faltan variables: {', '.join(missing)}")
    return {v: os.getenv(v) for v in required}


def main():
    env = load_env()

    db = DBLoader(
        host=env["DB_HOST"],
        port=env["DB_PORT"],
        dbname=env["DB_NAME"],
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
    )
    db.connect()

    try:
        rows = db.get_summary_per_repo()
        print(f"Repos en el reporte: {len(rows)}")

        df = pd.DataFrame(rows, columns=["repo", "issues", "commits"])
        # Mostramos la tabla en consola para que quede en los logs de Airflow
        print(df.to_string(index=False))

        # Escribimos el CSV en una carpeta temporal (se borra sola al salir)
        # y lo subimos a Drive.
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, REPORT_FILENAME)
            df.to_csv(csv_path, index=False, encoding="utf-8")
            print(f"CSV generado: {csv_path}")

            drive = DriveClient(
                credentials_path=env["GOOGLE_CREDENTIALS_PATH"],
                folder_id=env["GOOGLE_DRIVE_FOLDER_ID"],
            )
            file_id = drive.upload_csv(csv_path, REPORT_FILENAME)
            print(f"Reporte subido a Drive con id: {file_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()