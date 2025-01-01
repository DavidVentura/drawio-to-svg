import math

import svg

from pathlib import Path
from typing import Optional

from drawio_types import *

import xml.etree.ElementTree as ET

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
        x=float(geom_elem.get("x", 0.0)),
        y=float(geom_elem.get("y", 0.0)),
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


def parse_arrow_points(geom: ET.Element) -> ArrowPoints:
    sp = None
    tp = None
    extra = []
    for point in geom.findall("mxPoint"):
        type_ = point.get("as")
        point = Point(
            x=float(point.get("x", 0)),
            y=float(point.get("y", 0)),
        )
        match type_:
            case "sourcePoint":
                sp = point
            case "targetPoint":
                tp = point
            case _:
                raise ValueError("")

    # A source/target arrow with manually set points uses Array
    array_elem = geom.find("Array")
    if array_elem is not None:
        for point in array_elem.findall("mxPoint"):
            extra.append(Point(x=float(point.get("x", 0)), y=float(point.get("y", 0))))

    return ArrowPoints(sp, tp, extra)


def parse_arrow(cell: ET.Element) -> Arrow:
    geom_xml = cell.find("mxGeometry")
    assert geom_xml is not None
    geometry = parse_geometry(geom_xml)
    arrow_points = parse_arrow_points(geom_xml)
    styles = parse_styles(cell.get("style"))
    start_style = styles.get("startArrow", "none")
    end_style = styles.get("endArrow", "classic")

    if cell.get("source"):
        # exitX/exitY are reversed??
        exitX = opt_float(styles.get("exitX"))
        exitY = opt_float(styles.get("exitY"))
        if exitX is not None:
            exitX = 1.0 - exitX
        if exitY is not None:
            exitY = 1.0 - exitY
        source = ArrowAtNode(
            node=cell.get("source"),
            X=exitX,
            Y=exitY,
        )
    else:
        source = arrow_points.source

    if cell.get("target"):
        target = ArrowAtNode(
            node=cell.get("target"),
            X=opt_float(styles.get("entryX")),
            Y=opt_float(styles.get("entryY")),
        )
    else:
        target = arrow_points.target

    arr = Arrow(
        id=cell.get("id"),
        value=cell.get("value"),
        vertex=cell.get("vertex") == "1",
        parent=cell.get("parent", ""),
        geometry=geometry,
        source=source,
        target=target,
        strokeColor=styles.get("strokeColor", "#000"),
        points=arrow_points.extra,
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

                if styles.get("dashed") is not None:
                    ss = StrokeStyle.from_dash_pattern(styles.get("dashPattern"))
                else:
                    ss = StrokeStyle.SOLID

                stroke = Stroke(
                    style=ss,
                    width=int(styles.get("strokeWidth", "1")),
                    color=styles.get("strokeColor", "#000"),
                )
                c = Cell(
                    id=cell.get("id"),
                    value=cell.get("value"),
                    vertex=cell.get("vertex") == "1",
                    parent=cell.get("parent", ""),
                    geometry=geometry,
                    _style=styles,
                    stroke=stroke,
                    fillColor=styles.get("fillColor", "#fff"),
                    opacity=float(styles.get("opacity", "100")) / 100.0,
                    # left center right
                    labelPosition=styles.get("labelPosition", "center"),
                    # top middle bottom
                    verticalLabelPosition=styles.get("verticalLabelPosition", "middle"),
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
    )
    return t


def render_rect(cell: Cell) -> list:
    r = svg.Rect(
        x=cell.geometry.x,
        y=cell.geometry.y,
        width=cell.geometry.width,
        height=cell.geometry.height,
        stroke=cell.stroke.color,
        fill=cell.fillColor,
        opacity=cell.opacity,
        **cell.stroke.style.as_props(),
    )

    # Box alignment
    match cell.verticalLabelPosition:
        case "top":
            box_offset_y = -cell.geometry.height
        case "middle":
            box_offset_y = 0
        case "bottom":
            box_offset_y = cell.geometry.height

    match cell.labelPosition:
        case "left":
            box_offset_x = -cell.geometry.width
        case "center":
            box_offset_x = 0
        case "right":
            box_offset_x = cell.geometry.width

    t = Text.from_styles(cell.id + "-text", cell.value, cell.geometry, cell._style)
    t.geometry.x += box_offset_x
    t.geometry.y += box_offset_y
    content = render_text(t)
    return [r, content]


def closest_point(a: Cell | Point, b: Point) -> Point:
    if isinstance(a, Cell):
        assert a.geometry is not None
        a_points = a.center_points()
    else:
        a_points = [a]

    min_dist = float("inf")
    closest = None

    for ap in a_points:
        bp = b
        dist = ((ap.x - bp.x) ** 2 + (ap.y - bp.y) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            closest = ap

    assert closest is not None
    return closest


# 3 types of handling:
# - node to node, unconstrained
# - node (constrained) to node (un-constrained) -- also the reverse
#   - can also be partially-constrained (few points, then unconstrained)
# - arrow to node (implies constrained)
def render_arrow(arrow: Arrow, lut: dict[str, Cell]) -> list:

    target: Cell | Point
    target_point: None | Point = None
    if isinstance(arrow.target, ArrowAtNode):
        target = lut[arrow.target.node]
        target_point = Point(
            target.geometry.x + target.geometry.width * arrow.target.X,
            target.geometry.y + target.geometry.height * arrow.target.Y,
        )
        print("constrained target", target_point)
    else:
        target = arrow.target
        target_point = arrow.target

    source: Cell | Point
    if isinstance(arrow.source, ArrowAtNode):
        source = lut[arrow.source.node]
        if arrow.source.X is not None:
            # Constrained source
            source_point = Point(
                source.geometry.x + source.geometry.width * arrow.source.X,
                source.geometry.y + source.geometry.height * arrow.source.Y,
            )
            print("constrained source", source_point)
        else:
            # Unconstrained source
            # TODO: should use the target-margin-point
            # for calculating the source side more accurately
            # TODO(2): When source is un-constrained
            # If target is LEFT/RIGHT, prefer TOP/BOT side (closest)
            source_point = closest_point(source, target_point)
            print("Auto calc source is", source_point)
    else:
        source = arrow.source
        source_point = arrow.source

    # TODO: Not all points are fixed. We should still find best path
    # from source->arrow.points[0]) or arrow.points[-1]->target
    if len(arrow.points) == 0:
        assert isinstance(source, Cell)
        assert isinstance(target, Cell)
        # An arrow with no manual points gets auto-path
        points = find_best_path(source_point, target_point, source, target)
    else:
        # Manual points, set by the user
        points = arrow.points

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


def get_closest_side(c: Cell, p: Point) -> Point:
    pws = c.center_points_with_sides()
    closest: Point | None = None
    mindist: float = math.inf
    chosen_side: Side | None = None
    for sidep, side in pws:
        if closest is None:
            closest = sidep
            chosen_side = side
        elif p.distance_to(sidep) < mindist:
            closest = sidep
            chosen_side = side
        mindist = p.distance_to(closest)
    return chosen_side


def get_margin_point(c: Cell, p: Point) -> tuple[Point, Side]:
    # Closest side
    chosen_side = get_closest_side(c, p)
    mp: Point
    match chosen_side:
        case Side.LEFT:
            mp = Point(p.x - 20, p.y)
        case Side.RIGHT:
            mp = Point(p.x + 20, p.y)
        case Side.TOP:
            mp = Point(p.x, p.y - 20)
        case Side.BOTTOM:
            mp = Point(p.x, p.y + 20)
        case default:
            raise ValueError(f"Wrong side: {default}")
    return mp, chosen_side


def find_best_path(sp: Point, tp: Point, source: Cell, target: Cell) -> list[Point]:
    print(f"Pathing {sp} to {tp}")
    mps, ss = get_margin_point(source, sp)
    mpt, st = get_margin_point(target, tp)
    points = [mps]

    if {ss, st} == {Side.TOP, Side.BOTTOM}:
        # simple "N" shape
        ymid = mps.midpoint(mpt).y
        int_s = Point(mps.x, ymid)
        int_t = Point(mpt.x, ymid)
        points.append(int_s)
        points.append(int_t)
    elif {ss, st} == {Side.LEFT, Side.RIGHT}:
        # simple "N" shape
        int_s = Point(mps.midpoint(mpt).x, mps.y)
        int_t = Point(mps.midpoint(mpt).x, mpt.y)
        points.append(int_s)
        points.append(int_t)
    elif len({ss, st}) == 1:
        print("complex top/top bot/bot l/l r/r")
    else:
        # "L" shape
        if ss in {Side.LEFT, Side.RIGHT}:
            points.append(Point(mpt.x, mps.y))
        else:
            points.append(Point(mps.x, mpt.y))

    points.append(mpt)
    print("path points", points)

    return points


def render_file(f: Path) -> svg.SVG:
    # r = parse_mxfile(open("inputs/simple.drawio").read())
    with f.open() as fd:
        r = parse_mxfile(fd.read())
    PAGE = 0
    root = r.diagrams[PAGE].model.root
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
    return doc

if __name__ == "__main__":
    doc = render_file(Path("inputs/two-boxes-arrow.drawio"))
    #doc = render_file(Path("disk.drawio"))
    with open("output.svg", "w") as fd:
        print(doc, file=fd)
