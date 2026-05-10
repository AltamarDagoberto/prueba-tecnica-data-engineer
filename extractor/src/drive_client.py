"""Cliente para leer y escribir archivos en Google Drive.

Usa una cuenta de servicio (service account). La carpeta de Drive
tiene que estar compartida con el email de esa cuenta antes de
correr esto.
"""

import io
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# Permisos necesarios: lectura y escritura de archivos en Drive
SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveClient:
    """Wrapper sobre la API de Drive para leer la config y subir el reporte."""

    def __init__(self, credentials_path: str, folder_id: str):
        self.folder_id = folder_id
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )
        self.service = build(
            "drive", "v3", credentials=creds, cache_discovery=False
        )

    def _find_file_by_name(self, filename: str):
        """Devuelve el id del archivo si existe en la carpeta, si no None."""
        query = (
            f"name = '{filename}' "
            f"and '{self.folder_id}' in parents "
            f"and trashed = false"
        )
        results = self.service.files().list(
            q=query,
            fields="files(id, name)",
            pageSize=1,
        ).execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def read_json_config(self, filename: str) -> dict:
        """Baja un JSON de Drive y lo devuelve ya parseado."""
        file_id = self._find_file_by_name(filename)
        if not file_id:
            raise FileNotFoundError(
                f"No se encontró '{filename}' en la carpeta {self.folder_id}"
            )

        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        buffer.seek(0)
        return json.load(buffer)

    def upload_csv(self, local_path: str, drive_filename: str) -> str:
        """Sube un CSV a la carpeta. Si ya existe un archivo con el mismo
        nombre, lo reemplaza en vez de crear uno nuevo. Así no queda
        basura acumulada en Drive cada vez que corre el pipeline.
        """
        existing_id = self._find_file_by_name(drive_filename)
        media = MediaFileUpload(local_path, mimetype="text/csv", resumable=False)

        if existing_id:
            updated = self.service.files().update(
                fileId=existing_id,
                media_body=media,
            ).execute()
            return updated["id"]

        metadata = {
            "name": drive_filename,
            "parents": [self.folder_id],
        }
        created = self.service.files().create(
            body=metadata,
            media_body=media,
            fields="id",
        ).execute()
        return created["id"]