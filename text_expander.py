import math

import svg

from dataclasses import dataclass

from fontTools.ttLib import TTFont
from svg_pen import SVGPathPen


@dataclass
class TextLine:
    path: svg.Path
    w: float
    h: float


class FontRenderer:
    def __init__(self, font_path: str, font_size_px: int):
        self.font = TTFont(font_path)
        self.glyph_set = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.units_per_em = float(self.font["head"].unitsPerEm)
        self.scale = font_size_px / self.units_per_em

    def render(self, data: str, max_w: float = math.inf) -> list[TextLine]:
        height = self.units_per_em
        x_offset = 0.0

        max_w = max_w / self.scale
        ret = []

        pen = SVGPathPen(self.glyph_set, self.scale)
        for char in data:
            glyph_name = self.cmap.get(ord(char))
            glyph = self.glyph_set[glyph_name]
            glyf = self.glyph_set.glyfTable[glyph_name]
            # TODO: this is letter-level word-wrap
            # Maybe better to do word-level?
            if (x_offset + glyph.width) > max_w:
                path = pen.getCommands()
                tl = TextLine(path, x_offset * self.scale, height * self.scale)
                ret.append(tl)
                x_offset = 0.0
                pen = SVGPathPen(self.glyph_set, self.scale)

            glyf.draw(pen, self.glyph_set.glyfTable, x_offset)
            x_offset += glyph.width

        path = pen.getCommands()
        tl = TextLine(path, x_offset * self.scale, height * self.scale)
        ret.append(tl)
        path = pen.getCommands()
        return ret


def main():
    paths = []
    maxw = 0.0
    hoff = 0.0
    for fn in ["helvetica.ttf", "helvetica-bold.ttf", "helvetica-italic.ttf"]:
        f = FontRenderer(fn, 16)
        tls = f.render("aaaaaaabbbbbccc", 100)
        for line in tls:
            maxw = max(line.w, maxw)
            paths.append(f"""<g transform="translate(0, {hoff})">{line.path}</g>""")
            hoff += line.h

    print(
        f"""
    <svg width="{maxw*2}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {maxw} {hoff}">
          {"".join(paths)}
    </svg>
    """
    )


main()
