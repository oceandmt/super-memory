#!/usr/bin/env python3
"""Generate GitHub feature image for super-memory."""

from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1280, 640
OUT = "/home/oceandmt/.openclaw/workspace/projects/super-memory-github/docs/assets/super-memory-feature.png"

# Colors - dark cyber theme
BG = (13, 17, 23)       # GitHub dark bg
CARD = (22, 27, 34)     # card bg
ACCENT = (88, 166, 255)  # blue accent
GREEN = (63, 185, 80)    # green
PURPLE = (191, 97, 216)  # purple
ORANGE = (255, 165, 0)   # orange
GRAY = (139, 148, 158)   # text gray
WHITE = (240, 246, 252)  # text white
DIM = (48, 54, 61)       # border

img = Image.new("RGBA", (W, H), (*BG, 255))
draw = ImageDraw.Draw(img)

# Try to load fonts
try:
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 52)
    font_sub = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 22)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 16)
    font_tag = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 14)
except:
    font_title = ImageFont.load_default()
    font_sub = ImageFont.load_default()
    font_small = ImageFont.load_default()
    font_tag = ImageFont.load_default()

# Background grid pattern (subtle)
for x in range(0, W, 40):
    draw.line([(x, 0), (x, H)], fill=(22, 27, 34, 100), width=1)
for y in range(0, H, 40):
    draw.line([(0, y), (W, y)], fill=(22, 27, 34, 100), width=1)

# Neural network nodes visual (decorative)
nodes = [
    (100, 100), (200, 80), (350, 120), (500, 90),
    (150, 250), (300, 280), (450, 240), (600, 260),
    (80, 400), (220, 420), (380, 380), (520, 430), (650, 400),
    (1000, 100), (1100, 150), (1050, 280), (1150, 350), (1080, 500),
    (700, 100), (800, 180), (750, 300), (850, 400), (900, 520),
]

# Draw connections (synapses)
for i, (x1, y1) in enumerate(nodes):
    for j, (x2, y2) in enumerate(nodes):
        if i < j:
            dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
            if dist < 200 and dist > 40:
                alpha = max(10, int(60 - dist/4))
                draw.line([(x1, y1), (x2, y2)], fill=(88, 166, 255, alpha), width=1)

# Draw nodes with glow
for x, y in nodes:
    # Glow
    for r in [8, 5, 3]:
        alpha_glow = 60 - r * 7
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(88, 166, 255, max(0, alpha_glow)))
    # Core
    draw.ellipse([x-2, y-2, x+2, y+2], fill=(88, 166, 255, 200))

# Left panel - Hero text
draw.text((60, 60), "Super Memory", fill=ORANGE, font=font_title)
draw.text((60, 130), "Local Multi-Layer Memory for OpenClaw", fill=WHITE, font=font_sub)
draw.text((60, 165), "Multi-Agent Systems", fill=WHITE, font=font_sub)

# Feature tags
tags = ["🧠 Dream Engine", "⚡ Self-Improvement", "🌐 Cross-Agent Memory", 
        "📦 Semantic Closets", "🔗 Cognitive Graph", "🎯 Recall Arbitration"]
y_start = 230
for i, tag in enumerate(tags):
    row = i // 2
    col = i % 2
    tx = 60 + col * 290
    ty = y_start + row * 38

    # Tag pill
    pill_w = 260
    pill_h = 30
    draw.rounded_rectangle([tx, ty, tx+pill_w, ty+pill_h], radius=4, 
                          fill=(*CARD, 200), outline=(*DIM, 200), width=1)
    draw.text((tx + 12, ty + 6), tag, fill=ACCENT, font=font_tag)

# Right panel - Architecture layers
layers = [
    ("Layer 1", "Verbatim Memory", ACCENT),
    ("Layer 2", "Structured / Claims", GREEN),
    ("Layer 3", "Semantic Palace", PURPLE),
    ("Layer 4", "Cognitive Graph", ORANGE),
]

lx = 700
ly = 110
for i, (name, desc, color) in enumerate(layers):
    y = ly + i * 70
    # Layer card
    card_w = 480
    card_h = 55
    draw.rounded_rectangle([lx, y, lx+card_w, y+card_h], radius=6, 
                          fill=(*CARD, 200), outline=(*color, 100), width=1)
    # Left color bar
    draw.rounded_rectangle([lx+4, y+4, lx+8, y+card_h-4], radius=2, fill=(*color, 220))
    # Text
    draw.text((lx + 24, y + 8), name, fill=color, font=font_tag)
    draw.text((lx + 120, y + 8), desc, fill=GRAY, font=font_small)

# Bottom bar
draw.rounded_rectangle([0, H-50, W, H], radius=0, fill=(*CARD, 255))
draw.text((30, H-35), "v2.2.0", fill=GRAY, font=font_small)
draw.text((130, H-35), "•", fill=DIM, font=font_small)
draw.text((150, H-35), "2,312 memories", fill=GRAY, font=font_small)
draw.text((330, H-35), "•", fill=DIM, font=font_small)
draw.text((350, H-35), "254 MCP tools", fill=GRAY, font=font_small)
draw.text((530, H-35), "•", fill=DIM, font=font_small)
draw.text((550, H-35), "102 plugin tools", fill=GRAY, font=font_small)

draw.text((W-300, H-35), "github.com/oceandmt/super-memory", fill=ACCENT, font=font_small)

# Save
img.save(OUT, "PNG")
print(f"✅ Saved: {OUT}")
print(f"   Size: {W}x{H}")
