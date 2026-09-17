package api

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/bekand/EtymoGuessr/backend/internal/config"
	"github.com/bekand/EtymoGuessr/backend/internal/db"
	"github.com/bekand/EtymoGuessr/backend/internal/dbtest"
)

func TestHealthAndSolveAgainstPostgres(t *testing.T) {
	pool := dbtest.Open(t)
	store := db.NewStore(pool)
	p := dbtest.Sample("live-easy", 3, true, "de-en", 5)
	dbtest.Insert(t, pool, p)

	handler := New(store, config.Config{CORSOrigins: []string{"http://localhost:5173"}}, nil)
	handler.SetReady(func(r *http.Request) error {
		return store.Ping(r.Context())
	})
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)

	res, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatal(err)
	}
	res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("health %d", res.StatusCode)
	}

	res, err = http.Get(srv.URL + "/puzzles/random?mode=easy")
	if err != nil {
		t.Fatal(err)
	}
	body, err := io.ReadAll(res.Body)
	res.Body.Close()
	if err != nil {
		t.Fatal(err)
	}
	if res.StatusCode != http.StatusOK {
		t.Fatalf("random %d %s", res.StatusCode, body)
	}
	raw := string(body)
	if strings.Contains(raw, "correctChoice") || strings.Contains(raw, "correct_choice") {
		t.Fatalf("GET leaked gold: %s", raw)
	}
	if strings.Contains(raw, "goldGraph") || strings.Contains(raw, `"edges":[`) {
		t.Fatalf("GET leaked gold graph: %s", raw)
	}
	var prompt map[string]any
	if err := json.Unmarshal(body, &prompt); err != nil {
		t.Fatal(err)
	}
	if _, ok := prompt["promptGraph"]; ok {
		t.Fatal("easy prompt should omit promptGraph")
	}

	res, err = http.Post(srv.URL+"/puzzles/"+p.ID+"/solve", "application/json", strings.NewReader(`{"mode":"easy","choiceId":"c0"}`))
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	var solved solveResponse
	if err := json.NewDecoder(res.Body).Decode(&solved); err != nil {
		t.Fatal(err)
	}
	if !solved.Correct || solved.CorrectChoice != "c0" {
		t.Fatalf("solve %+v", solved)
	}
	if len(solved.GoldGraph.Edges) == 0 {
		t.Fatal("solve should reveal gold edges")
	}
}

func TestHealthUnavailableWhenPingFails(t *testing.T) {
	_ = dbtest.Open(t)
	url := strings.TrimSpace(os.Getenv("TEST_DATABASE_URL"))
	ctx := t.Context()
	dead, err := db.Connect(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	dead.Close()
	store := db.NewStore(dead)
	handler := New(store, config.Config{}, nil)
	handler.SetReady(func(r *http.Request) error {
		return store.Ping(r.Context())
	})

	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)

	res, err := http.Get(srv.URL + "/health")
	if err != nil {
		t.Fatal(err)
	}
	res.Body.Close()
	if res.StatusCode != http.StatusServiceUnavailable {
		t.Fatalf("health %d", res.StatusCode)
	}
}
