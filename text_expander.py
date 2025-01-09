import svg
from fontTools.ttLib import TTFont
from svg_pen import SVGPathPen

class FontRenderer:
    def __init__(self, font_path: str, font_size_px: int):
        self.font = TTFont(font_path)
        self.glyph_set = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.units_per_em = float(self.font['head'].unitsPerEm)
        self.scale = font_size_px / self.units_per_em

    def render(self, data: str) -> tuple[svg.Path, float, float]:
        """
        returns bounding-box width, height
        """
        pen = SVGPathPen(self.glyph_set, self.scale)

        height = self.units_per_em
        offset = 0.0

        for char in data:
            glyph_name = self.cmap.get(ord(char))
            glyph = self.glyph_set[glyph_name]
            glyf = self.glyph_set.glyfTable[glyph_name]
            glyf.draw(pen, self.glyph_set.glyfTable, offset)
            offset += glyph.width

        path = pen.getCommands()
        return path, offset * self.scale, height * self.scale


def main():
    paths = []
    maxw = 0.0
    hoff = 0.0
    for fn in ["helvetica.ttf", "helvetica-bold.ttf", "helvetica-italic.ttf"]:
        f = FontRenderer(fn, 16)
        p, w, h = f.render("Asd, this is a TEST !@#$%^&*()")
        maxw = max(w, maxw)
        paths.append(f'''<g transform="translate(0, {hoff})">{p}</g>''')
        hoff += h

    print(f'''
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {maxw} {hoff}">
          {"".join(paths)}
    </svg>
    '''
          )

main()
