package config

import (
	"os"
	"strings"
)

type Config struct {
	Addr        string
	DatabaseURL string
	PuzzlesPath string
	CORSOrigins []string
	AutoMigrate bool
}

func FromEnv() Config {
	origins := getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
	parts := strings.Split(origins, ",")
	cleaned := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			cleaned = append(cleaned, p)
		}
	}
	migrate := strings.ToLower(getenv("AUTO_MIGRATE", "true"))
	return Config{
		Addr:        listenAddr(),
		DatabaseURL: strings.TrimSpace(os.Getenv("DATABASE_URL")),
		PuzzlesPath: strings.TrimSpace(os.Getenv("PUZZLES_PATH")),
		CORSOrigins: cleaned,
		AutoMigrate: migrate == "1" || migrate == "true" || migrate == "yes",
	}
}

// listenAddr prefers Railway's PORT (digits only) over HTTP_ADDR.
func listenAddr() string {
	if port := strings.TrimSpace(os.Getenv("PORT")); port != "" {
		if strings.HasPrefix(port, ":") {
			return port
		}
		if strings.Contains(port, ":") {
			return port
		}
		return ":" + port
	}
	return getenv("HTTP_ADDR", ":8080")
}

func getenv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
