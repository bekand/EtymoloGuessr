package puzzle

import "testing"

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

func TestPromptGraphEasyIsNil(t *testing.T) {
	if g := PromptGraph(sampleGraph(), ModeEasy); g != nil {
		t.Fatalf("easy prompt should be omitted, got %#v", g)
	}
}

func TestPromptGraphHardStripsAncestorGloss(t *testing.T) {
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
	for _, n := range g.Nodes {
		if n.Role != "leaf" && n.Gloss != nil {
			t.Fatalf("hard prompt leaked ancestor gloss on %s", n.ID)
		}
		if n.Role != "leaf" && n.Term == "" {
			t.Fatalf("hard prompt should keep ancestor term for placement")
		}
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
