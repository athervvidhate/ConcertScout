"""Build standalone logo paths from the app's licensed Anton font.

Run with: uv run --no-project --with fonttools --with brotli scripts/brand/build-logo.py
PNG/ICO renditions are generated with the frontend's sharp dependency.
"""
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'frontend/public/brand'
font = TTFont(ROOT / 'frontend/app/fonts/anton.woff2')
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
x = 0
letters = []
for letter in 'CONCERT SCOUT':
    glyph = glyphs[cmap[ord(letter)]]
    pen = SVGPathPen(glyphs)
    glyph.draw(pen)
    if pen.getCommands():
        letters.append(f'<path transform="translate({x} 0)" d="{pen.getCommands()}"/>')
    x += glyph.width + 12
scale = 51 / font['OS/2'].sCapHeight
width = round(94 + x * scale)
# Ticket cut-outs and a southwest compass tail are true negative space.
shape = 'M16 4H64Q76 4 76 16V23A9 9 0 0 0 76 41V48Q76 60 64 60H16Q4 60 4 48V41A9 9 0 0 0 4 23V16Q4 4 16 4ZM22 49L38 27L47 35Z'
needle = 'M38 27L61 14L47 35L44 29Z'
for name, ink, accent in [('light', '#12261f', '#c4461f'), ('dark', '#e8f0eb', '#ff7449'), ('pine', '#eef4ef', '#ff9a78')]:
    mark = f'<path fill="{ink}" fill-rule="evenodd" d="{shape}"/><path fill="{accent}" d="{needle}"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 64" role="img" aria-label="Concert Scout"><title>Concert Scout</title>{mark}<g fill="{ink}" transform="translate(94 57) scale({scale} {-scale})">{"".join(letters)}</g></svg>\n'
    (OUT / f'logo-{name}.svg').write_text(svg)
    (OUT / f'mark-{name}.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 64"><title>Concert Scout</title>{mark}</svg>\n')
favicon = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><style>.ticket{{fill:#12261f}}.needle{{fill:#c4461f}}@media(prefers-color-scheme:dark){{.ticket{{fill:#e8f0eb}}.needle{{fill:#ff7449}}}}</style><g transform="translate(0 8)"><path class="ticket" fill-rule="evenodd" d="{shape}"/><path class="needle" d="{needle}"/></g></svg>\n'
(ROOT / 'frontend/app/icon.svg').write_text(favicon)
