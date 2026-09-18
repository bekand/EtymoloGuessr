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

func fixtureMediumPuzzles() []*puzzle.Puzzle {
	mk := func(id, aLang, aTerm, bLang, bTerm, ancLang, ancTerm, gloss string) *puzzle.Puzzle {
		return &puzzle.Puzzle{
			ID:      id,
			Enabled: true,
			LeafA:   json.RawMessage(`{"lang":"` + aLang + `","term":"` + aTerm + `"}`),
			LeafB:   json.RawMessage(`{"lang":"` + bLang + `","term":"` + bTerm + `"}`),
			AnswerGraph: puzzle.Graph{
				Nodes: []puzzle.Node{
					{ID: aLang + ":" + aTerm, Lang: aLang, Term: aTerm, Role: "leaf"},
					{ID: bLang + ":" + bTerm, Lang: bLang, Term: bTerm, Role: "leaf"},
					{ID: ancLang + ":" + ancTerm, Lang: ancLang, Term: ancTerm, Gloss: &gloss, Role: "ancestor"},
				},
				Edges: []puzzle.Edge{
					{From: aLang + ":" + aTerm, To: ancLang + ":" + ancTerm},
					{From: bLang + ":" + bTerm, To: ancLang + ":" + ancTerm},
				},
			},
			Choices:       []puzzle.Choice{{ID: "c0", Gloss: gloss}},
			CorrectChoice: "c0",
			QualityScore:  5,
			LangPair:      "de-en",
			Source:        "test",
		}
	}
	return []*puzzle.Puzzle{
		mk("m11111111111111111", "English", "father", "German", "Vater", "Proto-Germanic", "*fader", "a male parent"),
		mk("m22222222222222222", "English", "hound", "German", "Hund", "Proto-Germanic", "*hundaz", "a dog"),
		mk("m33333333333333333", "English", "gift", "German", "Gift", "Proto-Germanic", "*giftiz", "something given"),
		mk("m44444444444444444", "English", "house", "German", "Haus", "Proto-Germanic", "*hūsą", "a dwelling"),
	}
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
	if len(payload.PromptGraph.Nodes) < puzzle.MinHardModeNodes {
		t.Fatalf("hard prompt should have at least %d nodes, got %d", puzzle.MinHardModeNodes, len(payload.PromptGraph.Nodes))
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
	if payload.PromptGraph == nil || len(payload.PromptGraph.Nodes) < puzzle.MinHardModeNodes {
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

	easy := fixturePuzzle()
	hard := fixtureHardPuzzle()
	hard2 := fixtureHardPuzzle()
	hard2.ID = "ghi789ghi789ghi789"
	srv2 := httptest.NewServer(testHandlerWith(easy, hard, hard2))
	defer srv2.Close()
	for i := 0; i < 20; i++ {
		res2, err := http.Get(srv2.URL + "/puzzles/random?mode=hard&exclude=" + hard.ID)
		if err != nil {
			t.Fatal(err)
		}
		if res2.StatusCode != http.StatusOK {
			res2.Body.Close()
			t.Fatalf("status %d", res2.StatusCode)
		}
		var got promptResponse
		if err := json.NewDecoder(res2.Body).Decode(&got); err != nil {
			res2.Body.Close()
			t.Fatal(err)
		}
		res2.Body.Close()
		if got.ID == hard.ID {
			t.Fatalf("exclude ignored, got %q", got.ID)
		}
		if got.ID != hard2.ID {
			t.Fatalf("got %q want %q", got.ID, hard2.ID)
		}
	}
	for i := 0; i < 15; i++ {
		res2, err := http.Get(srv2.URL + "/puzzles/random?mode=easy&exclude=" + hard.ID + "," + hard2.ID)
		if err != nil {
			t.Fatal(err)
		}
		if res2.StatusCode != http.StatusOK {
			res2.Body.Close()
			t.Fatalf("status %d", res2.StatusCode)
		}
		var got promptResponse
		if err := json.NewDecoder(res2.Body).Decode(&got); err != nil {
			res2.Body.Close()
			t.Fatal(err)
		}
		res2.Body.Close()
		if got.ID != easy.ID {
			t.Fatalf("got %q want %q", got.ID, easy.ID)
		}
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
	if got.GoldGraph == nil || len(got.GoldGraph.Edges) != 2 {
		t.Fatalf("expected gold edges on solve, got %#v", got.GoldGraph)
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

func TestRandomMediumReturnsEightLeaves(t *testing.T) {
	set := fixtureMediumPuzzles()
	srv := httptest.NewServer(testHandlerWith(set...))
	defer srv.Close()

	res, err := http.Get(srv.URL + "/puzzles/random?mode=medium")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	body, _ := io.ReadAll(res.Body)
	raw := string(body)
	if strings.Contains(raw, "leafA") || strings.Contains(raw, "leafB") || strings.Contains(raw, "correctChoice") {
		t.Fatalf("medium GET leaked pairing fields: %s", raw)
	}
	var payload mediumPromptResponse
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatal(err)
	}
	if payload.Mode != puzzle.ModeMedium {
		t.Fatalf("mode %q", payload.Mode)
	}
	if len(payload.Leaves) != 8 {
		t.Fatalf("leaves %d", len(payload.Leaves))
	}
	ids := strings.Split(payload.ID, ",")
	if len(ids) != 4 {
		t.Fatalf("set id %q", payload.ID)
	}
	for _, leaf := range payload.Leaves {
		for _, pid := range ids {
			if strings.HasPrefix(leaf.ID, pid) || leaf.ID == pid {
				t.Fatalf("opaque leaf id %q exposes puzzle id %q", leaf.ID, pid)
			}
		}
	}
}

func TestGetMediumBySetID(t *testing.T) {
	set := fixtureMediumPuzzles()
	srv := httptest.NewServer(testHandlerWith(set...))
	defer srv.Close()

	setID := puzzle.MediumSetID([]string{set[0].ID, set[1].ID, set[2].ID, set[3].ID})
	res, err := http.Get(srv.URL + "/puzzles/" + setID + "?mode=medium")
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("status %d", res.StatusCode)
	}
	var payload mediumPromptResponse
	if err := json.NewDecoder(res.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.ID != setID {
		t.Fatalf("id %q want %q", payload.ID, setID)
	}
	if len(payload.Leaves) != 8 {
		t.Fatalf("leaves %d", len(payload.Leaves))
	}
}

func TestSolveMedium(t *testing.T) {
	set := fixtureMediumPuzzles()
	srv := httptest.NewServer(testHandlerWith(set...))
	defer srv.Close()
	setID := puzzle.MediumSetID([]string{set[0].ID, set[1].ID, set[2].ID, set[3].ID})

	correctPairs := make([][]string, 0, 4)
	for _, p := range set {
		correctPairs = append(correctPairs, []string{
			puzzle.LeafToken(p.ID, "a"),
			puzzle.LeafToken(p.ID, "b"),
		})
	}
	body, _ := json.Marshal(map[string]any{"mode": "medium", "pairs": correctPairs})
	res, err := http.Post(srv.URL+"/puzzles/"+setID+"/solve", "application/json", strings.NewReader(string(body)))
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var got solveResponse
	if err := json.NewDecoder(res.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}
	if !got.Correct {
		t.Fatal("expected correct medium solve")
	}
	if len(got.Ancestors) != 4 {
		t.Fatalf("ancestors %d", len(got.Ancestors))
	}
	if got.GoldGraph != nil {
		t.Fatal("medium solve should omit goldGraph")
	}

	wrong := [][]string{
		{puzzle.LeafToken(set[0].ID, "a"), puzzle.LeafToken(set[1].ID, "a")},
		{puzzle.LeafToken(set[0].ID, "b"), puzzle.LeafToken(set[1].ID, "b")},
		{puzzle.LeafToken(set[2].ID, "a"), puzzle.LeafToken(set[2].ID, "b")},
		{puzzle.LeafToken(set[3].ID, "a"), puzzle.LeafToken(set[3].ID, "b")},
	}
	wrongBody, _ := json.Marshal(map[string]any{"mode": "medium", "pairs": wrong})
	res2, err := http.Post(srv.URL+"/puzzles/"+setID+"/solve", "application/json", strings.NewReader(string(wrongBody)))
	if err != nil {
		t.Fatal(err)
	}
	defer res2.Body.Close()
	var gotWrong solveResponse
	if err := json.NewDecoder(res2.Body).Decode(&gotWrong); err != nil {
		t.Fatal(err)
	}
	if gotWrong.Correct {
		t.Fatal("mismatched pairs should be incorrect")
	}
}
