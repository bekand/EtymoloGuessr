package catalog

import _ "embed"

// EmbeddedJSONL is the production puzzle snapshot baked into the API binary.
// Replace puzzles.jsonl with a full generate (`uv run etl generate --jsonl …`)
// and rebuild to update the catalog.
//
//go:embed puzzles.jsonl
var EmbeddedJSONL []byte
