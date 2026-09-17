package db

import (
	"strings"
	"testing"
)

func TestUpSection(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		sql  string
		want string
	}{
		{
			name: "strips goose directives",
			sql: `-- +goose Up
CREATE TABLE puzzles (id TEXT PRIMARY KEY);

-- +goose Down
DROP TABLE puzzles;
`,
			want: "CREATE TABLE puzzles (id TEXT PRIMARY KEY);",
		},
		{
			name: "no markers returns whole file",
			sql:  "CREATE TABLE puzzles (id TEXT PRIMARY KEY);",
			want: "CREATE TABLE puzzles (id TEXT PRIMARY KEY);",
		},
		{
			name: "down without up does not truncate",
			sql: `CREATE TABLE puzzles (id TEXT PRIMARY KEY);

-- +goose Down
DROP TABLE puzzles;`,
			want: `CREATE TABLE puzzles (id TEXT PRIMARY KEY);

-- +goose Down
DROP TABLE puzzles;`,
		},
		{
			name: "up without down",
			sql: `-- +goose Up
CREATE TABLE puzzles (id TEXT PRIMARY KEY);
`,
			want: "CREATE TABLE puzzles (id TEXT PRIMARY KEY);",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := upSection(tt.sql)
			if strings.TrimSpace(got) != strings.TrimSpace(tt.want) {
				t.Fatalf("got %q, want %q", got, tt.want)
			}
		})
	}
}
