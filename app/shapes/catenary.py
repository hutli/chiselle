import math
import typing

from PIL import ImageDraw


def _solve_catenary_a(half: float, height: float, iterations: int = 80) -> float:
    """Solve  height = a * (cosh(half / a) - 1)  for the catenary parameter a.

    The right-hand side is strictly decreasing in a (small a -> tall and
    pointy, large a -> shallow), so a plain bisection converges reliably.
    """

    def f(a: float) -> float:
        x = half / a
        if x > 700:  # cosh overflow guard
            return float("inf")
        return a * (math.cosh(x) - 1) - height

    lo = 1e-9  # f(lo) -> +inf  (very tall)
    hi = max(half * half / (2 * height), half) * 4.0
    while f(hi) > 0:  # ensure hi brackets the root
        hi *= 2.0
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid  # root is at larger a
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _catenary_top(px: float, a: float, height: float, half: float) -> float:
    """Height of the inverted catenary arch at horizontal offset px.
    Returns -1 outside the span so the inside-test fails cleanly."""
    if abs(px) > half:
        return -1.0
    x = px / a
    if x > 700:
        return -1.0
    return height + a - a * math.cosh(x)


def fill_catenary(
    width: int, height: int, thickness: float, end_offset: int
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    W = float(width)
    H = float(height) if height > 0 else 0.01
    T = max(1.0, float(thickness))
    E = float(end_offset)

    half = W / 2.0
    xc = W / 2.0
    a = _solve_catenary_a(half, H)

    def center_depth(x: float) -> float:
        s = _catenary_top(x - xc, a, H, half)  # symmetric sag profile (>= 0)
        if s < 0.0:
            s = 0.0
        return (E / W) * x + s  # linear tilt for uneven ends

    def center_slope(x: float) -> float:
        return (E / W) - math.sinh((x - xc) / a)

    # Vertical span of the centreline, so the grid fits the rope + its thickness
    probe = [center_depth(W * i / 200.0) for i in range(201)]
    dmin = min(min(probe), 0.0)
    dmax = max(max(probe), 0.0)

    grid_w = math.ceil(W) + 4
    grid_h = math.ceil((dmax - dmin) + T) + 4
    if grid_w % 2 != 0:
        grid_w += 1
    if grid_h % 2 != 0:
        grid_h += 1

    left_x = 2.0  # world x = 0 sits 2 voxels from the left
    top_y = 2.0 + (T / 2.0) - dmin  # highest point of the rope ~2 from the top

    cx = left_x + W / 2.0
    cy = top_y + center_depth(W / 2.0)

    half_t = T / 2.0
    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            wx = (vx + 0.5) - left_x
            wy = vy + 0.5
            if wx < 0.0 or wx > W:  # only between the two anchors
                continue
            m = center_slope(wx)
            cyl = top_y + center_depth(wx)
            perp = abs(wy - cyl) / math.sqrt(1.0 + m * m)  # perpendicular gap
            filled[vy][vx] = perp <= half_t

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],
    ) -> None:
        steps = 240
        cen, up, lo = [], [], []
        for i in range(steps + 1):
            wx = W * i / steps
            cyl = top_y + center_depth(wx)
            m = center_slope(wx)
            nlen = math.sqrt(1.0 + m * m)
            nx, ny = -m / nlen, 1.0 / nlen  # unit normal
            cen.append(((left_x + wx) * cell_px, cyl * cell_px))
            up.append(
                ((left_x + wx + nx * half_t) * cell_px, (cyl + ny * half_t) * cell_px)
            )
            lo.append(
                ((left_x + wx - nx * half_t) * cell_px, (cyl - ny * half_t) * cell_px)
            )
        draw.line(cen, fill=center_mark, width=1)  # ideal centreline
        draw.line(up, fill=fill, width=2)  # rope edges
        draw.line(lo, fill=fill, width=2)

    label = f"catenary {width}×{height}  t={thickness}  end={end_offset}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
