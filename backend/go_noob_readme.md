# Go notes for this backend

This is a guided tour of the Go used in `backend/`, assuming you are comfortable with Python (the ETL) and new to Go. It is not a general language tutorial; it explains *this* tree.

Pair with [README.md](README.md) for product/API docs.

## Mental model vs Python

| Python | Go here |
|---|---|
| `uv run etl` script + imported packages | One **module** (`go.mod`) compiled to a **single binary** (`cmd/api`) |
| Duck typing, exceptions | Static types; functions return `(value, error)` |
| `venv` + `pyproject.toml` | `go.mod` + `go.sum` (checksums of every dep) |
| FastAPI / Flask classes | `net/http` handlers: `func(w http.ResponseWriter, r *http.Request)` |
| `psycopg` | `pgx` (`github.com/jackc/pgx/v5`) |
| `pytest` discovers `test_*.py` | `go test` runs `*_test.go` next to the code |

There is no interpreter at runtime and no GIL. `go run ./cmd/api` compiles, then starts the process. `go build -o api ./cmd/api` leaves a binary you can copy (the Docker image is that binary plus almost nothing).

## Module, packages, `internal/`

`go.mod` starts with:

```
module github.com/bekand/EtymoGuessr/backend
go 1.24.0
```

The module path is the prefix of every import:

```go
import "github.com/bekand/EtymoGuessr/backend/internal/puzzle"
```

A **package** is a directory of `.go` files that share a `package name` line. All files in `internal/puzzle/` are `package puzzle`. You import the *directory path*, then use the *package name*: `puzzle.PromptGraph(...)`.

**`internal/` is enforced by the compiler.** Another module cannot import `github.com/bekand/EtymoGuessr/backend/internal/...`. Only this module can. That is why HTTP, DB, and scoring live there: they are not a public library.

**`cmd/api` is `package main`.** Only `main` packages produce executables, and they must have `func main()`. Library packages (`puzzle`, `db`, `api`) have no `main`.

## Exported names (the capital letter)

Go has no `public` keyword. If a type, func, or field starts with an **uppercase** letter, other packages can use it. Lowercase is private to the package (all files in that folder).

```go
type Puzzle struct {   // exported
    ID string          // exported JSON field
    enabled bool       // would be unexported if we named it that
}
func promptPayload(...)  // unexported: only package api
```

Python `self.foo` vs `_foo` is a convention; here the compiler enforces it.

## Pointers, values, `nil`

`*Puzzle` is a pointer (roughly a Python object reference). `Puzzle` as a parameter copies the struct. We return `*Puzzle` from the store so “not found” can be `nil` plus an error:

```go
var ErrNotFound = errors.New("puzzle not found")

func (s *Store) GetPuzzle(...) (*puzzle.Puzzle, error) {
    // ...
    return nil, puzzle.ErrNotFound
}
```

Callers use `errors.Is(err, puzzle.ErrNotFound)` (like catching a specific exception, but it is just a value).

`*string` on `Node.Gloss` distinguishes JSON `null` / missing from `""`. A non-pointer `string` cannot be null.

## Error handling

No exceptions. The usual pattern:

```go
p, err := s.store.RandomPuzzle(r.Context(), filter)
if err != nil {
    // handle
}
```

`fmt.Errorf("answer_graph: %w", err)` **wraps** the cause (`%w`) so `errors.Is` / `errors.As` still work. Ignoring `err` is how you get silent bugs; `go vet` will not always save you.

`os.Exit(1)` in `main` is for fatal startup (missing `DATABASE_URL`, cannot connect). Request handlers write HTTP status codes instead.

## `context.Context`

Almost every I/O function takes `ctx` first. It carries deadlines and cancel (client hung up, SIGTERM, timeout). Passing `r.Context()` from a handler means a cancelled HTTP request stops the SQL query.

`context.Background()` in `main` is the root context for process lifetime. Shutdown uses `context.WithTimeout(..., 10*time.Second)` so drain cannot hang forever.

## Interfaces (why `puzzle.Store` exists)

```go
type Store interface {
    RandomPuzzle(ctx context.Context, filter Filter) (*Puzzle, error)
    GetPuzzle(ctx context.Context, id string) (*Puzzle, error)
}
```

**No `implements` keyword.** `db.Store` satisfies this because it has those methods. Tests fake it with `memStore` in `server_test.go` — same idea as a Python Protocol / duck-typed mock, but checked at compile time when you pass it to `api.New`.

Small interfaces (two methods) are idiomatic. Do not make a 20-method “IDatabase”.

## Methods and receivers

```go
func (s *Store) GetPuzzle(...) (*puzzle.Puzzle, error)
```

`(s *Store)` is a **pointer receiver**: the method is on `*Store`, can use `s.pool`. Value receivers copy; we use pointers for anything with a pool/mux inside.

`api.Server` implements `http.Handler` by defining:

```go
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request)
```

`http.Server.Handler` only needs that method. That is how we pass `handler` into `ListenAndServe`.

## HTTP (stdlib, Go 1.22 routes)

No Chi/Gin in v1. `http.NewServeMux()` plus method+path patterns:

```go
mux.HandleFunc("GET /puzzles/random", s.handleRandom)
mux.HandleFunc("POST /puzzles/{id}/solve", s.handleSolve)
id := r.PathValue("id")
```

A handler writes to `http.ResponseWriter` and reads `*http.Request`. JSON:

```go
json.NewEncoder(w).Encode(body)           // response
json.NewDecoder(r.Body).Decode(&req)      // request
```

Struct **tags** map Go fields to JSON keys:

```go
ChoiceID string `json:"choiceId"`
```

The HTTP envelope is camelCase (`leafA`, `goldGraph`). Nested graph objects keep ETL names (`from` / `to`) because those blobs are stored that way in JSONB.

Middleware is just wrapping `http.Handler`: `withCORS` returns a function that sets headers, handles `OPTIONS`, then calls `next.ServeHTTP`.

## Goroutines and shutdown

```go
go func() {
    httpSrv.ListenAndServe()
}()
```

`go f()` starts a concurrent function (a goroutine). The listener blocks, so it runs in the background while `main` waits on `SIGINT`/`SIGTERM` via `signal.Notify`. Then `Shutdown` stops accepting connections.

You do not `thread.join` the same way; the process exits when `main` returns.

## `defer`

```go
defer pool.Close()
defer res.Body.Close()  // in tests
```

`defer` runs when the surrounding function returns, LIFO. Use it for Close/Release so you do not leak on every error return. In `Migrate`, `conn.Release()` is called explicitly on each path because the acquire lives inside a loop (a deferred Release in the loop would pile up until `Migrate` returns).

## Generics: we barely use them

`make([]Node, 0, len(answer.Nodes))` pre-allocates a slice. Slices are the default list type (`[]Edge`). Maps are `map[string]bool` for the edge-set compare. No Python `set`; a map to `bool` or `struct{}` is the usual set.

## Embedding SQL (`go:embed`)

```go
//go:embed migrations/*.sql
var migrationsFS embed.FS
```

The compiler stuffs those files into the binary. Production Docker image has **no** filesystem copy of the `.sql` files at runtime; they live inside `/api`. Paths in `embed` are relative to the Go file (`internal/db/migrations/`).

`upSection` strips `-- +goose Up/Down` so we can keep familiar markers without importing the goose library (which pulls extra database drivers).

`pgx.QueryExecModeSimpleProtocol` is required for a migration file that contains **multiple** SQL statements. The default protocol prepares one statement and Postgres rejects `;`-separated batches.

## pgx vs `database/sql`

`pgxpool.Pool` is a connection pool typed for Postgres. `QueryRow` + `Scan` fills Go variables. JSONB columns are scanned into `[]byte` or `json.RawMessage` then `json.Unmarshal` into structs.

Placeholders are `$1`, `$2` (Postgres), never `%s` and never Python-style f-strings.

`filter.MinQuality *int` lets SQL see SQL `NULL` when the query param is omitted (`$2::int IS NULL OR quality_score >= $2`). A plain `int` cannot be null.

## Tests

Files named `foo_test.go` with `package puzzle` (or `package api`) are compiled **only** for `go test`.

```go
func TestEdgeSetsEqualIgnoresOrderAndReltype(t *testing.T) {
    if !EdgeSetsEqual(gold, ok) {
        t.Fatal("...")
    }
}
```

`t.Fatal` fails the test immediately. `httptest.NewServer(handler)` binds a random port and we `http.Get` it — still no real Postgres.

Run:

```bash
go test ./...                 # every package under backend/
go test -v ./internal/puzzle  # one package, verbose
go test -run TestSolveHard ./internal/api
```

`go test` caches passing results (`(cached)` in the output). Change a `.go` file or use `-count=1` to force a rerun.

## Everyday commands

Run from `backend/` (the directory that contains `go.mod`):

| Command | What |
|---|---|
| `go run ./cmd/api` | Compile in memory and start the server |
| `go build -o api.exe ./cmd/api` | Write a binary (`api.exe` on Windows) |
| `go test ./...` | All tests |
| `go mod tidy` | Add/remove deps to match imports; refresh `go.sum` |
| `go fmt ./...` | Canonical formatting (tabs, not a style debate) |
| `go vet ./...` | Static checks |

`./cmd/api` is a path relative to the module, not a shell glob. The `.` means “this module”.

After you change imports, run `go mod tidy` so `go.sum` stays in git. Never hand-edit `go.sum`.

## Docker build (why two stages)

1. `golang:1.24-bookworm` compiles with `CGO_ENABLED=0` (pure Go, no C toolchain) to a static binary.
2. `distroless/static` copies **only** that binary. No shell, no Python, no migration files on disk.

`EXPOSE 8080` is documentation; Compose maps the port. `USER nonroot` is so the process does not run as root.

## Config

Go has no constructor magic. `config.FromEnv()` reads `os.Getenv` once at boot. Changing env vars requires a restart.

`HTTP_ADDR` is `:8080` (all interfaces, port 8080), not `8080`. That is the `net` package’s address form (`host:port`; empty host = all).

## If something feels missing

- **No classes / inheritance.** Structs + interfaces. Share behavior by embedding or by passing interfaces.
- **No default parameter values.** Use zero values (`""`, `0`, `nil`) or option structs (`Filter`).
- **Zero value of a slice is `nil`.** `json` encodes `nil` slices as `null` and empty slices as `[]`. Prompt graphs always use `[]Edge{}` so clients get `[]`.
- **Package-level `var ErrNotFound`.** Sentinel errors are comparable; do not compare `err.Error()` strings.

When in doubt, grep this module for a name, then read the test with the same prefix (`TestPromptGraphHard...` documents the intended leak-prevention).
