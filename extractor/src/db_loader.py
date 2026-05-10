"""Carga de datos a PostgreSQL.

usa INSERT ... ON CONFLICT DO UPDATE para que correr
el proceso dos veces no produzca duplicados.
"""

from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values


class DBLoader:
    """Encapsula la conexión a Postgres y las operaciones de carga."""

    def __init__(self, host, port, dbname, user, password):
        self.conn_params = dict(
            host=host, port=port, dbname=dbname,
            user=user, password=password,
        )
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(**self.conn_params)

    def close(self):
        if self.conn:
            self.conn.close()

    def commit(self):
        self.conn.commit()

    def apply_schema(self, schema_path: str):
        """Aplica el schema.sql. Es seguro correrlo varias veces porque
        usa CREATE TABLE IF NOT EXISTS.
        """
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with self.conn.cursor() as cur:
            cur.execute(sql)
        self.conn.commit()

    # ---------- Repositorios y usuarios ----------

    def upsert_repository(self, owner: str, name: str) -> int:
        """Inserta el repo si no existe. Devuelve su id local."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repositories (owner, name)
                VALUES (%s, %s)
                ON CONFLICT (owner, name) DO UPDATE
                  SET owner = EXCLUDED.owner
                RETURNING id
                """,
                (owner, name),
            )
            return cur.fetchone()[0]

    def upsert_user(self, github_id: int, login: str, html_url: Optional[str]) -> int:
        """Inserta o actualiza el usuario. Devuelve su id local.

        Actualizamos login y html_url porque pueden cambiar
        (la gente cambia su username en GitHub).
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (github_id, login, html_url)
                VALUES (%s, %s, %s)
                ON CONFLICT (github_id) DO UPDATE
                  SET login = EXCLUDED.login,
                      html_url = EXCLUDED.html_url
                RETURNING id
                """,
                (github_id, login, html_url),
            )
            return cur.fetchone()[0]

    # ---------- Issues y commits ----------

    def upsert_issues(self, rows: list):
        """Carga una lista de issues en batch.

        Cada row debe ser una tupla con este orden:
        (github_id, repo_id, number, author_id, title, state,
         is_pull_request, created_at, updated_at, closed_at)
        """
        if not rows:
            return
        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO issues (
                    github_id, repo_id, number, author_id, title, state,
                    is_pull_request, created_at, updated_at, closed_at
                )
                VALUES %s
                ON CONFLICT (github_id) DO UPDATE
                  SET title = EXCLUDED.title,
                      state = EXCLUDED.state,
                      updated_at = EXCLUDED.updated_at,
                      closed_at = EXCLUDED.closed_at
                """,
                rows,
            )

    def upsert_commits(self, rows: list):
        """Carga una lista de commits en batch.

        Cada row debe ser una tupla con este orden:
        (sha, repo_id, author_id, committer_id, message,
         authored_at, committed_at)

        Para commits usamos DO NOTHING porque el contenido del
        commit no cambia: si ya existe ese sha en ese repo, no
        hay nada que actualizar.
        """
        if not rows:
            return
        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO commits (
                    sha, repo_id, author_id, committer_id, message,
                    authored_at, committed_at
                )
                VALUES %s
                ON CONFLICT (sha, repo_id) DO NOTHING
                """,
                rows,
            )

    # ---------- Estado de extracción ----------

    def get_last_extraction(self, repo_id: int, entity: str) -> Optional[datetime]:
        """Última fecha de extracción para ese repo y entidad.
        Devuelve None si es la primera corrida.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT last_extracted_at FROM extraction_state "
                "WHERE repo_id = %s AND entity = %s",
                (repo_id, entity),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def update_extraction_state(self, repo_id: int, entity: str, when: datetime):
        """Guarda hasta qué fecha se extrajo este repo+entidad."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extraction_state (repo_id, entity, last_extracted_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (repo_id, entity) DO UPDATE
                  SET last_extracted_at = EXCLUDED.last_extracted_at
                """,
                (repo_id, entity, when),
            )

    # ---------- Reporte ----------

    def get_summary_per_repo(self) -> list:
        """Devuelve filas (owner/name, issues_count, commits_count)
        para armar el CSV del reporte.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    r.owner || '/' || r.name AS repo,
                    COALESCE(i.cnt, 0) AS issues,
                    COALESCE(c.cnt, 0) AS commits
                FROM repositories r
                LEFT JOIN (
                    SELECT repo_id, COUNT(*) AS cnt
                    FROM issues
                    GROUP BY repo_id
                ) i ON i.repo_id = r.id
                LEFT JOIN (
                    SELECT repo_id, COUNT(*) AS cnt
                    FROM commits
                    GROUP BY repo_id
                ) c ON c.repo_id = r.id
                ORDER BY repo
                """
            )
            return cur.fetchall()