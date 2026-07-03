import math
import typing

from PIL import ImageDraw


def fill_oval(
    width: int, height: int, border: float | None
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    rx, ry = width / 2.0, height / 2.0
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
            dx = (vx + 0.5) - cx
            dy = (vy + 0.5) - cy
            nd = (dx / rx) ** 2 + (dy / ry) ** 2 if rx > 0 and ry > 0 else 999
            if border:
                ri, rj = rx - border, ry - border
                nd_in = (dx / ri) ** 2 + (dy / rj) ** 2 if ri > 0 and rj > 0 else 999
                filled[vy][vx] = nd <= 1.0 and nd_in >= 1.0
            else:
                filled[vy][vx] = nd <= 1.0

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],
    ) -> None:
        bbox = [
            (cx - rx) * cell_px,
            (cy - ry) * cell_px,
            (cx + rx) * cell_px,
            (cy + ry) * cell_px,
        ]
        draw.ellipse(bbox, outline=fill, width=2)

    label = f"oval {width}×{height}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
