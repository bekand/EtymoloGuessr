package config

import "testing"

func TestListenAddrPrefersPort(t *testing.T) {
	t.Setenv("PORT", "3000")
	t.Setenv("HTTP_ADDR", ":8080")
	if got := listenAddr(); got != ":3000" {
		t.Fatalf("addr %q", got)
	}
}

func TestListenAddrHTTPAddrFallback(t *testing.T) {
	t.Setenv("PORT", "")
	t.Setenv("HTTP_ADDR", ":9090")
	if got := listenAddr(); got != ":9090" {
		t.Fatalf("addr %q", got)
	}
}

func TestFromEnvPuzzlesPath(t *testing.T) {
	t.Setenv("PORT", "")
	t.Setenv("HTTP_ADDR", "")
	t.Setenv("DATABASE_URL", "")
	t.Setenv("PUZZLES_PATH", "/catalog/puzzles.jsonl")
	t.Setenv("CORS_ORIGINS", "https://web.example.com")
	t.Setenv("AUTO_MIGRATE", "false")
	cfg := FromEnv()
	if cfg.Addr != ":8080" {
		t.Fatalf("default addr %q", cfg.Addr)
	}
	if cfg.DatabaseURL != "" {
		t.Fatalf("database url %q", cfg.DatabaseURL)
	}
	if cfg.PuzzlesPath != "/catalog/puzzles.jsonl" {
		t.Fatalf("puzzles path %q", cfg.PuzzlesPath)
	}
	if cfg.AutoMigrate {
		t.Fatal("AUTO_MIGRATE false should disable migrate")
	}
	if len(cfg.CORSOrigins) != 1 || cfg.CORSOrigins[0] != "https://web.example.com" {
		t.Fatalf("cors %+v", cfg.CORSOrigins)
	}
}
