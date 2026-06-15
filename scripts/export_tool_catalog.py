#!/usr/bin/env python3
"""Generate tool catalog documentation from MCP server descriptors.

Usage:
    python scripts/export_tool_catalog.py
    python scripts/export_tool_catalog.py --format json
    python scripts/export_tool_catalog.py --format markdown
    python scripts/export_tool_catalog.py --format both
"""
import argparse
import json
import sys
from pathlib import Path

# Add super_memory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import super_memory.mcp_server as mcp

def categorize_tool(name: str) -> str:
    """Categorize tool by name prefix."""
    if name.startswith('super_memory_honcho'):
        return 'honcho'
    elif name.startswith('super_memory_palace'):
        return 'mempalace'
    elif name.startswith('super_memory_cross_agent'):
        return 'cross_agent'
    elif name.startswith('super_memory_session'):
        return 'session'
    elif name.startswith('super_memory_lifecycle'):
        return 'lifecycle'
    elif name.startswith('super_memory_graph') or name.startswith('super_memory_spreading'):
        return 'graph'
    elif name.startswith('nmem_'):
        return 'neural_passthrough'
    elif any(name.startswith(f'super_memory_{x}') for x in [
        'remember', 'recall', 'context', 'stats', 'status', 'health', 'todo',
        'auto', 'show', 'promote', 'normalize', 'sanitize', 'prefetch',
        'sync_turn', 'memory_search', 'memory_get', 'diagnostics', 'contract', 'smoke'
    ]):
        return 'core'
    elif any(name.startswith(f'super_memory_{x}') for x in [
        'conflicts', 'provenance', 'source', 'version', 'pin', 'consolidate',
        'gaps', 'explain', 'situation', 'reflex', 'boundaries', 'train',
        'import', 'index', 'sync', 'telegram', 'visualize', 'store', 'watch'
    ]):
        return 'knowledge_mgmt'
    elif any(name.startswith(f'super_memory_{x}') for x in [
        'hypothesis', 'evidence', 'prediction', 'verify'
    ]):
        return 'cognitive'
    elif any(name.startswith(f'super_memory_{x}') for x in [
        'working_memory', 'attention', 'route', 'parallel', 'recall_arbitrate',
        'consolidation_cycle', 'conflict_resolve', 'promotion', 'feedback'
    ]):
        return 'routing'
    elif any(name.startswith(f'super_memory_{x}') for x in [
        'post_turn', 'session_start', 'session_end', 'delegation', 'cross_scope',
        'extract_claims', 'find_contradictions', 'resolve_contradiction',
        'agent_belief', 'create_session_summary', 'get_session_summary',
        'list_session_summaries', 'search_session_archives', 'session_health',
        'memory_pollution', 'export_memory'
    ]):
        return 'p0_p5'
    elif any(name.startswith(f'super_memory_{x}') for x in [
        'capture', 'handoff', 'cross_session', 'shared_recall',
        'promote_to_shared', 'list_agents'
    ]):
        return 'cross_session'
    else:
        return 'other'

def get_profile_visibility(name: str, all_profiles: dict) -> list[str]:
    """Determine which profiles expose this tool."""
    visible = []
    for profile in ['user', 'admin', 'readonly']:
        mcp.MCP_PROFILE = profile
        tools = {t['name'] for t in mcp._tool_descriptors()}
        if name in tools:
            visible.append(profile)
    return visible

def export_json(tools: list[dict], output: Path):
    """Export tools as JSON."""
    catalog = {
        "version": "0.1.0",
        "generated_at": "2026-06-15T11:00:00Z",
        "total_tools": len(tools),
        "tools": tools
    }
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"✅ JSON catalog: {output} ({len(tools)} tools)")

def export_markdown(tools: list[dict], output: Path):
    """Export tools as Markdown, chunked if needed."""
    lines = [
        "# Super-Memory Tool Catalog",
        "",
        f"**Total Tools:** {len(tools)}",
        "**Generated:** 2026-06-15",
        "**Version:** 0.1.0",
        "",
        "## Tools by Category",
        ""
    ]
    
    # Group by category
    by_cat = {}
    for t in tools:
        by_cat.setdefault(t['category'], []).append(t)
    
    for cat, cat_tools in sorted(by_cat.items()):
        lines.append(f"### {cat.replace('_', ' ').title()} ({len(cat_tools)} tools)")
        lines.append("")
        
        for tool in sorted(cat_tools, key=lambda x: x['name']):
            lines.append(f"#### `{tool['name']}`")
            lines.append("")
            lines.append(f"**Description:** {tool.get('description', 'No description')}")
            lines.append("")
            
            if tool.get('profiles'):
                lines.append(f"**Profiles:** {', '.join(tool['profiles'])}")
                lines.append("")
            
            schema = tool.get('inputSchema', {})
            props = schema.get('properties', {})
            required = schema.get('required', [])
            
            if props:
                lines.append("**Parameters:**")
                for pname, pschema in props.items():
                    req = "✅" if pname in required else "⚪"
                    ptype = pschema.get('type', 'any')
                    pdesc = pschema.get('description', '')
                    lines.append(f"- {req} `{pname}` ({ptype}): {pdesc}")
                lines.append("")
            
            lines.append("---")
            lines.append("")
    
    # Check if chunking needed
    if len(lines) <= 300:
        output.write_text('\n'.join(lines))
        print(f"✅ Markdown catalog: {output} ({len(lines)} lines)")
    else:
        # Write in chunks
        output.write_text('\n'.join(lines[:250]))
        print(f"✅ Markdown catalog (initial): {output} (250 lines)")
        
        remaining = lines[250:]
        with output.open('a') as f:
            while remaining:
                chunk = remaining[:250]
                f.write('\n'.join(chunk) + '\n')
                print(f"✅ Appended {len(chunk)} lines")
                remaining = remaining[250:]

def main():
    parser = argparse.ArgumentParser(description='Export super-memory tool catalog')
    parser.add_argument('--format', choices=['json', 'markdown', 'both'], default='both')
    args = parser.parse_args()
    
    # Ensure docs/ exists
    docs_dir = Path(__file__).parent.parent / 'docs'
    docs_dir.mkdir(exist_ok=True)
    
    # Get all tools from admin profile
    mcp.MCP_PROFILE = 'admin'
    descriptors = mcp._tool_descriptors()
    
    # Build tool records
    tools = []
    for desc in descriptors:
        name = desc['name']
        tool = {
            'name': name,
            'category': categorize_tool(name),
            'description': desc.get('description', ''),
            'inputSchema': desc.get('inputSchema', {}),
            'profiles': get_profile_visibility(name, {'user': None, 'admin': None, 'readonly': None})
        }
        tools.append(tool)
    
    # Export
    if args.format in ['json', 'both']:
        export_json(tools, docs_dir / 'TOOL_CATALOG.json')
    
    if args.format in ['markdown', 'both']:
        export_markdown(tools, docs_dir / 'TOOL_CATALOG.md')
    
    print(f"\n✅ Tool catalog export complete: {len(tools)} tools")

if __name__ == '__main__':
    main()
