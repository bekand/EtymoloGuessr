package catalog

import (
	"context"
	"fmt"
	"math/rand/v2"
	"strings"

	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

// MemoryStore is an in-process catalog. It is filled once at boot (JSONL)
// and is safe for concurrent reads.
type MemoryStore struct {
	order []string
	byID  map[string]*puzzle.Puzzle
}

func NewMemoryStore(puzzles []*puzzle.Puzzle) (*MemoryStore, error) {
	s := &MemoryStore{
		order: make([]string, 0, len(puzzles)),
		byID:  make(map[string]*puzzle.Puzzle, len(puzzles)),
	}
	for _, p := range puzzles {
		if p == nil || p.ID == "" {
			return nil, fmt.Errorf("catalog: puzzle missing id")
		}
		if _, exists := s.byID[p.ID]; exists {
			return nil, fmt.Errorf("catalog: duplicate puzzle id %s", p.ID)
		}
		s.byID[p.ID] = p
		s.order = append(s.order, p.ID)
	}
	if len(s.byID) == 0 {
		return nil, fmt.Errorf("catalog: no puzzles")
	}
	return s, nil
}

func (s *MemoryStore) Len() int {
	if s == nil {
		return 0
	}
	return len(s.byID)
}

func (s *MemoryStore) matching(filter puzzle.Filter) []*puzzle.Puzzle {
	exclude := make(map[string]struct{}, len(filter.ExcludeIDs))
	for _, id := range filter.ExcludeIDs {
		id = strings.TrimSpace(id)
		if id != "" {
			exclude[id] = struct{}{}
		}
	}
	var matches []*puzzle.Puzzle
	var fallback []*puzzle.Puzzle
	for _, id := range s.order {
		p := s.byID[id]
		if !matchesFilter(p, filter) {
			continue
		}
		fallback = append(fallback, p)
		if _, skip := exclude[p.ID]; skip {
			continue
		}
		matches = append(matches, p)
	}
	if len(matches) == 0 {
		return fallback
	}
	return matches
}

func (s *MemoryStore) RandomPuzzle(_ context.Context, filter puzzle.Filter) (*puzzle.Puzzle, error) {
	matches := s.matching(filter)
	if len(matches) == 0 {
		return nil, puzzle.ErrNotFound
	}
	return matches[rand.IntN(len(matches))], nil
}

func (s *MemoryStore) RandomPuzzles(_ context.Context, filter puzzle.Filter, n int) ([]*puzzle.Puzzle, error) {
	if n <= 0 {
		return nil, puzzle.ErrNotFound
	}
	matches := s.matching(filter)
	picked := puzzle.SelectDistinctLeaves(shuffleCopy(matches), n)
	if len(picked) < n && len(filter.ExcludeIDs) > 0 {
		// Exclusion left too few distinct-leaf puzzles; retry without exclude.
		noExclude := filter
		noExclude.ExcludeIDs = nil
		matches = s.matching(noExclude)
		picked = puzzle.SelectDistinctLeaves(shuffleCopy(matches), n)
	}
	if len(picked) < n {
		return nil, puzzle.ErrNotFound
	}
	return picked, nil
}

func shuffleCopy(in []*puzzle.Puzzle) []*puzzle.Puzzle {
	out := append([]*puzzle.Puzzle(nil), in...)
	rand.Shuffle(len(out), func(i, j int) { out[i], out[j] = out[j], out[i] })
	return out
}

func (s *MemoryStore) GetPuzzle(_ context.Context, id string) (*puzzle.Puzzle, error) {
	p, ok := s.byID[id]
	if !ok || !p.Enabled {
		return nil, puzzle.ErrNotFound
	}
	return p, nil
}

func matchesFilter(p *puzzle.Puzzle, filter puzzle.Filter) bool {
	if p == nil || !p.Enabled {
		return false
	}
	if filter.LangPair != "" && p.LangPair != filter.LangPair {
		return false
	}
	if filter.MinQuality != nil && p.QualityScore < *filter.MinQuality {
		return false
	}
	if filter.MinNodes != nil && len(p.AnswerGraph.Nodes) < *filter.MinNodes {
		return false
	}
	return true
}
