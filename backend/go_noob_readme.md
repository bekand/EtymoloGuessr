# Go notes for this backend

This is a guided tour of the Go used in `backend/`, assuming you are comfortable with the Vite/React TypeScript frontend and new to Go. It is not a general language tutorial; it explains *this* tree.

Pair with [README.md](README.md) for product/API docs.

## Mental model vs TypeScript

| TypeScript / Node | Go here |
|---|---|
| `pnpm dev` + `tsc` / Vite, then Node or the browser | One **module** (`go.mod`) compiled to a **single native binary** (`cmd/api`) |
| Types erased at compile; runtime is still JS (`null`, `undefined`, thrown `Error`) | Types exist only at compile too, but there is no JS leftover. Functions return `(value, error)` instead of throwing |
| `package.json` + lockfile + `node_modules` | `go.mod` + `go.sum` (checksums of every dep). No `node_modules` directory to copy around |
| Express / Hono / `fetch` `Request` | `net/http` handlers: `func(w http.ResponseWriter, r *http.Request)` |
| `pg` / `postgres.js` / Prisma | `pgx` (`github.com/jackc/pgx/v5`) |
| Vitest/Jest pick up `*.test.ts` | `go test` runs `*_test.go` next to the code |

There is no `node` / V8 at runtime. `go run ./cmd/api` compiles, then starts the process. `go build -o api ./cmd/api` leaves a binary you can copy (the Docker image is that binary plus almost nothing — no `node_modules`, no `dist/`).

## Module, packages, `internal/`

`go.mod` starts with:

```
module github.com/bekand/EtymoloGuessr/backend
go 1.24.0
```

The module path is the prefix of every import, like a scoped npm name that is also a URL:

```go
import "github.com/bekand/EtymoloGuessr/backend/internal/puzzle"
```

A **package** is a directory of `.go` files that share a `package name` line. All files in `internal/puzzle/` are `package puzzle`. You import the *directory path*, then use the *package name*: `puzzle.PromptGraph(...)`.

This is the biggest module-system shock coming from TS. **Each `.ts` file is its own module** with its own imports. **All `.go` files in one folder are one namespace.** `puzzle.go` can call `firstDigitInID` from the same folder without importing it. Tests in `puzzle_test.go` sit in that same package (unless they use `package puzzle_test`).

**`internal/` is enforced by the compiler.** Another module cannot import `github.com/bekand/EtymoloGuessr/backend/internal/...`. Only this module can. That is why HTTP, DB, and scoring live there: they are not a public library. TS `src/` is only a convention.

**`cmd/api` is `package main`.** Only `main` packages produce executables, and they must have `func main()`. That is the `index.ts` / `bin` entrypoint. Library packages (`puzzle`, `db`, `api`) have no `main`.

## Exported names (the capital letter)

Go has no `export` keyword. If a type, func, or field starts with an **uppercase** letter, other packages can use it. Lowercase is visible to every file in the same package, but not outside it.

```go
type Puzzle struct {   // exported  — like `export type Puzzle`
    ID string          // exported JSON field
    enabled bool       // would be unexported if we named it that
}
func promptPayload(...)  // unexported: only package api
```

In TS, omitting `export` makes a binding **file-private**. In Go, a lowercase name is **package-private** (the whole folder). `export` vs nothing is a convention plus bundler rules; here the compiler enforces the capital letter.

JSON tags are independent of export. An exported field can still serialize as camelCase: `` ChoiceID string `json:"choiceId"` ``.

## Pointers, values, `nil`

In TS, objects and arrays are always references; `string` / `number` / `boolean` copy. In Go, **structs copy unless you take a pointer.** Passing `Puzzle` into a function copies every field. `*Puzzle` is a pointer (the closest thing to “an object reference”).

We return `*Puzzle` from the store so “not found” can be `nil` plus an error:

```go
var ErrNotFound = errors.New("puzzle not found")

func (s *Store) GetPuzzle(...) (*puzzle.Puzzle, error) {
    // ...
    return nil, puzzle.ErrNotFound
}
```

`nil` is Go’s `null`. There is **no `undefined`**. Pointers, slices, maps, interfaces, and channels can be `nil`; a plain `string` cannot.

Callers use `errors.Is(err, puzzle.ErrNotFound)` — like checking `err instanceof NotFound` / `err.code === "ENOENT"`, except the sentinel is a value, not a class.

`*string` on `Term.Gloss` and `Node.Gloss` is the same idea as `gloss?: string | null` in `frontend/src/api/types.ts`. A non-pointer `string` cannot be null; missing and `""` would collapse. `Choice.Gloss` stays `string` because every choice is a required meaning.

Pointer when the zero value (`""`, `0`, `false`) is real data and you still need “not present.” Value when the field is required or the zero already means none.

## Error handling

No `throw` / `try/catch` on the happy path. The usual pattern is a TypeScript `Result` that you actually have to unwrap:

```ts
const p = await store.randomPuzzle(filter) // might throw
```

```go
p, err := s.store.RandomPuzzle(r.Context(), filter)
if err != nil {
    // handle
}
```

`fmt.Errorf("answer_graph: %w", err)` **wraps** the cause (`%w`) so `errors.Is` / `errors.As` still work — like `cause:` on a thrown `Error`, but explicit. Ignoring `err` is how you get silent bugs; `go vet` will not always save you.

`os.Exit(1)` in `main` is for fatal startup (cannot open Postgres or JSONL catalog). Request handlers write HTTP status codes instead of throwing into an Express error middleware.

## `context.Context`

Almost every I/O function takes `ctx` first. It is `AbortSignal` passed as a required argument: deadlines, cancel (client hung up, SIGTERM, timeout). Passing `r.Context()` from a handler means a cancelled HTTP request stops the SQL query — the same reason `fetch(url, { signal })` exists.

`context.Background()` in `main` is the root context for process lifetime (`new AbortController()` that nobody aborts until shutdown). Shutdown uses `context.WithTimeout(..., 10*time.Second)` so drain cannot hang forever.

## Interfaces (why `puzzle.Store` exists)

```go
type Store interface {
    RandomPuzzle(ctx context.Context, filter Filter) (*Puzzle, error)
    RandomPuzzles(ctx context.Context, filter Filter, n int) ([]*Puzzle, error)
    GetPuzzle(ctx context.Context, id string) (*Puzzle, error)
    GetPuzzles(ctx context.Context, ids []string) ([]*Puzzle, error)
}
```

A Go interface is a **method set**, not a data shape. TS `interface Puzzle { id: string }` describes fields; `puzzle.Store` describes functions you can call.

**No `implements` keyword** (and unlike TS, you cannot write `class MemoryStore implements Store` as documentation). `db.Store` and `catalog.MemoryStore` both satisfy this because they have those methods. That is TS structural typing: if it has the methods, it fits. The check happens when you pass the value to `api.New`, not when you declare the struct.

HTTP tests construct a `catalog.MemoryStore` — a compile-time fake, not `vi.fn()`. Production without `DATABASE_URL` uses that same store, loaded from JSONL (`go:embed` or `PUZZLES_PATH`).

Small interfaces (a handful of methods) are idiomatic. Do not make a 20-method “IDatabase”.

## Methods and receivers

```go
func (s *Store) GetPuzzle(...) (*puzzle.Puzzle, error)
```

`(s *Store)` is a **pointer receiver**: the method is on `*Store`, like an object method that can mutate `this` (`s.pool`). There is no `class` and no implicit `this`. Value receivers copy the struct; we use pointers for anything with a pool/mux inside.

`api.Server` implements `http.Handler` by defining:

```go
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request)
```

`http.Server.Handler` only needs that method. That is how we pass `handler` into `ListenAndServe` — one-method interfaces, same idea as “if it has `handle(req): Response`, it’s a handler.”

## HTTP (stdlib, Go 1.22 routes)

No Express/Hono/Chi/Gin in v1. `http.NewServeMux()` plus method+path patterns:

```go
mux.HandleFunc("GET /puzzles/random", s.handleRandom)
mux.HandleFunc("POST /puzzles/{id}/solve", s.handleSolve)
id := r.PathValue("id")
```

A handler writes to `http.ResponseWriter` and reads `*http.Request`. There is no `return res.json(...)`; you write onto `w`. JSON:

```go
json.NewEncoder(w).Encode(body)           // response  — Response.json(body)
json.NewDecoder(r.Body).Decode(&req)      // request   — await req.json() into a struct
```

`Decode(&req)` takes a pointer so it can fill `req`. Forgetting `&` is a common first bug.

Struct **tags** map Go fields to JSON keys (class-transformer / a Zod `.transform` output name):

```go
ChoiceID string `json:"choiceId"`
```

The HTTP envelope is camelCase (`leafA`, `goldGraph`) to match the frontend. Nested graph objects keep ETL names (`from` / `to`) because those blobs are stored that way in JSONB.

Middleware is just wrapping `http.Handler`: `withCORS` returns a function that sets headers, handles `OPTIONS`, then calls `next.ServeHTTP` — `(req, res, next) => { ...; next() }`.

## Goroutines and shutdown

```go
go func() {
    httpSrv.ListenAndServe()
}()
```

`go f()` starts a concurrent function (a **goroutine**). It is not a `Promise` and not a Node worker thread. The function looks synchronous; the runtime multiplexes goroutines onto OS threads. The listener blocks, so it runs in the background while `main` waits on `SIGINT`/`SIGTERM` via `signal.Notify`. Then `Shutdown` stops accepting connections.

You do not `await` the listener. The process exits when `main` returns — like a Node process exiting when the event loop is empty, except here **`main` returning is the whole story**. Forgotten goroutines die with the process.

## `defer`

```go
defer pool.Close()
defer res.Body.Close()  // in tests
```

`defer` runs when the surrounding function returns, LIFO. Closest TS equivalent is `try/finally` or `using` / `Symbol.dispose`, except you write it next to the `Open` and it still runs on every `return`. Use it for Close/Release so you do not leak on every error return. `Migrate` delegates one migration to a helper so `defer conn.Release()` runs when that migration finishes, rather than piling up deferred releases across the loop.

## Slices, maps, the one generic we use

`[]Edge` is a **slice** (a JS array: length + backing storage). `make([]Node, 0, len(answer.Nodes))` pre-allocates capacity, like `new Array(n)` without filling it.

Maps are `map[string]bool`. There is no built-in `Set`; a map to `bool` or `struct{}` is the usual set (`PairSetsEqual`, `edgeSet`).

Go has generics; this tree barely uses them. `ShuffleByID[T any]` is the exception — same idea as `function shuffleById<T>(items: T[], id: string): T[]`.

## Embedding SQL (`go:embed`)

```go
//go:embed migrations/*.sql
var migrationsFS embed.FS
```

The compiler stuffs those files into the binary — `import sql from './foo.sql?raw'` that actually lands inside the executable. Production Docker image has **no** filesystem copy of the `.sql` files at runtime; they live inside `/api`. Paths in `embed` are relative to the Go file (`internal/db/migrations/`).

`upSection` strips `-- +goose Up/Down` so we can keep familiar markers without importing the goose library (which pulls extra database drivers).

`pgx.QueryExecModeSimpleProtocol` is required for a migration file that contains **multiple** SQL statements. The default protocol prepares one statement and Postgres rejects `;`-separated batches.

## pgx vs `database/sql`

`pgxpool.Pool` is a connection pool typed for Postgres. `QueryRow` + `Scan` fills Go variables (no `rows[0].id` objects unless you scan into a struct). JSONB columns are scanned into `[]byte` or `json.RawMessage` then `json.Unmarshal` into structs.

Placeholders are `$1`, `$2` (Postgres), never `` `${id}` `` interpolation and never `?` from some JS drivers.

`filter.MinQuality *int` lets SQL see SQL `NULL` when the query param is omitted (`$2::int IS NULL OR quality_score >= $2`). A plain `int` cannot be null — same optional-pointer rule as `gloss`.

## Tests

Files named `foo_test.go` with `package puzzle` (or `package api`) are compiled **only** for `go test`. They are not part of `go build`. That is `vitest` including `*.test.ts` without bundling them into production.

```go
func TestEdgeSetsEqualIgnoresOrderAndReltype(t *testing.T) {
    if !EdgeSetsEqual(gold, ok) {
        t.Fatal("...")
    }
}
```

`t.Fatal` fails the test immediately (`expect(...).toBeTruthy()` plus `return` from the test). There is no `describe` / `it` nesting required. `httptest.NewServer(handler)` binds a random port and we `http.Get` it — still no real Postgres.

Run:

```bash
go test ./...                 # every package under backend/
go test -v ./internal/puzzle  # one package, verbose
go test -run TestSolveHard ./internal/api
```

`-run` takes a regex on the test name (`TestSolveHard`), not a file path. `go test` caches passing results (`(cached)` in the output). Change a `.go` file or use `-count=1` to force a rerun (`vitest --no-cache`).

## Everyday commands

Run from `backend/` (the directory that contains `go.mod`):

| Command | TS-ish equivalent | What |
|---|---|---|
| `go run ./cmd/api` | `tsx src/index.ts` | Compile in memory and start the server |
| `go build -o api.exe ./cmd/api` | `tsc && node dist/index.js` (but native) | Write a binary (`api.exe` on Windows) |
| `go test ./...` | `vitest run` | All tests |
| `go mod tidy` | lockfile sync after import changes | Add/remove deps to match imports; refresh `go.sum` |
| `go fmt ./...` | Prettier, except there is one style | Canonical formatting (tabs, not a style debate) |
| `go vet ./...` | `tsc --noEmit` plus a few lint rules | Static checks |

`./cmd/api` is a path relative to the module, not a shell glob. The `.` means “this module”.

After you change imports, run `go mod tidy` so `go.sum` stays in git. Never hand-edit `go.sum` (same rule as a pnpm lockfile).

## Docker build (why two stages)

1. `golang:1.24-bookworm` compiles with `CGO_ENABLED=0` (pure Go, no C toolchain) to a static binary.
2. `distroless/static` copies **only** that binary. No shell, no Node, no `node_modules`, no migration files on disk.

`EXPOSE 8080` is documentation; Compose maps the port. `USER nonroot` is so the process does not run as root.

## Config

Go has no constructor / `zod` parse-at-import magic. `config.FromEnv()` reads `os.Getenv` once at boot (`process.env`). Changing env vars requires a restart.

`HTTP_ADDR` is `:8080` (all interfaces, port 8080), not `8080`. That is the `net` package’s address form (`host:port`; empty host = all).

## If something feels missing

### No classes / inheritance

Structs plus interfaces. Share behavior by passing an interface, not `extends`. `api.Server` holds `puzzle.Store`; it never names Postgres vs JSONL:

```go
// internal/api/server.go
type Server struct {
	store  puzzle.Store
	logger *slog.Logger
	ready  func(*http.Request) error
	mux    http.Handler
}
```

`catalog.MemoryStore` and `db.Store` both have `GetPuzzle` / `RandomPuzzle`. Neither writes `implements Store`. `api.New(store, ...)` is where the compiler checks the shape.

Methods live on the type, not a class body. `Filter.ForMode` is a **value** receiver: it copies `f`, maybe sets `MinNodes`, and returns the copy — no `this` mutation, no subclass.

```go
// internal/puzzle/puzzle.go
func (f Filter) ForMode(mode Mode) Filter {
	if mode == ModeHard {
		n := MinHardModeNodes
		f.MinNodes = &n
	}
	return f
}
```

### No default parameter values

No `mode = 'easy'` in the signature. Empty query string is the zero value `""`; `ParseMode` maps it to easy:

```go
// internal/puzzle/puzzle.go
func ParseMode(s string) (Mode, error) {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "", "easy":
		return ModeEasy, nil
	// ...
	}
}
```

Optional filters are an options struct. Unset fields stay zero (`""`, `nil`). `minQuality` is only a pointer when the query param is present:

```go
// internal/api/server.go
filter := puzzle.Filter{
	LangPair:   strings.TrimSpace(r.URL.Query().Get("langPair")),
	ExcludeIDs: parseExcludeIDs(r.URL.Query()["exclude"]),
}
if raw := strings.TrimSpace(r.URL.Query().Get("minQuality")); raw != "" {
	n, convErr := strconv.Atoi(raw)
	// ...
	filter.MinQuality = &n
}
filter = filter.ForMode(mode)
```

### No `undefined` / optional chaining

Missing data is `nil` on a pointer, or a `(value, bool)`. `RootAncestor` does not return `Term | undefined`; the second result is the `ok`:

```go
// internal/api/server.go — solveMedium
anc, ok := puzzle.RootAncestor(p.AnswerGraph)
if !ok {
	s.logger.Error("medium root ancestor missing", "id", p.ID)
	writeError(w, http.StatusInternalServerError, "failed to grade puzzle")
	return
}
```

`Term.Gloss` is `*string` (`gloss?: string | null` on the frontend). `PromptGraph` returns `nil` for easy/medium so `json:"omitempty"` drops `promptGraph` instead of sending `null`.

### Zero value of a slice is `nil`

`json` encodes a `nil` slice as `null` and a non-nil empty slice as `[]`. Hard prompt graphs force an allocated empty edge list so the client gets `[]`, not `null`:

```go
// internal/puzzle/puzzle.go
func PromptGraph(answer Graph, mode Mode) *Graph {
	if mode != ModeHard {
		return nil
	}
	nodes := make([]Node, len(answer.Nodes))
	copy(nodes, answer.Nodes)
	return &Graph{Nodes: nodes, Edges: []Edge{}}
}
```

### Package-level sentinel errors

`var ErrNotFound` is a comparable value. Handlers use `errors.Is`, not `err.Error() == "puzzle not found"` (the TS `error.message === "..."` trap):

```go
// internal/puzzle/puzzle.go
var ErrNotFound = errors.New("puzzle not found")
```

```go
// internal/api/server.go
p, err := s.store.RandomPuzzle(r.Context(), filter)
if errors.Is(err, puzzle.ErrNotFound) {
	writeError(w, http.StatusNotFound, "no enabled puzzles")
	return
}
```

Both stores return that same sentinel (`return nil, puzzle.ErrNotFound`). Wrapping with `%w` still matches `errors.Is`.

### No `async` / `await`

Blocking I/O in a goroutine. `RandomPuzzle` looks synchronous; `r.Context()` is how cancel arrives (not a `Promise`). The HTTP listener would block `main`, so it runs with `go`:

```go
// cmd/api/main.go
go func() {
	logger.Info("listening", "addr", cfg.Addr)
	if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		logger.Error("listen", "err", err)
		os.Exit(1)
	}
}()
```

When in doubt, grep this module for a name, then read the test with the same prefix (`TestPromptGraphHard...` documents the intended leak-prevention). Frontend types in `frontend/src/api/types.ts` are the wire contract those structs serialize to.
