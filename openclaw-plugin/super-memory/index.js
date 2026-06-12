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
