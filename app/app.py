import argparse
import io
import logging
import math
import os
import random
import typing

import discord
import dotenv
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

from app.shapes.catenary import fill_catenary
from app.shapes.egg import fill_egg
from app.shapes.lancet import fill_lancet
from app.shapes.oval import fill_oval
from app.shapes.polygon import fill_polygon
from app.shapes.horseshoe import fill_horseshoe
from app.shapes.star import fill_star

COLOR_BG = (30, 30, 30, 255)
COLOR_VOXEL = (180, 130, 70, 255)
COLOR_GRID_MINOR = (60, 60, 60, 255)
COLOR_GRID_MAJOR = (70, 130, 220, 200)
COLOR_CENTER_MARK = (100, 200, 255, 180)
COLOR_SHAPE_EDGE = (255, 220, 100, 120)
TERMS_OF_ENDEARMENT = ["sweety", "honey", "doll", "baby", "sweetheart", "darlin'"]
ACTIVITIES = ["Chiseling better than you 💅"]


def render(
    shape: str,
    width: int,
    height: int,
    cell_px: int = 24,
    block_size: int = 16,
    block_offset_x: int = 0,
    block_offset_y: int = 0,
    border: float | None = None,
    end_offset: int = 0,
    asymmetry: float = 0.0,
    sides: int = 3,
    angle: float = 0.0,
    opening: float = 62.0,
    nails: int = 7,
    inner_ratio: float = 0.5,
    coverage_threshold: float = 0.5,
) -> tuple[io.BytesIO, int]:
    # ── Pick shape ────────────────────────────────────────────────────────
    if shape == "oval":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_oval(
            width, height, border, coverage_threshold
        )
    elif shape == "lancet":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_lancet(
            width, height, border
        )
    elif shape == "catenary":
        if not border:
            border = 1.5
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_catenary(
            width, height, border, end_offset
        )
    elif shape == "egg":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_egg(
            width, height, border, asymmetry
        )
    elif shape == "polygon":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_polygon(
            width, height, border, sides, angle
        )
    elif shape == "horseshoe":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_horseshoe(
            width, height, border, opening, angle, nails
        )
    elif shape == "star":
        grid_w, grid_h, filled, cx, cy, label, draw_outline = fill_star(
            width, height, border, sides, angle, inner_ratio
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
    draw_outline(draw, cell_px, COLOR_SHAPE_EDGE, COLOR_CENTER_MARK)

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
        f"{'hollow  t=' + str(border) if border else 'filled'}",
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
    border: float | None = None,
    end_offset: int | None = None,
    asymmetry: float | None = None,
    sides: int | None = None,
    angle: float | None = None,
    opening: float | None = None,
    nails: int | None = None,
    inner_ratio: float | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_image(url="attachment://shape.png")

    embed.add_field(name="Width", value=str(width), inline=True)
    embed.add_field(name="Height", value=str(height), inline=True)
    if offset_x:
        embed.add_field(name="X Offset", value=str(offset_x), inline=True)
    if offset_y:
        embed.add_field(name="Y Offset", value=str(offset_y), inline=True)
    if border:
        embed.add_field(name="Border/Thickness", value=str(border), inline=True)
    if end_offset:
        embed.add_field(name="End Offset", value=str(end_offset), inline=True)
    if asymmetry:
        embed.add_field(name="Asymmetry", value=str(asymmetry), inline=True)
    if sides:
        embed.add_field(name="Sides/Points", value=str(sides), inline=True)
    if angle:
        embed.add_field(name="Angle", value=f"{angle}°", inline=True)
    if opening:
        embed.add_field(name="Opening", value=f"{opening}°", inline=True)
    if nails is not None:
        embed.add_field(name="Nails", value=str(nails), inline=True)
    if inner_ratio:
        embed.add_field(name="Inner Ratio", value=str(inner_ratio), inline=True)

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
    coverage_threshold="True oval coverage required to draw voxel. 0.0 = Any voxel touched by the oval gets drawn. 1.0 = Voxels must be completely covered by oval to be drawn.",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
    border="Makes the shape hollow - specify the thickness of the shape border.",
)
async def oval(
    interaction: discord.Interaction,
    width: int,
    height: int,
    coverage_threshold: float = 0.5,
    offset_x: int = 0,
    offset_y: int = 0,
    border: float | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "oval",
        width=width,
        height=height,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
        border=border,
        coverage_threshold=coverage_threshold,
    )

    await interaction.followup.send(
        embed=generate_embed(
            "Oval",
            f"A freshly generated oval, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.blurple(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            border,
        ),
        file=discord.File(buffer, filename="shape.png"),
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
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "lancet",
        width=width,
        height=height,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
    )

    await interaction.followup.send(
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
        file=discord.File(buffer, filename="shape.png"),
    )


@tree.command(description="Generate a hanging rope/vine (catenary)")
@app_commands.describe(
    length="Horizontal span between the two anchors in voxels",
    dip="Sag depth — how far the rope dips at its lowest point",
    thickness="Rope thickness in voxels",
    end_offset="Vertical drop of the right anchor vs the left (negative = right end higher)",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
)
async def catenary(
    interaction: discord.Interaction,
    length: int,
    dip: int,
    thickness: float = 1.5,
    end_offset: int = 0,
    offset_x: int = 0,
    offset_y: int = 0,
) -> None:
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "catenary",
        width=length,
        height=dip,
        border=thickness,
        end_offset=end_offset,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
    )

    await interaction.followup.send(
        embed=generate_embed(
            "Catenary Rope",
            f"A freshly draped rope, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.dark_green(),
            length,
            dip,
            offset_x,
            offset_y,
            total_voxels,
            thickness,
            end_offset,
        ),
        file=discord.File(buffer, filename="shape.png"),
    )


@tree.command(description="Generate an egg (Hügelschäffer oval)")
@app_commands.describe(
    width="Width (max breadth) of the egg in voxels",
    height="Height (length) of the egg in voxels",
    asymmetry="Pointiness: 0 = ellipse, ~0.3 = natural egg, up to 0.95.",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
    border="Makes the shape hollow - specify the thickness of the shape border.",
)
async def egg(
    interaction: discord.Interaction,
    width: int,
    height: int,
    asymmetry: float = 0.3,
    offset_x: int = 0,
    offset_y: int = 0,
    border: float = 0.0,
) -> None:
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "egg",
        width=width,
        height=height,
        asymmetry=asymmetry,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
        border=border,
    )

    await interaction.followup.send(
        embed=generate_embed(
            "Egg",
            f"A freshly laid egg, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.from_rgb(220, 200, 150),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            border,
            asymmetry=asymmetry,
        ),
        file=discord.File(buffer, filename="shape.png"),
    )


@tree.command(description="Generate a regular N-sided polygon")
@app_commands.describe(
    width="Width of the bounding box in voxels",
    height="Height of the bounding box in voxels",
    sides="Number of sides (3 = triangle, 4 = square, …)",
    angle="Rotation in degrees (counter-clockwise; 0 = flat bottom)",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
    border="Makes the shape hollow - specify the thickness of the shape border.",
)
async def polygon(
    interaction: discord.Interaction,
    width: int,
    height: int,
    sides: int,
    angle: float = 0.0,
    offset_x: int = 0,
    offset_y: int = 0,
    border: float | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "polygon",
        width=width,
        height=height,
        sides=sides,
        angle=angle,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
        border=border,
    )

    await interaction.followup.send(
        embed=generate_embed(
            "Polygon",
            f"A freshly chiselled {sides}-gon, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.teal(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            border,
            sides=sides,
            angle=angle,
        ),
        file=discord.File(buffer, filename="shape.png"),
    )


@tree.command(description="Generate a horseshoe")
@app_commands.describe(
    width="Width of the bounding box in voxels",
    height="Height of the bounding box in voxels",
    opening="Angular size of the gap at the top, in degrees",
    angle="Rotation in degrees (counter-clockwise; 0 = opening at the top)",
    nails="Number of nail holes along the band (0 to disable)",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
    border="Band thickness in voxels (defaults to ~28% of the radius).",
)
async def horseshoe(
    interaction: discord.Interaction,
    width: int,
    height: int,
    opening: float = 62.0,
    angle: float = 0.0,
    nails: int = 7,
    offset_x: int = 0,
    offset_y: int = 0,
    border: float | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "horseshoe",
        width=width,
        height=height,
        opening=opening,
        angle=angle,
        nails=nails,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
        border=border,
    )

    await interaction.followup.send(
        embed=generate_embed(
            "Horseshoe",
            f"Another horse is shoeless... {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.dark_grey(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            border,
            opening=opening,
            nails=nails,
        ),
        file=discord.File(buffer, filename="shape.png"),
    )


@tree.command(description="Generate an N-pointed star")
@app_commands.describe(
    width="Width of the bounding box in voxels",
    height="Height of the bounding box in voxels",
    points="Number of star points (5 = classic star)",
    inner_ratio="Spikiness: valley radius as a fraction of the point radius (lower = spikier)",
    angle="Rotation in degrees (counter-clockwise; 0 = a point straight up)",
    offset_x="Grid offset on the X axis in voxels.",
    offset_y="Grid offset on the Y axis in voxels.",
    border="Makes the shape hollow - specify the thickness of the shape border.",
)
async def star(
    interaction: discord.Interaction,
    width: int,
    height: int,
    points: int,
    inner_ratio: float = 0.5,
    angle: float = 0.0,
    offset_x: int = 0,
    offset_y: int = 0,
    border: float | None = None,
) -> None:
    await interaction.response.defer(thinking=True)
    buffer, total_voxels = render(
        "star",
        width=width,
        height=height,
        sides=points,
        inner_ratio=inner_ratio,
        angle=angle,
        block_offset_x=offset_x,
        block_offset_y=offset_y,
        border=border,
    )

    await interaction.followup.send(
        embed=generate_embed(
            "Star",
            f"A freshly cut {points}-point star, {random.choice(TERMS_OF_ENDEARMENT)} 💋",
            discord.Color.yellow(),
            width,
            height,
            offset_x,
            offset_y,
            total_voxels,
            border,
            sides=points,
            inner_ratio=inner_ratio,
        ),
        file=discord.File(buffer, filename="shape.png"),
    )


@tree.command(description="Calculate the raw fruit/syrup ratio with available fruit")
@app_commands.describe(
    total_fruit="Total amount of available fruit.",
    juice_per_fruit="The amount of juice 1 fruit produces.",
    syrup_per_juice="Ratio of syrup per juice.",
    syrup_per_candy="Amount of syrup used by 1 piece of candy.",
)
async def candied_fruit(
    interaction: discord.Interaction,
    total_fruit: int,
    juice_per_fruit: float = 0.3125,
    syrup_per_juice: float = 0.25,
    syrup_per_candy: float = 0.1,
    juice_limit: float = 5.0,
    bucket_limit: float = 10.0,
) -> None:
    optimal = total_fruit * 1.28 / 2.28
    to_juice = math.floor(optimal)

    # Walk up by 1 if rounding down wastes fruit
    for j in (to_juice, to_juice + 1):
        juice = j * juice_per_fruit
        syrup = juice * syrup_per_juice
        candy = min(total_fruit - j, int(syrup / syrup_per_candy))
        leftover_fruit = total_fruit - j - candy
        leftover_syrup = syrup - candy * syrup_per_candy
        if j == to_juice:
            best = (j, candy, leftover_fruit, leftover_syrup)
        elif candy > best[1] or (
            candy == best[1] and leftover_fruit + leftover_syrup < best[2] + best[3]
        ):
            best = (j, candy, leftover_fruit, leftover_syrup)

    j, candy, lf, ls = best

    total_syrup_needed = candy * syrup_per_candy
    total_juice_needed = total_syrup_needed / syrup_per_juice
    total_fruit_needed = math.ceil(total_juice_needed / juice_per_fruit)

    if total_juice_needed < juice_limit:
        await interaction.response.send_message(
            f"You only have enough fruit to juice {total_juice_needed}L. Which will not juice in the fruit press (you need at least {juice_limit}L).",
            ephemeral=True,
        )
        return

    fruit_per_bucket = int(bucket_limit // juice_per_fruit)

    full_stacks = total_fruit_needed // fruit_per_bucket
    left_over_fruit = total_fruit_needed - full_stacks * fruit_per_bucket
    left_over_arr = [left_over_fruit]
    if not left_over_fruit:
        left_over_arr = []
    elif left_over_fruit * juice_per_fruit < juice_limit:
        full_stacks -= 1
        juice_limit_fruit = math.ceil(juice_limit / juice_per_fruit)
        left_over_arr = [
            left_over_fruit + fruit_per_bucket - juice_limit_fruit,
            juice_limit_fruit,
        ]

    embed = discord.Embed(
        title=f"{total_fruit} fruit batch to candy", color=discord.Color.red()
    )
    embed.description = "# Procedure:\n"
    i = 1
    if full_stacks:
        embed.description += f"1. Juice {fruit_per_bucket} fruit {full_stacks} times (each gives {bucket_limit}L of juice)\n"
        i += 1
    for l in left_over_arr:
        embed.description += (
            f"{i}. Juice {l} fruits (Gives you {l*juice_per_fruit:.03}L of juice)\n"
        )
        i += 1

    embed.description += f"{i}. Simmer {total_juice_needed:.03}L juice into {total_syrup_needed:.03}L of syrup\n"
    i += 1
    embed.description += (
        f"{i}. Simmer the {candy} fruit with {candy*syrup_per_candy:.03}L of syrup\n"
    )
    i += 1
    embed.description += f"{i}. Enjoy a refreshing cup of {total_fruit_needed * juice_per_fruit - total_juice_needed:.03}L juice\n"
    i += 1

    embed.add_field(
        name="Total amount of fruit to juice",
        value=str(total_fruit_needed),
        inline=True,
    )
    embed.add_field(
        name="Amount of fruit to keep",
        value=str(total_fruit - total_fruit_needed),
        inline=True,
    )
    embed.add_field(name="Amount of candy created", value=str(candy), inline=True)
    embed.add_field(
        name="Leftover fruit",
        value=str(j - total_fruit_needed),
        inline=True,
    )
    embed.add_field(
        name="Leftover juice",
        value=f"{total_fruit_needed * juice_per_fruit - total_juice_needed:.03}L",
        inline=True,
    )

    await interaction.response.send_message(embed=embed)


client.run(os.environ["DISCORD_TOKEN"])
