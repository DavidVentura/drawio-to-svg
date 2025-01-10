import math

import svg

from dataclasses import dataclass

from fontTools.ttLib import TTFont
from svg_pen import SVGPathPen


@dataclass
class TextLine:
    pen: SVGPathPen
    w: float
    h: float
    ascent: float

    def path(self, x_offset: float = 0.0, y_offset: float = 0.0) -> svg.Path:
        return self.pen.getCommands(x_offset, y_offset)

    @property
    def descent(self) -> float:
        """
        How much, in pixels, the font should be offset from origin, downwards
        """
        return self.h - self.ascent


class FontRenderer:
    def __init__(self, font_path: str, font_size_px: int):
        self.font = TTFont(font_path)
        self.glyph_set = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.units_per_em = float(self.font["head"].unitsPerEm)
        self.scale = font_size_px / self.units_per_em
        self.hhea = self.font["hhea"]
        self.font_height_px = self.units_per_em * self.scale

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
                tl = TextLine(pen, x_offset * self.scale, height * self.scale, self.hhea.ascent * self.scale)
                ret.append(tl)
                x_offset = 0.0
                pen = SVGPathPen(self.glyph_set, self.scale)

            glyf.draw(pen, self.glyph_set.glyfTable, x_offset)
            x_offset += glyph.width

        tl = TextLine(pen, x_offset * self.scale, height * self.scale, self.hhea.ascent * self.scale)
        ret.append(tl)
        return ret
