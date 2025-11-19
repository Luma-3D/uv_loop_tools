# operators/equalize.py
import bpy
import bmesh
from mathutils import Vector
from bpy.app.translations import pgettext as pgett
from .. import utils, properties


class UV_OT_loop_equalize(bpy.types.Operator):
    bl_idname = "uv.loop_equalize"
    bl_label = "UV Edge Equalize"
    bl_description = "Evenly redistribute selected UV edge loops"
    bl_options = {'UNDO'}

    closed_loop = bpy.props.EnumProperty(
        name="Loop Type",
        description="Specify if auto-detection fails",
        items=[('AUTO','Auto','Auto detect'),('OPEN','Open','Treat as open loop'),('CLOSED','Closed','Treat as closed loop')],
        default='AUTO'
    )

    weld_tolerance = bpy.props.FloatProperty(
        name="Weld tolerance",
        description="Precision for treating UVs as identical",
        min=1e-8, max=1e-2, default=1e-6, subtype='FACTOR'
    )

    iter_mode = bpy.props.EnumProperty(
        name="Iteration Mode",
        items=[('AUTO','Auto','Auto until converge'), ('COUNT','Count','Fixed iterations')],
        default='AUTO'
    )
    iter_count = bpy.props.IntProperty(name="Iterations", min=1, max=100, default=5)
    auto_max_iter = bpy.props.IntProperty(name="Auto max iterations", min=1, max=25, default=12)
    converge_epsilon = bpy.props.FloatProperty(name="Converge epsilon", min=1e-9, max=1e-2, default=1e-6)

    def _safe_int(self, name, default=5):
        try:
            return int(getattr(self, name))
        except Exception:
            return int(default)

    def _safe_float(self, name, default=1e-6):
        try:
            return float(getattr(self, name))
        except Exception:
            return float(default)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        weld_tolerance = self._safe_float('weld_tolerance', 1e-6)
        converge_epsilon = self._safe_float('converge_epsilon', 1e-6)

        ts = getattr(context, 'tool_settings', None)
        if ts and getattr(ts, 'use_uv_select_sync', False):
            self.report({'WARNING'}, 'UV sync selection on; disable and retry')
            return {'CANCELLED'}

        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            if context.object and context.object.type == 'MESH' and context.object.mode == 'EDIT':
                objs = [context.object]
            else:
                self.report({'WARNING'}, 'No editable mesh in edit mode')
                return {'CANCELLED'}

        processed = 0
        skipped = 0
        moved_vis_total = 0
        total_iters = 0
        total_paths = 0
        count_open = 0
        count_closed = 0

        graph_tol = min(weld_tolerance * 0.25, 5e-7)
        def uv_key_graph(v):
            s = int(round(1.0 / max(graph_tol, 1e-12)))
            return (int(round(v.x * s)), int(round(v.y * s)))
        def uv_key_weld(v):
            s = int(round(1.0 / max(weld_tolerance, 1e-12)))
            return (int(round(v.x * s)), int(round(v.y * s)))

        for obj in objs:
            me = obj.data
            try:
                bm = bmesh.from_edit_mesh(me)
            except Exception:
                skipped += 1
                continue
            uv_layer = bm.loops.layers.uv.verify()

            graph = {}
            uv_to_loops = {}
            found = False
            for f in bm.faces:
                if f.hide: continue
                for l in f.loops:
                    luv = l[uv_layer]
                    ln = l.link_loop_next
                    luvn = ln[uv_layer]

                    # Blender 5.0 では select_edgeが機能しないため
                    if l.uv_select_edge:
                        ln = l.link_loop_next
                        p = Vector(luv.uv); q = Vector(luvn.uv)
                        a = uv_key_graph(p); b = uv_key_graph(q)
                        uv_to_loops.setdefault(a, []).append(l)
                        uv_to_loops.setdefault(b, []).append(ln)
                        graph.setdefault(a, set()).add(b)
                        graph.setdefault(b, set()).add(a)
                        found = True

            if not found:
                continue

            comps = utils.connected_components_keys(graph)
            if not comps:
                skipped += 1
                continue

            def read_uvs(keys):
                pts = []
                for k in keys:
                    L = uv_to_loops.get(k, [])
                    if not L: return None
                    pts.append(Vector(L[0][uv_layer].uv))
                return pts

            for comp in comps:
                sub = {k: set(nei for nei in graph.get(k, set()) if nei in comp) for k in comp}
                paths = utils.extract_paths_from_component(sub)
                if not paths:
                    skipped += 1
                    continue

                for ordered_keys, is_closed in paths:
                    if self.closed_loop == 'OPEN':
                        is_closed = False
                    elif self.closed_loop == 'CLOSED':
                        is_closed = True
                    else:
                        deg_vals = [len(sub.get(k, set())) for k in ordered_keys]
                        is_closed = (len(ordered_keys) >= 3 and all(d == 2 for d in deg_vals))

                    if len(set(ordered_keys)) <= 2:
                        skipped += 1
                        continue

                    pts = read_uvs(ordered_keys)
                    if pts is None:
                        continue

                    # simple equalize: redistribute along polyline preserving ends for open
                    if is_closed:
                        dedup, idx_map = utils.dedup_with_map(pts, closed=True, eps=1e-9)
                        if len(dedup) < 3:
                            skipped += 1
                            continue
                        new_pts = utils.redistribute_evenly(dedup, preserve_ends=False, closed=True)
                        if len(new_pts) != len(dedup):
                            new_pts = new_pts[:len(dedup)]
                    else:
                        dedup, idx_map = utils.dedup_with_map(pts, closed=False, eps=1e-9)
                        if len(dedup) < 2:
                            skipped += 1
                            continue
                        new_pts = utils.redistribute_evenly(dedup, preserve_ends=True, closed=False)

                    new_uvs = [new_pts[idx_map[i]] for i in range(len(ordered_keys))]
                    moved_vis_keys = set()
                    applied = set()
                    for i, k in enumerate(ordered_keys):
                        for loop in uv_to_loops.get(k, []):
                            for l2 in utils.gather_welded_uv_loops(loop, uv_layer, uv_key_weld):
                                if l2 not in applied:
                                    l2[uv_layer].uv = new_uvs[i]
                                    applied.add(l2)
                                    moved_vis_keys.add(k)

                    moved_vis_total += len(moved_vis_keys)
                    processed += 1
                    total_paths += 1
                    if is_closed:
                        count_closed += 1
                    else:
                        count_open += 1

            try:
                bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            except Exception:
                pass

        if processed == 0:
            if skipped > 0:
                self.report({'ERROR'}, 'No valid edge paths found (skipped due to topology).')
            else:
                self.report({'ERROR'}, 'No valid edge loops found.')
            return {'CANCELLED'}

        msg = pgett("Equalize: Open {count_open} / Closed {count_closed} Moved {moved_vis_total}").format(
            count_open=count_open,
            count_closed=count_closed,
            moved_vis_total=moved_vis_total
        )
        if skipped > 0:
            msg += pgett(" Skipped {skipped}").format(skipped=skipped)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class UV_OT_loop_equalize_straight_open(bpy.types.Operator):
    bl_idname = "uv.loop_equalize_straight_open"
    bl_label = "UV Straighten Open Loops"
    bl_description = "Redistribute open loops evenly along endpoint line"
    bl_options = {'UNDO'}

    weld_tolerance = bpy.props.FloatProperty(
        name="Weld tolerance",
        description="Precision for treating UVs as identical",
        min=1e-8, max=1e-2, default=1e-6, subtype='FACTOR'
    )

    def _safe_float(self, name, default=1e-6):
        try:
            return float(getattr(self, name))
        except Exception:
            return float(default)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        weld_tolerance = self._safe_float('weld_tolerance', 1e-6)

        ts = getattr(context, 'tool_settings', None)
        if ts and getattr(ts, 'use_uv_select_sync', False):
            self.report({'WARNING'}, 'UV sync selection on; disable and retry')
            return {'CANCELLED'}

        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            if context.object and context.object.type == 'MESH' and context.object.mode == 'EDIT':
                objs = [context.object]
            else:
                self.report({'WARNING'}, 'No editable mesh in edit mode')
                return {'CANCELLED'}

        processed = 0
        skipped = 0
        moved_vis_total = 0
        count_open = 0
        count_closed = 0

        for obj in objs:
            me = obj.data
            try:
                bm = bmesh.from_edit_mesh(me)
            except Exception:
                skipped += 1
                continue
            uv_layer = bm.loops.layers.uv.verify()

            graph_tol = min(weld_tolerance * 0.25, 5e-7)
            def uv_key_graph(v):
                s = int(round(1.0 / max(graph_tol, 1e-12)))
                return (int(round(v.x * s)), int(round(v.y * s)))
            def uv_key_weld(v):
                s = int(round(1.0 / max(weld_tolerance, 1e-12)))
                return (int(round(v.x * s)), int(round(v.y * s)))

            graph = {}
            uv_to_loops = {}
            found = False
            for f in bm.faces:
                if f.hide: continue
                for l in f.loops:
                    luv = l[uv_layer]
                    ln = l.link_loop_next
                    luvn = ln[uv_layer]

                    # Blender 5.0 では select_edgeが機能しないため
                    if l.uv_select_edge:
                        ln = l.link_loop_next
                        p = Vector(luv.uv); q = Vector(luvn.uv)
                        a = uv_key_graph(p); b = uv_key_graph(q)
                        uv_to_loops.setdefault(a, []).append(l)
                        uv_to_loops.setdefault(b, []).append(ln)
                        graph.setdefault(a, set()).add(b)
                        graph.setdefault(b, set()).add(a)
                        found = True
            if not found:
                continue

            comps = utils.connected_components_keys(graph)
            if not comps:
                skipped += 1
                continue

            def read_uvs(keys):
                pts = []
                for k in keys:
                    L = uv_to_loops.get(k, [])
                    if not L: return None
                    pts.append(Vector(L[0][uv_layer].uv))
                return pts

            for comp in comps:
                sub = {k: set(nei for nei in graph.get(k, set()) if nei in comp) for k in comp}
                paths = utils.extract_paths_from_component(sub)
                if not paths:
                    skipped += 1
                    continue

                for ordered_keys, is_closed in paths:
                    deg_vals = [len(sub.get(k, set())) for k in ordered_keys]
                    is_closed = (len(ordered_keys) >= 3 and all(d == 2 for d in deg_vals))
                    if is_closed:
                        count_closed += 1
                        skipped += 1
                        continue
                    if len(set(ordered_keys)) <= 2:
                        skipped += 1
                        continue

                    pts = read_uvs(ordered_keys)
                    if pts is None:
                        continue

                    dedup, idx_map = utils.dedup_with_map(pts, closed=False, eps=1e-9)
                    if len(dedup) < 2:
                        skipped += 1
                        continue

                    n = len(dedup)
                    a = dedup[0]; b = dedup[-1]
                    if n <= 2:
                        new_pts = dedup[:]
                    else:
                        step = 1.0 / (n - 1)
                        new_pts = [a.lerp(b, i * step) for i in range(n)]

                    new_uvs = [new_pts[idx_map[i]] for i in range(len(ordered_keys))]
                    moved_vis_keys = set()
                    applied = set()
                    for i, k in enumerate(ordered_keys):
                        for loop in uv_to_loops.get(k, []):
                            for l2 in utils.gather_welded_uv_loops(loop, uv_layer, uv_key_weld):
                                if l2 not in applied:
                                    l2[uv_layer].uv = new_uvs[i]
                                    applied.add(l2)
                                    moved_vis_keys.add(k)

                    moved_vis_total += len(moved_vis_keys)
                    processed += 1
                    count_open += 1

            try:
                bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            except Exception:
                pass

        if processed == 0:
            if skipped > 0:
                self.report({'INFO'}, 'No valid open loops found (closed loops unchanged).')
            else:
                self.report({'ERROR'}, 'No valid edge loops found.')
            return {'CANCELLED'}

        msg = pgett("Straighten open loops: Open {count_open} Moved {moved_vis_total}").format(count_open=count_open, moved_vis_total=moved_vis_total)
        if skipped > 0: msg += pgett(" Skipped {skipped}").format(skipped=skipped)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


classes = (
    UV_OT_loop_equalize,
    UV_OT_loop_equalize_straight_open,
)


def register():
    import bpy
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    import bpy
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)