-- +goose Up
CREATE TABLE puzzles (
    id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    leaf_a JSONB NOT NULL,
    leaf_b JSONB NOT NULL,
    answer_graph JSONB NOT NULL,
    choices JSONB NOT NULL,
    correct_choice TEXT NOT NULL,
    quality_score INTEGER NOT NULL DEFAULT 0,
    lang_pair TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'etymology-db+kaikki',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX puzzles_enabled_idx ON puzzles (enabled) WHERE enabled;
CREATE INDEX puzzles_lang_pair_idx ON puzzles (lang_pair);
CREATE INDEX puzzles_quality_idx ON puzzles (quality_score);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER puzzles_updated_at
BEFORE UPDATE ON puzzles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- Placeholder tables for later auth / leaderboards. ETL must not drop these.
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scores (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users (id),
    puzzle_id TEXT REFERENCES puzzles (id),
    mode TEXT NOT NULL,
    correct BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- +goose Down
DROP TABLE IF EXISTS scores;
DROP TABLE IF EXISTS users;
DROP TRIGGER IF EXISTS puzzles_updated_at ON puzzles;
DROP FUNCTION IF EXISTS set_updated_at();
DROP TABLE IF EXISTS puzzles;
