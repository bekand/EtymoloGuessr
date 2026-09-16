package config

import (
	"os"
	"strings"
)

type Config struct {
	Addr          string
	DatabaseURL   string
	CORSOrigins   []string
	AutoMigrate   bool
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
		Addr:        getenv("HTTP_ADDR", ":8080"),
		DatabaseURL: os.Getenv("DATABASE_URL"),
		CORSOrigins: cleaned,
		AutoMigrate: migrate == "1" || migrate == "true" || migrate == "yes",
	}
}

func getenv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
