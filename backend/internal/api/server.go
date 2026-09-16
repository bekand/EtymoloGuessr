package api

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"strings"

	"github.com/bekand/EtymoGuessr/backend/internal/config"
	"github.com/bekand/EtymoGuessr/backend/internal/puzzle"
)

type Server struct {
	store  puzzle.Store
	logger *slog.Logger
	ready  func(*http.Request) error
	mux    http.Handler
}

func New(store puzzle.Store, cfg config.Config, logger *slog.Logger) *Server {
	if logger == nil {
		logger = slog.Default()
	}
	s := &Server{store: store, logger: logger}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /puzzles/random", s.handleRandom)
	mux.HandleFunc("POST /puzzles/{id}/solve", s.handleSolve)
	s.mux = withCORS(cfg.CORSOrigins, mux)
	return s
}

func (s *Server) SetReady(fn func(*http.Request) error) {
	s.ready = fn
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mux.ServeHTTP(w, r)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if s.ready != nil {
		if err := s.ready(r); err != nil {
			writeError(w, http.StatusServiceUnavailable, "database unavailable")
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleRandom(w http.ResponseWriter, r *http.Request) {
	mode, err := puzzle.ParseMode(r.URL.Query().Get("mode"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	filter := puzzle.Filter{LangPair: strings.TrimSpace(r.URL.Query().Get("langPair"))}
	if raw := strings.TrimSpace(r.URL.Query().Get("minQuality")); raw != "" {
		n, convErr := strconv.Atoi(raw)
		if convErr != nil {
			writeError(w, http.StatusBadRequest, "minQuality must be an integer")
			return
		}
		filter.MinQuality = &n
	}
	p, err := s.store.RandomPuzzle(r.Context(), filter)
	if errors.Is(err, puzzle.ErrNotFound) {
		writeError(w, http.StatusNotFound, "no enabled puzzles")
		return
	}
	if err != nil {
		s.logger.Error("random puzzle", "err", err)
		writeError(w, http.StatusInternalServerError, "failed to load puzzle")
		return
	}
	writeJSON(w, http.StatusOK, promptPayload(p, mode))
}

type solveRequest struct {
	Mode     string        `json:"mode"`
	ChoiceID string        `json:"choiceId"`
	Edges    []puzzle.Edge `json:"edges"`
}

type solveResponse struct {
	Correct       bool            `json:"correct"`
	GoldGraph     puzzle.Graph    `json:"goldGraph"`
	Choices       []puzzle.Choice `json:"choices"`
	CorrectChoice string          `json:"correctChoice"`
}

func (s *Server) handleSolve(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing puzzle id")
		return
	}
	var req solveRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	mode, err := puzzle.ParseMode(req.Mode)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	p, err := s.store.GetPuzzle(r.Context(), id)
	if errors.Is(err, puzzle.ErrNotFound) {
		writeError(w, http.StatusNotFound, "puzzle not found")
		return
	}
	if err != nil {
		s.logger.Error("get puzzle", "err", err)
		writeError(w, http.StatusInternalServerError, "failed to load puzzle")
		return
	}

	var correct bool
	switch mode {
	case puzzle.ModeEasy:
		if req.ChoiceID == "" {
			writeError(w, http.StatusBadRequest, "choiceId is required for easy mode")
			return
		}
		correct = puzzle.ChoiceCorrect(p, req.ChoiceID)
	case puzzle.ModeHard:
		correct = puzzle.EdgeSetsEqual(p.AnswerGraph.Edges, req.Edges)
	}

	writeJSON(w, http.StatusOK, solveResponse{
		Correct:       correct,
		GoldGraph:     p.AnswerGraph,
		Choices:       p.Choices,
		CorrectChoice: p.CorrectChoice,
	})
}

type promptResponse struct {
	ID          string          `json:"id"`
	Mode        puzzle.Mode     `json:"mode"`
	LangPair    string          `json:"langPair"`
	LeafA       json.RawMessage `json:"leafA"`
	LeafB       json.RawMessage `json:"leafB"`
	Choices     []puzzle.Choice `json:"choices"`
	PromptGraph *puzzle.Graph   `json:"promptGraph,omitempty"`
}

func promptPayload(p *puzzle.Puzzle, mode puzzle.Mode) promptResponse {
	return promptResponse{
		ID:          p.ID,
		Mode:        mode,
		LangPair:    p.LangPair,
		LeafA:       p.LeafA,
		LeafB:       p.LeafB,
		Choices:     p.Choices,
		PromptGraph: puzzle.PromptGraph(p.AnswerGraph, mode),
	}
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func withCORS(origins []string, next http.Handler) http.Handler {
	allowed := make(map[string]struct{}, len(origins))
	allowAll := false
	for _, o := range origins {
		if o == "*" {
			allowAll = true
		}
		allowed[o] = struct{}{}
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" && (allowAll || contains(allowed, origin)) {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func contains(set map[string]struct{}, key string) bool {
	_, ok := set[key]
	return ok
}
