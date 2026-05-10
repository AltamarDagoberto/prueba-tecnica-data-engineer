#Refresca la vista materializada con conteos por repo.

import os

import psycopg2
from dotenv import load_dotenv


SQL_REFRESH = """
DROP MATERIALIZED VIEW IF EXISTS mv_repo_summary;

CREATE MATERIALIZED VIEW mv_repo_summary AS
SELECT
    r.id                       AS repo_id,
    r.owner || '/' || r.name   AS repo,
    COUNT(DISTINCT i.github_id)                                   AS issues_count,
    COUNT(DISTINCT i.github_id) FILTER (WHERE i.is_pull_request)  AS prs_count,
    COUNT(DISTINCT c.sha)                                         AS commits_count,
    MAX(i.updated_at)                                             AS last_issue_update,
    MAX(c.committed_at)                                           AS last_commit_at
FROM repositories r
LEFT JOIN issues  i ON i.repo_id = r.id
LEFT JOIN commits c ON c.repo_id = r.id
GROUP BY r.id, r.owner, r.name;
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