package catalog

import (
	"context"
	"strings"
	"testing"

	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

func TestLoadEmbedded(t *testing.T) {
	store, err := LoadBytes(EmbeddedJSONL)
	if err != nil {
		t.Fatal(err)
	}
	if store.Len() < 2 {
		t.Fatalf("embedded catalog too small: %d", store.Len())
	}
	minNodes := 4
	p, err := store.RandomPuzzle(context.Background(), puzzle.Filter{MinNodes: &minNodes})
	if err != nil {
		t.Fatal(err)
	}
	if len(p.AnswerGraph.Nodes) < 4 {
		t.Fatalf("hard filter ignored, nodes=%d", len(p.AnswerGraph.Nodes))
	}
}

func TestLoadRejectsPromptGraph(t *testing.T) {
	raw := `{"id":"x","enabled":true,"leaf_a":{},"leaf_b":{},"answer_graph":{"nodes":[],"edges":[]},"choices":[],"correct_choice":"c0","quality_score":4,"lang_pair":"de-en","prompt_graph":{"nodes":[],"edges":[]}}` + "\n"
	_, err := LoadBytes([]byte(raw))
	if err == nil || !strings.Contains(err.Error(), "prompt_graph") {
		t.Fatalf("err %v", err)
	}
}

func TestGetMissing(t *testing.T) {
	store, err := LoadBytes(EmbeddedJSONL)
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.GetPuzzle(context.Background(), "missing")
	if err != puzzle.ErrNotFound {
		t.Fatalf("err %v", err)
	}
}

func TestDisabledSkipped(t *testing.T) {
	raw := `{"id":"off","enabled":false,"leaf_a":{},"leaf_b":{},"answer_graph":{"nodes":[{"id":"a"}],"edges":[]},"choices":[],"correct_choice":"c0","quality_score":5,"lang_pair":"de-en"}` + "\n"
	store, err := LoadBytes([]byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.RandomPuzzle(context.Background(), puzzle.Filter{})
	if err != puzzle.ErrNotFound {
		t.Fatalf("disabled row should be skipped, err=%v", err)
	}
}
