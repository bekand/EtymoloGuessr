# Puzzle pipeline

Python stages that turn Wiktionary dumps into pregenerated puzzles. The Go API never walks this graph; it only reads the rows this package emits.

CLI: `uv run etl refresh` then `uv run etl generate`. Command flags and quality axes are in [`etl/README.md`](../README.md).

## End to end

```mermaid
flowchart LR
  subgraph sources [Sources]
    etym["etymology-db parquet / fixture jsonl"]
    kaikki["kaikki.org gloss jsonl"]
  end

  subgraph refreshMod [refresh.py]
    raw["data/raw dumps + NOTICE + manifest.json"]
  end

  subgraph deriveMods [gloss.py + reduce.py via derive.py]
    derived["data/derived edges, gloss, lemma, etym_parents"]
  end

  subgraph generateMods [extract.py + emit.py via generate.py]
    puzzles["Puzzle list + funnel.json"]
  end

  subgraph sinks [One generate sink]
    jsonl["JSONL"]
    stdout["stdout"]
    db["Postgres"]
  end

  etym --> raw
  kaikki --> raw
  raw --> derived
  derived --> puzzles
  puzzles --> jsonl
  puzzles --> stdout
  puzzles --> db
```

`refresh` downloads (or copies fixtures) and then calls `rebuild_derived()`. `generate` does **not** download; it errors if derived artifacts are missing. `validate.py` is a schema check on already-built puzzles (`etl validate` / `etl load`), not a generate stage.

---

## 1. Refresh — `refresh.py`

```mermaid
flowchart TD
  start([etl refresh]) --> mode{"fixtures flag?"}

  mode -->|yes| copy["Copy etl/fixtures jsonl+txt into data/raw"]
  copy --> dropParquet["Delete stale etymology.parquet if present"]
  dropParquet --> noticeFix["Write NOTICE + manifest.json source=fixtures"]

  mode -->|no| each["For each config sources entry"]
  each --> cached{"File exists and not force?"}
  cached -->|yes| verifyCached["sha256 verify if configured"]
  cached -->|no| download["HTTP download to .part then replace"]
  download --> verifyNew["sha256 verify"]
  verifyCached --> meta["Record name, url, digest, bytes"]
  verifyNew --> meta
  meta --> noticeDl["Write NOTICE + manifest.json source=download"]

  noticeFix --> skip{"skip derived?"}
  noticeDl --> skip
  skip -->|yes| rawOnly([raw only])
  skip -->|no| rebuild["rebuild_derived"]
  rebuild --> done([data/derived ready])
```

---

## 2. Derive — `gloss.py` + `reduce.py` via `derive.py` `rebuild_derived`

Gloss indexing runs **before** graph reduce so etymology templates from the winning gloss can align ancestor edges.

```mermaid
flowchart TD
  start([rebuild_derived]) --> langs["allowed_languages: leaf langs + ancestor allowlist"]

  langs --> gloss["index_glosses over kaikki jsonl"]
  gloss --> g1["Per object: first lexical gloss"]
  g1 --> g2["Skip form_of / grammatical senses"]
  g2 --> g3["Skip redirect stubs; strip case labels like with genitive"]
  g3 --> inherit{"No lexical gloss?"}
  inherit -->|form-only| form["Pending: inherit citation lemma gloss + lemma_index entry"]
  inherit -->|redirect stub| redir["Pending: inherit target meaning, keep surface spelling"]
  inherit -->|lexical| store["gloss_index lang+term to gloss"]
  form --> apply["Resolve pending chains, including macron-folded Latin look-ups"]
  redir --> apply
  store --> parents["etym_parents from inh/bor/der/root template arg 3"]
  apply --> parents

  langs --> load["load_raw_edges: parquet else etymology.jsonl"]
  parents --> reduce["reduce_edges"]
  load --> reduce

  reduce --> r1["Keep keep_reltypes"]
  r1 --> r2["Drop junk: null, multiword, affix-like, length > 80"]
  r2 --> r3["Both ends in allowed languages"]
  r3 --> r4["Drop duplicate edges"]
  r4 --> r5["Drop cross-term leaf-to-leaf ancestor hops (hipoxia to oxygen); keep same-term loans (panel to panel)"]
  r5 --> r6["align ancestor edges: keep related_term if it matches or reaches the winning-gloss parent allowlist; Latin-family macron aliases share reachability"]

  r6 --> write["Write data/derived"]
  write --> e["edges.parquet"]
  write --> gi["gloss_index.json"]
  write --> li["lemma_index.json"]
  write --> ep["etym_parents.json"]
  write --> meta["meta.json counts"]
```

Walks toward ancestors later use only `inherited_from` / `borrowed_from` / `derived_from` / `root` (`ancestor_reltypes`). Cognate / doublet edges are kept in the parquet but are not used for LCA paths.

---

## 3. Generate — `extract.py` + `emit.py` via `generate.py`

### Load and extract

```mermaid
flowchart TD
  start([etl generate]) --> loadE["load_derived_edges"]
  loadE --> loadG["load_gloss_index"]
  loadG --> loadL["load_lemma_index"]
  loadL --> buildG["build_graph: DiGraph, ancestor edges only"]

  buildG --> extract["extract_candidates"]
  extract --> leaves["Modern-language leaf nodes"]
  leaves --> leafFilter["reject_leaf per leaf"]
  leafFilter -->|proper_noun_leaf| drop1[drop]
  leafFilter -->|term_too_short| drop1
  leafFilter -->|no_gloss_leaf| drop1
  leafFilter -->|ok| paths["ancestor_paths along ancestor_reltypes"]

  paths --> pairs["iter related leaf pairs: only leaves that share an ancestor"]
  pairs --> note["Seeded rng: round-robin across ancestor families so English groups cannot monopolize early exit"]
  note --> pairLoop["For each unordered pair"]
```

### One leaf pair → candidate

```mermaid
flowchart TD
  pair["Leaf pair with glosses"] --> gold["gold_subgraph_for_pair"]
  gold --> common["Intersection of ancestor sets minus the two leaves"]
  common -->|empty| noLca["funnel: no_lca"]
  common --> rank["Rank LCAs by shortest combined path"]

  rank --> trial["Try LCAs until subgraph has at most max_nodes after unify"]
  trial -->|all too big| tooBig["funnel: too_big"]
  trial --> lemma{"Form-only LCA in lemma_index?"}
  lemma -->|yes| rewrite["rewrite form LCA to citation lemma"]
  lemma -->|no| norm
  rewrite --> norm["normalize_gold_subgraph: prefer_latin_chain_path + unify"]

  norm --> size{"nodes at or under max_nodes?"}
  size -->|no| tooBig
  size -->|yes| reject["reject_candidate"]

  reject --> assess["assess_pair"]
  assess --> hard{"Hard reject?"}
  hard -->|term_too_short / no_gloss / inflection_lca| dropH["funnel that reason"]
  hard -->|english_term_is_lca_gloss| dropH
  hard -->|pass| quality["quality_score 5 minus divergence axes"]

  quality --> ancScan["Non-leaf nodes"]
  ancScan -->|modern leaf lang as intermediate| mod["funnel: modern_lang_ancestor"]
  ancScan -->|grammatical or unresolved redirect gloss| nonlex["funnel: nonlexical_ancestor"]
  ancScan -->|ok| dedup{"pair+LCA already seen?"}
  dedup -->|yes| dup["funnel: duplicate_pair"]
  dedup -->|no| cand["Keep candidate: leaves, LCA, nodes, edges, quality, lang_pair"]

  cand --> early{"Finite n and both EN/other buckets have headroom?"}
  early -->|yes| more[next pair]
  early -->|enough quality survivors| earlyExit["funnel: early_exit"]
```

`assess_pair` hard-filters only structural LCA problems and “English term ≡ LCA gloss head”. Same-language / similar-spelling / shared-meaning are **scored**, not dropped here.

### Quality axes — `quality.py`

Start at 5; −1 per miss; cheap → expensive; may early-exit vs `--min-quality` (default 4).

```mermaid
flowchart TD
  s5["score = 5"] --> a1{"Same language?"}
  a1 -->|yes| m1["-1"]
  a1 -->|no| a2
  m1 --> a2{"Either leaf term = LCA term after normalize_label?"}
  a2 -->|yes| m2["-1"]
  a2 -->|no| a3
  m2 --> a3{"Leaf terms equal or share a 3-char prefix?"}
  a3 -->|yes| m3["-1"]
  a3 -->|no| a4
  m3 --> a4{"Leaf glosses share a lemmatized content token?"}
  a4 -->|yes| m4["-1"]
  a4 -->|no| a5
  m4 --> a5{"Either leaf gloss shares a token with the LCA gloss?"}
  a5 -->|yes| m5["-1"]
  a5 -->|no| out
  m5 --> out["score 0-5"]
```

Meaning axes use `simplemma` English lemmas. Spelling axes do not.

### Filter then emit

Lang-pair and quality cuts live in `generate.py`. Water-fill emit lives in `emit.py`. Funnel write and sinks are CLI / `generate.py` after `emit_puzzles` returns.

```mermaid
flowchart TD
  cands["Candidates from extract"] --> lp{"lang-pair filter? generate.py"}
  lp -->|yes| f1["Drop other pairs: lang_pair_filtered"]
  lp -->|no| q
  f1 --> q["Keep quality_score at or above min_quality: below_min_quality for the rest"]

  q --> emit["emit_puzzles"]
  emit --> pool["Distractor pool: unique lexical LCA glosses from the full quality-passing set"]
  pool --> buckets["prepare_score_buckets: by score desc, each split EN vs other, seed-shuffle"]

  buckets --> water["Water-fill: prefer the bucket that has emitted fewer so far"]
  water --> reuse{"Either leaf already used in this batch?"}
  reuse -->|yes| ru["funnel: leaf_reuse"]
  reuse -->|no| mc["make_choices: 1 gold + n_choices-1 real distractors"]
  mc -->|pool too thin| thin["funnel: insufficient_distractors"]
  mc -->|ok| puzzle["to_puzzle"]

  puzzle --> puzzleId["puzzle_id SHA-256 of sorted leaves + LCA + gold edge from/to"]
  puzzleId --> answerG["answer_graph nodes+edges; prompt_graph is derived later, never stored"]
  answerG --> emitted["Puzzle enabled=true"]

  emitted --> cap{"Hit n limit?"}
  cap -->|no| water
  cap -->|yes or buckets empty| back["return puzzles to generate.py"]
  back --> funnel["write data/reports/funnel.json"]
  funnel --> sink{"CLI sink"}
  sink -->|jsonl| jsonl["write JSONL"]
  sink -->|stdout| stdout["JSON array"]
  sink -->|db| db["truncate puzzles+scores, upsert"]
  sink -->|dry-run| dry["counts only"]
```

Placeholders are never used for multiple choice. Canonical gold is `answer_graph` only.

---

## 4. Validate — `validate.py`

Used by `etl validate` and `etl load`, not by `generate` itself.

```mermaid
flowchart TD
  puzzles["Puzzle list from JSONL or Postgres"] --> each["Per puzzle"]
  each --> v1["id is a content hash"]
  each --> v2["Exactly n_choices unique choice ids with gloss text"]
  each --> v3["Choices are not redirect/grammatical stubs"]
  each --> v4["correct_choice matches one id; distractors differ"]
  each --> v5["at most max_nodes; both leaves in graph with role=leaf"]
  each --> v6["Gold edges reference node ids"]
  each --> v7["lang_pair looks like en-de"]
  puzzles --> dup["No duplicate ids in the set"]
```

---

## Funnel reasons

| Reason | When |
|---|---|
| `proper_noun_leaf` | EN/ES/PT leaf starts with an uppercase letter (German exempt) |
| `term_too_short` | Leaf or LCA headword shorter than 3 characters |
| `no_gloss_leaf` / `no_gloss` | Missing leaf or LCA gloss |
| `no_lca` | Pair shares no ancestor |
| `too_big` | Connecting subgraph over `max_nodes` |
| `inflection_lca` | LCA gloss still looks grammatical |
| `english_term_is_lca_gloss` | English leaf term = first content token of the LCA gloss |
| `modern_lang_ancestor` | Intermediate node in EN/ES/PT/DE |
| `nonlexical_ancestor` | Intermediate gloss is grammatical or an unresolved redirect |
| `duplicate_pair` | Same leaves + LCA already kept |
| `below_min_quality` | Soft score under `--min-quality` |
| `lang_pair_filtered` | Failed `--lang-pair` |
| `leaf_reuse` | `(lang, term)` already emitted in this batch |
| `insufficient_distractors` | Fewer than 3 other real LCA glosses |
| `early_exit` | Finite `--n`; enough quality survivors in EN/other buckets |

---

## Modules

| File | Role |
|---|---|
| `refresh.py` | Fetch or copy dumps into `data/raw/` |
| `gloss.py` | Gloss / lemma / etym-parent indexes from kaikki dumps |
| `reduce.py` | Filter etymology edges and align to winning-gloss parents |
| `derive.py` | Orchestrate gloss+reduce into `data/derived/` |
| `extract.py` | Graph walk, LCA selection, hard filters, candidates |
| `quality.py` | Soft 0–5 divergence score + `assess_pair` hard rejects |
| `emit.py` | Distractors, water-fill emit, puzzle rows |
| `generate.py` | Orchestrate load → extract → emit; funnel / timings |
| `validate.py` | Schema check for JSONL / Postgres rows |
