import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from drive_client import DriveClient
from github_client import GitHubClient
from db_loader import DBLoader


# Cuántos registros agrupar antes de mandar al INSERT en lote
BATCH_SIZE = 500


def load_env():
    """Carga el .env y verifica que estén todas las variables requeridas."""
    load_dotenv()

    required = [
        "GITHUB_TOKEN",
        "GOOGLE_CREDENTIALS_PATH",
        "GOOGLE_DRIVE_FOLDER_ID",
        "DRIVE_CONFIG_FILENAME",
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
    ]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")

    return {v: os.getenv(v) for v in required}


def get_schema_path():
    """Devuelve la ruta al schema.sql.

    En el contenedor está en /app/sql/schema.sql. Si no, asumimos
    que estamos corriendo desde extractor/src/ localmente.
    """
    env_path = os.getenv("SCHEMA_PATH")
    if env_path:
        return env_path
    if os.path.exists("/app/sql/schema.sql"):
        return "/app/sql/schema.sql"
    return str(Path(__file__).resolve().parent.parent.parent / "sql" / "schema.sql")


def parse_iso(s):
    """Pasa un timestamp ISO 8601 de GitHub (ej: '2024-01-15T10:00:00Z')
    a datetime con timezone.
    """
    if s is None:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def upsert_user_if_present(db, user_dict):
    """Si user_dict tiene datos, hace upsert y devuelve su id local.
    Si viene en blanco (a veces los issues no tienen autor), devuelve None.
    """
    if not user_dict or not user_dict.get("id"):
        return None
    return db.upsert_user(
        github_id=user_dict["id"],
        login=user_dict["login"],
        html_url=user_dict.get("html_url"),
    )


def extract_issues(gh, db, repo_id, owner, name):
    """Extrae issues del repo y los carga por lotes."""
    last = db.get_last_extraction(repo_id, "issues")
    print(f"  issues: desde {last or 'inicio'}")

    batch = []
    count = 0
    for issue in gh.get_issues(owner, name, since=last):
        author_id = upsert_user_if_present(db, issue.get("user"))

        batch.append((
            issue["id"],
            repo_id,
            issue["number"],
            author_id,
            issue["title"],
            issue["state"],
            "pull_request" in issue,
            parse_iso(issue["created_at"]),
            parse_iso(issue["updated_at"]),
            parse_iso(issue["closed_at"]),
        ))
        count += 1

        if len(batch) >= BATCH_SIZE:
            db.upsert_issues(batch)
            db.commit()
            batch = []

    if batch:
        db.upsert_issues(batch)
        db.commit()

    print(f"  issues: {count} cargados")


def extract_commits(gh, db, repo_id, owner, name):
    """Extrae commits del repo y los carga por lotes."""
    last = db.get_last_extraction(repo_id, "commits")
    print(f"  commits: desde {last or 'inicio'}")

    batch = []
    count = 0
    for commit in gh.get_commits(owner, name, since=last):

        author_id = upsert_user_if_present(db, commit.get("author"))
        committer_id = upsert_user_if_present(db, commit.get("committer"))

        commit_data = commit["commit"]
        batch.append((
            commit["sha"],
            repo_id,
            author_id,
            committer_id,
            commit_data["message"],
            parse_iso(commit_data["author"]["date"]),
            parse_iso(commit_data["committer"]["date"]),
        ))
        count += 1

        if len(batch) >= BATCH_SIZE:
            db.upsert_commits(batch)
            db.commit()
            batch = []

    if batch:
        db.upsert_commits(batch)
        db.commit()

    print(f"  commits: {count} cargados")


def main():
    env = load_env()
    schema_path = get_schema_path()

    print("Iniciando extractor")
    print(f"Schema en: {schema_path}")

    db = DBLoader(
        host=env["DB_HOST"],
        port=env["DB_PORT"],
        dbname=env["DB_NAME"],
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
    )
    db.connect()
    db.apply_schema(schema_path)

    try:
        # Bajar la lista de repos desde Drive
        drive = DriveClient(
            credentials_path=env["GOOGLE_CREDENTIALS_PATH"],
            folder_id=env["GOOGLE_DRIVE_FOLDER_ID"],
        )
        config = drive.read_json_config(env["DRIVE_CONFIG_FILENAME"])
        repos = config.get("repositories", [])
        print(f"Repos en config: {len(repos)}")

        gh = GitHubClient(token=env["GITHUB_TOKEN"])

        for repo_cfg in repos:
            owner, name = repo_cfg["owner"], repo_cfg["name"]
            print(f"\n>>> {owner}/{name}")

            repo_id = db.upsert_repository(owner, name)
            db.commit()

            run_started_at = datetime.now(timezone.utc)

            extract_issues(gh, db, repo_id, owner, name)
            db.update_extraction_state(repo_id, "issues", run_started_at)
            db.commit()

            extract_commits(gh, db, repo_id, owner, name)
            db.update_extraction_state(repo_id, "commits", run_started_at)
            db.commit()

        print("\nExtracción terminada.")
    finally:
        db.close()


if __name__ == "__main__":
    main()