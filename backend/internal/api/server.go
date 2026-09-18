package api

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"strings"

	"github.com/bekand/EtymoloGuessr/backend/internal/config"
	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

const minHardModeNodes = 4

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
	mux.HandleFunc("GET /puzzles/{id}", s.handleGet)
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
	filter := puzzle.Filter{
		LangPair:   strings.TrimSpace(r.URL.Query().Get("langPair")),
		ExcludeIDs: parseExcludeIDs(r.URL.Query()["exclude"]),
	}
	if raw := strings.TrimSpace(r.URL.Query().Get("minQuality")); raw != "" {
		n, convErr := strconv.Atoi(raw)
		if convErr != nil {
			writeError(w, http.StatusBadRequest, "minQuality must be an integer")
			return
		}
		filter.MinQuality = &n
	}
	if mode == puzzle.ModeHard {
		n := minHardModeNodes
		filter.MinNodes = &n
	}

	if mode == puzzle.ModeMedium {
		puzzles, randErr := s.store.RandomPuzzles(r.Context(), filter, puzzle.MediumSetSize)
		if errors.Is(randErr, puzzle.ErrNotFound) {
			writeError(w, http.StatusNotFound, "no enabled puzzles")
			return
		}
		if randErr != nil {
			s.logger.Error("random medium set", "err", randErr)
			writeError(w, http.StatusInternalServerError, "failed to load puzzle")
			return
		}
		payload, buildErr := mediumPromptPayload(puzzles)
		if buildErr != nil {
			s.logger.Error("medium prompt", "err", buildErr)
			writeError(w, http.StatusInternalServerError, "failed to load puzzle")
			return
		}
		writeJSON(w, http.StatusOK, payload)
		return
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
	if !eligibleForMode(p, mode) {
		writeError(w, http.StatusNotFound, "no enabled puzzles")
		return
	}
	writeJSON(w, http.StatusOK, promptPayload(p, mode))
}

// parseExcludeIDs accepts repeated exclude= query values and comma-separated lists.
func parseExcludeIDs(values []string) []string {
	var out []string
	seen := make(map[string]struct{})
	for _, raw := range values {
		for _, part := range strings.Split(raw, ",") {
			id := strings.TrimSpace(part)
			if id == "" {
				continue
			}
			if _, ok := seen[id]; ok {
				continue
			}
			seen[id] = struct{}{}
			out = append(out, id)
		}
	}
	return out
}

func (s *Server) handleGet(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing puzzle id")
		return
	}
	mode, err := puzzle.ParseMode(r.URL.Query().Get("mode"))
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	if mode == puzzle.ModeMedium {
		puzzles, loadErr := s.loadMediumSet(w, r, id)
		if loadErr != nil {
			return
		}
		payload, buildErr := mediumPromptPayload(puzzles)
		if buildErr != nil {
			s.logger.Error("medium prompt", "err", buildErr)
			writeError(w, http.StatusInternalServerError, "failed to load puzzle")
			return
		}
		writeJSON(w, http.StatusOK, payload)
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
	if !eligibleForMode(p, mode) {
		writeError(w, http.StatusNotFound, "puzzle not found")
		return
	}
	writeJSON(w, http.StatusOK, promptPayload(p, mode))
}

type solveRequest struct {
	Mode     string        `json:"mode"`
	ChoiceID string        `json:"choiceId"`
	Edges    []puzzle.Edge `json:"edges"`
	Pairs    [][]string    `json:"pairs"`
}

type solveResponse struct {
	Correct       bool            `json:"correct"`
	GoldGraph     *puzzle.Graph   `json:"goldGraph,omitempty"`
	Choices       []puzzle.Choice `json:"choices,omitempty"`
	CorrectChoice string          `json:"correctChoice,omitempty"`
	Ancestors     []puzzle.Term   `json:"ancestors,omitempty"`
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

	if mode == puzzle.ModeMedium {
		s.solveMedium(w, r, id, req.Pairs)
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

	graph := p.AnswerGraph
	writeJSON(w, http.StatusOK, solveResponse{
		Correct:       correct,
		GoldGraph:     &graph,
		Choices:       p.Choices,
		CorrectChoice: p.CorrectChoice,
	})
}

func (s *Server) solveMedium(w http.ResponseWriter, r *http.Request, id string, pairs [][]string) {
	puzzles, err := s.loadMediumSet(w, r, id)
	if err != nil {
		return
	}
	if len(pairs) != puzzle.MediumSetSize {
		writeError(w, http.StatusBadRequest, "pairs must contain 4 pairs")
		return
	}
	submitted := make([][2]string, 0, len(pairs))
	for _, pair := range pairs {
		if len(pair) != 2 {
			writeError(w, http.StatusBadRequest, "each pair must have two leaf ids")
			return
		}
		submitted = append(submitted, [2]string{pair[0], pair[1]})
	}

	gold := make([][2]string, 0, puzzle.MediumSetSize)
	ancestors := make([]puzzle.Term, 0, puzzle.MediumSetSize)
	for _, p := range puzzles {
		gold = append(gold, [2]string{
			puzzle.LeafToken(p.ID, "a"),
			puzzle.LeafToken(p.ID, "b"),
		})
		anc, ok := puzzle.RootAncestor(p.AnswerGraph)
		if !ok {
			s.logger.Error("medium root ancestor missing", "id", p.ID)
			writeError(w, http.StatusInternalServerError, "failed to grade puzzle")
			return
		}
		ancestors = append(ancestors, anc)
	}

	writeJSON(w, http.StatusOK, solveResponse{
		Correct:   puzzle.PairSetsEqual(gold, submitted),
		Ancestors: ancestors,
	})
}

func (s *Server) loadMediumSet(w http.ResponseWriter, r *http.Request, id string) ([]*puzzle.Puzzle, error) {
	ids, err := puzzle.ParseMediumSetID(id)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return nil, err
	}
	puzzles := make([]*puzzle.Puzzle, 0, len(ids))
	for _, puzzleID := range ids {
		p, getErr := s.store.GetPuzzle(r.Context(), puzzleID)
		if errors.Is(getErr, puzzle.ErrNotFound) {
			writeError(w, http.StatusNotFound, "puzzle not found")
			return nil, getErr
		}
		if getErr != nil {
			s.logger.Error("get puzzle", "err", getErr)
			writeError(w, http.StatusInternalServerError, "failed to load puzzle")
			return nil, getErr
		}
		puzzles = append(puzzles, p)
	}
	return puzzles, nil
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

type mediumLeaf struct {
	ID   string `json:"id"`
	Lang string `json:"lang"`
	Term string `json:"term"`
}

type mediumPromptResponse struct {
	ID     string       `json:"id"`
	Mode   puzzle.Mode  `json:"mode"`
	Leaves []mediumLeaf `json:"leaves"`
}

func eligibleForMode(p *puzzle.Puzzle, mode puzzle.Mode) bool {
	if p == nil {
		return false
	}
	if mode == puzzle.ModeHard && len(p.AnswerGraph.Nodes) < minHardModeNodes {
		return false
	}
	return true
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

func mediumPromptPayload(puzzles []*puzzle.Puzzle) (mediumPromptResponse, error) {
	if len(puzzles) != puzzle.MediumSetSize {
		return mediumPromptResponse{}, errors.New("medium set size mismatch")
	}
	ids := make([]string, len(puzzles))
	leaves := make([]mediumLeaf, 0, puzzle.MediumSetSize*2)
	for i, p := range puzzles {
		ids[i] = p.ID
		a, err := puzzle.DecodeTerm(p.LeafA)
		if err != nil {
			return mediumPromptResponse{}, err
		}
		b, err := puzzle.DecodeTerm(p.LeafB)
		if err != nil {
			return mediumPromptResponse{}, err
		}
		leaves = append(leaves,
			mediumLeaf{ID: puzzle.LeafToken(p.ID, "a"), Lang: a.Lang, Term: a.Term},
			mediumLeaf{ID: puzzle.LeafToken(p.ID, "b"), Lang: b.Lang, Term: b.Term},
		)
	}
	setID := puzzle.MediumSetID(ids)
	return mediumPromptResponse{
		ID:     setID,
		Mode:   puzzle.ModeMedium,
		Leaves: puzzle.ShuffleByID(leaves, setID),
	}, nil
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
