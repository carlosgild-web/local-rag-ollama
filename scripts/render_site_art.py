"""Renders the product photos for the demo company's public website (decision 0011).

Blender is a build-time tool here; the app never needs it. Run from the repo root:

    blender -b --factory-startup -P scripts/render_site_art.py -- --out frontend/src/site/img
    blender -b --factory-startup -P scripts/render_site_art.py -- --only GB-1014 --samples 32

Every picture is built from geometry and shaders in this file, so it is original,
needs no license, and can be rendered again when the catalog changes. The product
data mirrors frontend/src/site/content.ts; keep the two in step.

Each shot is lit like a small product photo: warm paper underneath, a round key
light, a soft fill and a rim light, and a shallow depth of field.
"""

import argparse
import contextlib
import itertools
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

# --------------------------------------------------------------------------- catalog

BEADS = {
    "GB-1001": ("round", "#1f4f7a", "#2f8a8f"),  # Midnight Lagoon Round
    "GB-1002": ("faceted", "#d8b384", "#b98d5c"),  # Desert Sand Faceted
    "GB-1014": ("swirl", "#eadfe8", "#9fb0dd"),  # Opal Mist Swirl
    "GB-1027": ("round", "#c8643b", "#e9a23a"),  # Terracotta Sunrise
    "GB-1033": ("lentil", "#2d5443", "#7fae7f"),  # Deep Forest Lentil
}
CHARMS = {
    "CH-2004": ("moon", "gold"),
    "CH-2011": ("bee", "bronze"),
    "CH-2019": ("lotus", "rhodium"),
    "CH-2026": ("cactus", "gold"),
    "CH-2033": ("initial", "gold"),
}
FINDINGS = ("rings", "clasp", "wire", "memory")

S = 0.045  # Blender units per unit of the 100×100 charm drawings in art.tsx


# --------------------------------------------------------------------------- helpers


def lin(hexcolor: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """sRGB hex to the linear RGBA that Blender's shaders expect."""
    h = hexcolor.lstrip("#")
    rgb = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return (*rgb, alpha)


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def reset():
    for data in (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.node_groups,
    ):
        for item in list(data):
            data.remove(item)


# Principled BSDF input names changed in Blender 4.0; try the new name first.
INPUTS = {
    "color": ("Base Color",),
    "metallic": ("Metallic",),
    "roughness": ("Roughness",),
    "ior": ("IOR",),
    "transmission": ("Transmission Weight", "Transmission"),
    "subsurface": ("Subsurface Weight", "Subsurface"),
    "coat": ("Coat Weight", "Clearcoat"),
    "coat_roughness": ("Coat Roughness", "Clearcoat Roughness"),
}


def set_input(node, key, value):
    for name in INPUTS[key]:
        if name in node.inputs:
            node.inputs[name].default_value = value
            return


def material(name, color, **values):
    mat = bpy.data.materials.new(name)
    with contextlib.suppress(AttributeError):  # Blender 5 always uses nodes
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_input(bsdf, "color", lin(color) if isinstance(color, str) else color)
    for key, value in values.items():
        set_input(bsdf, key, value)
    return mat, bsdf


def add_bump(mat, bsdf, scale, strength, detail=4.0):
    """Fine surface noise: handmade glass and cast metal are never perfectly smooth."""
    nt = mat.node_tree
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return noise


def glass(name, body, accent, pattern="plain", transmission=0.25, milky=0.0):
    mat, bsdf = material(
        name,
        body,
        roughness=0.04,
        ior=1.52,
        transmission=transmission,
        subsurface=milky,
        coat=0.4,
        coat_roughness=0.02,
    )
    nt = mat.node_tree
    coords = nt.nodes.new("ShaderNodeTexCoord")
    if pattern == "swirl":
        # Organic lampwork swirl: bands bent by noise, so no two beads match.
        warp = nt.nodes.new("ShaderNodeTexNoise")
        warp.inputs["Scale"].default_value = 1.6
        warp.inputs["Detail"].default_value = 2.0
        offset = nt.nodes.new("ShaderNodeVectorMath")
        offset.operation = "MULTIPLY_ADD"
        offset.inputs[1].default_value = (0.9, 0.9, 0.9)
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "Z"
        wave.inputs["Scale"].default_value = 0.9
        wave.inputs["Distortion"].default_value = 3.0
        wave.inputs["Detail"].default_value = 2.0
        nt.links.new(coords.outputs["Object"], warp.inputs["Vector"])
        nt.links.new(warp.outputs["Color"], offset.inputs[0])
        nt.links.new(coords.outputs["Object"], offset.inputs[2])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[0].color = lin(body)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = lin(accent)
        nt.links.new(offset.outputs["Vector"], wave.inputs["Vector"])
        nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    elif pattern == "ring":
        # A band of the accent color around the face of a lentil bead.
        flat = nt.nodes.new("ShaderNodeVectorMath")
        flat.operation = "MULTIPLY"
        flat.inputs[1].default_value = (1.0, 1.0, 0.0)
        length = nt.nodes.new("ShaderNodeVectorMath")
        length.operation = "LENGTH"
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "EASE"
        els = ramp.color_ramp.elements
        els[0].position, els[0].color = 0.48, lin(body)
        els[1].position, els[1].color = 0.56, lin(accent)
        mid = els.new(0.66)
        mid.color = lin(accent)
        end = els.new(0.74)
        end.color = lin(body)
        nt.links.new(coords.outputs["Object"], flat.inputs[0])
        nt.links.new(flat.outputs["Vector"], length.inputs[0])
        nt.links.new(length.outputs["Value"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    add_bump(mat, bsdf, scale=6.0, strength=0.025)
    return mat


METAL = {
    "gold": ("#f2c66a", 0.16),
    "rhodium": ("#eef1f5", 0.08),
    "bronze": ("#8f643b", 0.36),
    "steel": ("#6b7078", 0.3),
    "base": ("#a3a29c", 0.28),
}


def metal(finish):
    color, rough = METAL[finish]
    mat, bsdf = material(f"metal-{finish}", color, metallic=1.0, roughness=rough)
    add_bump(mat, bsdf, scale=60.0, strength=0.06)
    if finish == "bronze":
        # Antique finish: darker in the recesses.
        nt = mat.node_tree
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = 0.15
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = lin("#3a2614")
        mix.inputs["B"].default_value = lin(color)
        nt.links.new(ao.outputs["AO"], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    return mat


def plain(name, color, roughness=0.5):
    return material(name, color, roughness=roughness)[0]


# --------------------------------------------------------------------------- meshes


def mesh_object(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def sphere(name, r, seg=64, rings=32, squash=1.0, smooth=True, along_hole=1.0):
    """A UV sphere; `squash` flattens Z, `along_hole` flattens X (lampwork beads are oblate)."""

    def build(bm):
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
        if squash != 1.0 or along_hole != 1.0:
            bmesh.ops.scale(bm, vec=(along_hole, 1.0, squash), verts=bm.verts)

    obj = mesh_object(name, build)
    for poly in obj.data.polygons:
        poly.use_smooth = smooth
    return obj


def cylinder(name, r, depth, seg=48):
    def build(bm):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth)

    obj = mesh_object(name, build)
    for poly in obj.data.polygons:
        poly.use_smooth = len(poly.vertices) == 4
    return obj


def torus(name, major, minor, seg=72, ring=18):
    me = bpy.data.meshes.new(name)
    verts, faces = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(ring):
            b = 2 * math.pi * j / ring
            rr = major + minor * math.cos(b)
            verts.append((rr * math.cos(a), rr * math.sin(a), minor * math.sin(b)))
    for i in range(seg):
        for j in range(ring):
            i2, j2 = (i + 1) % seg, (j + 1) % ring
            faces.append((i * ring + j, i2 * ring + j, i2 * ring + j2, i * ring + j2))
    me.from_pydata(verts, [], faces)
    for poly in me.polygons:
        poly.use_smooth = True
    return link(bpy.data.objects.new(name, me))


def tube(name, points, radius, mat, cyclic=False):
    """A wire or cord along 3D points."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 6
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for i, p in enumerate(points):
        sp.points[i].co = (*p, 1.0)
    sp.use_cyclic_u = cyclic
    obj = link(bpy.data.objects.new(name, cu))
    obj.data.materials.append(mat)
    return obj


# --------------------------------------------------------------------------- beads


def bead(code, r=1.0, at=(0.0, 0.0), yaw=0.0, name=None):
    """One glass bead resting on the ground, its hole along its local X axis."""
    shape, body, accent = BEADS[code]
    name = name or code
    if shape == "faceted":
        obj = sphere(name, r, seg=12, rings=8, smooth=False)
        mat = glass(name, body, accent, transmission=0.55)
        height = r
    elif shape == "lentil":
        obj = sphere(name, r, squash=0.55)
        mat = glass(name, body, accent, pattern="ring", transmission=0.2)
        height = 0.55 * r
    elif shape == "swirl":
        obj = sphere(name, r, along_hole=0.86)
        mat = glass(name, body, accent, pattern="swirl", transmission=0.35, milky=0.35)
        height = r
    else:
        obj = sphere(name, r, along_hole=0.86)
        mat = glass(name, body, accent, transmission=0.3, milky=0.15)
        height = r
    obj.data.materials.append(mat)

    cutter = cylinder(f"{name}-hole", 0.19 * r, 3.0 * r)
    cutter.rotation_euler = (0.0, math.pi / 2, 0.0)
    cutter.parent = obj
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    boolean = obj.modifiers.new("hole", "BOOLEAN")
    boolean.operation = "DIFFERENCE"
    boolean.object = cutter
    if shape != "faceted":
        bevel = obj.modifiers.new("soft-edge", "BEVEL")
        bevel.limit_method = "ANGLE"
        bevel.angle_limit = math.radians(50)
        bevel.width = 0.03 * r
        bevel.segments = 3

    if shape == "round":
        dot_mat = glass(f"{name}-dots", accent, accent, transmission=0.1)
        for k in range(6):
            phi = 2 * math.pi * k / 6 + (0.4 if k % 2 else 0.0)
            d = Vector((0.32 * (-1) ** k, math.cos(phi), math.sin(phi))).normalized()
            dot = sphere(f"{name}-dot{k}", 0.21 * r, seg=32, rings=16, squash=0.35)
            dot.data.materials.append(dot_mat)
            dot.parent = obj
            dot.location = d * 0.97 * r
            dot.rotation_euler = d.to_track_quat("Z", "Y").to_euler()

    obj.location = (at[0], at[1], height)
    obj.rotation_euler = (0.0, 0.0, yaw)
    return obj


# --------------------------------------------------------------------------- charms


def P(x, y):
    """A point of the 100×100 drawing (y down, centre 50,58) in Blender units."""
    return ((x - 50) * S, -(y - 58) * S)


def circle_pts(cx, cy, r, n=96):
    return [
        P(
            cx + r * math.cos(2 * math.pi * i / n),
            cy + r * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]


def ellipse_pts(cx, cy, rx, ry, rot=0.0, n=96):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        out.append(P(cx + x * c - y * s, cy + x * s + y * c))
    return out


def rrect_pts(x, y, w, h, r, n=10):
    out = []
    corners = (
        (x + w - r, y + r, -90),
        (x + w - r, y + h - r, 0),
        (x + r, y + h - r, 90),
        (x + r, y + r, 180),
    )
    for cx, cy, start in corners:
        for i in range(n + 1):
            a = math.radians(start + 90 * i / n)
            out.append(P(cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def cubic(p0, p1, p2, p3, n=24):
    out = []
    for i in range(n):
        t = i / n
        u = 1 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return out


def rotate(points, deg, cx, cy):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in points]


def star_pts(x, y, size):
    out = []
    for k in range(10):
        r = size * (0.45 if k % 2 else 1.0)
        a = -math.pi / 2 + k * math.pi / 5
        out.append(P(x + r * math.cos(a), y + r * math.sin(a)))
    return out


def crescent_pts(n=64):
    outer = [
        (52 + 28 * math.cos(math.radians(a)), 58 + 28 * math.sin(math.radians(a)))
        for a in _range(-90, -270, n)
    ]
    cx = 52 + math.sqrt(34**2 - 28**2)
    a0 = math.degrees(math.atan2(28, 52 - cx))
    inner = [
        (cx + 34 * math.cos(math.radians(a)), 58 + 34 * math.sin(math.radians(a)))
        for a in _range(a0, 360 - a0, n)
    ]
    return [P(x, y) for x, y in outer + inner[1:-1]]


def _range(start, stop, n):
    return [start + (stop - start) * i / n for i in range(n + 1)]


def charm_shapes(kind):
    """(points, extra height) for each solid piece of a charm."""
    if kind == "moon":
        # The star overlaps the inner edge of the moon, so the charm is cast in one piece.
        return [(crescent_pts(), 0.0), (star_pts(43, 61, 10.5), 0.04)]
    if kind == "bee":
        wings = [
            (ellipse_pts(37, 46, 11, 7, -25), -0.02),
            (ellipse_pts(63, 46, 11, 7, 25), -0.02),
        ]
        body = [(circle_pts(50, 37, 7), 0.0), (ellipse_pts(50, 62, 13, 18), 0.0)]
        stripes = [
            (rrect_pts(50 - w / 2, y - 1.6, w, 3.2, 1.5), 0.035)
            for y, w in ((56, 22), (63, 24), (70, 21))
        ]
        return wings + body + stripes
    if kind == "lotus":
        petal = cubic((50, 82), (39, 66), (41, 46), (50, 34)) + cubic(
            (50, 34), (59, 46), (61, 66), (50, 82)
        )
        pieces = []
        for deg, h in ((-62, -0.03), (62, -0.03), (-32, 0.0), (32, 0.0), (0, 0.03)):
            pieces.append(([P(x, y) for x, y in rotate(petal, deg, 50, 82)], h))
        pieces.append((ellipse_pts(50, 84, 18, 3.5), 0.0))
        return pieces
    if kind == "cactus":
        return [
            (rrect_pts(43, 30, 14, 54, 6.9), 0.03),
            (rrect_pts(27, 48, 10, 22, 4.9), 0.0),
            (rrect_pts(31, 63, 14, 7, 3.4), 0.0),
            (rrect_pts(63, 40, 10, 22, 4.9), 0.0),
            (rrect_pts(55, 55, 14, 7, 3.4), 0.0),
        ]
    if kind == "initial":
        return [(circle_pts(50, 58, 26), 0.0)]
    raise ValueError(kind)


def slab(name, points, mat, thick=0.1, bevel=0.025, lift=0.0, holes=()):
    """A flat piece cut from an outline (and any holes), lying on the ground."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = thick / 2
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    for loop in (points, *holes):
        sp = cu.splines.new("POLY")
        sp.points.add(len(loop) - 1)
        for i, (x, y) in enumerate(loop):
            sp.points[i].co = (x, y, 0.0, 1.0)
        sp.use_cyclic_u = True
    obj = link(bpy.data.objects.new(name, cu))
    obj.data.materials.append(mat)
    obj.location.z = thick / 2 + bevel + lift
    return obj


def charm(code_or_kind, finish=None, at=(0.0, 0.0), yaw=0.0, scale=1.0):
    """A charm lying flat with its bail loop and jump ring, parented to one empty."""
    kind, finish = CHARMS.get(code_or_kind, (code_or_kind, finish))
    mat = metal(finish)
    root = link(bpy.data.objects.new(f"{kind}-root", None))
    parts = []
    for i, (points, extra) in enumerate(charm_shapes(kind)):
        # Raised details are thicker, wings thinner; a hair of lift keeps faces from coinciding.
        parts.append(slab(f"{kind}-{i}", points, mat, thick=0.1 + extra, lift=i * 0.0007))
    if kind == "initial":
        parts.append(_letter(mat))
    bail = torus(f"{kind}-bail", 4.5 * S, 1.25 * S)
    bail.location = (*P(50, 26), 1.25 * S + 0.02)
    jump = torus(f"{kind}-jump", 6.5 * S, 1.1 * S)
    jump.location = (*P(50, 14), 1.1 * S + 0.12)
    jump.rotation_euler = (math.radians(14), 0.0, 0.0)
    for obj in (bail, jump):
        obj.data.materials.append(mat)
        parts.append(obj)
    for obj in parts:
        obj.parent = root
    root.location = (at[0], at[1], 0.0)
    root.rotation_euler = (0.0, 0.0, yaw)
    root.scale = (scale, scale, scale)
    return root


def _letter(mat):
    font_path = Path("C:/Windows/Fonts/georgiai.ttf")
    cu = bpy.data.curves.new("letter", "FONT")
    cu.body = "A"
    if font_path.exists():
        cu.font = bpy.data.fonts.load(str(font_path), check_existing=True)
    cu.size = 34 * S
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = 0.03
    cu.bevel_depth = 0.008
    obj = link(bpy.data.objects.new("letter", cu))
    obj.data.materials.append(mat)
    obj.location = (0.0, -0.05, 0.155)
    return obj


# --------------------------------------------------------------------------- findings


def finding(kind):
    if kind == "rings":
        for x, y, major, finish, tilt in (
            (-0.9, 0.2, 0.55, "rhodium", 0),
            (0.45, 0.6, 0.75, "gold", 8),
            (0.9, -0.55, 0.4, "base", -6),
        ):
            ring = torus(f"ring-{finish}", major, 0.075)
            ring.data.materials.append(metal(finish))
            ring.location = (x, y, 0.075 + abs(math.sin(math.radians(tilt))) * major)
            ring.rotation_euler = (math.radians(tilt), 0.0, 0.0)
            # a small gap, like a real open jump ring
            gap = ring.modifiers.new("gap", "BOOLEAN")
            cut = cylinder(f"gap-{finish}", 0.08, 1.0)
            cut.location = (x + major, y, 0.0)
            cut.hide_render = True
            cut.display_type = "WIRE"
            gap.operation = "DIFFERENCE"
            gap.object = cut
    elif kind == "clasp":
        # A lobster clasp: a claw-shaped body around its opening, the spring lever on
        # top of the right side, a trigger nub, and the ring it hangs from.
        gold = metal("gold")
        k = 1.5

        def at(points):
            return [(x * k, y * k) for x, y in (P(px, py) for px, py in points)]

        outer = cubic((50, 30), (66, 36), (72, 70), (50, 86)) + cubic(
            (50, 86), (30, 72), (32, 40), (50, 30)
        )
        hole = cubic((51, 42), (60, 47), (62, 68), (50, 76)) + cubic(
            (50, 76), (41, 68), (42, 50), (51, 42)
        )
        slab("clasp-body", at(outer), gold, thick=0.26, bevel=0.06, holes=[at(hole)])
        lever = cubic((53, 44), (60, 48), (62, 62), (57, 70)) + cubic(
            (57, 70), (59, 62), (58, 50), (53, 44)
        )
        slab("clasp-lever", at(lever), gold, thick=0.2, bevel=0.04, lift=0.2)
        slab(
            "clasp-nub",
            at([(61, 50), (68, 47), (69, 50), (62, 54)]),
            gold,
            thick=0.16,
            bevel=0.03,
            lift=0.2,
        )
        ring = torus("clasp-ring", 5.5 * S * k, 1.3 * S * k)
        ring.location = (*[v * k for v in P(50, 23)], 1.3 * S * k)
        ring.data.materials.append(gold)
    elif kind == "wire":
        spool = plain("spool", "#2b2622", 0.75)
        for z in (0.06, 1.04):
            flange = cylinder("flange", 1.25, 0.12)
            flange.location.z = z
            flange.data.materials.append(spool)
        core = cylinder("wire", 0.95, 0.86)
        core.location.z = 0.55
        wound = metal("rhodium")
        nt = wound.node_tree
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.bands_direction = "Z"
        wave.inputs["Scale"].default_value = 40.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.4
        nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
        core.data.materials.append(wound)
        end = [
            (0.95, 0.0, 0.5),
            (1.3, -0.15, 0.35),
            (1.75, -0.35, 0.05),
            (2.4, -0.45, 0.03),
            (2.9, -0.2, 0.03),
        ]
        tube("wire-end", end, 0.02, metal("rhodium"))
    elif kind == "memory":
        steel = metal("steel")
        turns, per_turn, radius, pitch = 4, 120, 1.1, 0.13
        pts = [
            (
                radius * math.cos(2 * math.pi * i / per_turn),
                radius * math.sin(2 * math.pi * i / per_turn),
                0.04 + pitch * i / per_turn,
            )
            for i in range(turns * per_turn + 1)
        ]
        tube("memory-wire", pts, 0.035, steel)
        for p in (pts[0], pts[-1]):
            cap = sphere("cap", 0.07, seg=24, rings=12)
            cap.location = p
            cap.data.materials.append(steel)


# --------------------------------------------------------------------------- studio


def studio(
    frame_width,
    target=(0.0, 0.0, 0.5),
    elevation=50.0,
    lens=85.0,
    res=(720, 540),
    fstop=0.2,
    samples=96,
    focus=None,
):
    """Camera, lights, paper and render settings. A low f-stop on these large
    units gives the shallow depth of field of a macro lens; `focus` is the point
    kept sharp (the target by default)."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 10
    scene.cycles.glossy_bounces = 6
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Punchy"
        scene.view_settings.exposure = 0.35
    except TypeError:
        scene.view_settings.view_transform = "Filmic"

    world = bpy.data.worlds.get("studio") or bpy.data.worlds.new("studio")
    with contextlib.suppress(AttributeError):
        world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = lin("#f8ecd9")
    bg.inputs["Strength"].default_value = 0.45
    scene.world = world

    ground = mesh_object(
        "ground",
        lambda bm: bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40.0),
    )
    paper, bsdf = material("paper", "#f4e6cf", roughness=0.75)
    add_bump(paper, bsdf, scale=180.0, strength=0.04)
    ground.data.materials.append(paper)

    target = Vector(target)
    fov = 2 * math.atan(18.0 / lens)
    distance = (frame_width / 2) / math.tan(fov / 2)
    el = math.radians(elevation)
    cam_data = bpy.data.cameras.new("camera")
    cam_data.lens = lens
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = fstop
    cam = link(bpy.data.objects.new("camera", cam_data))
    cam.location = target + Vector((0.0, -math.cos(el), math.sin(el))) * distance
    cam_data.dof.focus_distance = (Vector(focus or target) - cam.location).length
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    for name, size, energy, loc in (
        ("key", 5.0, 1150.0, (4.0, -4.5, 7.0)),
        ("fill", 8.0, 350.0, (-6.0, -3.0, 4.5)),
        ("rim", 3.0, 600.0, (-1.0, 6.0, 4.0)),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.shape = "DISK" if name == "key" else "RECTANGLE"
        data.size = size
        data.energy = energy * (frame_width / 6.0) ** 2
        light = link(bpy.data.objects.new(name, data))
        light.location = Vector(loc) * (frame_width / 6.0) + Vector((target.x, target.y, 0.0))
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()

    # A reflector where flat polished metal mirrors it toward the camera, so a
    # charm lying flat shows a bright sweep instead of the plain studio.
    data = bpy.data.lights.new("reflector", "AREA")
    data.shape = "RECTANGLE"
    data.size = frame_width * 0.5
    data.size_y = frame_width * 1.4
    data.energy = 260.0 * (frame_width / 6.0) ** 2
    reflector = link(bpy.data.objects.new("reflector", data))
    reflector.location = (
        target + Vector((frame_width * 0.12, math.cos(el), math.sin(el))) * distance * 0.35
    )
    reflector.rotation_euler = (target - reflector.location).to_track_quat("-Z", "Y").to_euler()


def render(out: Path, name: str):
    scene = bpy.context.scene
    settings = scene.render.image_settings
    try:
        settings.file_format = "WEBP"
        settings.quality = 82
    except TypeError:
        settings.file_format = "PNG"
    settings.color_mode = "RGB"
    scene.render.filepath = str(out / name)
    bpy.ops.render.render(write_still=True)
    print(f"rendered {name}", flush=True)


# --------------------------------------------------------------------------- shots


def shot_bead(code, samples):
    studio(7.6, target=(0.0, 1.0, 0.6), samples=samples, focus=(0.0, -0.3, 1.0), fstop=0.12)
    bead(code, at=(0.0, 0.0), yaw=math.radians(32), name=f"{code}-a")
    bead(code, at=(-1.9, 2.6), yaw=math.radians(-24), name=f"{code}-b")
    bead(code, at=(1.6, 3.4), yaw=math.radians(78), name=f"{code}-c")


def shot_charm(code, samples):
    studio(5.6, target=(0.0, 0.0, 0.1), elevation=58, samples=samples, fstop=0.6)
    charm(code, yaw=math.radians(-10))


def shot_finding(kind, samples):
    if kind == "wire":
        studio(5.6, target=(0.6, 0.0, 0.5), elevation=30, samples=samples, fstop=0.4)
    else:
        studio(5.2, target=(0.0, 0.0, 0.2), elevation=50, samples=samples, fstop=0.4)
    finding(kind)


def shot_starter_set(samples):
    """A scatter of beads and charms, like a starter set tipped out of its box."""
    studio(10.4, target=(0.0, 0.3, 0.3), elevation=56, samples=samples, fstop=5.6)
    rng = random.Random(7)
    placed: list[tuple[float, float, float]] = []

    def free(x, y, r):
        return all(math.hypot(x - px, y - py) > r + pr + 0.08 for px, py, pr in placed)

    # Charms first, so the biggest pieces always find room; then the beads, shuffled.
    beads = [("bead", code) for code in BEADS for _ in range(2)]
    rng.shuffle(beads)
    items = [("charm", code) for code in ("CH-2004", "CH-2011", "CH-2019", "CH-2026")] + beads
    for i, (what, code) in enumerate(items):
        r = 0.62 if what == "bead" else 1.35
        for _ in range(400):
            x, y = rng.uniform(-4.4, 4.4), rng.uniform(-2.6, 3.2)
            if (x / 4.5) ** 2 + ((y - 0.3) / 3.0) ** 2 <= 1 and free(x, y, r):
                break
        else:
            continue  # no room left for this piece: leave it out rather than overlap
        placed.append((x, y, r))
        if what == "bead":
            bead(code, r=r, at=(x, y), yaw=rng.uniform(0, math.pi), name=f"{code}-{i}")
        else:
            charm(code, at=(x, y), yaw=rng.uniform(-0.6, 0.6), scale=0.62)


def shot_hero(samples):
    """A necklace laid out in a U, graduated beads from the catalog and the moon charm."""
    studio(
        12.5,
        target=(0.0, 0.65, 0.3),
        elevation=62,
        lens=70,
        res=(1200, 900),
        samples=samples,
        fstop=8.0,
    )
    curve = [(5.5 * t, 4.4 * t * t) for t in _range(-1.0, 1.0, 400)]
    lengths = [0.0]
    for a, b in itertools.pairwise(curve):
        lengths.append(lengths[-1] + math.dist(a, b))

    def at(s):
        for i in range(1, len(lengths)):
            if lengths[i] >= s:
                f = (s - lengths[i - 1]) / (lengths[i] - lengths[i - 1])
                (x0, y0), (x1, y1) = curve[i - 1], curve[i]
                return (x0 + f * (x1 - x0), y0 + f * (y1 - y0)), math.atan2(y1 - y0, x1 - x0)
        return curve[-1], 0.0

    order = ["GB-1033", "GB-1001", "GB-1014", "GB-1027", "GB-1002"]
    radii = [0.72 - 0.04 * k for k in range(8)]
    mid = lengths[-1] / 2
    centers = []
    for side in (-1, 1):
        s = mid
        for k, r in enumerate(radii):
            if k:
                s += side * (radii[k - 1] + r + 0.02)
            elif side == 1:
                continue
            (x, y), angle = at(s)
            code = order[k % len(order)] if side < 0 else order[(k + 2) % len(order)]
            obj = bead(code, r=r, at=(x, y), yaw=angle, name=f"hero-{side}-{k}")
            centers.append((s, (x, y, obj.location.z)))
    centers.sort()
    cord = plain("cord", "#cbb89c", 0.7)
    (sx, sy), _ = at(max(centers[0][0] - 1.2, 0.0))
    (ex, ey), _ = at(min(centers[-1][0] + 1.2, lengths[-1]))
    tube(
        "cord",
        [(sx, sy, 0.05)] + [c for _, c in centers] + [(ex, ey, 0.05)],
        0.05,
        cord,
    )
    # Hung from the middle bead: its jump ring tucks under the bead.
    charm("CH-2004", at=(0.0, -2.05), scale=0.8)


# --------------------------------------------------------------------------- main


def jobs(samples):
    for code in BEADS:
        yield code, lambda c=code: shot_bead(c, samples)
    for code in CHARMS:
        yield code, lambda c=code: shot_charm(c, samples)
    for kind in FINDINGS:
        yield f"finding-{kind}", lambda k=kind: shot_finding(k, samples)
    yield "starter-set", lambda: shot_starter_set(samples)
    yield "hero-strand", lambda: shot_hero(samples)


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="render_site_art")
    parser.add_argument("--out", default="frontend/src/site/img")
    parser.add_argument("--only", nargs="*", help="names to render, e.g. GB-1014 hero-strand")
    parser.add_argument("--samples", type=int, default=96)
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name, build in jobs(args.samples):
        if args.only and name not in args.only:
            continue
        reset()
        build()
        render(out, name)


if __name__ == "__main__":
    main()
