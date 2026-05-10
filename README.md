# Prueba Técnica — Data Engineer

Pipeline de datos automatizado que extrae **issues** y **commits** desde repositorios de GitHub (públicos y privados), los almacena de forma idempotente en PostgreSQL, y genera un reporte resumido que se publica en Google Drive. Todo orquestado por **Apache Airflow** y empaquetado con **Docker**.

## Arquitectura general
Google Drive (config.json)

Apache Airflow (DAG)

Docker container (extractor en Python)

--> GitHub API

PostgreSQL (modelo normalizado, idempotente)


Reporte CSV --> Google Drive

