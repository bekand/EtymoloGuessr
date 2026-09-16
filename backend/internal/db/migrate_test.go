package db

import (
	"strings"
	"testing"
)

func TestUpSectionStripsGooseDirectives(t *testing.T) {
	sql := `-- +goose Up
CREATE TABLE puzzles (id TEXT PRIMARY KEY);

-- +goose Down
DROP TABLE puzzles;
`
	got := upSection(sql)
	if got != "CREATE TABLE puzzles (id TEXT PRIMARY KEY);" {
		t.Fatalf("got %q", got)
	}
}

func TestUpSectionWithoutMarkersReturnsWholeFile(t *testing.T) {
	sql := "CREATE TABLE puzzles (id TEXT PRIMARY KEY);"
	if got := upSection(sql); got != sql {
		t.Fatalf("got %q", got)
	}
}

func TestUpSectionDownWithoutUpDoesNotTruncate(t *testing.T) {
	sql := `CREATE TABLE puzzles (id TEXT PRIMARY KEY);

-- +goose Down
DROP TABLE puzzles;`
	got := upSection(sql)
	if got != strings.TrimSpace(sql) {
		t.Fatalf("down-only file was truncated: %q", got)
	}
	if !strings.Contains(got, "DROP TABLE puzzles;") {
		t.Fatalf("expected down SQL to remain when Up marker is missing, got %q", got)
	}
}

func TestUpSectionUpWithoutDown(t *testing.T) {
	sql := `-- +goose Up
CREATE TABLE puzzles (id TEXT PRIMARY KEY);
`
	if got := upSection(sql); got != "CREATE TABLE puzzles (id TEXT PRIMARY KEY);" {
		t.Fatalf("got %q", got)
	}
}
