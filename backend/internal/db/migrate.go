package db

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

func Connect(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	if databaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is not set")
	}
	pool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	return pool, nil
}

func Migrate(ctx context.Context, pool *pgxpool.Pool) error {
	if _, err := pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`); err != nil {
		return fmt.Errorf("schema_migrations: %w", err)
	}

	entries, err := fs.ReadDir(migrationsFS, "migrations")
	if err != nil {
		return err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
			continue
		}
		names = append(names, e.Name())
	}
	sort.Strings(names)

	for _, name := range names {
		var applied bool
		if err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = $1)`, name).Scan(&applied); err != nil {
			return err
		}
		if applied {
			continue
		}
		raw, err := fs.ReadFile(migrationsFS, "migrations/"+name)
		if err != nil {
			return err
		}
		up := upSection(string(raw))
		conn, err := pool.Acquire(ctx)
		if err != nil {
			return err
		}
		_, err = conn.Exec(ctx, up, pgx.QueryExecModeSimpleProtocol)
		if err != nil {
			conn.Release()
			return fmt.Errorf("migration %s: %w", name, err)
		}
		_, err = conn.Exec(ctx, `INSERT INTO schema_migrations (version) VALUES ($1)`, name)
		conn.Release()
		if err != nil {
			return err
		}
	}
	return nil
}

func upSection(sql string) string {
	const up = "-- +goose Up"
	const down = "-- +goose Down"
	start := strings.Index(sql, up)
	if start < 0 {
		// No Up marker: leave the file as-is. Do not treat a lone Down
		// marker as an end-of-script cut.
		return strings.TrimSpace(sql)
	}
	sql = sql[start+len(up):]
	if end := strings.Index(sql, down); end >= 0 {
		sql = sql[:end]
	}
	return strings.TrimSpace(sql)
}
