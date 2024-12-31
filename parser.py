import math
import pprint

import svg

from dataclasses import dataclass
from typing import List, Optional

import xml.etree.ElementTree as ET


@dataclass
class Geometry:
    x: Optional[float]
    y: Optional[float]
    width: Optional[float]
    height: Optional[float]
    relative: Optional[int]


@dataclass
class Cell:
    id: str
    value: Optional[str]
    vertex: bool
    parent: str
    geometry: Optional[Geometry]
    strokeColor: str
    fillColor: str
    # Do not use. only for debugging
    _style: dict[str, str]

    def contains(self, p: "Point") -> bool:
        assert self.geometry
        assert self.geometry.x
        assert self.geometry.y
        assert self.geometry.width
        assert self.geometry.height

        if p.x < self.geometry.x:
            return False
        if p.x > self.geometry.x + self.geometry.width:
            return False
        if p.y < self.geometry.y:
            return False
        if p.y > self.geometry.y + self.geometry.height:
            return False
        return True


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

    @staticmethod
    def from_styles(id_: str, text: str, geometry: Geometry, style: dict[str, str]) -> "Text":
        va_lut = {
                "middle": "center",
                "bottom": "end",
                "top": "start",
        }
        return Text(
            id=id_,
            value=text,
            geometry=geometry,
            strokeColor=style.get("strokeColor", "#000"),
            fontSize=style.get("fontSize", "12px"),
            alignment=style.get("align", "center"),
            fontFamily=style.get("fontFamily", "Helvetica"),
            verticalAlign=va_lut[style.get("verticalAlign", "middle")],
        )


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.sqrt((other.x - self.x) ** 2 + (other.y - self.y) ** 2)


@dataclass
class ArrowAtNode:
    node: str
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
    strokeColor: str
    points: list[Point]
    start_style: str
    end_style: str


@dataclass
class Root:
    cells: List[Cell]


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
    diagrams: List[Diagram]


def opt_float(val: str | None) -> float | None:
    if val is None:
        return None
    return float(val)


def opt_int(val: str | None) -> int | None:
    if val is None:
        return None
    return int(val)


def parse_geometry(geom_elem) -> Optional[Geometry]:
    if geom_elem is None:
        return None
    return Geometry(
        x=opt_float(geom_elem.get("x", 0)),
        y=opt_float(geom_elem.get("y", 0)),
        width=opt_float(geom_elem.get("width")),
        height=opt_float(geom_elem.get("height")),
        relative=opt_int(geom_elem.get("relative")),
    )


def parse_styles(styles: str | None) -> dict[str, str]:
    if styles is None:
        return {}
    items = styles.split(";")
    ret = {}
    for item in items:
        if item == "":
            continue
        k, _, v = item.partition("=")
        ret[k] = v
    return ret


# keys are sourcePoint, targetPoint
# FIXME ugh
def parse_arrow_points(geom: ET.Element) -> tuple[dict[str, Point], list[Point]]:
    points = {}
    for point in geom.findall("mxPoint"):
        point_type = point.get("as")
        assert point_type in ["sourcePoint", "targetPoint"]
        points[point_type] = Point(
            x=float(point.get("x", 0)),
            y=float(point.get("y", 0)),
        )
    # A source/target arrow with manually set points uses Array
    array_points = []

    array_elem = geom.find("Array")
    if array_elem is not None:
        for point in array_elem.findall("mxPoint"):
            array_points.append(Point(x=float(point.get("x", 0)), y=float(point.get("y", 0))))

    return (points, array_points)


def parse_arrow(cell: ET.Element) -> Arrow:
    geom_xml = cell.find("mxGeometry")
    geometry = parse_geometry(geom_xml)
    named_points, anon_points = parse_arrow_points(geom_xml)
    styles = parse_styles(cell.get("style"))
    start_style = styles.get("startArrow", "none")
    end_style = styles.get("endArrow", "classic")

    if cell.get("source"):
        source = ArrowAtNode(
            node=cell.get("source"),
            X=opt_float(styles.get("exitX")),
            Y=opt_float(styles.get("exitY")),
        )
    else:
        source = named_points["sourcePoint"]

    if cell.get("target"):
        target = ArrowAtNode(
            node=cell.get("target"),
            X=opt_float(styles.get("entryX")),
            Y=opt_float(styles.get("entryY")),
        )
    else:
        target = named_points["targetPoint"]

    arr = Arrow(
        id=cell.get("id"),
        value=cell.get("value"),
        vertex=cell.get("vertex") == "1",
        parent=cell.get("parent", ""),
        geometry=geometry,
        source=source,
        target=target,
        strokeColor=styles.get("strokeColor", "#000"),
        points=anon_points,
        start_style=start_style,
        end_style=end_style,
    )
    return arr


def parse_mxfile(xml_string: str) -> MxFile:
    root = ET.fromstring(xml_string)

    diagrams = []
    for diagram in root.findall("diagram"):
        model_elem = diagram.find(".//mxGraphModel")
        assert model_elem is not None

        cells = []
        for cell in model_elem.findall(".//mxCell"):
            styles = parse_styles(cell.get("style"))
            if cell.get("edge") == "1":
                c = parse_arrow(cell)
            elif styles.get("text") is not None:
                geometry = parse_geometry(cell.find("mxGeometry"))
                c = Text.from_styles(cell.get("id"), cell.get("value"), geometry, styles)
            else:
                geometry = parse_geometry(cell.find("mxGeometry"))
                c = Cell(
                    id=cell.get("id"),
                    value=cell.get("value"),
                    vertex=cell.get("vertex") == "1",
                    parent=cell.get("parent", ""),
                    geometry=geometry,
                    _style=styles,
                    strokeColor=styles.get("strokeColor", "#000"),
                    fillColor=styles.get("fillColor", "#fff"),
                )
            cells.append(c)

        model = Model(
            dx=float(model_elem.get("dx", 0)),
            dy=float(model_elem.get("dy", 0)),
            grid=int(model_elem.get("grid", 0)),
            grid_size=int(model_elem.get("gridSize", 0)),
            root=Root(cells=cells),
        )

        diagrams.append(Diagram(name=diagram.get("name"), id=diagram.get("id"), model=model))

    return MxFile(version=root.get("version"), diagrams=diagrams)


@dataclass
class HTMLDiv(svg.Element):
    element_name: str = "div"
    xmlns: str = "http://www.w3.org/1999/xhtml"


@dataclass
class HTMLSpan(svg.Element):
    text: str
    element_name: str = "span"


def render_text(text: Text) -> svg.Element:
    # Text wrapping is not supported by `Text`
    # Need to use `foreignObject` with a <p> HTML element
    t = svg.ForeignObject(
        x=text.geometry.x,
        y=text.geometry.y,
        width=text.geometry.width,
        height=text.geometry.height,
        elements=[
            HTMLDiv(
                elements=[HTMLSpan(text=text.value.replace("<", ""), style="width: 100%")],
                style=f"height: 100%; display: flex; flex-direction: row; align-items: {text.verticalAlign}",
            )
        ],
        style=f"font-size: {text.fontSize}; text-align: {text.alignment}; font-family: {text.fontFamily};",
        # stroke=text.strokeColor,
        # text=text.value.replace("<", "!"),  # TODO parse HTML to italic/bold
    )
    return t


def render_rect(cell: Cell) -> list:
    r = svg.Rect(
        x=cell.geometry.x,
        y=cell.geometry.y,
        width=cell.geometry.width,
        height=cell.geometry.height,
        stroke=cell.strokeColor,
        fill=cell.fillColor,
    )

    dX = cell.geometry.width / 2
    tX = -50
    match cell._style.get("align"):
        case "left":
            dX = 0
            tX = 0
        case "right":
            dX = cell.geometry.width
            tX = -100

    dY = cell.geometry.height / 2
    tY = 40
    match cell._style.get("verticalAlign"):
        case "top":
            dY = 0
            tY = 75
        case "bottom":
            dY = cell.geometry.height
            tY = -15

    content = svg.Text(
        text=cell.value.replace("<", "!"),  # TODO parse HTML to italic/bold
        stroke="#000",
        x=cell.geometry.x + dX,
        y=cell.geometry.y + dY,
        style=f"transform: translate({tX}%, {tY}%); transform-box: content-box",
    )
    content = render_text(Text.from_styles(cell.id + "-text", cell.value, cell.geometry, cell._style))
    # align
    # verticalAlign
    # r.elements = [content]
    return [r, content]


@dataclass
class SArrPoints:
    source: Point
    source_margin: Point | None
    dst_margin: Point


def render_source_arrow_at_node(arrow: Arrow, target_point: Point) -> SArrPoints:
    """
    Returns 2/3 points: source, margin_source, margin_dest?
    """
    tnode = lut[arrow.target.node]
    node = lut[arrow.source.node]
    # TODO: source X/Y is usually None, as "best fit" is desired
    # need to find: closest side to dest, then use the center of that side
    closestXFactor = -1.0
    closestYFactor = -1.0
    if arrow.source.X is None:
        assert arrow.source.Y is None, "otherwise, how is this arrow freestanding?"
        assert len(arrow.points) == 0, "how can the arrow be freestanding with pinned points"

        if target_point.x > node.geometry.x + node.geometry.width:
            closestYFactor = 0.5
            closestXFactor = 1.0
        elif target_point.x + node.geometry.width < node.geometry.x:
            closestYFactor = 0.5
            closestXFactor = 0.0
        else:
            closestXFactor = 0.5
            if node.geometry.y < tnode.geometry.y:
                closestYFactor = 1.0
            else:
                closestYFactor = 0.0

    sx = node.geometry.x + node.geometry.width * (arrow.source.X or closestXFactor)
    sy = node.geometry.y + node.geometry.height * (arrow.source.Y or closestYFactor)
    spoint = Point(sx, sy)
    smargin = None
    dmargin = None

    if arrow.source.X is None:
        # if sx==dx && abs(sy-dy) < 40, only add the spoint
        # TODO: some degenerate cases (like dy==sy when chosen side=top+bot)
        match (closestXFactor, closestYFactor):
            case (0.5, 0.0):  # Top Center
                smargin = Point(sx, sy - 20)
            case (0.5, 1.0):  # Bottom Center
                smargin = Point(sx, sy + 20)
            case (1.0, 0.5):  # Right middle
                smargin = Point(sx + 20, sy)
            case (0.0, 0.5):  # Left middle
                smargin = Point(sx - 20, sy)
            case _:
                assert False, "invalid closestX/Y Factors"

    dx = target_point.x
    dy = target_point.y
    possible_dx_imm = [Point(dx + 20, dy), Point(dx - 20, dy), Point(dx, dy + 20), Point(dx, dy - 20)]

    mindist = None

    margin_from_src = smargin or spoint
    # TODO: cases where entry to target very close to exit point
    for p in possible_dx_imm:
        # do not add potential points inside the target node, includng the edges
        if tnode.contains(p):
            continue
        distance = margin_from_src.distance_to(p)
        if mindist is None or distance <= mindist:
            mindist = distance
            dmargin = p
    assert dmargin is not None

    return SArrPoints(spoint, smargin, dmargin)


def render_arrow(arrow: Arrow, lut: dict[str, Cell]) -> list:
    dx = dy = 0
    if isinstance(arrow.target, ArrowAtNode):
        tnode = lut[arrow.target.node]
        dx = tnode.geometry.x + tnode.geometry.width * arrow.target.X
        dy = tnode.geometry.y + tnode.geometry.height * arrow.target.Y
        target_point = Point(dx, dy)
    else:
        target_point = arrow.target

    spoints: SArrPoints | None = None
    if isinstance(arrow.source, ArrowAtNode):
        # start, post_start?, pre_end?
        spoints = render_source_arrow_at_node(arrow, target_point)
        source_point = spoints.source
    else:
        source_point = arrow.source

    points = arrow.points

    if spoints is not None:
        if spoints.source_margin is not None:
            points = [spoints.source_margin] + points
        points = points + [spoints.dst_margin]

    if target_point not in points:
        # target here is dupe?
        # FIXME HACK
        points = points + [target_point]

    if source_point not in points:
        # target here is dupe?
        # FIXME HACK
        points = [source_point] + points

    start = points[0]
    commands: list[svg.MoveTo | svg.LineTo] = [svg.MoveTo(start.x, start.y)]
    for point in points[1:]:
        commands.append(svg.LineTo(point.x, point.y))
    optargs = {}

    if arrow.start_style == "classic":
        optargs["marker_start"] = "url(#arrow)"
    if arrow.end_style == "classic":
        optargs["marker_end"] = "url(#arrow)"

    return [
        svg.Path(
            stroke=arrow.strokeColor,
            d=commands,
            fill="none",
            **optargs,
        )
    ]


# r = parse_mxfile(open("inputs/simple.drawio").read())
r = parse_mxfile(open("inputs/two-boxes-arrow.drawio").read())
root = r.diagrams[0].model.root
lut = {}
for cell in root.cells:
    lut[cell.id] = cell

doc = svg.SVG(elements=[], viewBox="-0.5 600.5 500 60")
assert doc.elements is not None
doc.elements.append(
    svg.Defs(
        elements=[
            svg.Marker(
                id="arrow",
                viewBox="0 0 10 10",
                refX="5",
                refY="5",
                markerWidth="6",
                markerHeight="6",
                orient="auto",
                elements=[
                    svg.Path(d="M 0 0 L 5 5 L 0 10 z", stroke="context-stroke", fill="context-stroke"),
                    # fill uses context-stroke intentionally
                ],
            ),
        ]
    )
)
# Rendering order depends on cell order
for cell in root.cells:
    if cell.geometry is None:
        continue
    if isinstance(cell, Arrow):
        doc.elements.extend(render_arrow(cell, lut))
        continue
    elif isinstance(cell, Text):
        doc.elements.append(render_text(cell))
        continue
    # pprint.pprint(cell)
    # Assuming rect
    doc.elements.extend(render_rect(cell))

with open("output.svg", "w") as fd:
    print(doc, file=fd)
