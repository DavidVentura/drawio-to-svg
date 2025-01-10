import math
import enum

import svg

from dataclasses import dataclass
from typing import Optional


@dataclass
class Geometry:
    x: float
    y: float
    width: float
    height: float
    relative: Optional[int] = None

    @staticmethod
    def from_geom(item: "Point | Geometry") -> "Geometry":
        if isinstance(item, Point):
            return Geometry(
                x=item.x,
                y=item.y,
                width=0,
                height=0,
            )
        else:
            return Geometry(
                x=item.x,
                y=item.y,
                width=item.width,
                height=item.height,
            )

    def stretch_to_contain_point(self: "Geometry", item: "Point", stroke_width: float) -> "Geometry":
        hw = stroke_width / 2
        return self.stretch_to_contain(Geometry(item.x-hw, item.y-hw, item.x+hw, item.y+hw))

    def stretch_to_contain(self: "Geometry | None", item: "Geometry") -> "Geometry":
        if self is None:
            return Geometry.from_geom(item)
        if isinstance(item, Point):
            min_x = min(self.x, item.x)
            min_y = min(self.y, item.y)
            max_x = max(self.x + self.width, item.x)
            max_y = max(self.y + self.height, item.y)
        else:
            min_x = min(self.x, item.x)
            min_y = min(self.y, item.y)
            max_x = max(self.x + self.width, item.x + item.width)
            max_y = max(self.y + self.height, item.y + item.height)

        return Geometry(
            width=max_x - min_x,
            height=max_y - min_y,
            x=min_x,
            y=min_y,
        )


class StrokeStyle(enum.Enum):
    SOLID = enum.auto()
    DOTTED_1 = enum.auto()  # 1 1
    DOTTED_2 = enum.auto()  # 1 2
    DOTTED_3 = enum.auto()  # 1 4
    DASHED_1 = enum.auto()  # 2
    DASHED_2 = enum.auto()  # 8 8
    DASHED_3 = enum.auto()  # 12 12

    @staticmethod
    def from_dash_pattern(dp: str | None) -> "StrokeStyle":
        match dp:
            case "1 1":
                return StrokeStyle.DOTTED_1
            case "1 2":
                return StrokeStyle.DOTTED_2
            case "1 4":
                return StrokeStyle.DOTTED_3
            case None:
                return StrokeStyle.DASHED_1
            case "8 8":
                return StrokeStyle.DASHED_2
            case "12 12":
                return StrokeStyle.DASHED_3
        raise ValueError(f"Illegal dash pattern {dp}")

    def as_props(self) -> dict[str, str]:
        match self:
            case StrokeStyle.SOLID:
                da = "none"
            case StrokeStyle.DOTTED_1:
                da = "1 1"
            case StrokeStyle.DOTTED_2:
                da = "1 2"
            case StrokeStyle.DOTTED_3:
                da = "1 4"
            case StrokeStyle.DASHED_1:
                da = "3 3"
            case StrokeStyle.DASHED_2:
                da = "8 8"
            case StrokeStyle.DASHED_3:
                da = "12 12"
            case _:
                raise ValueError(f"Invalid enum variant {self}")

        return {
            "stroke_dasharray": da,
        }


@dataclass
class Stroke:
    style: StrokeStyle
    width: float
    color: str


class Shape(enum.Enum):
    Rect = enum.auto()
    Curly = enum.auto()

    @staticmethod
    def from_str(s: str) -> "Shape":
        match s:
            case "rect":
                return Shape.Rect
            case "curlyBracket":
                return Shape.Curly
            case unsupported:
                raise NotImplementedError(f"Shape {unsupported}")


@dataclass
class Cell:
    id: str
    value: Optional[str]
    vertex: bool
    geometry: Optional[Geometry]
    fillColor: str
    stroke: Stroke
    opacity: float
    # Labels can be right next to the actual rect
    # regardless of the alignment within the label itself
    labelPosition: str
    verticalLabelPosition: str
    shape: Shape
    direction: "Direction"
    parent_node: Optional["Cell"]
    is_group: bool

    # Do not use. only for debugging
    _style: dict[str, str]

    def contains(self, p: "Point") -> bool:
        assert self.geometry

        if p.x < self.geometry.x:
            return False
        if p.x > self.geometry.x + self.geometry.width:
            return False
        if p.y < self.geometry.y:
            return False
        if p.y > self.geometry.y + self.geometry.height:
            return False
        return True

    def center_points_with_sides(self) -> list[tuple["Point", "Side"]]:
        return list(
            zip(
                self.center_points(),
                [
                    Side.LEFT,
                    Side.RIGHT,
                    Side.TOP,
                    Side.BOTTOM,
                ],
            )
        )

    def center_points(self) -> list["Point"]:
        return [
            # Left center
            Point(self.geometry.x, self.geometry.y + self.geometry.height / 2),
            # Right center
            Point(self.geometry.x + self.geometry.width, self.geometry.y + self.geometry.height / 2),
            # Top center
            Point(self.geometry.x + self.geometry.width / 2, self.geometry.y),
            # Bottom center
            Point(self.geometry.x + self.geometry.width / 2, self.geometry.y + self.geometry.height),
        ]


@dataclass
class EdgeLabel:
    id: str
    value: str
    pathPercentage: float
    orthogonalDistance: float
    offset: 'Point'
    __doc__ = """
    EdgeLabel abuses the cell format quite a bit:

    <mxCell value="Text" style="edgeLabel" parent="iTblz-XGe7cfMYIo-zEC-33">
      <mxGeometry x="0.59" y="9" relative="1" as="geometry">
        <mxPoint x="5" y="1" as="offset" />
      </mxGeometry>
    </mxCell>

    The mxGeometry X means "How far along the arrow, as a percentage (0.0-1.0) should the label be
    The mxGeometry Y is "orthogonal distance to the arrow"

    The mxPoint X/Y are static offsets from the previous point
    """

@dataclass
class Text:
    id: str
    value: str
    geometry: Geometry
    strokeColor: str
    fontSize: str
    alignment: str
    fontFamily: str
    verticalAlign: str
    verticalPosition: str
    horizontalPosition: str
    fontStyle: "FontStyle"
    fontColor: str

    @property
    def direction(self) -> "Direction":
        # Direction _cannot_ be set on Text
        return Direction.EAST

    @property
    def styled_as_html(self):
        return "<" in self.value

    @staticmethod
    def from_styles(id_: str, text: str, geometry: Geometry,
                    verticalPosition: str,
                    horizontalPosition: str,
                    style: dict[str, str]) -> "Text":
        va_lut = {
            "middle": "center",
            "bottom": "end",
            "top": "start",
        }
        color = style.get("strokeColor", "#000")
        if color == "none":
            color = "#000"

        # TODO: there's a "basic style" and "html style"
        # even though both can be set at the same time,
        # only one is valid to use.
        # Switch styles to BasicStyle | HTMLStyle
        # or similar
        return Text(
            id=id_,
            value=text,
            geometry=geometry,
            strokeColor=color,
            fontSize=style.get("fontSize", "12px"),
            alignment=style.get("align", "center"),
            fontFamily=style.get("fontFamily", "Helvetica"),
            verticalAlign=va_lut[style.get("verticalAlign", "middle")],
            verticalPosition=verticalPosition,
            horizontalPosition=horizontalPosition,
            fontStyle=FontStyle.from_bitflags(int(style.get("fontStyle", 0))),
            fontColor=style.get("fontColor", "#000"),
        )


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.sqrt((other.x - self.x) ** 2 + (other.y - self.y) ** 2)

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y)

    def __mul__(self, other: float) -> "Point":
        return Point(self.x * other, self.y * other)

    def normalized(self) -> "Point":
        if self.x == 0:
            x = 0
        else:
            x = self.x / abs(self.x)
        if self.y == 0:
            y = 0
        else:
            y = self.y / abs(self.y)

        return Point(x, y)

    def midpoint(self, other: "Point") -> "Point":
        minx = min([self.x, other.x])
        miny = min([self.y, other.y])
        maxx = max([self.x, other.x])
        maxy = max([self.y, other.y])

        res = Point((maxx + minx) / 2, (maxy + miny) / 2)
        return res

    def contains(self, other: "Point") -> bool:
        # For interface matching with Cell
        return False


@dataclass
class ArrowAtNode:
    node: Cell
    X: Optional[float]
    Y: Optional[float]


@dataclass
class Arrow:
    id: str
    value: Optional[str]
    vertex: bool
    parent: str
    geometry: Optional[Geometry]
    source: Point | ArrowAtNode
    target: Point | ArrowAtNode
    points: list[Point]
    start_style: str
    end_style: str
    stroke: Stroke


@dataclass
class Root:
    cells: list[Cell]


@dataclass
class Model:
    dx: float
    dy: float
    grid: int
    grid_size: int
    root: Root


@dataclass
class Diagram:
    name: str
    id: str
    model: Model


@dataclass
class MxFile:
    version: str
    diagrams: list[Diagram]


@dataclass
class ArrowPoints:
    source: Point | None
    target: Point | None
    extra: list[Point]


@dataclass
class HTMLDiv(svg.Element):
    element_name: str = "div"
    xmlns: str = "http://www.w3.org/1999/xhtml"


@dataclass
class HTMLSpan(svg.Element):
    text: str
    element_name: str = "span"


class Side(enum.Enum):
    LEFT = enum.auto()
    RIGHT = enum.auto()
    TOP = enum.auto()
    BOTTOM = enum.auto()


class Direction(enum.Enum):
    WEST = enum.auto()
    EAST = enum.auto()
    SOUTH = enum.auto()
    NORTH = enum.auto()

    @staticmethod
    def from_str(s: str) -> "Direction":
        return Direction[s.upper()]

    def rotation_angle(self) -> float:
        match self:
            case Direction.SOUTH:
                return 270
            case Direction.NORTH:
                return 90
            case Direction.WEST:
                return 180
            case Direction.EAST:
                return 0

@dataclass
class FontStyle:
    bold: bool
    italic: bool
    underline: bool

    @staticmethod
    def from_bitflags(val: int) -> 'FontStyle':
        return FontStyle(
            bold=val & 0b1 == 0b1,
            italic=val & 0b10 == 0b10,
            underline=val & 0b100 == 0b100,
        )
