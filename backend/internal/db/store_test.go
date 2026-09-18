package db_test

import (
	"context"
	"errors"
	"testing"

	"github.com/bekand/EtymoloGuessr/backend/internal/db"
	"github.com/bekand/EtymoloGuessr/backend/internal/dbtest"
	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

func TestStoreRandomAndGet(t *testing.T) {
	pool := dbtest.Open(t)
	store := db.NewStore(pool)
	enabled := dbtest.Sample("enabled-de-en", 3, true, "de-en", 5)
	disabled := dbtest.Sample("disabled-de-en", 3, false, "de-en", 5)
	spanish := dbtest.Sample("enabled-en-es", 3, true, "en-es", 4)
	lowQ := dbtest.Sample("low-quality", 3, true, "de-en", 1)
	dbtest.Insert(t, pool, enabled)
	dbtest.Insert(t, pool, disabled)
	dbtest.Insert(t, pool, spanish)
	dbtest.Insert(t, pool, lowQ)

	ctx := context.Background()

	got, err := store.GetPuzzle(ctx, enabled.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ID != enabled.ID {
		t.Fatalf("id %q", got.ID)
	}

	if _, err := store.GetPuzzle(ctx, disabled.ID); !errors.Is(err, puzzle.ErrNotFound) {
		t.Fatalf("disabled puzzle: %v", err)
	}
	if _, err := store.GetPuzzle(ctx, "missing"); !errors.Is(err, puzzle.ErrNotFound) {
		t.Fatalf("missing puzzle: %v", err)
	}

	pair, err := store.RandomPuzzle(ctx, puzzle.Filter{LangPair: "en-es"})
	if err != nil {
		t.Fatal(err)
	}
	if pair.ID != spanish.ID {
		t.Fatalf("langPair filter got %q", pair.ID)
	}

	minQ := 5
	high, err := store.RandomPuzzle(ctx, puzzle.Filter{LangPair: "de-en", MinQuality: &minQ})
	if err != nil {
		t.Fatal(err)
	}
	if high.ID != enabled.ID {
		t.Fatalf("minQuality filter got %q", high.ID)
	}
}

func TestStoreMinNodesFilter(t *testing.T) {
	pool := dbtest.Open(t)
	store := db.NewStore(pool)
	small := dbtest.Sample("three-nodes", 3, true, "de-en", 5)
	large := dbtest.Sample("four-nodes", 4, true, "de-en", 5)
	dbtest.Insert(t, pool, small)
	dbtest.Insert(t, pool, large)

	minNodes := 4
	got, err := store.RandomPuzzle(context.Background(), puzzle.Filter{MinNodes: &minNodes})
	if err != nil {
		t.Fatal(err)
	}
	if got.ID != large.ID {
		t.Fatalf("minNodes filter got %q", got.ID)
	}
	if len(got.AnswerGraph.Nodes) < 4 {
		t.Fatalf("nodes %d", len(got.AnswerGraph.Nodes))
	}
}

func TestStoreRandomPuzzles(t *testing.T) {
	pool := dbtest.Open(t)
	store := db.NewStore(pool)
	for i, sample := range []*puzzle.Puzzle{
		mediumSample("mp1", "English", "father", "German", "Vater"),
		mediumSample("mp2", "English", "hound", "German", "Hund"),
		mediumSample("mp3", "English", "gift", "German", "Gift"),
		mediumSample("mp4", "English", "house", "German", "Haus"),
		mediumSample("mp5", "English", "water", "German", "Wasser"),
	} {
		_ = i
		dbtest.Insert(t, pool, sample)
	}

	got, err := store.RandomPuzzles(context.Background(), puzzle.Filter{}, 4)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 4 {
		t.Fatalf("got %d", len(got))
	}
	seen := map[string]bool{}
	for _, p := range got {
		if seen[p.ID] {
			t.Fatalf("duplicate %s", p.ID)
		}
		seen[p.ID] = true
	}
}

func mediumSample(id, aLang, aTerm, bLang, bTerm string) *puzzle.Puzzle {
	p := dbtest.Sample(id, 3, true, "de-en", 5)
	p.LeafA = []byte(`{"lang":"` + aLang + `","term":"` + aTerm + `"}`)
	p.LeafB = []byte(`{"lang":"` + bLang + `","term":"` + bTerm + `"}`)
	return p
}

func TestMigrateIdempotent(t *testing.T) {
	pool := dbtest.Open(t)
	if err := db.Migrate(context.Background(), pool); err != nil {
		t.Fatal(err)
	}
}
