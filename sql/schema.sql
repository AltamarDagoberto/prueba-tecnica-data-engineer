-- ============================================================
-- Esquema para el pipeline de datos de GitHub
-- Base de datos: PostgreSQL 13+
-- ============================================================
-- Notas:
--   * Tablas normalizadas: cada repo y cada usuario se guarda
--     una sola vez y se referencia por id.
--   * Las llaves primarias usan los ids que ya vienen de GitHub
--     (sha del commit, id del issue, id del usuario) para que
--     al cargar dos veces no se dupliquen los datos.
--   * La tabla extraction_state guarda hasta qué fecha se
--     extrajo cada repo, para que la siguiente corrida solo
--     traiga lo nuevo.
-- ============================================================


-- ------------------------------------------------------------
-- repositories: lista de repos que se están monitoreando
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS repositories (
    id          SERIAL       PRIMARY KEY,
    owner       VARCHAR(255) NOT NULL,
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (owner, name)
);


-- ------------------------------------------------------------
-- users: usuarios de GitHub que aparecen como autores
-- Guardamos github_id porque el login (nombre de usuario)
-- puede cambiar, pero el id no.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          SERIAL       PRIMARY KEY,
    github_id   BIGINT       NOT NULL UNIQUE,
    login       VARCHAR(255) NOT NULL,
    html_url    VARCHAR(512)
);


-- ------------------------------------------------------------
-- issues
-- Aquí estan caen los pull requests (la API de GitHub los
-- devuelve en /issues), por eso la columna is_pull_request:
-- así se pueden filtrar después si se necesita.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS issues (
    github_id        BIGINT       PRIMARY KEY,
    repo_id          INTEGER      NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    number           INTEGER      NOT NULL,
    author_id        INTEGER      REFERENCES users(id),
    title            TEXT         NOT NULL,
    state            VARCHAR(20)  NOT NULL,
    is_pull_request  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ  NOT NULL,
    updated_at       TIMESTAMPTZ  NOT NULL,
    closed_at        TIMESTAMPTZ,
    UNIQUE (repo_id, number)
);

CREATE INDEX IF NOT EXISTS idx_issues_repo_id    ON issues(repo_id);
CREATE INDEX IF NOT EXISTS idx_issues_updated_at ON issues(updated_at);


-- ------------------------------------------------------------
-- commits
-- La PK es (sha, repo_id) porque un mismo commit puede aparecer
-- en varios repos (ej: forks).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS commits (
    sha           VARCHAR(40) NOT NULL,
    repo_id       INTEGER     NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    author_id     INTEGER     REFERENCES users(id),
    committer_id  INTEGER     REFERENCES users(id),
    message       TEXT        NOT NULL,
    authored_at   TIMESTAMPTZ NOT NULL,
    committed_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (sha, repo_id)
);

CREATE INDEX IF NOT EXISTS idx_commits_repo_id      ON commits(repo_id);
CREATE INDEX IF NOT EXISTS idx_commits_committed_at ON commits(committed_at);


-- ------------------------------------------------------------
-- extraction_state
-- Guarda la última fecha de extracción por repo y entidad
-- (issues o commits). La próxima corrida usa este valor para
-- pedir solo lo que cambió después.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extraction_state (
    repo_id            INTEGER     NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    entity             VARCHAR(20) NOT NULL CHECK (entity IN ('issues', 'commits')),
    last_extracted_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (repo_id, entity)
);