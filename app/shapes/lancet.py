import math
import typing

from PIL import ImageDraw


def _lancet_inside(
    px: float, py: float, a: float, H: float, R: float, d: float
) -> bool:
    if py < 0:
        return False
    dist_left = math.sqrt((px - d) ** 2 + py**2)
    dist_right = math.sqrt((px + d) ** 2 + py**2)
    return dist_left <= R and dist_right <= R


def fill_lancet(
    width: int, height: int, border: float | None
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    a = width / 2.0
    H: float = height

    if H <= a:
        # Degenerate: make it at least slightly pointed
        H = a + 0.01

    # Arc geometry:  d = (H² - a²) / (2a),  R = (a² + H²) / (2a)
    d = (H * H - a * a) / (2.0 * a)
    R = (a * a + H * H) / (2.0 * a)

    grid_w = math.ceil(width) + 4
    grid_h = math.ceil(height) + 4
    if grid_w % 2 != 0:
        grid_w += 1
    if grid_h % 2 != 0:
        grid_h += 1

    # Place the arch so its base sits at the bottom of the grid
    # cx = horizontal centre, base_y = bottom row (in voxel coords, y-down)
    cx = grid_w / 2.0
    base_y = grid_h - 2  # 2-voxel padding at bottom
    cy = base_y - H / 2.0  # vertical midpoint (for crosshair)

    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            # Convert to arch coords: origin at base-centre, Y-up
            px = (vx + 0.5) - cx
            py = base_y - (vy + 0.5)  # flip Y
            inside = _lancet_inside(px, py, a, H, R, d)
            if border:
                a_in = a - border
                H_in = H - border
                if a_in > 0 and H_in > a_in:
                    d_in = (H_in * H_in - a_in * a_in) / (2.0 * a_in)
                    R_in = (a_in * a_in + H_in * H_in) / (2.0 * a_in)
                    inside_inner = _lancet_inside(
                        px, py - border, a_in, H_in, R_in, d_in
                    )
                    # Also keep the base strip
                    if py < border:
                        inside_inner = False
                else:
                    inside_inner = False
                filled[vy][vx] = inside and not inside_inner
            else:
                filled[vy][vx] = inside

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],
    ) -> None:
        # Draw the two arcs as polylines + the base line
        steps = 200
        pts_left = []
        pts_right = []

        # Left arc: centre at (d, 0) in arch coords
        # Sweeps from the base-left corner (-a, 0) up to the apex (0, H)
        # Angle from centre (d,0) to (-a, 0):  atan2(0, -a-d) = pi
        # Angle from centre (d,0) to (0, H):   atan2(H, -d)
        ang_start_l = math.atan2(0, -a - d)  # = pi
        ang_end_l = math.atan2(H, 0 - d)
        for i in range(steps + 1):
            t = i / steps
            ang = ang_start_l + t * (ang_end_l - ang_start_l)
            ax = d + R * math.cos(ang)
            ay = R * math.sin(ang)
            # Convert to pixel coords
            sx = (cx + ax) * cell_px
            sy = (base_y - ay) * cell_px
            pts_left.append((sx, sy))

        # Right arc: centre at (-d, 0), mirrors left
        ang_start_r = math.atan2(0, a + d)  # = 0
        ang_end_r = math.atan2(H, 0 + d)
        for i in range(steps + 1):
            t = i / steps
            ang = ang_start_r + t * (ang_end_r - ang_start_r)
            ax = -d + R * math.cos(ang)
            ay = R * math.sin(ang)
            sx = (cx + ax) * cell_px
            sy = (base_y - ay) * cell_px
            pts_right.append((sx, sy))

        # Base line
        base_px_y = base_y * cell_px
        left_x = (cx - a) * cell_px
        right_x = (cx + a) * cell_px
        draw.line([(left_x, base_px_y), (right_x, base_px_y)], fill=fill, width=2)
        # Arcs
        if len(pts_left) > 1:
            draw.line(pts_left, fill=fill, width=2)
        if len(pts_right) > 1:
            draw.line(pts_right, fill=fill, width=2)

    label = f"lancet {width}×{height}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
