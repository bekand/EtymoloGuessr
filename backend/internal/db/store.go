package db

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Store struct {
	pool *pgxpool.Pool
}

func NewStore(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

func (s *Store) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

func (s *Store) RandomPuzzle(ctx context.Context, filter puzzle.Filter) (*puzzle.Puzzle, error) {
	p, err := s.randomPuzzle(ctx, filter)
	if errors.Is(err, puzzle.ErrNotFound) && len(filter.ExcludeIDs) > 0 {
		noExclude := filter
		noExclude.ExcludeIDs = nil
		return s.randomPuzzle(ctx, noExclude)
	}
	return p, err
}

func (s *Store) randomPuzzle(ctx context.Context, filter puzzle.Filter) (*puzzle.Puzzle, error) {
	const q = `
SELECT id, enabled, leaf_a, leaf_b, answer_graph, choices, correct_choice, quality_score, lang_pair, source
FROM puzzles
WHERE enabled = true
  AND ($1::text IS NULL OR lang_pair = $1)
  AND ($2::int IS NULL OR quality_score >= $2)
  AND ($3::int IS NULL OR jsonb_array_length(COALESCE(answer_graph->'nodes', '[]'::jsonb)) >= $3)
  AND (cardinality($4::text[]) = 0 OR NOT (id = ANY ($4::text[])))
ORDER BY random()
LIMIT 1`
	var langPair *string
	if filter.LangPair != "" {
		langPair = &filter.LangPair
	}
	exclude := normalizeExclude(filter.ExcludeIDs)
	return s.scanOne(ctx, q, langPair, filter.MinQuality, filter.MinNodes, exclude)
}

func (s *Store) RandomPuzzles(ctx context.Context, filter puzzle.Filter, n int) ([]*puzzle.Puzzle, error) {
	picked, err := s.randomPuzzles(ctx, filter, n)
	if (errors.Is(err, puzzle.ErrNotFound) || len(picked) < n) && len(filter.ExcludeIDs) > 0 {
		noExclude := filter
		noExclude.ExcludeIDs = nil
		return s.randomPuzzles(ctx, noExclude, n)
	}
	return picked, err
}

func (s *Store) randomPuzzles(ctx context.Context, filter puzzle.Filter, n int) ([]*puzzle.Puzzle, error) {
	if n <= 0 {
		return nil, puzzle.ErrNotFound
	}
	limit := n * 20
	if limit < 40 {
		limit = 40
	}
	const q = `
SELECT id, enabled, leaf_a, leaf_b, answer_graph, choices, correct_choice, quality_score, lang_pair, source
FROM puzzles
WHERE enabled = true
  AND ($1::text IS NULL OR lang_pair = $1)
  AND ($2::int IS NULL OR quality_score >= $2)
  AND ($3::int IS NULL OR jsonb_array_length(COALESCE(answer_graph->'nodes', '[]'::jsonb)) >= $3)
  AND (cardinality($4::text[]) = 0 OR NOT (id = ANY ($4::text[])))
ORDER BY random()
LIMIT $5`
	var langPair *string
	if filter.LangPair != "" {
		langPair = &filter.LangPair
	}
	exclude := normalizeExclude(filter.ExcludeIDs)
	rows, err := s.pool.Query(ctx, q, langPair, filter.MinQuality, filter.MinNodes, exclude, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var candidates []*puzzle.Puzzle
	for rows.Next() {
		p, scanErr := scanPuzzle(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		candidates = append(candidates, p)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	picked := puzzle.SelectDistinctLeaves(candidates, n)
	if len(picked) < n {
		return nil, puzzle.ErrNotFound
	}
	return picked, nil
}

func normalizeExclude(ids []string) []string {
	out := make([]string, 0, len(ids))
	seen := make(map[string]struct{}, len(ids))
	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	if out == nil {
		return []string{}
	}
	return out
}

func (s *Store) GetPuzzle(ctx context.Context, id string) (*puzzle.Puzzle, error) {
	const q = `
SELECT id, enabled, leaf_a, leaf_b, answer_graph, choices, correct_choice, quality_score, lang_pair, source
FROM puzzles
WHERE id = $1 AND enabled = true`
	return s.scanOne(ctx, q, id)
}

type rowScanner interface {
	Scan(dest ...any) error
}

func (s *Store) scanOne(ctx context.Context, q string, args ...any) (*puzzle.Puzzle, error) {
	row := s.pool.QueryRow(ctx, q, args...)
	p, err := scanPuzzle(row)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, puzzle.ErrNotFound
	}
	return p, err
}

func scanPuzzle(row rowScanner) (*puzzle.Puzzle, error) {
	var (
		p          puzzle.Puzzle
		answerRaw  []byte
		choicesRaw []byte
	)
	err := row.Scan(
		&p.ID,
		&p.Enabled,
		&p.LeafA,
		&p.LeafB,
		&answerRaw,
		&choicesRaw,
		&p.CorrectChoice,
		&p.QualityScore,
		&p.LangPair,
		&p.Source,
	)
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(answerRaw, &p.AnswerGraph); err != nil {
		return nil, fmt.Errorf("answer_graph: %w", err)
	}
	if err := json.Unmarshal(choicesRaw, &p.Choices); err != nil {
		return nil, fmt.Errorf("choices: %w", err)
	}
	return &p, nil
}
