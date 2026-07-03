import math
import typing

from PIL import ImageDraw


def _polygon_vertices(
    sides: int, angle_deg: float, width: int, height: int
) -> list[tuple[float, float]]:
    """Vertices of a regular N-gon, centred on the origin (y-up), scaled so its
    bounding box is exactly width × height.

    At angle 0 the polygon sits flat-bottomed (odd N then points straight up).
    A positive angle rotates it counter-clockwise. Because the bounding box is
    pinned to width × height, rotating shrinks the actual polygon to fit (e.g. a
    square at 45° becomes a diamond touching the four edge mid-points). When
    width ≠ height the polygon is stretched to fill the box.
    """
    base = -math.pi / 2.0 + math.pi / sides  # flat bottom; odd N points up
    rot = math.radians(angle_deg)
    raw = [
        (
            math.cos(base + rot + 2.0 * math.pi * k / sides),
            math.sin(base + rot + 2.0 * math.pi * k / sides),
        )
        for k in range(sides)
    ]

    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    xmid, ymid = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    sx = width / (xmax - xmin)
    sy = height / (ymax - ymin)
    return [((x - xmid) * sx, (y - ymid) * sy) for x, y in raw]


def _point_in_convex(
    px: float, py: float, verts: list[tuple[float, float]], eps: float = 1e-9
) -> bool:
    """Convex point-in-polygon test: the point is inside when it lies on the
    same side of every edge. Valid here because a (stretched) regular polygon
    stays convex."""
    sign = 0
    n = len(verts)
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        if cross < -eps:
            if sign > 0:
                return False
            sign = -1
        elif cross > eps:
            if sign < 0:
                return False
            sign = 1
    return True


def _dist_to_boundary(px: float, py: float, verts: list[tuple[float, float]]) -> float:
    """Shortest distance from a point to the polygon outline (min over edges of
    the point-to-segment distance). Used to carve a uniform-thickness border."""
    best = float("inf")
    n = len(verts)
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq == 0.0:
            t = 0.0
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        nx, ny = x1 + t * dx, y1 + t * dy
        d = math.hypot(px - nx, py - ny)
        if d < best:
            best = d
    return best


def fill_polygon(
    width: int, height: int, border: float | None, sides: int, angle: float
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    """A regular N-sided polygon scaled to fill the width × height bounding box.

    sides   number of sides (clamped to a minimum of 3)
    angle   rotation in degrees (counter-clockwise; 0 = flat bottom)
    border  if set, makes the shape hollow with this border thickness in voxels
    """
    sides = max(3, sides)
    verts = _polygon_vertices(sides, angle, width, height)

    grid_w = math.ceil(width) + 4
    grid_h = math.ceil(height) + 4
    if grid_w % 2 != 0:
        grid_w += 1
    if grid_h % 2 != 0:
        grid_h += 1
    cx, cy = grid_w / 2.0, grid_h / 2.0

    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            ey = (vx + 0.5) - cx  # horizontal offset from centre
            ex = cy - (vy + 0.5)  # vertical offset, +ex points up
            inside = _point_in_convex(ey, ex, verts)
            if border:
                filled[vy][vx] = inside and _dist_to_boundary(ey, ex, verts) <= border
            else:
                filled[vy][vx] = inside

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],
    ) -> None:
        pts = [((cx + X) * cell_px, (cy - Y) * cell_px) for X, Y in verts]
        pts.append(pts[0])  # close the loop
        draw.line(pts, fill=fill, width=2)

    label = f"{sides}-gon {width}×{height}  ang={angle}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
