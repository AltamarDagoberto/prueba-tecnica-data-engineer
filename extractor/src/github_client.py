"""Cliente para la API de GitHub.

Trae issues y commits de un repositorio, con paginación y
soporte para extracción incremental (parámetro since).
"""

import time
from datetime import datetime
from typing import Iterator, Optional

import requests


API_BASE = "https://api.github.com"
PAGE_SIZE = 100  # el máximo que permite GitHub


class GitHubClient:
    """Wrapper sobre la API REST de GitHub para issues y commits."""

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """Hace un GET y si nos topamos con el rate limit espera y reintenta."""
        while True:
            response = self.session.get(url, params=params, timeout=30)

            # Si nos quedamos sin requests, dormir hasta que se resetee
            remaining = response.headers.get("X-RateLimit-Remaining")
            if response.status_code == 403 and remaining == "0":
                reset = int(response.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset - int(time.time()), 1) + 1
                print(f"Rate limit alcanzado, esperando {wait} segundos...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

    def _paginate(self, url: str, params: dict) -> Iterator[dict]:
        """Recorre todas las páginas y va devolviendo cada item uno por uno."""
        params = {**params, "per_page": PAGE_SIZE}
        next_url = url
        while next_url:
            response = self._get(next_url, params=params)
            for item in response.json():
                yield item
            # GitHub manda la URL de la siguiente página en el header Link
            next_url = self._next_page_url(response.headers.get("Link", ""))
            params = None  # después de la primera, los params ya vienen en la URL

    @staticmethod
    def _next_page_url(link_header: str) -> Optional[str]:
        """Saca la URL con rel="next" del header Link."""
        for part in link_header.split(","):
            chunks = part.split(";")
            if len(chunks) >= 2 and 'rel="next"' in chunks[1]:
                return chunks[0].strip(" <>")
        return None

    @staticmethod
    def _format_since(since: Optional[datetime]) -> Optional[str]:
        """GitHub espera ISO 8601 en UTC con la 'Z' al final."""
        if since is None:
            return None
        return since.strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_issues(
        self, owner: str, name: str, since: Optional[datetime] = None
    ) -> Iterator[dict]:
        """Trae todos los issues del repo (incluye PRs).

        Si se pasa since, solo devuelve los que se actualizaron después.
        Ordenamos por updated_at ascendente para que, si la corrida se
        cae a la mitad, el último timestamp guardado sirva como punto
        para retomar.
        """
        url = f"{API_BASE}/repos/{owner}/{name}/issues"
        params = {
            "state": "all",
            "sort": "updated",
            "direction": "asc",
        }
        since_str = self._format_since(since)
        if since_str:
            params["since"] = since_str
        yield from self._paginate(url, params)

    def get_commits(
        self, owner: str, name: str, since: Optional[datetime] = None
    ) -> Iterator[dict]:
        """Trae todos los commits del repo.

        Si se pasa since, solo devuelve los hechos después de esa fecha.
        """
        url = f"{API_BASE}/repos/{owner}/{name}/commits"
        params = {}
        since_str = self._format_since(since)
        if since_str:
            params["since"] = since_str
        yield from self._paginate(url, params)