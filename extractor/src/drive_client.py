"""Cliente para leer y escribir archivos en Google Drive.

Soporta dos formas de autenticarse:

  1. Service Account (cuenta de servicio): patron de servidor, ideal
     para Workspace + Shared Drives. En cuentas de Gmail personal NO
     puede crear archivos por la politica de cuotas de Google.

  2. OAuth user token: la app actua en nombre del usuario que autorizo.
     Funciona en cualquier cuenta, incluida Gmail personal.

El cliente detecta automaticamente cual es por el contenido del JSON
que recibe en credentials_path.
"""

import io
import json

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


# Permisos necesarios: lectura y escritura de archivos en Drive
SCOPES = ["https://www.googleapis.com/auth/drive"]


def _load_credentials(credentials_path: str):
    """Carga credenciales desde un JSON, detectando si son SA o OAuth.

    - Si el JSON tiene "type": "service_account" -> Service Account.
    - Si no, asumimos que es un token de OAuth user (refresh + access).
      En ese caso refrescamos el access token si esta vencido.
    """
    with open(credentials_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") == "service_account":
        return service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )

    # OAuth user token (generado por auth_oauth.py)
    creds = Credentials.from_authorized_user_file(credentials_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


class DriveClient:
    """Wrapper sobre la API de Drive para leer la config y subir el reporte."""

    def __init__(self, credentials_path: str, folder_id: str):
        self.folder_id = folder_id
        creds = _load_credentials(credentials_path)
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