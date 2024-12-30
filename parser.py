import pprint
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
    # Do not use. only for debugging
    _style: dict[str, str]


@dataclass
class Point:
    x: float
    y: float


@dataclass
class ArrowAtNode:
    node: str
    X: Optional[float]
    Y: Optional[float]
    style: str


@dataclass
class Arrow(Cell):
    source: Point | ArrowAtNode
    target: Point | ArrowAtNode


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
        x=opt_float(geom_elem.get("x")),
        y=opt_float(geom_elem.get("y")),
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
def parse_arrow_points(geom: ET.Element) -> dict[str, Point]:
    points = {}
    for point in geom.findall('mxPoint'):
        point_type = point.get('as')
        assert point_type in ["sourcePoint", "targetPoint"]
        points[point_type] = Point(
            x=float(point.get('x', 0)),
            y=float(point.get('y', 0)),
        )
    return points

def parse_arrow(cell: ET.Element) -> Arrow:
    geom_xml = cell.find("mxGeometry")
    geometry = parse_geometry(geom_xml)
    points = parse_arrow_points(geom_xml)
    styles = parse_styles(cell.get("style"))
    if cell.get("source"):
        source = ArrowAtNode(
            node=cell.get("source"),
            X=opt_float(styles.get("exitX")),
            Y=opt_float(styles.get("exitY")),
            style=styles.get("startArrow", "none"),
        )
    else:
        source = points["sourcePoint"]

    if cell.get("target"):
        target = ArrowAtNode(
            node=cell.get("target"),
            X=opt_float(styles.get("entryX")),
            Y=opt_float(styles.get("entryY")),
            style=styles.get("endArrow", "classic"),
        )
    else:
        target = points["targetPoint"]

    arr = Arrow(
        id=cell.get("id"),
        value=cell.get("value"),
        vertex=cell.get("vertex") == "1",
        parent=cell.get("parent", ""),
        geometry=geometry,
        _style=styles,
        source=source,
        target=target,
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
            if cell.get("edge") == "1":
                c = parse_arrow(cell)
            else:
                geometry = parse_geometry(cell.find("mxGeometry"))
                styles = parse_styles(cell.get("style"))
                c = Cell(
                    id=cell.get("id"),
                    value=cell.get("value"),
                    vertex=cell.get("vertex") == "1",
                    parent=cell.get("parent", ""),
                    geometry=geometry,
                    _style=styles,
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


# r = parse_mxfile(open("inputs/simple.drawio").read())
r = parse_mxfile(open("inputs/two-boxes-arrow.drawio").read())
pprint.pprint(r.diagrams[0].model.root)
