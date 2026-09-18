package puzzle

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
)

var ErrNotFound = errors.New("puzzle not found")

type Mode string

const (
	ModeEasy   Mode = "easy"
	ModeHard   Mode = "hard"
	ModeMedium Mode = "medium"
)

const MediumSetSize = 4

func ParseMode(s string) (Mode, error) {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "", "easy":
		return ModeEasy, nil
	case "hard":
		return ModeHard, nil
	case "medium":
		return ModeMedium, nil
	default:
		return "", fmt.Errorf("mode must be easy, hard, or medium")
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
	ExcludeIDs []string
}

const MinHardModeNodes = 4

func (f Filter) ForMode(mode Mode) Filter {
	if mode == ModeHard {
		n := MinHardModeNodes
		f.MinNodes = &n
	}
	return f
}

func (f Filter) WithoutExclusions() Filter {
	f.ExcludeIDs = nil
	return f
}

type Store interface {
	RandomPuzzle(ctx context.Context, filter Filter) (*Puzzle, error)
	RandomPuzzles(ctx context.Context, filter Filter, n int) ([]*Puzzle, error)
	GetPuzzle(ctx context.Context, id string) (*Puzzle, error)
	GetPuzzles(ctx context.Context, ids []string) ([]*Puzzle, error)
}

func (p *Puzzle) Validate() error {
	if p == nil {
		return errors.New("puzzle is nil")
	}
	if strings.TrimSpace(p.ID) == "" {
		return errors.New("puzzle id is missing")
	}
	if _, err := DecodeTerm(p.LeafA); err != nil {
		return fmt.Errorf("leaf_a: %w", err)
	}
	if _, err := DecodeTerm(p.LeafB); err != nil {
		return fmt.Errorf("leaf_b: %w", err)
	}
	if len(p.AnswerGraph.Nodes) == 0 {
		return errors.New("answer graph has no nodes")
	}
	nodeIDs := make(map[string]struct{}, len(p.AnswerGraph.Nodes))
	for _, node := range p.AnswerGraph.Nodes {
		if strings.TrimSpace(node.ID) == "" || strings.TrimSpace(node.Lang) == "" || strings.TrimSpace(node.Term) == "" {
			return errors.New("answer graph contains an incomplete node")
		}
		nodeIDs[node.ID] = struct{}{}
	}
	for _, edge := range p.AnswerGraph.Edges {
		if _, ok := nodeIDs[edge.From]; !ok {
			return fmt.Errorf("answer graph edge references unknown node %q", edge.From)
		}
		if _, ok := nodeIDs[edge.To]; !ok {
			return fmt.Errorf("answer graph edge references unknown node %q", edge.To)
		}
	}
	if len(p.Choices) == 0 {
		return errors.New("puzzle has no choices")
	}
	choiceIDs := make(map[string]struct{}, len(p.Choices))
	for _, choice := range p.Choices {
		if strings.TrimSpace(choice.ID) == "" {
			return errors.New("puzzle contains a choice without an id")
		}
		choiceIDs[choice.ID] = struct{}{}
	}
	if _, ok := choiceIDs[p.CorrectChoice]; !ok {
		return fmt.Errorf("correct choice %q is not present", p.CorrectChoice)
	}
	return nil
}

func EligibleForMode(p *Puzzle, mode Mode) bool {
	if p == nil {
		return false
	}
	return mode != ModeHard || len(p.AnswerGraph.Nodes) >= MinHardModeNodes
}

func PromptGraph(answer Graph, mode Mode) *Graph {
	if mode != ModeHard {
		return nil
	}
	nodes := make([]Node, len(answer.Nodes))
	copy(nodes, answer.Nodes)
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

func ChoiceCorrect(p *Puzzle, choiceID string) bool {
	return p != nil && choiceID != "" && choiceID == p.CorrectChoice
}

// LeafToken returns an opaque id for one side of a puzzle so the client cannot
// recover the cognate grouping from token prefixes.
func LeafToken(puzzleID, side string) string {
	sum := sha256.Sum256([]byte(puzzleID + "\x00" + side))
	return hex.EncodeToString(sum[:8])
}

func DecodeTerm(raw json.RawMessage) (Term, error) {
	var t Term
	if err := json.Unmarshal(raw, &t); err != nil {
		return Term{}, err
	}
	t.Lang = strings.TrimSpace(t.Lang)
	t.Term = strings.TrimSpace(t.Term)
	if t.Lang == "" || t.Term == "" {
		return Term{}, fmt.Errorf("term missing lang or term")
	}
	return t, nil
}

func LeafKey(t Term) string {
	return t.Lang + "\x00" + t.Term
}

// RootAncestor returns the unique answer-graph node with out-degree 0.
// If several roots exist, the lowest id wins so feedback stays deterministic.
func RootAncestor(g Graph) (Term, bool) {
	outgoing := make(map[string]bool, len(g.Edges))
	for _, e := range g.Edges {
		from := strings.TrimSpace(e.From)
		if from != "" {
			outgoing[from] = true
		}
	}
	var roots []Node
	for _, n := range g.Nodes {
		if !outgoing[n.ID] {
			roots = append(roots, n)
		}
	}
	if len(roots) == 0 {
		return Term{}, false
	}
	sort.Slice(roots, func(i, j int) bool { return roots[i].ID < roots[j].ID })
	n := roots[0]
	return Term{Lang: n.Lang, Term: n.Term, Gloss: n.Gloss}, true
}

func PairKey(a, b string) string {
	a = strings.TrimSpace(a)
	b = strings.TrimSpace(b)
	if a > b {
		a, b = b, a
	}
	return a + "\x00" + b
}

func PairSetsEqual(gold, submitted [][2]string) bool {
	want := make(map[string]bool, len(gold))
	for _, p := range gold {
		if strings.TrimSpace(p[0]) == "" || strings.TrimSpace(p[1]) == "" {
			continue
		}
		want[PairKey(p[0], p[1])] = true
	}
	got := make(map[string]bool, len(submitted))
	for _, p := range submitted {
		if strings.TrimSpace(p[0]) == "" || strings.TrimSpace(p[1]) == "" {
			continue
		}
		got[PairKey(p[0], p[1])] = true
	}
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

func MediumSetID(ids []string) string {
	sorted := append([]string(nil), ids...)
	sort.Strings(sorted)
	return strings.Join(sorted, ",")
}

func ParseMediumSetID(id string) ([]string, error) {
	parts := strings.Split(id, ",")
	if len(parts) != MediumSetSize {
		return nil, fmt.Errorf("medium set id must contain %d puzzle ids", MediumSetSize)
	}
	out := make([]string, 0, MediumSetSize)
	seen := make(map[string]bool, MediumSetSize)
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			return nil, fmt.Errorf("medium set id has empty puzzle id")
		}
		if seen[p] {
			return nil, fmt.Errorf("medium set id has duplicate puzzle id")
		}
		seen[p] = true
		out = append(out, p)
	}
	return out, nil
}

// ShuffleByID is a deterministic Fisher–Yates variant matching frontend shuffle().
func ShuffleByID[T any](items []T, id string) []T {
	next := append([]T(nil), items...)
	seed := firstDigitInID(id)
	for i := len(next) - 1; i > 0; i-- {
		j := seed % (i + 1)
		next[i], next[j] = next[j], next[i]
	}
	return next
}

// SelectDistinctLeaves greedily keeps puzzles whose (lang,term) leaves do not collide.
func SelectDistinctLeaves(candidates []*Puzzle, n int) []*Puzzle {
	if n <= 0 {
		return nil
	}
	picked := make([]*Puzzle, 0, n)
	used := make(map[string]bool)
	for _, p := range candidates {
		if p == nil {
			continue
		}
		a, errA := DecodeTerm(p.LeafA)
		b, errB := DecodeTerm(p.LeafB)
		if errA != nil || errB != nil {
			continue
		}
		ka, kb := LeafKey(a), LeafKey(b)
		if ka == kb || used[ka] || used[kb] {
			continue
		}
		used[ka] = true
		used[kb] = true
		picked = append(picked, p)
		if len(picked) == n {
			return picked
		}
	}
	return nil
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

// firstDigitInID matches the frontend shuffle seed (first digit in the id, else 0).
func firstDigitInID(id string) int {
	for _, r := range id {
		if r >= '0' && r <= '9' {
			return int(r - '0')
		}
	}
	return 0
}
