package catalog

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
)

func LoadFile(path string) (*MemoryStore, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("catalog: open %s: %w", path, err)
	}
	defer f.Close()
	return Load(f)
}

func LoadBytes(data []byte) (*MemoryStore, error) {
	return Load(bytes.NewReader(data))
}

func Load(r io.Reader) (*MemoryStore, error) {
	scanner := bufio.NewScanner(r)
	// Graphs can be a few hundred KB per line; 4 MiB is plenty.
	scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
	var puzzles []*puzzle.Puzzle
	lineNo := 0
	for scanner.Scan() {
		lineNo++
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var raw map[string]json.RawMessage
		if err := json.Unmarshal([]byte(line), &raw); err != nil {
			return nil, fmt.Errorf("catalog: line %d: %w", lineNo, err)
		}
		if _, ok := raw["prompt_graph"]; ok {
			return nil, fmt.Errorf("catalog: line %d: prompt_graph is not stored; derive at serve time", lineNo)
		}
		var p puzzle.Puzzle
		if err := json.Unmarshal([]byte(line), &p); err != nil {
			return nil, fmt.Errorf("catalog: line %d: %w", lineNo, err)
		}
		if p.ID == "" {
			return nil, fmt.Errorf("catalog: line %d: missing id", lineNo)
		}
		puzzles = append(puzzles, &p)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("catalog: read: %w", err)
	}
	return NewMemoryStore(puzzles)
}
