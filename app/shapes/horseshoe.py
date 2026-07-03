import math
import typing

from PIL import ImageDraw


def _angdiff(a: float, b: float) -> float:
    """Smallest absolute angle between a and b (radians)."""
    d = abs(a - b) % (2.0 * math.pi)
    return min(d, 2.0 * math.pi - d)


def _heel_radii(s: float, R_in: float, t: float, notches: bool) -> tuple[float, float]:
    """Inner/outer band radius as a function of the angular distance s (radians)
    from the nearest heel end. This sculpts each heel into a chunky cap that
    swells inward, followed by a pinched notch, before the normal band."""
    if not notches:
        return R_in, 1.0
    cap_span = 1.0 * t
    notch_span = 0.55 * t
    if s < cap_span:  # chunky heel cap (swells inward)
        return R_in - 0.5 * t, 1.0
    if s < cap_span + notch_span:  # notch: a dip in the outer rim
        return R_in, 1.0 - 0.38 * t
    return R_in, 1.0  # normal band


def fill_horseshoe(
    width: int,
    height: int,
    border: float | None,
    opening: float,
    angle: float,
    nails: int,
    notches: bool = True,
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    """A horseshoe: an annular band with a wedge removed at the top, chunky
    notched heels, and optional nail holes.

    border    band thickness in voxels (falls back to ~28% of the radius if unset)
    opening   angular size of the gap at the top, in degrees
    angle     rotation in degrees (counter-clockwise; 0 = opening at the top)
    nails     number of nail holes spaced along the band (0 to disable)
    notches   sculpt the chunky cap + notch at each heel (True) or leave the
              heels as plain flat cuts (False)

    The band is defined on a unit circle and scaled to the width × height box, so
    a square box stays a true circle (rotation never clips or distorts it) while a
    non-square box makes it elliptical and rotation will shear it.
    """
    rx, ry = width / 2.0, height / 2.0

    # Band thickness as a fraction of the radius. `border` is given in voxels;
    # convert against the smaller half-axis, or fall back to a sensible default.
    t = border / min(rx, ry) if border else 0.28
    t = max(0.05, min(0.95, t))

    R_in = 1.0 - t
    R_mid = (1.0 + R_in) / 2.0
    half_gap = math.radians(opening) / 2.0
    th = math.radians(angle)
    ct, st = math.cos(th), math.sin(th)
    hole_r = 0.30 * t
    eL = math.pi / 2.0 + half_gap
    eR = math.pi / 2.0 - half_gap
    arc_len = 2.0 * math.pi - math.radians(opening)

    # Nail-hole centres along the band centreline, kept clear of the heel notches.
    nail_centres: list[tuple[float, float]] = []
    if nails > 0:
        pad = (1.55 * t + 0.12) if notches else 0.0
        span = arc_len - 2.0 * pad
        for i in range(nails):
            ang = eL + pad + (i + 0.5) / nails * span
            nail_centres.append((R_mid * math.cos(ang), R_mid * math.sin(ang)))

    # Size the grid to the rotated outer-ellipse bounding box so a rotated,
    # non-square horseshoe never gets clipped.
    grid_w = math.ceil(2 * math.hypot(rx * ct, ry * st)) + 4
    grid_h = math.ceil(2 * math.hypot(rx * st, ry * ct)) + 4
    if grid_w % 2 != 0:
        grid_w += 1
    if grid_h % 2 != 0:
        grid_h += 1
    cx, cy = grid_w / 2.0, grid_h / 2.0

    filled = [[False] * grid_w for _ in range(grid_h)]
    for vy in range(grid_h):
        for vx in range(grid_w):
            ey = (vx + 0.5) - cx
            ex = cy - (vy + 0.5)
            u = (ey / rx) * ct + (ex / ry) * st  # inverse-rotate into
            v = -(ey / rx) * st + (ex / ry) * ct  # canonical space

            rho = math.hypot(u, v)
            phi = math.atan2(v, u)

            g = abs(phi - math.pi / 2.0)  # cut the opening at top
            if g > math.pi:
                g = 2.0 * math.pi - g
            if g < half_gap:
                continue

            s = min(_angdiff(phi, eL), _angdiff(phi, eR))
            Ri, Ro = _heel_radii(s, R_in, t, notches)
            if rho < Ri or rho > Ro:
                continue

            is_hole = False  # punch the nail holes
            for nx, ny in nail_centres:
                if (u - nx) ** 2 + (v - ny) ** 2 < hole_r * hole_r:
                    is_hole = True
                    break
            filled[vy][vx] = not is_hole

    def draw_outline(
        draw: ImageDraw.ImageDraw,
        cell_px: int,
        fill: tuple[int, int, int, int],
        center_mark: tuple[int, int, int, int],
    ) -> None:
        def to_px(cu: float, cv: float) -> tuple[float, float]:
            x = (cu * ct - cv * st) * rx
            y = (cu * st + cv * ct) * ry
            return ((cx + x) * cell_px, (cy - y) * cell_px)

        steps = 240
        a0, a1 = eL, eR + 2.0 * math.pi
        outer, inner = [], []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            s = min(_angdiff(a, eL), _angdiff(a, eR))
            Ri, Ro = _heel_radii(s, R_in, t, notches)
            outer.append(to_px(Ro * math.cos(a), Ro * math.sin(a)))
            inner.append(to_px(Ri * math.cos(a), Ri * math.sin(a)))
        draw.line(outer, fill=fill, width=2)
        draw.line(inner, fill=fill, width=2)
        draw.line([outer[0], inner[0]], fill=fill, width=2)
        draw.line([outer[-1], inner[-1]], fill=fill, width=2)

        r_px = hole_r * (rx + ry) / 2.0 * cell_px  # nail holes
        for nx, ny in nail_centres:
            px, py = to_px(nx, ny)
            draw.ellipse(
                [px - r_px, py - r_px, px + r_px, py + r_px],
                outline=fill,
                width=2,
            )

    label = f"horseshoe {width}×{height}  open={opening}  nails={nails}  ang={angle}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline
