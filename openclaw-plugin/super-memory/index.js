module.exports = async function superMemoryPlugin(api) {
  const cfg = api.config || {};
  const baseUrl = cfg.apiBaseUrl || 'http://127.0.0.1:8765';

  async function post(path, body) {
    const res = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body || {})
    });
    if (!res.ok) throw new Error(`super-memory ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  async function get(path) {
    const res = await fetch(`${baseUrl}${path}`);
    if (!res.ok) throw new Error(`super-memory ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  if (typeof api.registerMemoryCorpusSupplement === 'function') {
    api.registerMemoryCorpusSupplement({
      async search(params) {
        const payload = await post('/memory-search', {
          query: params.query,
          max_results: params.maxResults || 5,
          corpus: 'all'
        });
        return (payload.results || []).map((hit) => ({
          corpus: hit.corpus || 'super-memory',
          path: hit.path,
          title: hit.memory_id || hit.id,
          kind: 'memory',
          score: hit.score || 0,
          snippet: hit.snippet || '',
          id: hit.id,
          startLine: hit.startLine || 1,
          endLine: hit.endLine || 1,
          citation: `${hit.path}#${hit.startLine || 1}`,
          source: 'super-memory',
          provenanceLabel: `super-memory:${hit.layer || 'unknown'}`,
          sourceType: 'super-memory',
          sourcePath: hit.path
        }));
      },
      async get(params) {
        const payload = await post('/memory-get', {
          path: params.lookup,
          from_line: params.fromLine || 1,
          lines: params.lineCount || 20,
          corpus: 'all'
        });
        if (!payload || payload.error) return null;
        return {
          corpus: payload.source === 'workspace' ? 'memory' : 'super-memory',
          path: payload.path,
          title: payload.metadata?.id || payload.path,
          kind: 'memory',
          content: payload.content || '',
          fromLine: payload.from || payload.fromLine || 1,
          lineCount: payload.lines || payload.lineCount || 1,
          id: payload.metadata?.id,
          provenanceLabel: payload.source || 'super-memory',
          sourceType: payload.source || 'super-memory',
          sourcePath: payload.path
        };
      }
    });
  }

  if (typeof api.registerMemoryPromptSupplement === 'function') {
    api.registerMemoryPromptSupplement(async () => [
      'Super Memory is available as an additional local memory corpus. Use super_memory_search_compatible / super_memory_get_compatible for replacement-path testing.'
    ]);
  }

  api.registerTool({
    name: 'super_memory_remember',
    description: 'Save a memory through Super Memory canonical layer order.',
    inputSchema: {
      type: 'object',
      properties: {
        content: { type: 'string' },
        type: { type: 'string', default: 'context' },
        scope: { type: 'string', default: 'session' },
        agent_id: { type: 'string', default: 'lucas' },
        session_id: { type: 'string' },
        project: { type: 'string' },
        tags: { type: 'array', items: { type: 'string' } },
        source: { type: 'string' },
        metadata: { type: 'object' }
      },
      required: ['content']
    },
    handler: async (input) => post('/remember', input)
  });

  api.registerTool({
    name: 'super_memory_recall',
    description: 'Recall memories from Super Memory derived layers.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string' },
        limit: { type: 'number', default: 10 }
      },
      required: ['query']
    },
    handler: async (input) => post('/recall', input)
  });

  api.registerTool({
    name: 'super_memory_search_compatible',
    description: 'OpenClaw memory_search-compatible recall payload from Super Memory.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string' },
        max_results: { type: 'number', default: 5 },
        min_score: { type: 'number', default: 0 },
        corpus: { type: 'string', default: 'all' }
      },
      required: ['query']
    },
    handler: async (input) => post('/memory-search', input)
  });

  api.registerTool({
    name: 'super_memory_get_compatible',
    description: 'OpenClaw memory_get-compatible read payload from Super Memory virtual paths or workspace files.',
    inputSchema: {
      type: 'object',
      properties: {
        path: { type: 'string' },
        from_line: { type: 'number', default: 1 },
        lines: { type: 'number', default: 20 },
        corpus: { type: 'string', default: 'all' }
      },
      required: ['path']
    },
    handler: async (input) => post('/memory-get', input)
  });

  api.registerTool({
    name: 'super_memory_prefetch',
    description: 'Merged/deduped Super Memory recall for prompt prefetch.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string' },
        limit: { type: 'number', default: 10 }
      },
      required: ['query']
    },
    handler: async (input) => post('/prefetch', input)
  });

  api.registerTool({
    name: 'super_memory_sync_turn',
    description: 'Save compact OpenClaw turn event to Super Memory.',
    inputSchema: {
      type: 'object',
      properties: {
        agent_id: { type: 'string', default: 'lucas' },
        session_id: { type: 'string' },
        user_message: { type: 'string' },
        assistant_message: { type: 'string' },
        project: { type: 'string' },
        metadata: { type: 'object' }
      }
    },
    handler: async (input) => post('/sync-turn', input)
  });

  api.registerTool({
    name: 'super_memory_promote',
    description: 'Promote a Super Memory item to MEMORY.md and the matching register.',
    inputSchema: {
      type: 'object',
      properties: { memory_id: { type: 'string' } },
      required: ['memory_id']
    },
    handler: async (input) => post('/promote', input)
  });

  api.registerTool({
    name: 'super_memory_status',
    description: 'Show Super Memory local service status.',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => get('/status')
  });
};
