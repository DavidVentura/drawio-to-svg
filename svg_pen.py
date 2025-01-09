from fontTools.pens.basePen import BasePen
from svg import MoveTo, LineTo, CubicBezier, QuadraticBezier, Path, ClosePath, Scale


class SVGPathPen(BasePen):
    def __init__(self, glyphSet, scale: float = 1.0):
        BasePen.__init__(self, glyphSet)
        self._path = []
        self.scale = scale

    def _moveTo(self, pt):
        x, y = pt
        self._path.append(MoveTo(x*self.scale, y*self.scale))

    def _lineTo(self, pt):
        x, y = pt
        self._path.append(LineTo(x*self.scale, y*self.scale))

    def _curveToOne(self, pt1, pt2, pt3):
        self._path.append(CubicBezier(
            pt1[0] * self.scale, pt1[1] * self.scale,
            pt2[0] * self.scale, pt2[1] * self.scale,
            pt3[0] * self.scale, pt3[1] * self.scale
        ))

    def _qCurveToOne(self, pt1, pt2):
        self._path.append(QuadraticBezier(
            pt1[0]*self.scale, pt1[1]*self.scale,
            pt2[0]*self.scale, pt2[1]*self.scale
        ))

    def _closePath(self):
        self._path.append(ClosePath())

    def _endPath(self):
        pass

    def getCommands(self) -> Path:
        # The font data is y-mirrored, so y-mirror it back
        return Path(d=self._path, transform=[Scale(1.0, -1.0)])
