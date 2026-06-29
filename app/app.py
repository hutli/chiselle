import argparse
import io
import logging
import math
import random
import typing

import discord
import dotenv
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

COLOR_BG = (30, 30, 30, 255)
COLOR_VOXEL = (180, 130, 70, 255)
COLOR_GRID_MINOR = (60, 60, 60, 255)
COLOR_GRID_MAJOR = (70, 130, 220, 200)
COLOR_CENTER_MARK = (100, 200, 255, 180)
COLOR_SHAPE_EDGE = (255, 220, 100, 120)
TERMS_OF_ENDEARMENT = ["sweety", "honey", "doll", "baby", "sweetheart", "darlin'"]
ACTIVITIES = ["Chiseling better than you 💅"]


# ================= RENDER LOGIC =================


def _fill_oval(
    width: int, height: int, hollow: bool, thickness: float
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
            if hollow:
                ri, rj = rx - thickness, ry - thickness
                nd_in = (dx / ri) ** 2 + (dy / rj) ** 2 if ri > 0 and rj > 0 else 999
                filled[vy][vx] = nd <= 1.0 and nd_in >= 1.0
            else:
                filled[vy][vx] = nd <= 1.0

    def draw_outline(draw: ImageDraw.ImageDraw, cell_px: int) -> None:
        bbox = [
            (cx - rx) * cell_px,
            (cy - ry) * cell_px,
            (cx + rx) * cell_px,
            (cy + ry) * cell_px,
        ]
        draw.ellipse(bbox, outline=COLOR_SHAPE_EDGE, width=2)

    label = f"oval {width}×{height}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline


def _lancet_inside(
    px: float, py: float, a: float, H: float, R: float, d: float
) -> bool:
    if py < 0:
        return False
    dist_left = math.sqrt((px - d) ** 2 + py**2)
    dist_right = math.sqrt((px + d) ** 2 + py**2)
    return dist_left <= R and dist_right <= R


def _fill_lancet(
    width: int, height: int, hollow: bool, thickness: float
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
            if hollow:
                a_in = a - thickness
                H_in = H - thickness
                if a_in > 0 and H_in > a_in:
                    d_in = (H_in * H_in - a_in * a_in) / (2.0 * a_in)
                    R_in = (a_in * a_in + H_in * H_in) / (2.0 * a_in)
                    inside_inner = _lancet_inside(
                        px, py - thickness, a_in, H_in, R_in, d_in
                    )
                    # Also keep the base strip
                    if py < thickness:
                        inside_inner = False
                else:
                    inside_inner = False
                filled[vy][vx] = inside and not inside_inner
            else:
                filled[vy][vx] = inside

    def draw_outline(draw: ImageDraw.ImageDraw, cell_px: int) -> None:
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
        draw.line(
            [(left_x, base_px_y), (right_x, base_px_y)], fill=COLOR_SHAPE_EDGE, width=2
        )
        # Arcs
        if len(pts_left) > 1:
            draw.line(pts_left, fill=COLOR_SHAPE_EDGE, width=2)
        if len(pts_right) > 1:
            draw.line(pts_right, fill=COLOR_SHAPE_EDGE, width=2)

    label = f"lancet {width}×{height}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline


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


def _fill_catenary(
    width: int, height: int, thickness: float, end_offset: int
) -> tuple[int, int, list[list[bool]], float, float, str, typing.Callable]:
    """A hanging rope/vine: a catenary that sags downward between two anchors.

    width       horizontal span between anchors (voxels)
    height      sag depth -- how far the rope dips at its lowest point
    thickness   rope thickness (voxels)
    end_offset  vertical drop of the right anchor relative to the left
                (positive = right end lower; negative = right end higher)
    """
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

    def draw_outline(draw: ImageDraw.ImageDraw, cell_px: int) -> None:
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
        draw.line(cen, fill=COLOR_CENTER_MARK, width=1)  # ideal centreline
        draw.line(up, fill=COLOR_SHAPE_EDGE, width=2)  # rope edges
        draw.line(lo, fill=COLOR_SHAPE_EDGE, width=2)

    label = f"catenary {width}×{height}  t={thickness}  end={end_offset}"
    return grid_w, grid_h, filled, cx, cy, label, draw_outline


def render(
    shape: str,
    width: int,
    height: int,
    cell_px: int = 24,
    block_size: int = 16,
    block_offset_x: int = 0,
    block_offset_y: int = 0,
    hollow: bool = False,
    thickness: float = 1.0,
    end_offset: int = 0,
) -> tuple[io.BytesIO, int]:
    # ── Pick shape ────────────────────────────────────────────────────────
    if shape == "oval":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = _fill_oval(
            width, height, hollow, thickness
        )
    elif shape == "lancet":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = _fill_lancet(
            width, height, hollow, thickness
        )
    elif shape == "catenary":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = _fill_catenary(
            width, height, thickness, end_offset
        )
    else:
        raise ValueError(f"Unknown shape: {shape}")

    # ── Draw the image ───────────────────────────────────────────────────
    img_w = grid_w * cell_px + 1
    img_h = grid_h * cell_px + 1
    img = Image.new("RGBA", (img_w, img_h), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # Filled voxels
    for vy in range(grid_h):
        for vx in range(grid_w):
            if filled[vy][vx]:
                x0, y0 = vx * cell_px, vy * cell_px
                draw.rectangle([x0, y0, x0 + cell_px, y0 + cell_px], fill=COLOR_VOXEL)

    # Minor grid (voxel borders)
    for ix in range(grid_w + 1):
        p = ix * cell_px
        draw.line([(p, 0), (p, img_h)], fill=COLOR_GRID_MINOR, width=1)
    for iy in range(grid_h + 1):
        p = iy * cell_px
        draw.line([(0, p), (img_w, p)], fill=COLOR_GRID_MINOR, width=1)

    # Major grid (block borders)
    for ix in range(grid_w + 1):
        if (ix - block_offset_x - 2) % block_size == 0:
            p = ix * cell_px
            draw.line([(p, 0), (p, img_h)], fill=COLOR_GRID_MAJOR, width=3)
    for iy in range(grid_h + 1):
        if (iy - block_offset_y - 2) % block_size == 0:
            p = iy * cell_px
            draw.line([(0, p), (img_w, p)], fill=COLOR_GRID_MAJOR, width=3)

    # Mathematical outline
    draw_outline(draw, cell_px)

    # Centre crosshair
    cpx, cpy = cx * cell_px, cy * cell_px
    arm = cell_px * 1.5
    draw.line([(cpx - arm, cpy), (cpx + arm, cpy)], fill=COLOR_CENTER_MARK, width=1)
    draw.line([(cpx, cpy - arm), (cpx, cpy + arm)], fill=COLOR_CENTER_MARK, width=1)

    # ── Legend ────────────────────────────────────────────────────────────
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 13
        )
    except OSError:
        font = ImageFont.load_default()  # type: ignore

    info_lines = [
        f"{label}   grid = {grid_w}×{grid_h}",
        f"block = {block_size}   offset = ({block_offset_x}, {block_offset_y})",
        f"{'hollow  t=' + str(thickness) if hollow else 'filled'}",
    ]
    ty = 4
    for line in info_lines:
        draw.text((6, ty), line, fill=(200, 200, 200, 220), font=font)
        ty += 16

    # ── Voxel count per block ────────────────────────────────────────────
    for by_start in range(block_offset_y % block_size - block_size, grid_h, block_size):
        for bx_start in range(
            block_offset_x % block_size - block_size, grid_w, block_size
        ):
            count = 0
            for vy in range(max(0, by_start), min(grid_h, by_start + block_size)):
                for vx in range(max(0, bx_start), min(grid_w, bx_start + block_size)):
                    if filled[vy][vx]:
                        count += 1
            if count > 0:
                lbl = str(count)
                lx = (
                    (max(0, bx_start) + min(grid_w, bx_start + block_size))
                    / 2.0
                    * cell_px
                )
                ly = (
                    (max(0, by_start) + min(grid_h, by_start + block_size))
                    / 2.0
                    * cell_px
                )
                bb = draw.textbbox((0, 0), lbl, font=font)
                draw.text(
                    (lx - (bb[2] - bb[0]) / 2, ly - (bb[3] - bb[1]) / 2),
                    lbl,
                    fill=(255, 255, 255, 100),
                    font=font,
                )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    total = sum(row.count(True) for row in filled)
    return buffer, total


# ================= DISCORD =================

TOKEN = dotenv.get_key(".env", "TOKEN")
if not TOKEN:
    raise Exception("Must provide Discord Token!")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
logger = logging.getLogger("discord")


def generate_embed(
    title: str,
    description: str,
    color: discord.Colour,
    width: int,
    height: int,
    offset_x: int,
    offset_y: int,
    total_voxels: int,
    thickness: float | None = None,
    end_offset: int | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_image(url="attachment://shape.png")

    embed.add_field(name="Width", value=str(width), inline=True)
    embed.add_field(name="Height", value=str(height), inline=True)
    if offset_x:
        embed.add_field(name="X Offset", value=str(offset_x), inline=True)
    if offset_y:
        embed.add_field(name="Y Offset", value=str(offset_y), inline=True)
    if thickness:
        embed.add_field(name="Thickness", value=str(thickness), inline=True)
    if end_offset:
        embed.add_field(name="End Offset", value=str(end_offset), inline=True)

    embed.add_field(name="Total Voxels", value=str(total_voxels), inline=True)

    return embed


@client.event
async def on_ready() -> None:
    await tree.sync()
    await client.change_presence(
        activity=discord.CustomActivity(name=random.choice(ACTIVITIES)),
        status=discord.Status.online,
    )
    logger.info(f"We have logged in as {client.user}")
    for g in client.guilds:
        logger.info(f'Connected to guild "{g}"')


@tree.command(description="Generate an oval")
@app_commands.describe(
    width="Width of the oval in voxels",
    height="Height of the oval in voxels",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
    hollow="Wether the shape should be hollow.",
    border_thickness="The thickness of the shape border. Only applicable if hollow is set.",
)
async def oval(
    interaction: discord.Interaction,
    width: int,
    height: int,
    offset_x: int = 0,
    offset_y: int = 0,
    hollow: bool = False,
    border_thickness: float = 0.0,
) -> None:
    buffer, total_voxels = render(
        "oval",
        width=width,
        height=height,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
        hollow=hollow,
        thickness=border_thickness,
    )

    await interaction.response.send_message(
        embed=generate_embed(
            "Oval",
            f"A freshly generated oval, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.blurple(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            border_thickness,
        ),
        file=discord.File(buffer, filename="oval.png"),
    )


@tree.command(description="Generate a lancet curve")
@app_commands.describe(
    width="Width of the lancet curve in voxels",
    height="Height of the lancet curve in voxels",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
)
async def lancet(
    interaction: discord.Interaction,
    width: int,
    height: int,
    offset_x: int = 0,
    offset_y: int = 0,
) -> None:
    buffer, total_voxels = render(
        "lancet",
        width=width,
        height=height,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
    )

    await interaction.response.send_message(
        embed=generate_embed(
            "Lancet Curve",
            f"A freshly generated Lancet Curve, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.gold(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
        ),
        file=discord.File(buffer, filename="lancet.png"),
    )


@tree.command(description="Generate a hanging rope/vine (catenary)")
@app_commands.describe(
    width="Horizontal span between the two anchors in voxels",
    height="Sag depth — how far the rope dips at its lowest point",
    thickness="Rope thickness in voxels",
    end_offset="Vertical drop of the right anchor vs the left (negative = right end higher)",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
)
async def catenary(
    interaction: discord.Interaction,
    width: int,
    height: int,
    thickness: float = 1.0,
    end_offset: int = 0,
    offset_x: int = 0,
    offset_y: int = 0,
) -> None:
    buffer, total_voxels = render(
        "catenary",
        width=width,
        height=height,
        thickness=thickness,
        end_offset=end_offset,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
    )

    await interaction.response.send_message(
        embed=generate_embed(
            "Catenary Rope",
            f"A freshly draped rope, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.dark_green(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            thickness,
            end_offset,
        ),
        file=discord.File(buffer, filename="catenary.png"),
    )


client.run(TOKEN)
