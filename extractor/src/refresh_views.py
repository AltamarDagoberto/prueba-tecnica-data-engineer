#Refresca la vista materializada con conteos por repo.

import os

import psycopg2
from dotenv import load_dotenv


SQL_REFRESH = """
DROP MATERIALIZED VIEW IF EXISTS mv_repo_summary;

-- Agregamos issues y commits por repo en subconsultas separadas.
-- Si hicieramos LEFT JOIN issues y LEFT JOIN commits a la vez,
-- saldria un producto cartesiano (issues x commits por repo) y la
-- query se demora muchisimo en repos con miles de filas.
CREATE MATERIALIZED VIEW mv_repo_summary AS
SELECT
    r.id                                AS repo_id,
    r.owner || '/' || r.name            AS repo,
    COALESCE(i.issues_count, 0)         AS issues_count,
    COALESCE(i.prs_count, 0)            AS prs_count,
    COALESCE(c.commits_count, 0)        AS commits_count,
    i.last_issue_update                 AS last_issue_update,
    c.last_commit_at                    AS last_commit_at
FROM repositories r
LEFT JOIN (
    SELECT
        repo_id,
        COUNT(*)                                       AS issues_count,
        COUNT(*) FILTER (WHERE is_pull_request)        AS prs_count,
        MAX(updated_at)                                AS last_issue_update
    FROM issues
    GROUP BY repo_id
) i ON i.repo_id = r.id
LEFT JOIN (
    SELECT
        repo_id,
        COUNT(*)                                       AS commits_count,
        MAX(committed_at)                              AS last_commit_at
    FROM commits
    GROUP BY repo_id
) c ON c.repo_id = r.id;
"""


def main():
    load_dotenv()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_REFRESH)
        conn.commit()
        print("Vista mv_repo_summary refrescada")
    finally:
        conn.close()


if __name__ == "__main__":
    main()