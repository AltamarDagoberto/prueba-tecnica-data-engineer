"""Script de un solo uso para obtener el token OAuth de Google Drive.

Abre el navegador, pide que aceptes los permisos, y guarda un
oauth_token.json con el refresh token. Despues de eso el drive_client
puede usar ese token automaticamente sin volver a abrir el navegador.

Como correrlo (una sola vez):
    pip install google-auth-oauthlib
    python auth_oauth.py
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow


# Misma scope que usa drive_client (lectura y escritura en Drive)
SCOPES = ["https://www.googleapis.com/auth/drive"]

CLIENT_SECRETS = os.path.join("credentials", "oauth_client.json")
TOKEN_OUT = os.path.join("credentials", "oauth_token.json")


def main():
    if not os.path.exists(CLIENT_SECRETS):
        raise FileNotFoundError(
            f"No encontre {CLIENT_SECRETS}. Bajalo del Cloud Console "
            f"(Credenciales -> ID de cliente OAuth) y guardalo ahi."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    # Abre el navegador y espera a que aceptes los permisos
    creds = flow.run_local_server(port=0)

    # Guardamos refresh + access token. El drive_client usa este archivo.
    with open(TOKEN_OUT, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"OK: {TOKEN_OUT} guardado.")
    print("Ya podes correr el pipeline: usara este token para subir a Drive.")


if __name__ == "__main__":
    main()
