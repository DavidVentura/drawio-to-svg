"""
Goals for now:
    0. Label rendering outside of box, size is wrong
    1. Parent relationship/relative -- if a cell has parent, its coordinates are relative
    2. Non-HTML text decoration
    3. Non-boxes
        3.0 split "Rect" from "Cell"
    4. Path finding for arrows
"""

import math

import svg

import shapes

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


def parse_geometry(geom_elem: ET.Element, parent_geom: Optional[Geometry]) -> Geometry:
    assert geom_elem is not None
    px = 0
    py = 0
    if parent_geom is not None:
        px = parent_geom.x
        py = parent_geom.y
    return Geometry(
        x=float(geom_elem.get("x", 0.0)) + px,
        y=float(geom_elem.get("y", 0.0)) + py,
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


def parse_arrow(cell: ET.Element, lut: dict[str, Cell]) -> Arrow:
    geom_xml = cell.find("mxGeometry")
    assert geom_xml is not None
    geometry = parse_geometry(geom_xml, None)
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
        # exitY is _NOT_ reversed??
        # if exitY is not None:
        #    exitY = 1.0 - exitY
        source = ArrowAtNode(
            node=lut[cell.get("source")],
            X=exitX,
            Y=exitY,
        )
    else:
        source = arrow_points.source

    if cell.get("target"):
        target = ArrowAtNode(
            node=lut[cell.get("target")],
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

    lut: dict[str, Cell] = {}
    diagrams = []
    for diagram in root.findall("diagram"):
        model_elem = diagram.find(".//mxGraphModel")
        assert model_elem is not None

        cells = []
        _cells_with_idx = list(enumerate(model_elem.findall(".//mxCell")))
        # Arrows have `source` and `target` which may be unpopulated
        # if we are going in rendering order, so we put the arrows last
        # generate the LUT with full nodes
        # then we sort them back based on the original index
        _cells = sorted(_cells_with_idx, key=lambda t: t[1].get("edge") == "1")
        for og_idx, cell in _cells:
            styles = parse_styles(cell.get("style"))
            parent_node = lut.get(cell.get("parent"))
            _g = cell.find("mxGeometry")
            geometry = None
            if _g is not None:
                pg = None
                if parent_node.geometry:
                    pg = parent_node.geometry
                geometry = parse_geometry(_g, pg)

            if cell.get("edge") == "1":
                c = parse_arrow(cell, lut)
            elif styles.get("text") is not None:
                c = Text.from_styles(cell.get("id"), cell.get("value"), geometry, "middle", "center", styles)
            else:
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
                    geometry=geometry,
                    _style=styles,
                    stroke=stroke,
                    fillColor=styles.get("fillColor", "#fff"),
                    opacity=float(styles.get("opacity", "100")) / 100.0,
                    # left center right
                    labelPosition=styles.get("labelPosition", "center"),
                    # top middle bottom
                    verticalLabelPosition=styles.get("verticalLabelPosition", "middle"),
                    shape=Shape.from_str(styles.get("shape", "rect")),
                    direction=Direction.from_str(styles.get("direction", "east")),
                    parent_node=parent_node,
                )
            lut[c.id] = c
            cells.append((og_idx, c))

        # Re-sort cells based on their original index
        resorted_cells = [c for _, c in sorted(cells)]

        model = Model(
            dx=float(model_elem.get("dx", 0)),
            dy=float(model_elem.get("dy", 0)),
            grid=int(model_elem.get("grid", 0)),
            grid_size=int(model_elem.get("gridSize", 0)),
            root=Root(cells=resorted_cells),
        )

        diagrams.append(Diagram(name=diagram.get("name"), id=diagram.get("id"), model=model))

    return MxFile(version=root.get("version"), diagrams=diagrams)


def render_text(text: Text) -> tuple[svg.Element, Geometry]:
    # Text wrapping is not supported by `Text`
    # Need to use `foreignObject` with a <span> HTML element
    # Which is also used to align text vertically with `flex`

    # FIXME DANGER this pipes HTML straight in
    # - always need to close tags
    # There's basic styling supported in the text element in drawio
    # but also, you can inject arbitrary HTML if you double-click
    # the text objects. WHY?
    # FIXME: entities such as &nbsp; crash

    # FIXME: text elements outside of the holding Cell have no
    # bounding box of their own, which means the final viewBox will not
    # consider them, for text at the edges of the diagrams
    # for this, initially I had used the "mirrored" cell bounding box,
    # but they are too large, and need to be cropped
    # so we still need to somehow calculate the bounding box of text
    # which requires a rendering library
    match text.horizontalPosition:
        case "left":
            ml = "-100%"
        case "center":
            ml = "0px"
        case "right":
            ml = "100%"
        case default:
            raise ValueError(f"Wrong hp {default}")

    match text.verticalPosition:
        case "top":
            mt = "-100%"
        case "middle":
            mt = "0px"
        case "bottom":
            mt = "100%"
        case default:
            raise ValueError(f"Wrong vp {default}")

    textContent = text.value.replace("<br>", "<br/>")
    t = svg.ForeignObject(
        x=text.geometry.x,
        y=text.geometry.y,
        width=text.geometry.width,
        height=text.geometry.height,
        elements=[
            #HTMLDiv(elements=[
                HTMLDiv(
                    style=f"display: flex; flex-direction: row; align-items: {text.verticalAlign}; width: 100%; height: 100%; transform:translate({ml}, {mt});",
                    elements=[HTMLSpan(text=textContent, style="width: 100%")],
                )
                #])
        ],
        style=f"font-size: {text.fontSize}; text-align: {text.alignment}; font-family: {text.fontFamily}; overflow: visible;",
    )
    return (t, text.geometry)


def render_rect(cell: Cell) -> tuple[list[svg.Element], Geometry]:

    match cell.shape:
        case Shape.Rect:
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
        case Shape.Curly:
            # When rotating, the dimensions change!
            if cell.direction in [Direction.NORTH, Direction.SOUTH]:
                w = cell.geometry.width
                cell.geometry.width = cell.geometry.height
                cell.geometry.height = w
                pass
            r = shapes.curly(cell.geometry, direction=cell.direction)


    # TODO: rotation?
    bb = Geometry.from_geom(cell.geometry)
    t = Text.from_styles(
        cell.id + "-text", cell.value, cell.geometry, cell.verticalLabelPosition, cell.labelPosition, cell._style
    )
    # t.geometry.x += box_offset_x
    # t.geometry.y += box_offset_y
    bb = bb.stretch_to_contain(t.geometry)
    content, bb2 = render_text(t)
    bb = bb.stretch_to_contain(bb2)
    return ([r, content], bb)


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
def render_arrow(arrow: Arrow) -> tuple[list[svg.Element], Geometry]:

    target: Cell | Point
    target_point: None | Point = None
    if isinstance(arrow.target, ArrowAtNode):
        target = arrow.target.node
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
        source = arrow.source.node
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
    if len(arrow.points) == 0 and isinstance(source, Cell):
        assert isinstance(target, Cell)
        # An arrow with no manual points gets auto-path
        print("finding for s", source_point, source)
        points = find_best_path(source_point, target_point, source, target)
    else:
        # (maybe) manual points, set by the user
        points = arrow.points

    if target_point not in points:
        # target here is dupe?
        # FIXME HACK
        points = points + [target_point]

    if source_point not in points:
        # target here is dupe?
        # FIXME HACK
        points = [source_point] + points

    optargs = {}

    if arrow.start_style == "classic":
        optargs["marker_start"] = "url(#arrow)"
        # If we have start-cap, the line should not start at the source, but 1 unit before
        first_p = (points[1] - points[0]).normalized()
        points[0] = points[0] + first_p

    if arrow.end_style == "classic":
        optargs["marker_end"] = "url(#arrow)"
        # If we have end-cap, the line should not finish in the target, but 1 unit before
        last_p = (points[-1] - points[-2]).normalized()
        points[-1] = points[-1] - last_p

    start = points[0]
    commands: list[svg.MoveTo | svg.LineTo] = [svg.MoveTo(start.x, start.y)]
    bb = Geometry.from_geom(start)
    for point in points[1:]:
        # TODO: this should include stroke-width
        bb = bb.stretch_to_contain(point)
        commands.append(svg.LineTo(point.x, point.y))

    path = svg.Path(
        stroke=arrow.strokeColor,
        d=commands,
        fill="none",
        **optargs,
    )
    return ([path], bb)


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

    print(ss, st)
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


def render_file(r: MxFile, page=0) -> svg.SVG:
    root = r.diagrams[page].model.root

    elements = []
    main_bb = None
    # Rendering order depends on cell order
    for cell in root.cells:
        if cell.geometry is None:
            continue
        if isinstance(cell, Arrow):
            svge, bb = render_arrow(cell)
            main_bb = Geometry.stretch_to_contain(main_bb, bb)
            elements.extend(svge)
            continue
        elif isinstance(cell, Text):
            svge, bb = render_text(cell)
            main_bb = Geometry.stretch_to_contain(main_bb, bb)
            elements.append(svge)
            continue
        # Assuming rect
        svge, bb = render_rect(cell)
        main_bb = Geometry.stretch_to_contain(main_bb, bb)
        elements.extend(svge)

    assert main_bb is not None

    classic_arrow_path = [
        svg.MoveTo(7, 7),
        svg.LineTo(0, 10.5),
        svg.LineTo(1.75, 7),
        svg.LineTo(0, 3.5),
        svg.Z(),
    ]
    arrow = svg.Marker(
        id="arrow",
        viewBox=svg.ViewBoxSpec(0, 0, 10, 15),
        refX=6.5,
        refY=7,
        markerWidth=10,
        markerHeight=10,
        orient="auto-start-reverse",
        elements=[
            svg.Path(d=classic_arrow_path, stroke="context-stroke", fill="context-stroke"),
            # fill uses context-stroke intentionally
        ],
    )
    elements.append(
        svg.Defs(
            elements=[
                arrow,
            ]
        )
    )
    doc = svg.SVG(
        elements=elements,
        xmlns="http://www.w3.org/2000/svg",
        width=main_bb.width + 0.5,
        height=main_bb.height + 0.5,
        viewBox=svg.ViewBoxSpec(main_bb.x - 0.5, main_bb.y - 0.5, main_bb.width + 1.0, main_bb.height + 1.0),
    )

    return doc


if __name__ == "__main__":
    # f = Path("inputs/two-boxes-arrow.drawio")
    f = Path("disk.drawio")
    with f.open() as fd:
        r = parse_mxfile(fd.read())
    doc = render_file(r, page=3)
    with open("output.svg", "w") as fd:
        print(doc, file=fd)
