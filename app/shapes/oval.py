import math
import typing

from PIL import ImageDraw


def _G(u: float) -> float:
    """Antiderivative of sqrt(1 - u^2), clamped to the valid domain."""
    u = max(-1.0, min(1.0, u))
    return 0.5 * (u * math.sqrt(max(0.0, 1.0 - u * u)) + math.asin(u))


def _unit_circle_rect_area(u0: float, u1: float, v0: float, v1: float) -> float:
    u0, u1 = max(u0, -1.0), min(u1, 1.0)
    if u0 >= u1 or v0 >= 1.0 or v1 <= -1.0 or v1 <= v0:
        return 0.0

    breakpoints = {u0, u1}
    for v in (v0, v1):
        if abs(v) < 1.0:
            b = math.sqrt(1.0 - v * v)
            for s in (-b, b):
                if u0 < s < u1:
                    breakpoints.add(s)
    xs = sorted(breakpoints)

    area = 0.0
    for a, b in zip(xs, xs[1:]):
        # Branch structure is constant on (a, b); probe the midpoint.
        gm = math.sqrt(max(0.0, 1.0 - (0.5 * (a + b)) ** 2))
        top_is_arc = gm < v1  # top(u)    = min(v1, g(u))
        bot_is_arc = -gm > v0  # bottom(u) = max(v0, -g(u))
        top_m = gm if top_is_arc else v1
        bot_m = -gm if bot_is_arc else v0
        if top_m <= bot_m:
            continue  # rectangle slice lies outside the disk here
        arc = _G(b) - _G(a)
        top_int = arc if top_is_arc else v1 * (b - a)
        bot_int = -arc if bot_is_arc else v0 * (b - a)
        area += top_int - bot_int
    return area


def _ellipse_pixel_area(
    vx: int, vy: int, cx: float, cy: float, rx: float, ry: float
) -> float:
    if rx <= 0 or ry <= 0:
        return 0.0
    u0, u1 = (vx - cx) / rx, (vx + 1 - cx) / rx
    v0, v1 = (vy - cy) / ry, (vy + 1 - cy) / ry
    return rx * ry * _unit_circle_rect_area(u0, u1, v0, v1)


def fill_oval(
    width: float,
    height: float,
    border: float | None,
    coverage_threshold: float,
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    if coverage_threshold < 1e-9 * 2:
        coverage_threshold = 1e-9 * 2
    elif coverage_threshold > 1.0:
        coverage_threshold = 1.0

    # Tiny tolerance so coverage=0.5 fills exactly-half voxels and float
    # noise doesn't flip borderline cases.
    threshold = coverage_threshold - 1e-9

    rx, ry = width / 2.0, height / 2.0
    grid_w = max(1, math.ceil(width)) + 4
    grid_h = max(1, math.ceil(height)) + 4
    cx = rx + 2
    cy = ry + 2

    # Inner radii for the ring variant. If the border eats the whole
    # radius, drop the hole and fill the solid oval instead.
    ri = rj = None
    if border is not None and border > 0:
        ri, rj = rx - border, ry - border
        if ri <= 0 or rj <= 0:
            ri = rj = None

    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            area = _ellipse_pixel_area(vx, vy, cx, cy, rx, ry)
            if ri is not None and rj is not None:
                area -= _ellipse_pixel_area(vx, vy, cx, cy, ri, rj)
            filled[vy][vx] = area >= threshold

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],  # unused; kept for API compat
    ) -> None:
        """Overlay the exact oval outline on a grid rendered at cell_px
        pixels per cell. Closes over cx/cy/rx/ry from fill_oval."""
        bbox = [
            (cx - rx) * cell_px,
            (cy - ry) * cell_px,
            (cx + rx) * cell_px,
            (cy + ry) * cell_px,
        ]
        draw.ellipse(bbox, outline=fill, width=2)

    label = f"oval {width}×{height}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
