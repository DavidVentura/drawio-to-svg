"""
Goals for now:
    - Non-HTML text decoration
    - Non-boxes
      - split "Rect" from "Cell"
    - Path finding for arrows
    - Rotation
"""

import math

import svg

import shapes

from pathlib import Path
from typing import Optional

from drawio_types import *
from text_expander import FontRenderer, TextLine
from html_flattener import parse_html, NewlineToken, TextToken

import xml.etree.ElementTree as ET

_font_cache = {}


def get_font(font_fam: str, style: str, font_size: int) -> FontRenderer:
    key = f"{font_fam}-{style}"
    if f := _font_cache.get(key):
        return f
    f = FontRenderer(f"{key}.ttf", font_size)
    _font_cache[key] = f
    return f


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
        source = ArrowAtNode(
            node=lut[cell.get("source")],
            X=opt_float(styles.get("exitX")),
            Y=opt_float(styles.get("exitY")),
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

    if styles.get("dashed") is not None:
        ss = StrokeStyle.from_dash_pattern(styles.get("dashPattern"))
    else:
        ss = StrokeStyle.SOLID
    arr = Arrow(
        id=cell.get("id"),
        value=cell.get("value"),
        vertex=cell.get("vertex") == "1",
        parent=cell.get("parent", ""),
        geometry=geometry,
        source=source,
        target=target,
        stroke=Stroke(
            color=styles.get("strokeColor", "#000"),
            width=float(styles.get("strokeWidth", "1")),
            style=ss,
        ),
        points=arrow_points.extra,
        start_style=start_style,
        end_style=end_style,
    )
    return arr


def parse_mxfile(xml_string: str) -> MxFile:
    root = ET.fromstring(xml_string)

    lut: dict[str, Arrow | Text | Cell] = {}
    diagrams = []
    for diagram in root.findall("diagram"):
        model_elem = diagram.find(".//mxGraphModel")
        assert model_elem is not None

        cells = []
        _cells_with_idx = list(enumerate(model_elem.findall(".//mxCell")))
        # Arrows have `source` and `target` which may be unpopulated
        # edgeLabels depend on parent
        # if we are going in rendering order, so we put the arrows last
        # generate the LUT with full nodes
        # then we sort them back based on the original index
        # this should be generalized to ordering based on seen parents..
        _cells = sorted(
            _cells_with_idx,
            key=lambda t: t[1].get("edge") == "1" or parse_styles(t[1].get("style", "")).get("edgeLabel") is not None,
        )
        for og_idx, cell in _cells:
            styles = parse_styles(cell.get("style"))
            parent_node = lut.get(cell.get("parent"))
            _g = cell.find("mxGeometry")
            geometry = None
            if _g is not None:
                pg = None
                if parent_node and parent_node.geometry:
                    pg = parent_node.geometry
                geometry = parse_geometry(_g, pg)

            if cell.get("edge") == "1":
                c = parse_arrow(cell, lut)
            elif styles.get("text") is not None:
                c = Text.from_styles(cell.get("id"), cell.get("value"), geometry, "middle", "center", styles)
            elif styles.get("edgeLabel") is not None:
                # FIXME point/offset
                assert _g is not None
                _p = _g.findall("mxPoint")
                offset = Point(0, 0)
                if _p:
                    assert len(_p) == 1
                    _p = _p[0]
                    _px = int(_p.get("x", "0"))
                    _py = int(_p.get("y", "0"))
                    offset = Point(_px, _py)

                assert parent_node is not None
                if parent_node.id == "1":
                    parent_node = None
                assert geometry
                if geometry.relative:
                    assert parent_node is not None
                    ep = EdgeLabelRelative(geometry.x, geometry.y, parent_node, offset)
                else:
                    ep = EdgeLabelAbsolute(geometry.x, geometry.y)

                c = EdgeLabel(cell.get("id"), cell.get("value"), styles, ep)
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
                    fillColor=styles.get("fillColor", "#fff"),  # TODO "default" value
                    opacity=float(styles.get("opacity", "100")) / 100.0,
                    # left center right
                    labelPosition=styles.get("labelPosition", "center"),
                    # top middle bottom
                    verticalLabelPosition=styles.get("verticalLabelPosition", "middle"),
                    shape=Shape.from_str(styles.get("shape", "rect")),
                    direction=Direction.from_str(styles.get("direction", "east")),
                    parent_node=parent_node,
                    is_group=styles.get("group") != None,
                    rotation=int(styles.get("rotation", 0)),
                    flip_h=bool(int(styles.get("flipH", 0))),
                    flip_y=bool(int(styles.get("flipY", 0))),
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


def _render_browser_text(text: Text, textContent: str) -> svg.Element:
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

    fs = text.fontSize if text.fontSize.endswith("px") else f"{text.fontSize}px"
    t = svg.ForeignObject(
        x=text.geometry.x,
        y=text.geometry.y,
        width=text.geometry.width,
        height=text.geometry.height,
        elements=[
            HTMLDiv(
                style=f"display: flex; flex-direction: row; align-items: {text.verticalAlign}; width: 100%; height: 100%; transform:translate({ml}, {mt});",
                elements=[HTMLSpan(text=textContent, style="width: 100%")],
            ),
        ],
        style=f"font-size: {fs}; text-align: {text.alignment}; font-family: {text.fontFamily}; overflow: visible;",
    )
    return t


def _render_exploded_text(text: Text) -> tuple[svg.Element, Geometry]:
    leftX = text.geometry.x
    rightX = text.geometry.x + text.geometry.width

    topY = text.geometry.y
    botY = text.geometry.y + text.geometry.height

    def off_(r: TextLine) -> tuple[float, float]:
        g = text.geometry
        x = 0
        y = 0

        # X-align Outside the box
        match text.horizontalPosition:
            case "left":
                x = leftX - g.width
            case "center":
                x = leftX
            case "right":
                x = rightX
            case default:
                raise ValueError(f"Wrong hp {default}")

        # Y-align Outside the box
        match text.verticalPosition:
            case "top":
                y = topY - g.height
            case "middle":
                y = topY
            case "bottom":
                y = botY
            case default:
                raise ValueError(f"Wrong vp {default}")

        # Inside the box
        match text.verticalAlign:
            case "start":
                y += r.h
            case "center":
                y += g.height / 2 + r.ascent / 2
            case "end":
                y += g.height - r.descent
            case default:
                raise ValueError(f"Wrong va {default}")

        # Inside the box
        match text.alignment:
            case "left":
                x -= 0
            case "center":
                x += g.width / 2 - r.w / 2
            case "right":
                x += g.width - r.w
            case default:
                raise ValueError(f"Wrong ta {default}")
        return (x, y)

    # assert text.fontFamily == "Helvetica"
    ff = text.fontFamily.lower()
    if text.fontFamily == "Verdana":
        # HACK, fixme
        # this fallback is :!cp
        ff = "Liberation Serif"
        text.fontFamily = ff

    fs = int(text.fontSize.replace("px", ""))

    parsed: list[NewlineToken | TextToken] = parse_html(text.value)

    r_text = []
    geom = None

    y_off = 0.0
    x_off = 0.0
    ascent = 0.0
    for token in parsed:
        if isinstance(token, NewlineToken):
            x_off = 0.0
            y_off += get_font(ff, "regular", fs).font_height_px
            continue

        if text.styled_as_html:
            bold = token.bold
            italic = token.italic
            color = token.color or text.strokeColor
        else:
            bold = text.fontStyle.bold
            italic = text.fontStyle.italic
            color = text.fontColor

        match bold, italic:
            case (False, False):
                style = "regular"
            case (True, False):
                style = "bold"
            case (False, True):
                style = "italic"
            case (True, True):
                style = "bold-italic"
            case default:
                raise ValueError(f"Illegal token state {token}={default}")

        f = get_font(ff, style, fs)
        # TODO inside boxes, there is some kind of margin, looks like
        # 6px total (3px left 3px right)
        # but .. not outside boxes?
        rendered = f.render(token.text, text.geometry.width)

        for idx, line in enumerate(rendered):
            ascent = line.ascent
            x, y = off_(line)
            if idx > 0 and idx < len(rendered):
                y_off += line.h
                x_off = 0
            x += x_off
            y += y_off
            x_off += line.w
            path = line.path(x, y)
            path.fill = color

            geom = Geometry.stretch_to_contain(geom, Geometry(x, y - line.ascent, line.w, line.h))
            r_text.append(path)

    assert geom is not None
    assert ascent != 0.0
    # TODO: doing translate like this requires manual fix to the geometry
    # it should be better
    deltaY = -geom.height / 2 + ascent / 2
    # FIXME: the 108pt font has 5px offset, idk why
    # normal font should be +1px offset?
    if f.font_height_px == 108:
        deltaY -= 6
        pass
    else:
        deltaY += 1.5
    translated = svg.G(elements=r_text, transform=[svg.Translate(0, deltaY)])
    geom.y += deltaY
    return translated, geom


def get_point_from_line(p1: Point, p2: Point, path_percentage: float, orthogonal_distance: float) -> Point:
    """
    Find a point relative to the line segment defined by this point and another point.

    Args:
        p1 (Point): Point that defines the line segment
        p2 (Point): Point that defines the line segment
        path_percentage (float): Percentage along the line from the midpoint.
                               0 is middle, -1.0 is start point, 1.0 is end point
        orthogonal_distance (float): Distance from the line. Positive values are to the left
                                   of the direction vector, negative to the right

    Returns:
        Point: The calculated point
    """
    # First get the direction vector of the line
    dx = p2.x - p1.x
    dy = p2.y - p1.y

    # Calculate the length of the vector
    length = (dx * dx + dy * dy) ** 0.5

    if length == 0:
        raise ValueError("Points are identical - no valid point exists")

    # Normalize the direction vector
    dx /= length
    dy /= length

    # Calculate midpoint
    mid_x = (p1.x + p2.x) / 2
    mid_y = (p1.y + p2.y) / 2

    # Convert percentage to actual distance from midpoint
    path_distance = (path_percentage) * (length / 2)
    point_on_line_x = mid_x + (dx * path_distance)
    point_on_line_y = mid_y + (dy * path_distance)

    # Now calculate the orthogonal offset
    # Rotate direction vector 90 degrees counterclockwise
    orthogonal_x = dy
    orthogonal_y = -dx

    # Apply orthogonal offset
    final_x = point_on_line_x + (orthogonal_x * orthogonal_distance)
    final_y = point_on_line_y + (orthogonal_y * orthogonal_distance)

    return Point(final_x, final_y)


def render_edge_label(el: EdgeLabel) -> tuple[svg.G, Geometry]:
    if isinstance(el.positioning, EdgeLabelRelative):
        el.positioning.orthogonalDistance
    match el.positioning:
        case EdgeLabelAbsolute(x, y):
            g = Geometry(x, y, 0, 0)
        case EdgeLabelRelative(pathPercentage, orthogonalDistance, parent, offset):
            print(pathPercentage, offset)
            assert isinstance(parent.source, Point)
            assert isinstance(parent.target, Point)

            p = get_point_from_line(parent.source, parent.target, pathPercentage, orthogonalDistance)
            # if pathPercentage is 0, we should start from the middle
            # the offset is absolute
            # TODO: pathPercentage, orthogonalDistance
            # orthogonalDistance is absolute
            g = Geometry(p.x + offset.x, p.y + offset.y, 0, 0)
        case default:
            assert False, default

    # TODO: middle/center are hardcoded, but if they were not, what's the actual size of the
    # bounding box?
    vp = "middle"
    hp = "center"

    t = Text.from_styles("idk", el.value, g, vp, hp, el.styles)
    return render_text(t)


# TODO: bools to enum
def render_text(text: Text, browser_text=False, explode=True) -> tuple[svg.G, Geometry]:

    elems = []
    path, geom = _render_exploded_text(text)
    if explode:
        elems.append(path)

    # TODO: could probably use a native Text element
    # which would depend on the user's fonts, instead
    # of exploding the text to paths

    if browser_text:
        # "basic" sanitization for unsupported svg features
        textContent = text.value.replace("<br>", "<br/>").replace("&nbsp;", " ")
        # DANGER this pipes HTML straight in
        elems.append(_render_browser_text(text, textContent))

    t = svg.G(elements=elems)

    return (t, geom)


def render_rect(cell: Cell) -> tuple[list[svg.Element], Geometry]:
    match cell.shape:
        case Shape.Rect:
            r = svg.Rect(
                x=cell.geometry.x,
                y=cell.geometry.y,
                width=cell.geometry.width,
                height=cell.geometry.height,
                stroke=cell.stroke.color,
                stroke_width=cell.stroke.width,
                fill=cell.fillColor,
                opacity=cell.opacity,
                **cell.stroke.style.as_props(),
            )
        case Shape.Curly:
            # When rotating, the dimensions change!
            if cell.direction in [Direction.NORTH, Direction.SOUTH]:
                old_w = cell.geometry.width
                new_w = cell.geometry.height
                old_h = cell.geometry.height
                new_h = cell.geometry.width
                cell.geometry.width = new_w
                cell.geometry.height = new_h
                # centerpoint should remain the same
                cell.geometry.x += old_w / 2 - new_w / 2
                cell.geometry.y += old_h / 2 - new_h / 2
                pass
            r = shapes.curly(cell.geometry, direction=cell.direction, rotation=cell.rotation, flip_h=cell.flip_h)
        # how did an ellipse even WORK

    # TODO: rotation?
    bb = Geometry.from_geom(cell.geometry)
    t = Text.from_styles(
        cell.id + "-text", cell.value, cell.geometry, cell.verticalLabelPosition, cell.labelPosition, cell._style
    )
    # t.geometry.x += box_offset_x
    # t.geometry.y += box_offset_y
    bb = bb.stretch_to_contain(t.geometry)
    ret = [r]
    if t.value:
        content, bb2 = render_text(t)
        bb = bb.stretch_to_contain(bb2)
        ret.append(content)
    return (ret, bb)


def closest_point(a: Cell | Point, b: Cell | Point) -> Point:
    if isinstance(a, Cell):
        assert a.geometry is not None
        a_points = a.center_points()
    else:
        a_points = [a]

    if isinstance(b, Cell):
        assert b.geometry is not None
        b_points = b.center_points()
    else:
        b_points = [b]

    min_dist = float("inf")
    closest = None

    for ap in a_points:
        for bp in b_points:
            dist = ((ap.x - bp.x) ** 2 + (ap.y - bp.y) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                closest = ap

    assert closest is not None
    return closest


def point_from_rotated_cell(c: Cell, arrow: ArrowAtNode) -> Point:
    assert c.geometry is not None
    assert arrow.X is not None
    assert arrow.Y is not None

    match c.direction:
        case Direction.EAST:
            x_factor = arrow.X
            y_factor = arrow.Y
        case Direction.SOUTH:
            # Flip axes
            x_factor = arrow.Y
            y_factor = arrow.X
        case Direction.WEST:
            # Flip X
            x_factor = 1 - arrow.X
            y_factor = arrow.Y
        case Direction.NORTH:
            # Flip axes AND y-factor
            x_factor = arrow.Y
            y_factor = 1 - arrow.X

    point = Point(
        c.geometry.x + c.geometry.width * x_factor,
        c.geometry.y + c.geometry.height * y_factor,
    )
    return point


# 3 types of handling:
# - node to node, unconstrained
# - node (constrained) to node (un-constrained) -- also the reverse
#   - can also be partially-constrained (few points, then unconstrained)
# - arrow to node (implies constrained)
def render_arrow(arrow: Arrow) -> tuple[list[svg.Element], Geometry]:
    # TODO: source/dest X/Y are affected by node orientation

    target: Cell | Point = None
    target_point: None | Point = None
    if isinstance(arrow.target, ArrowAtNode):
        target = arrow.target.node
        if arrow.target.X is not None:
            # Constrained target
            assert isinstance(target, Cell)
            target_point = point_from_rotated_cell(target, arrow.target)
            print("constrained target", target_point)
    else:
        target = arrow.target
        target_point = arrow.target

    source: Cell | Point
    source_point: Point | None = None
    if isinstance(arrow.source, ArrowAtNode):
        source = arrow.source.node
        if arrow.source.X is not None:
            # Constrained source
            source_point = point_from_rotated_cell(source, arrow.source)
            print("constrained source", source_point)
    else:
        source = arrow.source
        source_point = arrow.source

    # Unconstrained source
    if isinstance(arrow.source, ArrowAtNode) and arrow.source.X is None:
        # TODO: should use the target-margin-point
        # for calculating the source side more accurately
        # TODO(2): When source is un-constrained
        # If target is LEFT/RIGHT, prefer TOP/BOT side (closest)
        # If we picked a point already, use it, otherwise pick closest side
        source_point = closest_point(source, target_point or target)
        print("Auto calc source is", source_point)

    assert source_point is not None

    # Unconstrained target
    if isinstance(arrow.target, ArrowAtNode) and arrow.target.X is None:
        # TODO: should use the target-margin-point
        # for calculating the source side more accurately
        # TODO(2): When source is un-constrained
        # If target is LEFT/RIGHT, prefer TOP/BOT side (closest)
        print(source, source_point)
        # If we picked a point already, use it, otherwise pick closest side
        target_point = closest_point(arrow.target.node, source_point or source)
        print("Auto calc dest is", target_point)

    assert target_point is not None

    # TODO: Not all points are fixed. We should still find best path
    # from source->arrow.points[0]) or arrow.points[-1]->target
    if len(arrow.points) == 0 and isinstance(source, Cell):
        assert isinstance(target, Cell)
        # An arrow with no manual points gets auto-path
        print("finding for s", source_point, source.geometry)
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
        bb = bb.stretch_to_contain_point(point, arrow.stroke.width)
        commands.append(svg.LineTo(point.x, point.y))

    path = svg.Path(
        stroke=arrow.stroke.color,
        stroke_width=arrow.stroke.width,
        d=commands,
        fill="none",
        **optargs,
        **arrow.stroke.style.as_props(),
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

    return points


def render_file(r: MxFile, page_name: str) -> svg.SVG:
    page = None
    for _page in r.diagrams:
        if _page.name == page_name:
            page = _page
            break
    if page is None:
        raise ValueError(f"No page named {page_name}")
    root = page.model.root

    elements = []
    main_bb = None
    # Rendering order depends on cell order
    for cell in root.cells:
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
        elif isinstance(cell, EdgeLabel):
            svge, bb = render_edge_label(cell)
            main_bb = Geometry.stretch_to_contain(main_bb, bb)
            elements.append(svge)
            # raise NotImplementedError
            continue
        if cell.is_group:
            continue
        if cell.geometry is None:
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
    f = Path("inputs/two-boxes-arrow.drawio")
    f = Path("inputs/text-align.drawio")
    f = Path("disk.drawio")
    f = Path("inputs/diagrams.drawio")
    with f.open() as fd:
        r = parse_mxfile(fd.read())
    doc = render_file(r, page_name="font")
    with open("output.svg", "w") as fd:
        print(doc, file=fd)
