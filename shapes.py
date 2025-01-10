import svg

from drawio_types import Geometry, Direction


def curly(g: Geometry, direction: Direction) -> svg.Path:
    # Generated poking around on
    # https://sean.brunnock.com/SVG/SVGPathGenerator/

    # TODO: Direction flips width/height!

    right = g.x + g.width
    bot = g.y + g.height
    centerY = g.y + g.height / 2

    # TODO: curlyLeft/curlyRight are _customizable_
    # meaning that while width is constant
    # the position of the curly is not
    curlyWidth = 20
    curlyLeft = g.x + (g.width - curlyWidth) / 2
    curlyRight = curlyLeft + curlyWidth
    # The curly itself is 10px wide
    # then straight lines
    points = [
        svg.MoveTo(g.x, bot),
        svg.LineTo(curlyLeft, bot),
        # Curly
        svg.CubicBezier(curlyRight, bot, curlyLeft, centerY, curlyRight, centerY),  # curve
        # "Point"
        svg.LineTo(right, centerY),
        svg.MoveTo(curlyRight, centerY),
        # End "Point"
        svg.CubicBezier(curlyLeft, centerY, curlyRight, g.y, curlyLeft, g.y),  # curve
        # End curly
        svg.LineTo(g.x, g.y),
        # Do not close
        svg.MoveTo(g.x, bot),
        svg.Z(),
    ]
    rotation_angle = direction.rotation_angle()
    return svg.Path(
        d=points,
        fill="none",
        stroke="rgb(0, 0, 0)",
        # TODO: arg
        transform=[svg.Rotate(rotation_angle)],
        # rotate around the center
        style="transform-box: fill-box; transform-origin: center;",
    )
