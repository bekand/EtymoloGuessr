package db

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

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
	const q = `
SELECT id, enabled, leaf_a, leaf_b, answer_graph, choices, correct_choice, quality_score, lang_pair, source
FROM puzzles
WHERE enabled = true
  AND ($1::text IS NULL OR lang_pair = $1)
  AND ($2::int IS NULL OR quality_score >= $2)
  AND ($3::int IS NULL OR jsonb_array_length(COALESCE(answer_graph->'nodes', '[]'::jsonb)) >= $3)
ORDER BY random()
LIMIT 1`
	var langPair *string
	if filter.LangPair != "" {
		langPair = &filter.LangPair
	}
	return s.scanOne(ctx, q, langPair, filter.MinQuality, filter.MinNodes)
}

func (s *Store) GetPuzzle(ctx context.Context, id string) (*puzzle.Puzzle, error) {
	const q = `
SELECT id, enabled, leaf_a, leaf_b, answer_graph, choices, correct_choice, quality_score, lang_pair, source
FROM puzzles
WHERE id = $1 AND enabled = true`
	return s.scanOne(ctx, q, id)
}

func (s *Store) scanOne(ctx context.Context, q string, args ...any) (*puzzle.Puzzle, error) {
	row := s.pool.QueryRow(ctx, q, args...)
	var (
		p            puzzle.Puzzle
		answerRaw    []byte
		choicesRaw   []byte
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
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, puzzle.ErrNotFound
	}
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
