import math
import typing

from PIL import ImageDraw


def _star_vertices(
    points: int, inner_ratio: float, angle_deg: float, width: int, height: int
) -> list[tuple[float, float]]:
    """The 2*points vertices of a star, alternating between the outer radius (the
    tips) and the inner radius (the valleys), centred on the origin (y-up) and
    scaled so the bounding box is exactly width × height.

    At angle 0 a tip points straight up. A positive angle rotates it
    counter-clockwise. inner_ratio sets how spiky the star is: small values give
    long thin points, values near 1 barely dent the outline. When width ≠ height
    the star is stretched to fill the box.
    """
    inner_ratio = max(0.05, min(0.95, inner_ratio))
    rot = math.radians(angle_deg)
    raw = []
    for j in range(2 * points):
        r = 1.0 if j % 2 == 0 else inner_ratio
        a = math.pi / 2.0 + rot + math.pi * j / points
        raw.append((r * math.cos(a), r * math.sin(a)))

    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    xmid, ymid = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    sx = width / (xmax - xmin)
    sy = height / (ymax - ymin)
    return [((x - xmid) * sx, (y - ymid) * sy) for x, y in raw]


def _point_in_polygon(px: float, py: float, verts: list[tuple[float, float]]) -> bool:
    """General (non-convex) point-in-polygon test by ray casting, since a star
    is not convex."""
    n = len(verts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = verts[i]
        xj, yj = verts[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _dist_to_boundary(px: float, py: float, verts: list[tuple[float, float]]) -> float:
    """Shortest distance from a point to the star outline (min over edges of the
    point-to-segment distance). Used to carve a uniform-thickness border."""
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


def fill_star(
    width: int,
    height: int,
    border: float | None,
    points: int,
    angle: float,
    inner_ratio: float,
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    """An N-pointed star scaled to fill the width × height bounding box.

    points       number of star points (clamped to a minimum of 2)
    angle        rotation in degrees (counter-clockwise; 0 = a point straight up)
    inner_ratio  valley radius as a fraction of the tip radius (spikiness)
    border       if set, makes the shape hollow with this border thickness in voxels
    """
    points = max(2, points)
    verts = _star_vertices(points, inner_ratio, angle, width, height)

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
            inside = _point_in_polygon(ey, ex, verts)
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

    label = f"{points}-point star {width}×{height}  ir={inner_ratio}  ang={angle}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
