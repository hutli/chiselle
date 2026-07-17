import math
import typing

from PIL import ImageDraw


def _egg_inside(ex: float, ey: float, a: float, b: float, w: float) -> bool:
    """Hügelschäffer egg inside-test in egg-local coords.
    ex runs along the length (axis of symmetry), ey across the breadth.
    a = half-length, b = max half-breadth, w = asymmetry shift (needs w < a)."""
    if abs(ex) > a:
        return False
    denom = a * a + w * w + 2.0 * w * ex
    if denom <= 0:
        return False
    return ey * ey <= b * b * (a * a - ex * ex) / denom


def fill_egg(
    width: int, height: int, border: float | None, asymmetry: float
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    """A Hügelschäffer egg, long axis vertical, pointed end up.

    asymmetry  fraction of the half-length the breadth is shifted by:
               0.0 -> symmetric ellipse, ~0.3 -> natural egg, clamped at 0.95.
    """
    a = height / 2.0  # half-length (vertical)
    b = width / 2.0  # half-breadth (horizontal)
    w = max(0.0, min(asymmetry, 0.95)) * a  # asymmetry shift, kept < a

    grid_w = max(1, math.ceil(width)) + 4
    grid_h = max(1, math.ceil(height)) + 4
    cx = width / 2.0 + 2
    cy = height / 2.0 + 2

    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            ey = (vx + 0.5) - cx
            ex = cy - (vy + 0.5)  # +ex points up (pointy end)
            inside = _egg_inside(ex, ey, a, b, w)
            if border:
                a_in = a - border
                b_in = b - border
                w_in = w * (a_in / a) if a > 0 else 0.0
                inside_inner = _egg_inside(ex, ey, a_in, b_in, w_in)
                filled[vy][vx] = inside and not inside_inner
            else:
                filled[vy][vx] = inside

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],
    ) -> None:
        # Trace the Hügelschäffer parametric curve directly.
        steps = 400
        pts = []
        for i in range(steps + 1):
            t = 2.0 * math.pi * i / steps
            s, c = math.sin(t), math.cos(t)
            ex = -w * s * s + c * math.sqrt(a * a - w * w * s * s)
            ey = b * s
            pts.append(((cx + ey) * cell_px, (cy - ex) * cell_px))
        draw.line(pts, fill=fill, width=2)

    label = f"egg {width}×{height}  asym={asymmetry}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
