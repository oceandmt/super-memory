module.exports = function superMemoryPlugin(api) {
  const cfg = api.config || {};
  // api.config returns the global OpenClaw config, not plugin-specific config.
  // Plugin config lives at plugins.entries.<id>.config. Merge into cfg.
  const pluginCfg = (cfg.plugins && cfg.plugins.entries && cfg.plugins.entries['super-memory'] && cfg.plugins.entries['super-memory'].config) || cfg || {};
  const effectiveAutoSyncTurns = pluginCfg.autoSyncTurns === true || pluginCfg.mode === 'admin' || pluginCfg.mode === 'exclusive';
  const effectiveAutoFlush = pluginCfg.autoFlush === true || pluginCfg.mode === 'admin' || pluginCfg.mode === 'exclusive';
  const effectiveAutoContext = pluginCfg.autoContext === true || pluginCfg.mode === 'exclusive';
  const effectiveExclusiveMemory = pluginCfg.registerExclusiveMemoryCapability === true || pluginCfg.mode === 'exclusive';
  const effectiveLegacyMemoryShims = pluginCfg.registerLegacyMemoryShims === true || pluginCfg.mode === 'exclusive';
  // Override cfg fields with plugin-specific values so downstream code works unchanged
  Object.assign(cfg, pluginCfg);
  try { require('fs').appendFileSync('/tmp/super-memory-cfg-dump.ndjson', JSON.stringify({ts:new Date().toISOString(), cfgKeys:Object.keys(cfg), mode:cfg.mode, autoSyncTurns:cfg.autoSyncTurns, agentId:cfg.agentId, autoFlush:cfg.autoFlush, registerSuperMemoryHooks:cfg.registerSuperMemoryHooks, pluginCfgMode:pluginCfg.mode, pluginAutoSyncTurns:pluginCfg.autoSyncTurns, effectiveAutoSyncTurns:effectiveAutoSyncTurns}) + '\n'); } catch(_){}
  const childProcess = require('child_process');
  const baseUrl = pluginCfg.apiBaseUrl || cfg.apiBaseUrl || 'http://127.0.0.1:8765';
  const mode = pluginCfg.mode || 'safe';
  const registeredTools = [];
  let managedApiProcess = null;


  function registerTool(def) {
    if (typeof api.registerTool !== 'function') {
      return false;
    }
    const parameters = def.parameters || def.inputSchema || {
      type: 'object',
      properties: {},
      additionalProperties: false
    };
    const execute = def.execute || (def.handler
      ? async (_id, args) => def.handler(args || {})
      : undefined);
    if (typeof execute !== 'function') {
      throw new Error('super-memory tool ' + def.name + ' missing execute/handler');
    }
    api.registerTool({
      name: def.name,
      description: def.description,
      parameters: parameters,
      execute: execute
    }, { name: def.name });
    registeredTools.push({ name: def.name, description: def.description });
    return true;
  }

  function buildToolInstructions() {
    const toolList = registeredTools
      .map((t) => `- ${t.name}: ${String(t.description || '').slice(0, 100)}`)
      .join('\n');
    return `Super Memory gives you canonical-first local memory for OpenClaw. These are TOOL CALLS, not CLI commands. Use them for project memory when available.\n\n## Available Super Memory Tools\n${toolList}\n\nUse super_memory_search_compatible / super_memory_get_compatible for OpenClaw memory_search/memory_get compatibility checks. If Super Memory owns the exclusive memory slot, legacy memory_search/memory_get shims may also be available.`;
  }

  function cleanText(raw) {
    return String(raw || '')
      .replace(/^```json[\s\S]*?```/gim, '')
      .replace(/^(?:Conversation info|Sender|Context)\s*\(.*?\)\s*:?.*$/gim, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }


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

  function apiStartHint() {
    const command = cfg.apiCommand || 'super-memory-api --host 127.0.0.1 --port 8765';
    return `Start it with: ${command}`;
  }

  function startManagedApiService() {
    if (cfg.manageApiService !== true || managedApiProcess) return;
    const command = cfg.apiCommand || 'super-memory-api --host 127.0.0.1 --port 8765';
    managedApiProcess = childProcess.spawn(command, {
      shell: true,
      stdio: 'ignore',
      detached: false,
      env: process.env
    });
    managedApiProcess.on('exit', (code, signal) => {
      api.logger?.warn?.(`Super Memory managed API process exited code=${code} signal=${signal}`);
      managedApiProcess = null;
    });
    api.logger?.info?.(`Super Memory managed API process started: ${command}`);
  }

  function stopManagedApiService() {
    if (!managedApiProcess) return;
    try { managedApiProcess.kill('SIGTERM'); }
    catch (err) { api.logger?.warn?.(`Super Memory managed API stop failed: ${err.message}`); }
    managedApiProcess = null;
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

  if (effectiveExclusiveMemory === true) {
    api.logger?.warn?.('Super Memory running in EXCLUSIVE memory slot mode — canonical markdown may diverge from memory-core');
    if (typeof api.registerMemoryCapability === 'function') {
      api.registerMemoryCapability({
        async promptBuilder(event = {}) {
          const base = ['Super Memory is the active OpenClaw memory slot. Preserve Workspace Markdown as canonical truth and use Super Memory search/get for recall.'];
          try {
            const query = cleanText(event.prompt || event.query || event.input || '');
            if (query) {
              const payload = await post('/prefetch', { query, limit: cfg.prePromptLimit || 8 });
              const text = payload.answer || payload.context || payload.text || payload.summary;
              if (text) base.push(`[Super Memory semantic context]\n${text}`);
            }
          } catch (err) {
            api.logger?.warn?.(`Super Memory capability promptBuilder failed: ${err.message}`);
          }
          return base;
        },
        flushPlanResolver: () => ({
          provider: 'super-memory',
          canonical: 'workspace_markdown',
          captureTurns: true,
          captureToolOutcomes: true,
          captureDecisions: true,
          redactSecrets: true,
          maintenance: { cleanup: true, semanticIndex: true, dreaming: true }
        }),
        runtime: {
          async getMemorySearchManager() {
            return { manager: createSearchManager() };
          },
          resolveMemoryBackendConfig() {
            return { backend: 'super-memory', canonical: 'workspace_markdown', vector: cfg.vectorBackend || 'sqlite_vec', apiBaseUrl: baseUrl };
          },
          async closeMemorySearchManager() {},
          async closeAllMemorySearchManagers() {}
        },
        publicArtifacts: {
          async listArtifacts() {
            return [
              { id: 'super-memory-daily', kind: 'markdown', path: 'memory/YYYY-MM-DD.md' },
              { id: 'super-memory-long-term', kind: 'markdown', path: 'MEMORY.md' },
              { id: 'super-memory-registers', kind: 'directory', path: 'memory/registers' },
              { id: 'super-memory-dreams', kind: 'directory', path: 'memory/dreams' }
            ];
          }
        }
      });
    }
  }

  if (cfg.registerDynamicMcpToolProxy === true && typeof api.registerTool === 'function') {
    registerTool({
      name: 'super_memory_mcp_tools_list',
      description: 'Development-only dynamic MCP tools/list proxy for Super Memory.',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
      handler: async () => get('/mcp-tools')
    });
  }

  if (typeof api.registerService === 'function') {
    api.registerService({
      id: 'super-memory-api',
      async start() {
        startManagedApiService();
        try {
          await get('/health');
          api.logger?.info?.('Super Memory API reachable in service.start()');
        } catch (err) {
          api.logger?.warn?.(`Super Memory API health check failed: ${err.message}. ${apiStartHint()}`);
        }
      },
      async stop() { stopManagedApiService(); }
    });
  }

  if (typeof api.on === 'function') {
    api.on('before_prompt_build', async (event = {}) => {
      const result = { systemPrompt: buildToolInstructions() };
      if (effectiveAutoContext === true) {
        try {
          const query = cleanText(event.prompt || event.query || '');
          if (query) {
            const payload = await post('/prefetch', { query, limit: cfg.prePromptLimit || 8 });
            const text = payload.answer || payload.context || payload.text || payload.summary;
            if (text) result.prependContext = `[Super Memory — relevant context]\n${text}`;
          }
        } catch (err) {
          api.logger?.warn?.(`Super Memory auto-context failed: ${err.message}`);
        }
      }
      return result;
    }, { priority: 10 });

    if (effectiveAutoSyncTurns === true) {
      // Hook agent_end + before_agent_finalize confirmed working via DB evidence.
      // Content blocks are arrays on Discord — flatten array content blocks to text.
      const syncTurnFromHook = async (hookName, event = {}, ctx = {}) => {
        if (event.success === false) return;
        try {
          const agentChannelMap = cfg.agentChannelMap || {};
          const eventChannel = event.channelId || event.channel || ctx.channelId || ctx.channel || event.accountId || ctx.accountId;
          const eventAgentId = event.agentId || event.agent || ctx.agentId || ctx.agent;
          const effectiveAgentId =
            (eventChannel && agentChannelMap[eventChannel]) ||
            eventAgentId ||
            cfg.agentId ||
            'lucas';
          const rawMessages = Array.isArray(event.messages)
            ? event.messages
            : (Array.isArray(ctx.messages) ? ctx.messages : []);
          const messages = rawMessages.slice(-8);
          const userMessage = messages
            .filter((m) => m && m.role === 'user')
            .map((m) => {
              const c = m.content;
              if (typeof c === 'string') return c;
              if (Array.isArray(c)) return c.map((b) => { if (typeof b === 'string') return b; if (b && typeof b === 'object') return b.text || b.content || b.value || JSON.stringify(b); return String(b); }).filter(Boolean).join('\n');
              return String(c || '');
            })
            .join('\n').slice(-6000);
          const assistantMessage = (() => {
            const assistantMessages = messages.filter((m) => m && m.role === 'assistant');
            // Take the LAST assistant message (final text reply), skip intermediate tool calls
            const lastAssistant = assistantMessages[assistantMessages.length - 1];
            if (!lastAssistant) return '';
            const c = lastAssistant.content;
            let text = '';
            if (typeof c === 'string') text = c;
            else if (Array.isArray(c)) text = c.map((b) => { if (typeof b === 'string') return b; if (b && typeof b === 'object') return b.text || b.content || b.value || JSON.stringify(b); return String(b); }).filter(Boolean).join('\n');
            else text = String(c || '');
            // Strip leading tool call JSON blocks from the last message
            const lines = text.split('\n').filter(l => !l.trim().startsWith('{'));
            return lines.join('\n').trim().slice(-6000);
          })();
          if (userMessage || assistantMessage) {
            await post('/sync-turn', {
              agent_id: effectiveAgentId,
              session_id: event.sessionId || event.sessionKey || ctx.sessionId || ctx.sessionKey || ctx.runId || event.runId,
              user_message: cleanText(userMessage),
              assistant_message: cleanText(assistantMessage),
              metadata: {
                hook: hookName,
                channelId: eventChannel,
                eventAgentId,
                runId: event.runId || ctx.runId,
                sessionKey: event.sessionKey || ctx.sessionKey
              }
            });
          } else {
            api.logger?.debug?.(`Super Memory ${hookName} skipped: no user/assistant messages`);
          }
        } catch (err) {
          api.logger?.warn?.(`Super Memory auto-sync ${hookName} failed: ${err.message}`);
        }
      };
      api.on('before_agent_finalize', async (event = {}, ctx = {}) => syncTurnFromHook('before_agent_finalize', event, ctx), { priority: 90 });
      api.on('agent_end', async (event = {}, ctx = {}) => syncTurnFromHook('agent_end', event, ctx), { priority: 90 });
    }

    api.on('before_compaction', async () => {
      if (effectiveAutoFlush === true) {
        try { await post('/auto', { text: '[pre-compact emergency flush]', save: true }); }
        catch (err) { api.logger?.warn?.(`Super Memory pre-compact flush failed: ${err.message}`); }
      }
    }, { priority: 5 });

    api.on('before_reset', async () => {
      if (effectiveAutoFlush === true) {
        try { await post('/auto', { text: '[session boundary — reset]', save: true }); }
        catch (err) { api.logger?.warn?.(`Super Memory reset flush failed: ${err.message}`); }
      }
    }, { priority: 5 });

    api.on('gateway_start', async () => {
      if (cfg.startupConsolidation === true) {
        try { await post('/consolidate', { strategy: 'startup', dry_run: true }); }
        catch (err) { api.logger?.warn?.(`Super Memory startup consolidation failed: ${err.message}`); }
      }
    }, { priority: 50 });
  } else if (cfg.registerSuperMemoryHooks === true) {
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

  if ((effectiveLegacyMemoryShims === true || effectiveExclusiveMemory === true) && typeof api.registerTool === 'function') {
    registerTool({
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

    registerTool({
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

  registerTool({
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

  registerTool({
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

  registerTool({
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

  registerTool({
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

  registerTool({
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

  registerTool({
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

  registerTool({
    name: 'super_memory_promote',
    description: 'Promote a Super Memory item to MEMORY.md and the matching register.',
    inputSchema: {
      type: 'object',
      properties: { memory_id: { type: 'string' } },
      required: ['memory_id']
    },
    handler: async (input) => post('/promote', input)
  });

  registerTool({
    name: 'super_memory_status',
    description: 'Show Super Memory local service status.',
    inputSchema: { type: 'object', properties: {} },
    handler: async () => get('/status')
  });

  // Phase 1-3 additional tools via HTTP bridge
  const additionalTools = [
    ['super_memory_remember_batch', 'Store multiple memories at once.', { type: 'object', properties: { memories: { type: 'array', items: { type: 'object' } } }, required: ['memories'] }, '/remember-batch'],
    ['super_memory_show', 'Get full content of a memory by ID.', { type: 'object', properties: { memory_id: { type: 'string' } }, required: ['memory_id'] }, '/show'],
    ['super_memory_context', 'Get recent context records.', { type: 'object', properties: { limit: { type: 'number', default: 10 } } }, '/context'],
    ['super_memory_todo', 'Create a quick TODO.', { type: 'object', properties: { task: { type: 'string' }, priority: { type: 'number', default: 5 } }, required: ['task'] }, '/todo'],
    ['super_memory_auto', 'Auto-extract memories from text.', { type: 'object', properties: { text: { type: 'string' }, save: { type: 'boolean', default: true } }, required: ['text'] }, '/auto'],
    ['super_memory_stats', 'Brain stats: counts and freshness.', { type: 'object', properties: {} }, '/stats'],
    ['super_memory_health', 'Health check: purity score, grade, warnings.', { type: 'object', properties: {} }, '/health'],
    ['super_memory_conflicts', 'Detect conflicting memories.', { type: 'object', properties: { content: { type: 'string' }, memory_id: { type: 'string' } } }, '/conflicts'],
    ['super_memory_provenance', 'Trace memory origin chain.', { type: 'object', properties: { memory_id: { type: 'string' }, action: { type: 'string', default: 'trace' } }, required: ['memory_id'] }, '/provenance'],
    ['super_memory_pin', 'Pin/unpin as permanent KB.', { type: 'object', properties: { memory_id: { type: 'string' }, action: { type: 'string', default: 'pin' } }, required: ['memory_id'] }, '/pin'],
    ['super_memory_consolidate', 'Run brain consolidation.', { type: 'object', properties: { strategy: { type: 'string', default: 'all' }, dry_run: { type: 'boolean', default: true } } }, '/consolidate'],
    ['super_memory_situation', 'Working situation snapshot.', { type: 'object', properties: {} }, '/situation'],
    ['super_memory_boundaries', 'Manage safety boundaries.', { type: 'object', properties: { domain: { type: 'string' }, content: { type: 'string' } } }, '/boundaries'],
  ];

  const getOnlyTools = new Set(['super_memory_stats', 'super_memory_health', 'super_memory_situation']);
  for (const [name, desc, schema, path] of additionalTools) {
    registerTool({
      name,
      description: desc,
      inputSchema: schema,
      handler: getOnlyTools.has(name) ? async () => get(path) : async (input) => post(path, input)
    });
  }
};
