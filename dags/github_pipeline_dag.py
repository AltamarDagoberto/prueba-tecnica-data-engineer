"""DAG del pipeline de extracción de GitHub.

Cuatro fases:
  1. Validar que config.json esté disponible en Drive
  2. Correr el extractor (fetch + load a Postgres)
  3. Refrescar la vista materializada (transformación SQL)
  4. Generar el reporte CSV y subirlo a Drive

"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount



HOST_PROJECT_DIR = os.environ.get("HOST_PROJECT_DIR", "/missing")

NETWORK_NAME = os.environ.get("AIRFLOW_DOCKER_NETWORK", "pipeline-net")

EXTRACTOR_IMAGE = "github-extractor:latest"


def extractor_env():
    return {
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", ""),
        "GOOGLE_CREDENTIALS_PATH": "/app/credentials/oauth_token.json",
        "GOOGLE_DRIVE_FOLDER_ID": os.environ.get("GOOGLE_DRIVE_FOLDER_ID", ""),
        "DRIVE_CONFIG_FILENAME": os.environ.get("DRIVE_CONFIG_FILENAME", "config.json"),
        "DB_HOST": "postgres-data",
        "DB_PORT": "5432",
        "DB_NAME": os.environ.get("DB_NAME", "github_data"),
        "DB_USER": os.environ.get("DB_USER", "pipeline"),
        "DB_PASSWORD": os.environ.get("DB_PASSWORD", "pipeline_dev_2026"),
        "SCHEMA_PATH": "/app/sql/schema.sql",
    }


def extractor_mounts():
    """Volumenes que necesita el contenedor del extractor:
      - credentials/ : read-only, para autenticarse con Google Drive
      - reports/     : read-write, donde generate_report deja el CSV
                       (utilio cuando la subida a Drive falla por cuotas)
    El codigo y el schema.sql ya viven dentro de la imagen.
    """
    return [
        Mount(
            source=f"{HOST_PROJECT_DIR}/credentials",
            target="/app/credentials",
            type="bind",
            read_only=True,
        ),
        Mount(
            source=f"{HOST_PROJECT_DIR}/reports",
            target="/app/reports",
            type="bind",
            read_only=False,
        ),
    ]


def docker_task(task_id: str, command: str) -> DockerOperator:
    """Helper para no repetir los mismos parámetros en cada tarea."""
    return DockerOperator(
        task_id=task_id,
        image=EXTRACTOR_IMAGE,
        command=command,
        environment=extractor_env(),
        mounts=extractor_mounts(),
        network_mode=NETWORK_NAME,
        auto_remove="success",
        mount_tmp_dir=False,
        docker_url="unix:///var/run/docker.sock",
    )


default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


with DAG(
    dag_id="github_pipeline",
    description="Pipeline diario: extrae issues/commits de GitHub a Postgres y publica reporte en Drive",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["github", "etl"],
) as dag:

    validate_config = docker_task("validate_config", "python validate_config.py")
    run_extractor   = docker_task("run_extractor",   "python main.py")
    refresh_views   = docker_task("refresh_views",   "python refresh_views.py")
    generate_report = docker_task("generate_report", "python report.py")

    validate_config >> run_extractor >> refresh_views >> generate_report