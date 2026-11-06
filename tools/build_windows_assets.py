from __future__ import annotations

import binascii
import struct
import zlib
import sys
from math import atan2, cos, pi, sin
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.version import APP_VERSION


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
SMALL_ICON_SIZES = {16, 20, 24, 32}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def _inside_rounded_square(x: float, y: float, size: float, radius: float) -> bool:
    if radius <= x < size - radius or radius <= y < size - radius:
        return True
    cx = radius if x < radius else size - radius
    cy = radius if y < radius else size - radius
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def _angle_in_range(angle: float, start: float, end: float) -> bool:
    angle %= 360.0
    start %= 360.0
    end %= 360.0
    if start <= end:
        return start <= angle <= end
    return angle >= start or angle <= end


def _point_in_triangle(px: float, py: float, a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    ax, ay = a
    bx, by = b
    cx, cy = c
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay
    dot00 = v0x * v0x + v0y * v0y
    dot01 = v0x * v1x + v0y * v1y
    dot02 = v0x * v2x + v0y * v2y
    dot11 = v1x * v1x + v1y * v1y
    dot12 = v1x * v2x + v1y * v2y
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-9:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    return u >= 0 and v >= 0 and (u + v) <= 1


def _arrow_triangle(center: float, radius: float, angle_deg: float, size: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    angle = angle_deg * pi / 180.0
    tip = (center + cos(angle) * radius, center - sin(angle) * radius)
    tangent = angle_deg + 90.0
    back = (tangent + 180.0) * pi / 180.0
    left = (tangent + 150.0) * pi / 180.0
    right = (tangent - 150.0) * pi / 180.0
    base = (tip[0] + cos(back) * size * 0.92, tip[1] - sin(back) * size * 0.92)
    left_pt = (base[0] + cos(left) * size * 0.78, base[1] - sin(left) * size * 0.78)
    right_pt = (base[0] + cos(right) * size * 0.78, base[1] - sin(right) * size * 0.78)
    return tip, left_pt, right_pt


def _blend(base: tuple[int, int, int, int], top: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    br, bg, bb, ba = base
    tr, tg, tb, ta = top
    if ta <= 0:
        return base
    if ta >= 255:
        return top
    a_top = ta / 255.0
    a_base = ba / 255.0
    out_a = a_top + a_base * (1.0 - a_top)
    if out_a <= 0:
        return (0, 0, 0, 0)
    r = int((tr * a_top + br * a_base * (1.0 - a_top)) / out_a + 0.5)
    g = int((tg * a_top + bg * a_base * (1.0 - a_top)) / out_a + 0.5)
    b = int((tb * a_top + bb * a_base * (1.0 - a_top)) / out_a + 0.5)
    return (r, g, b, int(out_a * 255 + 0.5))


def _sample_icon(x: float, y: float, size: int) -> tuple[int, int, int, int]:
    minimalist = size in SMALL_ICON_SIZES
    transparent = (0, 0, 0, 0)
    border = (53, 61, 79, 255)
    dark = (20, 24, 33, 255)
    dark_soft = (28, 33, 48, 255)
    violet = (143, 130, 255, 255)
    violet_soft = (176, 167, 255, 255)
    mint = (121, 221, 160, 255)
    mint_soft = (169, 239, 195, 255)
    highlight = (255, 255, 255, 30)

    center = size / 2.0
    corner_radius = size * (0.22 if minimalist else 0.18)
    if not _inside_rounded_square(x, y, size - 1.0, corner_radius):
        return transparent

    if minimalist:
        pixel = dark
    else:
        t = ((x / max(size - 1.0, 1.0)) + (y / max(size - 1.0, 1.0))) / 2.0
        pixel = tuple(int(dark_soft[i] * (1.0 - t) + dark[i] * t + 0.5) for i in range(3)) + (255,)
        border_width = max(1.0, size * 0.02)
        if not _inside_rounded_square(x - border_width, y - border_width, size - 1.0 - 2 * border_width, max(1.0, corner_radius - border_width)):
            return border
        dxg = x - center
        dyg = y - center
        glow_r = (dxg * dxg + dyg * dyg) ** 0.5 / max(size * 0.34, 1.0)
        if glow_r < 1.0:
            alpha = int((1.0 - glow_r) * 14)
            pixel = _blend(pixel, (255, 255, 255, max(0, alpha)))

    margin = size * (0.17 if minimalist else 0.20)
    ring_radius = (size - 2 * margin) / 2.0
    ring_thickness = size * (0.18 if minimalist else 0.115)
    inner_radius = ring_radius - ring_thickness / 2.0
    outer_radius = ring_radius + ring_thickness / 2.0

    dx = x - center
    dy = center - y
    distance = (dx * dx + dy * dy) ** 0.5
    angle = (atan2(dy, dx) * 180.0 / pi) % 360.0

    if minimalist:
        violet_start, violet_end = 28.0, 182.0
        mint_start, mint_end = 208.0, 362.0
        violet_arrow = _arrow_triangle(center, ring_radius, 182.0, size * 0.18)
        mint_arrow = _arrow_triangle(center, ring_radius, 362.0, size * 0.18)
    else:
        violet_start, violet_end = 24.0, 194.0
        mint_start, mint_end = 204.0, 374.0
        violet_arrow = _arrow_triangle(center, ring_radius, 194.0, size * 0.145)
        mint_arrow = _arrow_triangle(center, ring_radius, 374.0, size * 0.145)

    if inner_radius <= distance <= outer_radius and _angle_in_range(angle, violet_start, violet_end):
        pixel = violet
    elif inner_radius <= distance <= outer_radius and _angle_in_range(angle, mint_start, mint_end):
        pixel = mint
    elif _point_in_triangle(x, y, *violet_arrow):
        pixel = violet if minimalist else violet_soft
    elif _point_in_triangle(x, y, *mint_arrow):
        pixel = mint if minimalist else mint_soft

    if minimalist:
        return pixel

    inner_orbit_radius = size * 0.165
    inner_orbit_thickness = max(1.0, size * 0.02)
    if inner_orbit_radius - inner_orbit_thickness <= distance <= inner_orbit_radius + inner_orbit_thickness and _angle_in_range(angle, 48.0, 312.0):
        pixel = _blend(pixel, highlight)

    core_radius = size * 0.07
    if distance <= core_radius:
        alpha = int((1.0 - distance / max(core_radius, 1e-6)) * 105)
        pixel = _blend(pixel, (220, 224, 255, alpha))

    return pixel


def _make_icon_png(size: int = 256, supersample: int = 4) -> bytes:
    offsets = [((sx + 0.5) / supersample - 0.5, (sy + 0.5) / supersample - 0.5) for sy in range(supersample) for sx in range(supersample)]
    rows: list[bytes] = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            rs = gs = bs = alphas = 0
            for ox, oy in offsets:
                r, g, b, a = _sample_icon(x + 0.5 + ox, y + 0.5 + oy, size)
                rs += r
                gs += g
                bs += b
                alphas += a
            total = len(offsets)
            row.extend((
                int(rs / total + 0.5),
                int(gs / total + 0.5),
                int(bs / total + 0.5),
                int(alphas / total + 0.5),
            ))
        rows.append(bytes(row))

    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b"")


def write_icon(path: Path) -> None:
    images = [(size, _make_icon_png(size)) for size in ICON_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    directory = bytearray()
    offset = 6 + 16 * len(images)
    payload = bytearray()
    for size, png in images:
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        directory.extend(struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(png), offset))
        payload.extend(png)
        offset += len(png)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + payload)


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    values = []
    for part in version.split("."):
        try:
            values.append(int(part))
        except ValueError:
            values.append(0)
    return tuple((values + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def write_version_info(path: Path) -> None:
    version_tuple = _version_tuple(APP_VERSION)
    version_csv = ", ".join(str(value) for value in version_tuple)
    text = f'''VSVersionInfo(\n  ffi=FixedFileInfo(\n    filevers=({version_csv}),\n    prodvers=({version_csv}),\n    mask=0x3f,\n    flags=0x0,\n    OS=0x40004,\n    fileType=0x1,\n    subtype=0x0,\n    date=(0, 0)\n  ),\n  kids=[\n    StringFileInfo([\n      StringTable(\n        u'040904B0',\n        [StringStruct(u'CompanyName', u'TransferLoop'),\n         StringStruct(u'FileDescription', u'TransferLoop'),\n         StringStruct(u'FileVersion', u'{APP_VERSION}'),\n         StringStruct(u'InternalName', u'TransferLoop'),\n         StringStruct(u'OriginalFilename', u'TransferLoop.exe'),\n         StringStruct(u'ProductName', u'TransferLoop'),\n         StringStruct(u'ProductVersion', u'{APP_VERSION}')])\n    ]),\n    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])\n  ]\n)\n'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    output = Path("build") / "windows"
    write_icon(output / "transferloop.ico")
    write_version_info(output / "version_info.txt")
    print(APP_VERSION)


if __name__ == "__main__":
    main()
