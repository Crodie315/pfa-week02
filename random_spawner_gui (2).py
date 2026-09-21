"""
random_spawner_gui.py  --  paste into Maya's Script Editor (Python tab) and run with Ctrl+Enter.

Opens a small window with:
  * Count       how many primary objects to make (sphere companions are extra)
  * Min / Max   the size range of each object
  * Spawn       make the objects
  * Clear last  delete the objects from the most recent Spawn
  * Delete overlapping groups
                find objects in the most recent Spawn whose bounding boxes overlap, treat each
                connected cluster of overlapping objects as one group, and delete every object
                in those groups (objects that overlap nothing are kept)

Rules (unchanged): random sphere / cube / cone / cylinder with random color and position.
Every SPHERE gets one CUBE touching it; the other shapes get nothing extra.
One Ctrl+Z undoes one Spawn. Clear only deletes groups this tool created.
"""

import colorsys
import math
import random

import maya.cmds as cmds

# ----------------- fixed settings (not on the window; edit here if you like) -----------------
AREA = ((-10, 10), (0, 5), (-10, 10))   # x, y, z ranges for object centres
ON_GROUND = True                        # True: objects rest on y=0
WEIGHTS = {"sphere": 1, "cube": 1, "cone": 1, "cylinder": 1}   # relative odds
GAP = 0.0                               # extra space between a sphere and its companion cube
COLOR = None                            # None = random | (r, g, b) fixed | [(r,g,b), ...] palette
SEED = None                             # e.g. 42 for repeatable results
OVERLAP_TOL = 0.001                     # boxes must interpenetrate by more than this to count as overlapping
#                                         (so a sphere and its just-touching companion cube do NOT count)
# ---------------------------------------------------------------------------------------------

WINDOW = "randomSpawnerWin"
GROUP_NAME = "randomSpawn_grp"
TAG_ATTR = "randomSpawnerNodes"


# ------------------------------------------------------------------ building blocks
def make_shape(kind, size):
    r = size / 2.0
    if kind == "sphere":
        return cmds.polySphere(radius=r, name="spawn_sphere")[0]
    if kind == "cube":
        return cmds.polyCube(width=size, height=size, depth=size, name="spawn_cube")[0]
    if kind == "cone":
        return cmds.polyCone(radius=r, height=size, name="spawn_cone")[0]
    return cmds.polyCylinder(radius=r, height=size, name="spawn_cylinder")[0]


def pick_color(rng):
    if COLOR is None:
        return colorsys.hsv_to_rgb(rng.random(), rng.uniform(0.5, 0.9), rng.uniform(0.7, 1.0))
    if len(COLOR) == 3 and all(isinstance(c, (int, float)) for c in COLOR):
        return tuple(COLOR)
    return tuple(rng.choice(list(COLOR)))


def paint(transform, rgb):
    shader = cmds.shadingNode("lambert", asShader=True, name="spawn_lambert")
    cmds.setAttr(shader + ".color", rgb[0], rgb[1], rgb[2], type="double3")
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
    cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
    cmds.sets(transform, edit=True, forceElement=sg)
    return [shader, sg]


def weighted_choice(rng, kinds, odds):
    r = rng.uniform(0, sum(odds))
    for kind, w in zip(kinds, odds):
        r -= w
        if r <= 0:
            return kind
    return kinds[-1]


# ------------------------------------------------------------------ spawn / clear
def spawn(count, size_min, size_max):
    """Make `count` random objects (+ a companion cube per sphere). Returns (group, stats)."""
    if count < 1:
        raise ValueError("Count must be at least 1.")
    if size_min <= 0 or size_min > size_max:
        raise ValueError("Sizes must satisfy 0 < min <= max.")
    kinds = [k for k in ("sphere", "cube", "cone", "cylinder") if WEIGHTS.get(k, 0) > 0]
    if not kinds:
        raise ValueError("WEIGHTS needs at least one shape above 0.")
    odds = [WEIGHTS[k] for k in kinds]

    rng = random.Random(SEED)
    (xr, yr, zr) = AREA
    stats = {"sphere": 0, "cube": 0, "cone": 0, "cylinder": 0}

    cmds.undoInfo(openChunk=True, chunkName="randomSpawn")      # one Ctrl+Z per Spawn
    try:
        made, nodes = [], []

        def place(kind, size, x, z, y=None):
            t = make_shape(kind, size)
            if y is None:
                y = size / 2.0 if ON_GROUND else rng.uniform(yr[0], yr[1])
            cmds.xform(t, translation=(x, y, z), worldSpace=True)
            nodes.extend(paint(t, pick_color(rng)))
            made.append(t)
            stats[kind] += 1
            return y

        for _ in range(int(count)):
            kind = weighted_choice(rng, kinds, odds)
            size = rng.uniform(size_min, size_max)
            x, z = rng.uniform(xr[0], xr[1]), rng.uniform(zr[0], zr[1])
            y = place(kind, size, x, z)

            if kind == "sphere":                                 # the only rule that adds objects
                csize = rng.uniform(size_min, size_max)
                a = rng.uniform(0, 2 * math.pi)
                d = size / 2.0 + csize / 2.0 + GAP
                place("cube", csize, x + math.cos(a) * d, z + math.sin(a) * d,
                      y=(csize / 2.0 if ON_GROUND else y))

        group = cmds.group(made, name=GROUP_NAME)
        cmds.addAttr(group, longName=TAG_ATTR, dataType="string")
        cmds.setAttr(group + "." + TAG_ATTR, " ".join(nodes), type="string")
        cmds.select(group, replace=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    return group, stats


def newest_group():
    """The newest group this tool made (recognised by its tag attribute), or None."""
    groups = [g for g in (cmds.ls(GROUP_NAME + "*", type="transform") or [])
              if cmds.attributeQuery(TAG_ATTR, node=g, exists=True)]
    return groups[-1] if groups else None


def find_overlap_groups(boxes, tol=OVERLAP_TOL):
    """
    boxes: list of (xmin, ymin, zmin, xmax, ymax, zmax).
    Two boxes overlap if they interpenetrate by more than `tol` on ALL three axes.
    Overlaps chain: if A overlaps B and B overlaps C, then A, B and C form ONE group.
    Returns a list of groups (lists of indices); objects overlapping nothing are left out.
    """
    n = len(boxes)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        a = boxes[i]
        for j in range(i + 1, n):
            b = boxes[j]
            if all(a[k] < b[k + 3] - tol and b[k] < a[k + 3] - tol for k in range(3)):
                parent[find(i)] = find(j)

    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    return [c for c in clusters.values() if len(c) > 1]


def delete_overlaps():
    """
    In the newest spawn group, find clusters of overlapping objects and delete every
    object in every cluster (plus their shaders). Returns (group, clusters, objects),
    or None if there is no spawn group.
    """
    group = newest_group()
    if group is None:
        return None
    kids = cmds.listRelatives(group, children=True, type="transform", fullPath=True) or []
    boxes = [cmds.exactWorldBoundingBox(k) for k in kids]
    clusters = find_overlap_groups(boxes)
    if not clusters:
        return group, 0, 0
    doomed = [kids[i] for c in clusters for i in c]

    cmds.undoInfo(openChunk=True, chunkName="randomSpawnDeleteOverlaps")
    try:
        # collect the shaders that belong only to the objects being deleted
        shaders = set()
        for t in doomed:
            for shape in cmds.listRelatives(t, shapes=True, fullPath=True) or []:
                for sg in cmds.listConnections(shape, type="shadingEngine") or []:
                    shaders.add(sg)
                    shaders.update(cmds.listConnections(sg + ".surfaceShader",
                                                        source=True, destination=False) or [])
        cmds.delete(doomed)
        cmds.delete([s for s in shaders if cmds.objExists(s)])

        remaining = cmds.listRelatives(group, children=True, type="transform") or []
        if not remaining:
            cmds.delete(group)                     # nothing left: remove the empty group too
        else:
            kept = [n for n in (cmds.getAttr(group + "." + TAG_ATTR) or "").split()
                    if cmds.objExists(n)]
            cmds.setAttr(group + "." + TAG_ATTR, " ".join(kept), type="string")
    finally:
        cmds.undoInfo(closeChunk=True)
    return group, len(clusters), len(doomed)


def clear_last():
    """Delete the newest group this tool made (and its shaders). Returns its name or None."""
    group = newest_group()
    if group is None:
        return None
    cmds.undoInfo(openChunk=True, chunkName="randomSpawnClear")
    try:
        nodes = (cmds.getAttr(group + "." + TAG_ATTR) or "").split()
        cmds.delete(group)
        left = [n for n in nodes if cmds.objExists(n)]
        if left:
            cmds.delete(left)
    finally:
        cmds.undoInfo(closeChunk=True)
    return group


# ------------------------------------------------------------------ the window
def show_window():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    if cmds.windowPref(WINDOW, exists=True):
        cmds.windowPref(WINDOW, remove=True)

    cmds.window(WINDOW, title="Random Spawner", widthHeight=(400, 315), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))

    cmds.separator(height=6, style="none")
    count_ctrl = cmds.intSliderGrp(label="Count", field=True, value=20,
                                   minValue=1, maxValue=100, fieldMinValue=1, fieldMaxValue=1000,
                                   columnWidth3=(60, 60, 200))
    min_ctrl = cmds.floatSliderGrp(label="Min size", field=True, value=0.5, precision=2,
                                   minValue=0.1, maxValue=5, fieldMinValue=0.01, fieldMaxValue=100,
                                   columnWidth3=(60, 60, 200))
    max_ctrl = cmds.floatSliderGrp(label="Max size", field=True, value=2.0, precision=2,
                                   minValue=0.1, maxValue=5, fieldMinValue=0.01, fieldMaxValue=100,
                                   columnWidth3=(60, 60, 200))
    status = cmds.text(label="Set the values, then press Spawn.", align="left", height=32,
                       wordWrap=True)

    def set_status(msg):
        cmds.text(status, edit=True, label=msg)

    def on_spawn(*_):
        n = cmds.intSliderGrp(count_ctrl, query=True, value=True)
        lo = cmds.floatSliderGrp(min_ctrl, query=True, value=True)
        hi = cmds.floatSliderGrp(max_ctrl, query=True, value=True)
        try:
            group, stats = spawn(n, lo, hi)
        except ValueError as err:
            set_status("Cannot spawn: %s" % err)
            return
        total = sum(stats.values())
        set_status("Made %d objects (%d spheres, %d cubes, %d cones, %d cylinders)." % (
            total, stats["sphere"], stats["cube"], stats["cone"], stats["cylinder"]))
        try:
            cmds.viewFit(group)
        except Exception:
            pass

    def on_clear(*_):
        gone = clear_last()
        set_status("Cleared %s." % gone if gone else "Nothing to clear.")

    def on_delete_overlaps(*_):
        result = delete_overlaps()
        if result is None:
            set_status("Nothing to check: spawn something first.")
        elif result[2] == 0:
            set_status("No overlapping objects found.")
        else:
            set_status("Deleted %d overlapping objects in %d group(s)." % (result[2], result[1]))

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnAttach=[(1, "both", 2), (2, "both", 2)])
    cmds.button(label="Spawn", height=32, command=on_spawn)
    cmds.button(label="Clear last", height=32, command=on_clear)
    cmds.setParent("..")
    cmds.button(label="Delete overlapping groups", height=32, command=on_delete_overlaps)

    def on_undo(*_):
        # Every action above runs inside one undo chunk, so ONE undo reverses a whole
        # Spawn / Clear / Delete-overlaps, exactly like pressing Ctrl+Z.
        try:
            cmds.undo()
            set_status("Undid the last action.")
        except RuntimeError:
            set_status("Nothing to undo.")

    cmds.button(label="Undo (same as Ctrl+Z)", height=28, command=on_undo)

    cmds.showWindow(WINDOW)


show_window()
