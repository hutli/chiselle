import math
import typing

from PIL import ImageDraw

_Point = tuple[float, float]


def _polygon_vertices(
    sides: int, angle_deg: float, width: float, height: float
) -> list[_Point]:
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


def _clip_halfplane(
    poly: list[_Point], sfun: typing.Callable[[_Point], float]
) -> list[_Point]:
    """One Sutherland-Hodgman step: keep the part of `poly` where
    sfun(point) >= 0. `sfun` must be affine (a signed line equation) so that
    linear interpolation finds the exact crossing point. Clipping a convex
    polygon by a half-plane yields a convex polygon, so steps can be chained.
    """
    out: list[_Point] = []
    n = len(poly)
    for i in range(n):
        cur, nxt = poly[i], poly[(i + 1) % n]
        sc, sn = sfun(cur), sfun(nxt)
        if sc >= 0:
            out.append(cur)
            if sn < 0:  # leaving the half-plane: emit the crossing point
                t = sc / (sc - sn)
                out.append(
                    (cur[0] + t * (nxt[0] - cur[0]), cur[1] + t * (nxt[1] - cur[1]))
                )
        elif sn >= 0:  # entering the half-plane: emit the crossing point
            t = sc / (sc - sn)
            out.append((cur[0] + t * (nxt[0] - cur[0]), cur[1] + t * (nxt[1] - cur[1])))
    return out


def _shoelace_area(poly: list[_Point]) -> float:
    """Unsigned area of a simple polygon (shoelace formula)."""
    a = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _poly_pixel_area(poly: list[_Point], vx: int, vy: int) -> float:
    """Exact area of the 1x1 voxel [vx, vx+1] x [vy, vy+1] covered by a convex
    polygon: clip the polygon against the voxel's four edges, then measure
    what's left with the shoelace formula."""
    p = _clip_halfplane(poly, lambda q: q[0] - vx)
    if len(p) < 3:
        return 0.0
    p = _clip_halfplane(p, lambda q: (vx + 1) - q[0])
    if len(p) < 3:
        return 0.0
    p = _clip_halfplane(p, lambda q: q[1] - vy)
    if len(p) < 3:
        return 0.0
    p = _clip_halfplane(p, lambda q: (vy + 1) - q[1])
    if len(p) < 3:
        return 0.0
    return _shoelace_area(p)


def _erode_convex(poly: list[_Point], d: float) -> list[_Point] | None:
    """Erode a convex polygon by a disk of radius d: every boundary edge's
    half-plane is shifted inward by d and the polygon is clipped by each.
    (Erosion distributes over the intersection of half-planes, and eroding a
    half-plane by a disk just shifts it, so this is exact.)

    The result is the set of interior points farther than d from the boundary.
    Returns None when the border swallows the whole polygon — i.e. the shape
    should be filled solid, matching fill_oval's behaviour.
    """
    n = len(poly)
    gx = sum(p[0] for p in poly) / n  # centroid-ish interior point,
    gy = sum(p[1] for p in poly) / n  # used only to orient normals inward
    result = poly
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        length = math.hypot(ex, ey)
        if length < 1e-12:
            continue
        nx, ny = -ey / length, ex / length  # unit normal; flip to point inward
        if (gx - x1) * nx + (gy - y1) * ny < 0:
            nx, ny = -nx, -ny
        result = _clip_halfplane(
            result,
            lambda q, x1=x1, y1=y1, nx=nx, ny=ny: (q[0] - x1) * nx  # type: ignore
            + (q[1] - y1) * ny
            - d,
        )
        if len(result) < 3:
            return None
    return result


def fill_polygon(
    width: float,
    height: float,
    border: float | None,
    sides: int,
    angle: float,
    coverage_threshold: float = 0.5,
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    """Rasterize a regular N-sided polygon, scaled to fill the width x height
    bounding box, onto a boolean voxel grid.

    The polygon's bounding box is aligned to the voxel grid: it spans
    [2, 2 + width] x [2, 2 + height] on a grid padded with 2 empty voxels on
    all four sides (ceil(width) + 4 x ceil(height) + 4), same as fill_oval.
    Further positioning on a larger canvas is the caller's job.

    A voxel is marked True when at least `coverage_threshold` of its 1x1 area
    is covered by the shape. Coverage is computed exactly (no sampling): the
    polygon is clipped against each voxel with Sutherland-Hodgman and the
    remaining area measured with the shoelace formula. For a hollow shape the
    covered area is area(polygon ∩ voxel) - area(eroded polygon ∩ voxel),
    where the eroded polygon is the exact set of points farther than `border`
    from the outline — equivalent to the previous distance-to-boundary test,
    but as an area instead of a point test.

    Args:
        width:    Width of the bounding box (may be fractional).
        height:   Height of the bounding box (may be fractional).
        border:   If given and > 0, only a band of this thickness along the
                  outline is filled. If the border swallows the whole polygon,
                  the shape is filled solid.
        sides:    Number of sides (clamped to a minimum of 3).
        angle:    Rotation in degrees (counter-clockwise; 0 = flat bottom).
        coverage_threshold:
                  Fraction of a voxel's area (0..1] that must be covered for
                  it to be filled. 0.5 means "at least half". Small values
                  fill any voxel the shape merely touches; 1.0 fills only
                  fully covered voxels. Out-of-range values are clamped.

    Returns:
        A 7-tuple of:
        - grid_w, grid_h:  Grid dimensions (ceil(width), ceil(height)).
        - filled:          grid_h x grid_w booleans, row-major (filled[y][x]).
        - cx, cy:          Center of the shape in grid coordinates.
        - label:           Human-readable description of the shape.
        - draw_outline:    Callback that draws the true (vector) outline onto
                           a PIL ImageDraw, for overlaying on a scaled-up
                           rendering of the grid.
    """
    coverage_threshold = min(1.0, max(2e-9, coverage_threshold))
    # Tiny tolerance so coverage=0.5 fills exactly-half voxels and float
    # noise doesn't flip borderline cases.
    threshold = coverage_threshold - 1e-9

    sides = max(3, sides)
    verts = _polygon_vertices(sides, angle, width, height)

    # The grid pads the shape with PAD empty voxels on all four sides (room
    # for the outline overlay in the draw). The bounding box is anchored at
    # (PAD, PAD) — an integer position — so the polygon's box edges land on
    # voxel boundaries and stay aligned to the 1x1 grid, odd sizes included.
    PAD = 2
    grid_w = max(1, math.ceil(width)) + 2 * PAD
    grid_h = max(1, math.ceil(height)) + 2 * PAD
    cx, cy = PAD + width / 2.0, PAD + height / 2.0

    # _polygon_vertices is origin-centered with y pointing up; the grid has
    # its origin at the top-left with y pointing down. Convert once, then all
    # geometry below works directly in grid coordinates (no axis juggling in
    # the inner loop).
    grid_verts = [(cx + x, cy - y) for x, y in verts]

    # Hollow variant: precompute the eroded (inner) polygon once.
    inner: list[_Point] | None = None
    if border is not None and border > 0:
        inner = _erode_convex(grid_verts, border)

    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            area = _poly_pixel_area(grid_verts, vx, vy)
            if inner is not None:
                area -= _poly_pixel_area(inner, vx, vy)
            filled[vy][vx] = area >= threshold

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],  # unused; kept for API compat
    ) -> None:
        """Overlay the exact polygon outline on a grid rendered at cell_px
        pixels per cell."""
        pts = [(x * cell_px, y * cell_px) for x, y in grid_verts]
        pts.append(pts[0])  # close the loop
        draw.line(pts, fill=fill, width=2)

    label = f"{sides}-gon {width}×{height}  ang={angle}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline


if __name__ == "__main__":
    # A hollow hexagon: exact coverage, flush on a 15x15 grid.
    grid_w, grid_h, filled, cx, cy, label, _ = fill_polygon(
        15, 15, border=1.5, sides=6, angle=0, coverage_threshold=0.5
    )
    print(label, f"({grid_w}x{grid_h} grid, center at {cx},{cy})")
    for row in filled:
        print("".join("█" if c else "·" for c in row))
