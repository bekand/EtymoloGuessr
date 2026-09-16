package puzzle

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

var ErrNotFound = errors.New("puzzle not found")

type Mode string

const (
	ModeEasy Mode = "easy"
	ModeHard Mode = "hard"
)

func ParseMode(s string) (Mode, error) {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "", "easy":
		return ModeEasy, nil
	case "hard":
		return ModeHard, nil
	default:
		return "", fmt.Errorf("mode must be easy or hard")
	}
}

type Term struct {
	Lang  string  `json:"lang"`
	Term  string  `json:"term"`
	Gloss *string `json:"gloss,omitempty"`
}

type Choice struct {
	ID    string `json:"id"`
	Gloss string `json:"gloss"`
}

type Node struct {
	ID    string  `json:"id"`
	Lang  string  `json:"lang"`
	Term  string  `json:"term"`
	Gloss *string `json:"gloss"`
	Role  string  `json:"role"`
}

type Edge struct {
	From    string  `json:"from"`
	To      string  `json:"to"`
	Reltype *string `json:"reltype,omitempty"`
}

type Graph struct {
	Nodes []Node `json:"nodes"`
	Edges []Edge `json:"edges"`
}

type Puzzle struct {
	ID            string          `json:"id"`
	Enabled       bool            `json:"enabled"`
	LeafA         json.RawMessage `json:"leaf_a"`
	LeafB         json.RawMessage `json:"leaf_b"`
	AnswerGraph   Graph           `json:"answer_graph"`
	Choices       []Choice        `json:"choices"`
	CorrectChoice string          `json:"correct_choice"`
	QualityScore  int             `json:"quality_score"`
	LangPair      string          `json:"lang_pair"`
	Source        string          `json:"source"`
}

type Filter struct {
	LangPair   string
	MinQuality *int
	MinNodes   *int
}

type Store interface {
	RandomPuzzle(ctx context.Context, filter Filter) (*Puzzle, error)
	GetPuzzle(ctx context.Context, id string) (*Puzzle, error)
}

func PromptGraph(answer Graph, mode Mode) *Graph {
	if mode != ModeHard {
		return nil
	}
	nodes := make([]Node, 0, len(answer.Nodes))
	for _, n := range answer.Nodes {
		node := n
		if node.Role != "leaf" {
			node.Gloss = nil
		}
		nodes = append(nodes, node)
	}
	return &Graph{Nodes: nodes, Edges: []Edge{}}
}

func EdgeSetsEqual(gold, submitted []Edge) bool {
	want := edgeSet(gold)
	got := edgeSet(submitted)
	if len(want) != len(got) {
		return false
	}
	for k := range want {
		if !got[k] {
			return false
		}
	}
	return true
}

func edgeSet(edges []Edge) map[string]bool {
	out := make(map[string]bool, len(edges))
	for _, e := range edges {
		from := strings.TrimSpace(e.From)
		to := strings.TrimSpace(e.To)
		if from == "" || to == "" {
			continue
		}
		out[from+"\x00"+to] = true
	}
	return out
}

func ChoiceCorrect(p *Puzzle, choiceID string) bool {
	return p != nil && choiceID != "" && choiceID == p.CorrectChoice
}
