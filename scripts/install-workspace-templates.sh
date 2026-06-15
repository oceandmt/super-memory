#!/usr/bin/env bash
# Install Super Memory OpenClaw workspace templates and skills
# Run from super-memory project root

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$HOME/.openclaw/plugins/super-memory"
WORKSPACE_DIR="$HOME/.openclaw/workspace"
SKILLS_DIR="$HOME/.openclaw/workspace/skills"

echo "Super Memory workspace template installer"
echo "Repository: $REPO_ROOT"
echo "Plugin dir: $PLUGIN_DIR"
echo "Workspace:  $WORKSPACE_DIR"
echo "Skills:     $SKILLS_DIR"
echo

mkdir -p "$WORKSPACE_DIR" "$SKILLS_DIR"

# Workspace templates
echo "Installing workspace templates..."
TEMPLATES_DIR="$PLUGIN_DIR/workspace-templates"
if [[ -d "$TEMPLATES_DIR" ]]; then
    for f in "$TEMPLATES_DIR"/*.md; do
        target="$WORKSPACE_DIR/$(basename "$f")"
        if [[ -f "$target" ]]; then
            echo "  Skipping (exists): $(basename "$f")"
        else
            cp "$f" "$target"
            echo "  Installed: $(basename "$f")"
        fi
    done
    # memory subdir
    if [[ -d "$TEMPLATES_DIR/memory" ]]; then
        mkdir -p "$WORKSPACE_DIR/memory"
        for f in "$TEMPLATES_DIR/memory"/*.md; do
            target="$WORKSPACE_DIR/memory/$(basename "$f")"
            if [[ -f "$target" ]]; then
                echo "  Skipping (exists): memory/$(basename "$f")"
            else
                cp "$f" "$target"
                echo "  Installed: memory/$(basename "$f")"
            fi
        done
    fi
else
    echo "  WARNING: $TEMPLATES_DIR not found"
fi

# Skills
echo
echo "Installing skills..."
SKILLS_SRC="$PLUGIN_DIR/skills"
if [[ -d "$SKILLS_SRC" ]]; then
    for skill_dir in "$SKILLS_SRC"/*; do
        if [[ -d "$skill_dir" && -f "$skill_dir/SKILL.md" ]]; then
            skill_name="$(basename "$skill_dir")"
            target="$SKILLS_DIR/$skill_name"
            if [[ -d "$target" ]]; then
                echo "  Skipping (exists): $skill_name"
            else
                cp -r "$skill_dir" "$target"
                echo "  Installed skill: $skill_name"
            fi
        fi
    done
else
    echo "  WARNING: $SKILLS_SRC not found"
fi

echo
echo "Installation complete."
echo
echo "Next steps:"
echo "1. Ensure OpenClaw config has:"
echo "   - tools.profile: \"full\" or tools.allow includes \"group:plugins\""
echo "   - plugins.load.paths includes \"$PLUGIN_DIR\""
echo "   - plugins.slots.memory: \"super-memory\""
echo "2. Run: openclaw config validate"
echo "3. Run: openclaw plugins doctor"
echo "4. Start API: systemctl --user start super-memory-api.service"
echo "5. Verify: curl http://127.0.0.1:8765/status"
echo "6. Restart gateway: openclaw gateway restart"
echo "6. Verify: openclaw status"
