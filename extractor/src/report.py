"""Genera un CSV con el conteo de issues y commits por repo.

Lo guarda en una carpeta local (montada como volumen) y ademas
intenta subirlo a Google Drive. Si la subida a Drive falla porque
la Service Account no tiene cuota propia (caso tipico con cuentas
de Gmail personales sin Workspace), igual deja el archivo en disco
y la tarea termina ok.

Se corre despues del extractor. Usa las mismas variables de entorno.
"""

import os
import shutil
import tempfile

import pandas as pd
from dotenv import load_dotenv

from drive_client import DriveClient
from db_loader import DBLoader


REPORT_FILENAME = "reporte_resumen.csv"

# Carpeta dentro del contenedor donde tambien dejamos el CSV.
# El docker-compose / DAG monta esta ruta al host (a la carpeta
# reports/ del proyecto), asi el archivo queda visible afuera.
LOCAL_REPORTS_DIR = "/app/reports"


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


def try_upload_to_drive(env, csv_path):
    """Sube el CSV a Drive. Si falla por la cuota de la Service Account,
    no rompe la tarea, solo deja un warning en los logs. Asi el pipeline
    queda en verde aunque la cuenta no soporte uploads desde SA.
    """
    try:
        drive = DriveClient(
            credentials_path=env["GOOGLE_CREDENTIALS_PATH"],
            folder_id=env["GOOGLE_DRIVE_FOLDER_ID"],
        )
        file_id = drive.upload_csv(csv_path, REPORT_FILENAME)
        print(f"Reporte subido a Drive con id: {file_id}")
        return True
    except Exception as e:
        msg = str(e)
        if "storageQuotaExceeded" in msg or "storage quota" in msg:
            print(
                "WARN: no se pudo subir a Drive porque la Service Account "
                "no tiene cuota propia (limitacion de Gmail personal). "
                "El reporte queda solo en la carpeta local reports/."
            )
        else:
            print(f"WARN: fallo la subida a Drive: {e}")
        return False


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
        # Mostramos la tabla en consola para que quede en los logs
        print(df.to_string(index=False))

        # Generamos el CSV en una carpeta temporal y luego lo copiamos
        # tanto a la carpeta local montada como (intentamos) a Drive.
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, REPORT_FILENAME)
            df.to_csv(csv_path, index=False, encoding="utf-8")
            print(f"CSV generado: {csv_path}")

            # Copia local: se ve afuera del contenedor en reports/
            os.makedirs(LOCAL_REPORTS_DIR, exist_ok=True)
            local_dest = os.path.join(LOCAL_REPORTS_DIR, REPORT_FILENAME)
            shutil.copy2(csv_path, local_dest)
            print(f"CSV copiado a {local_dest}")

            # Intento a Drive (puede fallar por cuota de SA en Gmail personal)
            try_upload_to_drive(env, csv_path)
    finally:
        db.close()


if __name__ == "__main__":
    main()
