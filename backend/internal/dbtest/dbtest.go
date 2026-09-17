package dbtest

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/bekand/EtymoloGuessr/backend/internal/db"
	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
	"github.com/jackc/pgx/v5/pgxpool"
)

func Open(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := strings.TrimSpace(os.Getenv("TEST_DATABASE_URL"))
	if url == "" {
		t.Skip("TEST_DATABASE_URL is not set")
	}

	var pool *pgxpool.Pool
	var err error
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		pool, err = db.Connect(ctx, url)
		cancel()
		if err == nil {
			break
		}
		time.Sleep(400 * time.Millisecond)
	}
	if err != nil {
		t.Skipf("postgres unreachable: %v", err)
	}

	t.Cleanup(pool.Close)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := db.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	Truncate(t, pool)
	return pool
}

func Truncate(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), `TRUNCATE TABLE scores, puzzles`); err != nil {
		t.Fatalf("truncate: %v", err)
	}
}

func Insert(t *testing.T, pool *pgxpool.Pool, p *puzzle.Puzzle) {
	t.Helper()
	answer, err := json.Marshal(p.AnswerGraph)
	if err != nil {
		t.Fatal(err)
	}
	choices, err := json.Marshal(p.Choices)
	if err != nil {
		t.Fatal(err)
	}
	_, err = pool.Exec(context.Background(), `
INSERT INTO puzzles (
    id, enabled, leaf_a, leaf_b, answer_graph,
    choices, correct_choice, quality_score, lang_pair, source
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
		p.ID, p.Enabled, []byte(p.LeafA), []byte(p.LeafB), answer,
		choices, p.CorrectChoice, p.QualityScore, p.LangPair, p.Source,
	)
	if err != nil {
		t.Fatalf("insert %s: %v", p.ID, err)
	}
}

func Sample(id string, nodes int, enabled bool, langPair string, quality int) *puzzle.Puzzle {
	gloss := "a male parent"
	graph := puzzle.Graph{
		Nodes: []puzzle.Node{
			{ID: "English:father", Lang: "English", Term: "father", Role: "leaf"},
			{ID: "German:Vater", Lang: "German", Term: "Vater", Role: "leaf"},
			{ID: "Proto-Germanic:*fader", Lang: "Proto-Germanic", Term: "*fader", Gloss: &gloss, Role: "ancestor"},
		},
		Edges: []puzzle.Edge{
			{From: "English:father", To: "Proto-Germanic:*fader"},
			{From: "German:Vater", To: "Proto-Germanic:*fader"},
		},
	}
	if nodes >= 4 {
		graph.Nodes = append(graph.Nodes, puzzle.Node{
			ID: "Proto-Indo-European:*ph2ter", Lang: "Proto-Indo-European", Term: "*ph₂tḗr", Gloss: &gloss, Role: "ancestor",
		})
		graph.Edges = append(graph.Edges, puzzle.Edge{
			From: "Proto-Germanic:*fader", To: "Proto-Indo-European:*ph2ter",
		})
	}
	return &puzzle.Puzzle{
		ID:            id,
		Enabled:       enabled,
		LeafA:         json.RawMessage(`{"lang":"English","term":"father","gloss":"male parent"}`),
		LeafB:         json.RawMessage(`{"lang":"German","term":"Vater","gloss":"father"}`),
		AnswerGraph:   graph,
		Choices:       []puzzle.Choice{{ID: "c0", Gloss: "a male parent"}, {ID: "c1", Gloss: "a river"}, {ID: "c2", Gloss: "to walk"}, {ID: "c3", Gloss: "a stone"}},
		CorrectChoice: "c0",
		QualityScore:  quality,
		LangPair:      langPair,
		Source:        "test",
	}
}
