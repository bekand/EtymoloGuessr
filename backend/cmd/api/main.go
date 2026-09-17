package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/bekand/EtymoloGuessr/backend/internal/api"
	"github.com/bekand/EtymoloGuessr/backend/internal/catalog"
	"github.com/bekand/EtymoloGuessr/backend/internal/config"
	"github.com/bekand/EtymoloGuessr/backend/internal/db"
	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))
	slog.SetDefault(logger)

	cfg := config.FromEnv()
	ctx := context.Background()

	store, cleanup, ready, err := openStore(ctx, cfg, logger)
	if err != nil {
		logger.Error("store", "err", err)
		os.Exit(1)
	}
	if cleanup != nil {
		defer cleanup()
	}

	handler := api.New(store, cfg, logger)
	if ready != nil {
		handler.SetReady(ready)
	}

	httpSrv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		logger.Info("listening", "addr", cfg.Addr)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("listen", "err", err)
			os.Exit(1)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
}

func openStore(ctx context.Context, cfg config.Config, logger *slog.Logger) (puzzle.Store, func(), func(*http.Request) error, error) {
	if cfg.DatabaseURL != "" {
		pool, err := db.Connect(ctx, cfg.DatabaseURL)
		if err != nil {
			return nil, nil, nil, err
		}
		if cfg.AutoMigrate {
			if err := db.Migrate(ctx, pool); err != nil {
				pool.Close()
				return nil, nil, nil, err
			}
			logger.Info("migrations applied")
		}
		store := db.NewStore(pool)
		logger.Info("store", "backend", "postgres")
		return store, pool.Close, func(r *http.Request) error {
			return store.Ping(r.Context())
		}, nil
	}

	var (
		mem    *catalog.MemoryStore
		err    error
		source string
	)
	if cfg.PuzzlesPath != "" {
		mem, err = catalog.LoadFile(cfg.PuzzlesPath)
		source = cfg.PuzzlesPath
	} else {
		mem, err = catalog.LoadBytes(catalog.EmbeddedJSONL)
		source = "embed"
	}
	if err != nil {
		return nil, nil, nil, err
	}
	logger.Info("store", "backend", "jsonl", "source", source, "puzzles", mem.Len())
	return mem, nil, nil, nil
}
