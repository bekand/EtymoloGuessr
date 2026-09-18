package puzzle

import (
	"encoding/json"
	"testing"
)

func sampleGraph() Graph {
	lcaGloss := "father"
	return Graph{
		Nodes: []Node{
			{ID: "English:father", Lang: "English", Term: "father", Role: "leaf"},
			{ID: "German:Vater", Lang: "German", Term: "Vater", Role: "leaf"},
			{ID: "Proto-Germanic:*fader", Lang: "Proto-Germanic", Term: "*fader", Gloss: &lcaGloss, Role: "ancestor"},
		},
		Edges: []Edge{
			{From: "English:father", To: "Proto-Germanic:*fader"},
			{From: "German:Vater", To: "Proto-Germanic:*fader"},
		},
	}
}

func TestParseMode(t *testing.T) {
	m, err := ParseMode("medium")
	if err != nil || m != ModeMedium {
		t.Fatalf("medium: %v %q", err, m)
	}
	if _, err := ParseMode("expert"); err == nil {
		t.Fatal("expert should be invalid")
	}
}

func TestModePolicy(t *testing.T) {
	hardFilter := (Filter{}).ForMode(ModeHard)
	if hardFilter.MinNodes == nil || *hardFilter.MinNodes != MinHardModeNodes {
		t.Fatalf("hard filter min nodes = %v, want %d", hardFilter.MinNodes, MinHardModeNodes)
	}
	if (Filter{}).ForMode(ModeEasy).MinNodes != nil {
		t.Fatal("easy filter should not set a minimum node count")
	}
	if EligibleForMode(&Puzzle{AnswerGraph: Graph{Nodes: make([]Node, MinHardModeNodes-1)}}, ModeHard) {
		t.Fatal("hard mode should reject a puzzle below the node threshold")
	}
	if !EligibleForMode(&Puzzle{AnswerGraph: Graph{Nodes: make([]Node, MinHardModeNodes)}}, ModeHard) {
		t.Fatal("hard mode should accept a puzzle at the node threshold")
	}
}

func TestPromptGraphEasyIsNil(t *testing.T) {
	if g := PromptGraph(sampleGraph(), ModeEasy); g != nil {
		t.Fatalf("easy prompt should be omitted, got %#v", g)
	}
}

func TestPromptGraphHardKeepsAncestorGloss(t *testing.T) {
	g := PromptGraph(sampleGraph(), ModeHard)
	if g == nil {
		t.Fatal("hard prompt should be present")
	}
	if len(g.Edges) != 0 {
		t.Fatalf("hard prompt must have no edges")
	}
	if len(g.Nodes) != 3 {
		t.Fatalf("hard prompt should keep all nodes, got %d", len(g.Nodes))
	}
	foundAncestor := false
	for _, n := range g.Nodes {
		if n.Role != "leaf" {
			foundAncestor = true
			if n.Gloss == nil || *n.Gloss != "father" {
				t.Fatalf("hard prompt should keep ancestor gloss on %s, got %v", n.ID, n.Gloss)
			}
			if n.Term == "" {
				t.Fatalf("hard prompt should keep ancestor term for placement")
			}
		}
	}
	if !foundAncestor {
		t.Fatal("hard prompt should include ancestor nodes")
	}
}

func TestEdgeSetsEqualIgnoresOrderAndReltype(t *testing.T) {
	rel := "inherited_from"
	gold := []Edge{
		{From: "a", To: "b", Reltype: &rel},
		{From: "c", To: "b"},
	}
	ok := []Edge{
		{From: "c", To: "b"},
		{From: " a ", To: "b"},
	}
	if !EdgeSetsEqual(gold, ok) {
		t.Fatal("expected matching directed edge sets")
	}
	wrong := []Edge{{From: "a", To: "b"}}
	if EdgeSetsEqual(gold, wrong) {
		t.Fatal("missing edge should not match")
	}
	reversed := []Edge{
		{From: "b", To: "a"},
		{From: "b", To: "c"},
	}
	if EdgeSetsEqual(gold, reversed) {
		t.Fatal("reversed edges should not match")
	}
}

func TestChoiceCorrect(t *testing.T) {
	p := &Puzzle{CorrectChoice: "c0"}
	if !ChoiceCorrect(p, "c0") {
		t.Fatal("expected correct")
	}
	if ChoiceCorrect(p, "c1") {
		t.Fatal("expected incorrect")
	}
	if ChoiceCorrect(nil, "c0") || ChoiceCorrect(p, "") {
		t.Fatal("nil puzzle or empty id should be incorrect")
	}
}

func TestPuzzleValidate(t *testing.T) {
	p := &Puzzle{
		ID:            "p1",
		LeafA:         json.RawMessage(`{"lang":"English","term":"father"}`),
		LeafB:         json.RawMessage(`{"lang":"German","term":"Vater"}`),
		AnswerGraph:   sampleGraph(),
		Choices:       []Choice{{ID: "c0", Gloss: "father"}},
		CorrectChoice: "c0",
	}
	if err := p.Validate(); err != nil {
		t.Fatalf("valid puzzle rejected: %v", err)
	}

	p.LeafA = json.RawMessage(`{"lang":"English"}`)
	if err := p.Validate(); err == nil {
		t.Fatal("invalid leaf should be rejected")
	}
}

func TestRootAncestor(t *testing.T) {
	t.Run("single root", func(t *testing.T) {
		term, ok := RootAncestor(sampleGraph())
		if !ok {
			t.Fatal("expected root")
		}
		if term.Lang != "Proto-Germanic" || term.Term != "*fader" {
			t.Fatalf("got %+v", term)
		}
	})
	t.Run("lowest id among roots", func(t *testing.T) {
		g := Graph{
			Nodes: []Node{
				{ID: "z-root", Lang: "Latin", Term: "z"},
				{ID: "a-root", Lang: "Latin", Term: "a"},
				{ID: "leaf", Lang: "English", Term: "x", Role: "leaf"},
			},
			Edges: []Edge{},
		}
		term, ok := RootAncestor(g)
		if !ok || term.Term != "a" {
			t.Fatalf("want lowest id root a, got ok=%v %+v", ok, term)
		}
	})
}

func TestPairSetsEqual(t *testing.T) {
	gold := [][2]string{{"a", "b"}, {"c", "d"}}
	ok := [][2]string{{"d", "c"}, {"b", "a"}}
	if !PairSetsEqual(gold, ok) {
		t.Fatal("unordered pairs should match")
	}
	wrong := [][2]string{{"a", "b"}, {"a", "c"}}
	if PairSetsEqual(gold, wrong) {
		t.Fatal("wrong pairing should not match")
	}
}

func TestLeafTokenOpaque(t *testing.T) {
	tok := LeafToken("abc123abc123abc123", "a")
	if tok == "" || len(tok) < 8 {
		t.Fatalf("token %q", tok)
	}
	if stringsHasPrefix(tok, "abc") {
		t.Fatalf("token should not expose puzzle id prefix: %q", tok)
	}
	if LeafToken("abc123abc123abc123", "a") != tok {
		t.Fatal("token should be stable")
	}
	if LeafToken("abc123abc123abc123", "b") == tok {
		t.Fatal("sides should differ")
	}
}

func stringsHasPrefix(s, prefix string) bool {
	return len(s) >= len(prefix) && s[:len(prefix)] == prefix
}

func TestMediumSetID(t *testing.T) {
	id := MediumSetID([]string{"c", "a", "d", "b"})
	if id != "a,b,c,d" {
		t.Fatalf("id %q", id)
	}
	parts, err := ParseMediumSetID(id)
	if err != nil {
		t.Fatal(err)
	}
	if len(parts) != 4 || parts[0] != "a" {
		t.Fatalf("parts %#v", parts)
	}
	if _, err := ParseMediumSetID("a,b"); err == nil {
		t.Fatal("short set should fail")
	}
}

func TestSelectDistinctLeaves(t *testing.T) {
	mk := func(id, aLang, aTerm, bLang, bTerm string) *Puzzle {
		a, _ := json.Marshal(Term{Lang: aLang, Term: aTerm})
		b, _ := json.Marshal(Term{Lang: bLang, Term: bTerm})
		return &Puzzle{ID: id, LeafA: a, LeafB: b}
	}
	cands := []*Puzzle{
		mk("1", "English", "father", "German", "Vater"),
		mk("2", "English", "father", "Spanish", "padre"),
		mk("3", "English", "hound", "German", "Hund"),
		mk("4", "English", "gift", "German", "Gift"),
		mk("5", "English", "house", "German", "Haus"),
	}
	picked := SelectDistinctLeaves(cands, 4)
	if len(picked) != 4 {
		t.Fatalf("picked %d", len(picked))
	}
	ids := map[string]bool{}
	for _, p := range picked {
		ids[p.ID] = true
	}
	if ids["2"] {
		t.Fatal("colliding puzzle should be skipped")
	}
}
