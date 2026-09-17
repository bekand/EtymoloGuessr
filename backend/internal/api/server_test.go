package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/bekand/EtymoloGuessr/backend/internal/catalog"
	"github.com/bekand/EtymoloGuessr/backend/internal/config"
	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

func testHandlerWith(puzzles ...*puzzle.Puzzle) http.Handler {
	store, err := catalog.NewMemoryStore(puzzles)
	if err != nil {
		panic(err)
	}
	return New(store, config.Config{
		CORSOrigins: []string{"http://localhost:5173"},
	}, nil)
}

func fixturePuzzle() *puzzle.Puzzle {
	gloss := "a male parent"
	return &puzzle.Puzzle{
		ID:      "abc123abc123abc123",
		Enabled: true,
		LeafA:   json.RawMessage(`{"lang":"English","term":"father","gloss":"male parent"}`),
		LeafB:   json.RawMessage(`{"lang":"German","term":"Vater","gloss":"father"}`),
		AnswerGraph: puzzle.Graph{
			Nodes: []puzzle.Node{
				{ID: "English:father", Lang: "English", Term: "father", Role: "leaf"},
				{ID: "German:Vater", Lang: "German", Term: "Vater", Role: "leaf"},
				{ID: "Proto-Germanic:*fader", Lang: "Proto-Germanic", Term: "*fader", Gloss: &gloss, Role: "ancestor"},
			},
			Edges: []puzzle.Edge{
				{From: "English:father", To: "Proto-Germanic:*fader"},
				{From: "German:Vater", To: "Proto-Germanic:*fader"},
			},
		},
		Choices: []puzzle.Choice{
			{ID: "c0", Gloss: "a male parent"},
			{ID: "c1", Gloss: "a river"},
			{ID: "c2", Gloss: "to walk"},
			{ID: "c3", Gloss: "a stone"},
		},
		CorrectChoice: "c0",
		QualityScore:  5,
		LangPair:      "de-en",
		Source:        "etymology-db+kaikki",
	}
}

func fixtureHardPuzzle() *puzzle.Puzzle {
	gloss := "a male parent"
	p := fixturePuzzle()
	p.ID = "def456def456def456"
	p.AnswerGraph = puzzle.Graph{
		Nodes: []puzzle.Node{
			{ID: "English:father", Lang: "English", Term: "father", Role: "leaf"},
			{ID: "German:Vater", Lang: "German", Term: "Vater", Role: "leaf"},
			{ID: "Proto-Germanic:*fader", Lang: "Proto-Germanic", Term: "*fader", Gloss: &gloss, Role: "ancestor"},
			{ID: "Proto-Indo-European:*ph2ter", Lang: "Proto-Indo-European", Term: "*ph₂tḗr", Gloss: &gloss, Role: "ancestor"},
		},
		Edges: []puzzle.Edge{
			{From: "English:father", To: "Proto-Germanic:*fader"},
			{From: "German:Vater", To: "Proto-Germanic:*fader"},
			{From: "Proto-Germanic:*fader", To: "Proto-Indo-European:*ph2ter"},
		},
	}
	return p
}

func testHandler() http.Handler {
	return testHandlerWith(fixturePuzzle())
}

func TestRandomHardKeepsAncestorGloss(t *testing.T) {
	srv := httptest.NewServer(testHandlerWith(fixtureHardPuzzle()))
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/random?mode=hard")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var payload promptResponse
	if err := json.NewDecoder(res.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.PromptGraph == nil {
		t.Fatal("hard prompt should include promptGraph")
	}
	if len(payload.PromptGraph.Edges) != 0 {
		t.Fatal("hard prompt must omit edges")
	}
	foundAncestor := false
	for _, n := range payload.PromptGraph.Nodes {
		if n.Role == "ancestor" {
			foundAncestor = true
			if n.Gloss == nil || *n.Gloss != "a male parent" {
				t.Fatalf("ancestor gloss missing on %s, got %v", n.ID, n.Gloss)
			}
			if n.Term == "" {
				t.Fatal("ancestor term should remain for placement")
			}
		}
	}
	if !foundAncestor {
		t.Fatal("hard prompt should include ancestor nodes")
	}
	if len(payload.PromptGraph.Nodes) < minHardModeNodes {
		t.Fatalf("hard prompt should have at least %d nodes, got %d", minHardModeNodes, len(payload.PromptGraph.Nodes))
	}
}

func TestRandomHardRejectsFewerThanFourNodes(t *testing.T) {
	srv := httptest.NewServer(testHandlerWith(fixturePuzzle()))
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/random?mode=hard")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusNotFound {
		t.Fatalf("status %d", res.StatusCode)
	}
	var body map[string]string
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["error"] != "no enabled puzzles" {
		t.Fatalf("error %q", body["error"])
	}
}

func TestRandomHardServesFourNodePuzzleAmongSmallerOnes(t *testing.T) {
	small := fixturePuzzle()
	large := fixtureHardPuzzle()
	srv := httptest.NewServer(testHandlerWith(small, large))
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/random?mode=hard")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	var payload promptResponse
	if err := json.NewDecoder(res.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.ID != large.ID {
		t.Fatalf("id %q, want four-node puzzle %q", payload.ID, large.ID)
	}
	if payload.PromptGraph == nil || len(payload.PromptGraph.Nodes) < minHardModeNodes {
		t.Fatal("hard prompt should include at least four nodes")
	}
}

func TestGetHardRejectsFewerThanFourNodes(t *testing.T) {
	p := fixturePuzzle()
	srv := httptest.NewServer(testHandlerWith(p))
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/" + p.ID + "?mode=hard")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusNotFound {
		t.Fatalf("status %d", res.StatusCode)
	}
}

func TestGetHardServesFourNodePuzzle(t *testing.T) {
	p := fixtureHardPuzzle()
	srv := httptest.NewServer(testHandlerWith(p))
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/" + p.ID + "?mode=hard")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	var payload promptResponse
	if err := json.NewDecoder(res.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.PromptGraph == nil || len(payload.PromptGraph.Nodes) != 4 {
		t.Fatal("hard GET should return a four-node prompt graph")
	}
}

func TestRandomEasyHidesGold(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/random?mode=easy")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	body, _ := io.ReadAll(res.Body)
	raw := string(body)
	if strings.Contains(raw, "correctChoice") || strings.Contains(raw, "correct_choice") {
		t.Fatalf("GET leaked correct_choice: %s", raw)
	}
	if strings.Contains(raw, "Proto-Germanic:*fader") {
		t.Fatalf("easy GET leaked ancestor node: %s", raw)
	}

	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatal(err)
	}
	if _, ok := payload["promptGraph"]; ok {
		t.Fatalf("easy GET should omit promptGraph; leaves are leafA/leafB: %s", raw)
	}
}

func TestSolveEasy(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()
	id := fixturePuzzle().ID

	res, err := http.Post(srv.URL+"/puzzles/"+id+"/solve", "application/json", strings.NewReader(`{"mode":"easy","choiceId":"c0"}`))
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var got solveResponse
	if err := json.NewDecoder(res.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if !got.Correct {
		t.Fatal("expected correct easy solve")
	}
	if got.CorrectChoice != "c0" {
		t.Fatalf("gold choice %q", got.CorrectChoice)
	}
	if len(got.GoldGraph.Edges) != 2 {
		t.Fatalf("expected gold edges on solve, got %d", len(got.GoldGraph.Edges))
	}
}

func TestSolveHardEdgeSet(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()
	id := fixturePuzzle().ID
	body := `{"mode":"hard","edges":[{"from":"German:Vater","to":"Proto-Germanic:*fader"},{"from":"English:father","to":"Proto-Germanic:*fader"}]}`
	res, err := http.Post(srv.URL+"/puzzles/"+id+"/solve", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var got solveResponse
	if err := json.NewDecoder(res.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if !got.Correct {
		t.Fatal("expected matching edge set")
	}
}

func TestCORSPreflight(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()
	req, _ := http.NewRequest(http.MethodOptions, srv.URL+"/puzzles/random", nil)
	req.Header.Set("Origin", "http://localhost:5173")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusNoContent {
		t.Fatalf("status %d", res.StatusCode)
	}
	if got := res.Header.Get("Access-Control-Allow-Origin"); got != "http://localhost:5173" {
		t.Fatalf("cors origin %q", got)
	}
}

func TestGetPuzzleByID(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()
	id := fixturePuzzle().ID

	res, err := http.Get(srv.URL + "/puzzles/" + id + "?mode=easy")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	var payload promptResponse
	if err := json.NewDecoder(res.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.ID != id {
		t.Fatalf("id %q", payload.ID)
	}
	if payload.PromptGraph != nil {
		t.Fatal("easy GET by id should omit promptGraph")
	}
}

func TestGetPuzzleNotFound(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/missing-id?mode=hard")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusNotFound {
		t.Fatalf("status %d", res.StatusCode)
	}
	var body map[string]string
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["error"] != "puzzle not found" {
		t.Fatalf("error %q", body["error"])
	}
}

func TestHealthOKWithoutPostgres(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()

	res, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	var body map[string]string
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "ok" {
		t.Fatalf("body %+v", body)
	}
}

func TestInvalidMode(t *testing.T) {
	srv := httptest.NewServer(testHandler())
	defer srv.Close()
	res, err := http.Get(srv.URL + "/puzzles/random?mode=expert")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusBadRequest {
		t.Fatalf("status %d", res.StatusCode)
	}
}
