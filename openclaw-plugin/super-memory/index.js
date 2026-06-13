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

  function registerHookSkeleton(name, handler) {
    const candidates = [
      `register${name}`,
      `on${name}`,
      'registerHook'
    ];
    for (const key of candidates) {
      if (typeof api[key] === 'function') {
        if (key === 'registerHook') api[key](name, handler);
        else api[key](handler);
        return true;
      }
    }
    return false;
  }

  async function get(path) {
    const res = await fetch(`${baseUrl}${path}`);
    if (!res.ok) throw new Error(`super-memory ${path} failed: ${res.status} ${await res.text()}`);
    return res.json();
  }

  function createSearchManager() {
    return {
      async search(query, opts = {}) {
        const payload = await post('/memory-search', {
          query,
          max_results: opts.maxResults || 5,
          min_score: opts.minScore || 0,
          corpus: 'all'
        });
        if (typeof opts.onDebug === 'function') {
          opts.onDebug({ backend: 'builtin', configuredMode: 'super-memory', effectiveMode: 'super-memory' });
        }
        return (payload.results || []).map((hit) => ({
          path: hit.path,
          startLine: hit.startLine || 1,
          endLine: hit.endLine || 1,
          score: hit.score || 0,
          textScore: hit.textScore || hit.score || 0,
          snippet: hit.snippet || '',
          source: hit.corpus === 'sessions' ? 'sessions' : 'memory',
          citation: `${hit.path}#${hit.startLine || 1}`
        }));
      },
      async readFile(params) {
        const payload = await post('/memory-get', {
          path: params.relPath,
          from_line: params.from || 1,
          lines: params.lines || 20,
          corpus: 'all'
        });
        if (!payload || payload.error) {
          return { text: '', path: params.relPath, truncated: false, from: params.from || 1, lines: 0 };
        }
        return {
          text: payload.content || '',
          path: payload.path,
          truncated: Boolean(payload.truncated),
          from: payload.from || 1,
          lines: payload.lines || 0
        };
      },
      status() {
        return {
          backend: 'builtin',
          provider: 'super-memory',
          dirty: false,
          sources: ['memory'],
          custom: { mode: 'development-slot-adapter', apiBaseUrl: baseUrl }
        };
      },
      async sync() {},
      getCachedEmbeddingAvailability() { return { ok: true, checked: true, cached: true }; },
      async probeEmbeddingAvailability() { return { ok: true, checked: true }; },
      async probeVectorStoreAvailability() { return true; },
      async close() {}
    };
  }

  if (cfg.registerExclusiveMemoryCapability === true && typeof api.registerMemoryCapability === 'function') {
    api.registerMemoryCapability({
      promptBuilder: () => [
        'Super Memory is the active development memory slot. Preserve Workspace Markdown as canonical truth and use Super Memory search/get for recall.'
      ],
      flushPlanResolver: () => null,
      runtime: {
        async getMemorySearchManager() {
          return { manager: createSearchManager() };
        },
        resolveMemoryBackendConfig() {
          return { backend: 'builtin' };
        },
        async closeMemorySearchManager() {},
        async closeAllMemorySearchManagers() {}
      },
      publicArtifacts: {
        async listArtifacts() { return []; }
      }
    });
  }

  if (cfg.registerDynamicMcpToolProxy === true && typeof api.registerTool === 'function') {
    api.registerTool({
      name: 'super_memory_mcp_tools_list',
      description: 'Development-only dynamic MCP tools/list proxy for Super Memory.',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
      handler: async () => get('/mcp-tools')
    });
  }

  if (cfg.registerSuperMemoryHooks === true) {
    registerHookSkeleton('PrePromptContext', async (ctx = {}) => post('/prefetch', { query: ctx.query || ctx.prompt || '', limit: cfg.prePromptLimit || 8 }));
    registerHookSkeleton('PostAgentCapture', async (ctx = {}) => post('/sync-turn', { user_message: ctx.userMessage, assistant_message: ctx.assistantMessage, session_id: ctx.sessionId, metadata: { hook: 'post-agent-capture' } }));
    registerHookSkeleton('PreCompactionFlush', async (ctx = {}) => post('/auto', { text: ctx.text || ctx.transcript || '', save: true }));
    registerHookSkeleton('ResetFlush', async (ctx = {}) => post('/auto', { text: ctx.text || 'reset flush', save: true }));
    registerHookSkeleton('StartupConsolidation', async () => post('/consolidate', { strategy: 'startup', dry_run: true }));
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

  if ((cfg.registerLegacyMemoryShims === true || cfg.registerExclusiveMemoryCapability === true) && typeof api.registerTool === 'function') {
    api.registerTool({
      name: 'memory_search',
      description: 'Legacy OpenClaw memory_search shim backed by Super Memory. Enable only when Super Memory owns the exclusive memory slot.',
      inputSchema: {
        type: 'object',
        properties: {
          query: { type: 'string' },
          maxResults: { type: 'number', default: 5 },
          minScore: { type: 'number', default: 0 },
          corpus: { type: 'string', default: 'all' }
        },
        required: ['query'],
        additionalProperties: false
      },
      handler: async (input) => post('/memory-search', {
        query: input.query,
        max_results: input.maxResults || input.max_results || 5,
        min_score: input.minScore || input.min_score || 0,
        corpus: input.corpus || 'all'
      })
    });

    api.registerTool({
      name: 'memory_get',
      description: 'Legacy OpenClaw memory_get shim backed by Super Memory. Enable only when Super Memory owns the exclusive memory slot.',
      inputSchema: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          from: { type: 'number', default: 1 },
          lines: { type: 'number', default: 20 },
          corpus: { type: 'string', default: 'all' }
        },
        required: ['path'],
        additionalProperties: false
      },
      handler: async (input) => post('/memory-get', {
        path: input.path,
        from_line: input.from || input.from_line || 1,
        lines: input.lines || 20,
        corpus: input.corpus || 'all'
      })
    });
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
