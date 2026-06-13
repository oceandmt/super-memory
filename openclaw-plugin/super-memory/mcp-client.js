const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');

class SuperMemoryMcpClient {
  constructor(options = {}) {
    this.command = options.command || 'super-memory-mcp';
    this.args = options.args || ['--stdio', '--profile', options.profile || 'normal'];
    this.env = { ...process.env, ...(options.env || {}) };
    this.proc = null;
    this.nextId = 1;
    this.pending = new Map();
  }

  start() {
    if (this.proc) return;
    this.proc = spawn(this.command, this.args, { stdio: ['pipe', 'pipe', 'pipe'], env: this.env });
    const rl = createInterface({ input: this.proc.stdout });
    rl.on('line', (line) => this._handleLine(line));
    this.proc.on('exit', (code, signal) => {
      for (const [, pending] of this.pending) pending.reject(new Error(`super-memory MCP exited code=${code} signal=${signal}`));
      this.pending.clear();
      this.proc = null;
    });
  }

  async initialize() {
    this.start();
    return this.request('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'super-memory-openclaw-plugin' } });
  }

  async listTools() {
    return this.request('tools/list', {});
  }

  async callTool(name, args = {}) {
    return this.request('tools/call', { name, arguments: args });
  }

  request(method, params = {}) {
    this.start();
    const id = this.nextId++;
    const payload = JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n';
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(payload, (err) => {
        if (err) {
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  close() {
    if (this.proc) this.proc.kill();
    this.proc = null;
  }

  _handleLine(line) {
    let msg;
    try { msg = JSON.parse(line); } catch { return; }
    const pending = this.pending.get(msg.id);
    if (!pending) return;
    this.pending.delete(msg.id);
    if (msg.error) pending.reject(new Error(msg.error.message || 'MCP error'));
    else pending.resolve(msg.result);
  }
}

module.exports = { SuperMemoryMcpClient };
