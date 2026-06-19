# Semantic Mode

Semantic mode adds sqlite-vec vector search and Ollama embeddings to Super Memory recall.

## Requirements

- Python 3.11+
- Super Memory installed with the `semantic` extra
- Ollama running locally
- Ollama embedding model `nomic-embed-text`
- A Super Memory SQLite database with `workspace_markdown` memories

## Fresh Install From GitHub

```bash
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install "super-memory[semantic] @ git+https://github.com/oceandmt/super-memory.git@v1.1.2"
```

If your shell has trouble with PEP 508 direct references, use:

```bash
pip install "git+https://github.com/oceandmt/super-memory.git@v1.1.2#egg=super-memory[semantic]"
```

## Ollama Setup

```bash
ollama serve
ollama pull nomic-embed-text
```

The default config expects:

```yaml
embedding_provider: ollama
embedding_model: nomic-embed-text
embedding_endpoint: http://127.0.0.1:11434/api/embed
embedding_dimension: 768
```

## Configure OpenClaw Workspace

From your OpenClaw workspace root:

```bash
mkdir -p .openclaw
cp config/examples/super-memory.semantic.yaml .openclaw/super-memory.yaml
```

Edit `.openclaw/super-memory.yaml` and set:

```yaml
workspace_root: /absolute/path/to/openclaw/workspace
sqlite_path: data/super-memory.sqlite3
```

## Doctor

Check prerequisites:

```bash
super-memory semantic doctor --config .openclaw/super-memory.yaml
```

JSON output:

```bash
super-memory semantic doctor --config .openclaw/super-memory.yaml --json
```

## Build / Update Vector Index

```bash
super-memory semantic index --config .openclaw/super-memory.yaml
```

Rebuild from scratch:

```bash
super-memory semantic index --config .openclaw/super-memory.yaml --rebuild
```

Smoke-test a small subset:

```bash
super-memory semantic index --config .openclaw/super-memory.yaml --limit 10
```

The index is written to:

```text
data/vectors.sqlite3
```

This file is a machine-local runtime artifact. Rebuild it on each machine rather than committing it to source control.

## Verify Semantic Query

```bash
super-memory semantic verify "super memory neural memory import honcho" --config .openclaw/super-memory.yaml
```

A successful result includes hydrated memory rows with:

```json
{
  "provenance": { "layer": "semantic" },
  "semantic_score": 0.58
}
```

## OpenClaw MCP Runtime

After installing or updating the package, restart/reload OpenClaw so MCP processes import the new code.

Then verify the MCP tool returns semantic results, for example:

```text
super_memory_cross_scope_recall(query="super memory neural memory import honcho", source_layers=["markdown"])
```

Expected characteristics:

- results are non-empty
- `provenance.layer` is `semantic`
- each semantic hit includes `semantic_score`

## Troubleshooting

### `sqlite-vec not installed`

Install the semantic extra or direct dependency:

```bash
pip install "super-memory[semantic]"
# or
pip install sqlite-vec
```

### Ollama embedding request fails

Check Ollama is running and the model is available:

```bash
curl http://127.0.0.1:11434/api/tags
ollama pull nomic-embed-text
```

### Dimension mismatch

`nomic-embed-text` returns 768-dimensional vectors. Ensure config uses:

```yaml
embedding_dimension: 768
```

If changing models, rebuild the vector DB:

```bash
rm -f data/vectors.sqlite3 data/vectors.sqlite3-wal data/vectors.sqlite3-shm
super-memory semantic index --config .openclaw/super-memory.yaml --rebuild
```

### Empty semantic results

Run:

```bash
super-memory semantic doctor --config .openclaw/super-memory.yaml
super-memory semantic index --config .openclaw/super-memory.yaml
super-memory semantic verify "your query" --config .openclaw/super-memory.yaml
```

If CLI verification works but MCP does not, restart OpenClaw/MCP runtime.
