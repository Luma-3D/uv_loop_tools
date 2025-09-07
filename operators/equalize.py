# operators/equalize.py
import bpy
import bmesh

# mathutils の Vector / Color 等
from mathutils import Vector
    
from .. import utils, properties

class UV_OT_loop_equalize(bpy.types.Operator):
    bl_idname = "uv.loop_equalize"
    bl_label = "UVエッジを等間隔に配置"
    bl_description = "選択したUVエッジループの開/閉を自動判定し、頂点を等間隔に並べ替えます"
    bl_options = {'REGISTER', 'UNDO'}

    closed_loop: bpy.props.EnumProperty(
        name="ループの種類",
        description="自動判定がうまくいかない場合に指定します",
        items=[
            ('AUTO', "自動判定", "端点数から開/閉を自動判定"),
            ('OPEN', "開ループ", "開ループとして処理"),
            ('CLOSED', "閉ループ", "閉ループとして処理"),
        ],
        default='AUTO'
    )

    repeat_closed_only: bpy.props.BoolProperty(
        name="閉ループのみ",
        description="有効な場合、開ループは繰り返しを1回に固定し、閉ループのみで繰り返しオプションを適用します",
        default=True
    )
    
    weld_tolerance: bpy.props.FloatProperty(
        name="同一点判定の丸め",
        description="この精度でUV座標を丸めて同一点として扱います",
        min=1e-8, max=1e-2, default=1e-6, subtype='FACTOR'
    )

    # --- 繰り返し制御 ---
    iter_mode: bpy.props.EnumProperty(
        name="繰り返しモード",
        description="Auto=収束するまで繰り返す / 回数指定=指定回数だけ実行",
        items=[
            ('AUTO',  "Auto",     "収束するまで自動で繰り返す（上限あり）"),
            ('COUNT', "回数指定", "指定回数だけ実行"),
        ],
        default='AUTO',
    )

    iter_count: bpy.props.IntProperty(
        name="繰り返し",
        description="回数指定モードの実行回数",
        min=1, max=100, default=5,
    )

    auto_max_iter: bpy.props.IntProperty(
        name="繰り返し回数上限",
        description="Auto時の最大繰り返し回数",
        min=1, max=25, default=12, options={'HIDDEN'}
    )

    converge_epsilon: bpy.props.FloatProperty(
        name="位置変化しきい値",
        description="Auto収束判定：最大位置変化で停止する距離しきい値",
        min=1e-9, max=1e-2, default=1e-6, options={'HIDDEN'}
    )

    spacing_cv_tol: bpy.props.FloatProperty(
        name="均等化率しきい値",
        description="Auto収束判定：セグメント長CV（標準偏差/平均）がこの値以下で停止",
        min=0.0, max=0.1, default=0.002, options={'HIDDEN'}
    )

    f9_iter_choice: bpy.props.EnumProperty(
        name="繰り返し（実行時に参照）",
        description="Nパネルと同じAuto/回数プリセット。変更すると内部の繰り返しモード/回数に同期されます",
        items=[('AUTO', "Auto", "収束するまで自動で繰り返す（上限あり）")] +
              [(c, c + "回", f"{c} 回だけ実行") for c in properties._PRESET_COUNTS],
        default='AUTO',
        update=utils._update_iter_from_f9_choice,
        options=set()  # HIDDENにしない：F9に表示したい
    )

    def invoke(self, context, event):
        if self.iter_mode == 'AUTO':
            self.f9_iter_choice = 'AUTO'
        else:
            self.f9_iter_choice = str(max(1, min(100, int(self.iter_count))))
        return self.execute(context)

    def draw(self, context):
        layout = self.layout

        box0 = layout.box()
        box0.label(text="ループ種別 / オプション")
        row = box0.row(align=True)
        row.prop(self, "closed_loop", expand=True)
        box0.prop(self, "weld_tolerance")

        box2 = layout.box()
        box2.label(text="繰り返し（実行時に参照）")
        row2 = box2.row(align=True)
        row2.prop(self, "f9_iter_choice", expand=True)

        box2.prop(self, "repeat_closed_only", text="閉ループのみ")

        col_adv = box2.column(align=True)
        col_adv.enabled = (self.iter_mode == 'AUTO')
        col_adv.prop(self, "auto_max_iter", text="Auto上限")
        col_adv.prop(self, "converge_epsilon")
        col_adv.prop(self, "spacing_cv_tol")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

    def execute(self, context):
        # Process all selected editable mesh objects in EDIT mode, or fallback to active_object.
        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            if context.object and context.object.type == 'MESH' and context.object.mode == 'EDIT':
                objs = [context.object]
            else:
                self.report({'WARNING'}, "編集モードにあるメッシュオブジェクトがありません。")
                return {'CANCELLED'}

        ts = getattr(context, "tool_settings", None)
        if ts and getattr(ts, "use_uv_select_sync", False):
            self.report({'WARNING'}, "UV選択同期がONのため実行できません。UVエディタのヘッダーで同期をOFFにしてください。")
            return {'CANCELLED'}

        # Aggregates across all objects
        processed = 0
        moved_vis_total = 0
        skipped = 0
        count_open = 0
        count_closed = 0
        total_iters = 0
        total_paths = 0

        graph_tolerance_global = min(self.weld_tolerance * 0.25, 5e-7)
        def uv_key_weld_global(v):
            s = int(round(1.0 / max(self.weld_tolerance, 1e-12)))
            return (int(round(v.x * s)), int(round(v.y * s)))

        for obj in objs:
            me = obj.data
            try:
                bm = bmesh.from_edit_mesh(me)
            except Exception:
                skipped += 1
                continue
            uv_layer = bm.loops.layers.uv.verify()

            graph_tolerance = min(self.weld_tolerance * 0.25, 5e-7)
            def uv_key_graph(v):
                s = int(round(1.0 / max(graph_tolerance, 1e-12)))
                return (int(round(v.x * s)), int(round(v.y * s)))

            def uv_key_weld(v):
                s = int(round(1.0 / max(self.weld_tolerance, 1e-12)))
                return (int(round(v.x * s)), int(round(v.y * s)))

            graph = {}
            uv_to_loops = {}
            def add_map_local(pt, loop):
                k = uv_key_graph(pt)
                uv_to_loops.setdefault(k, []).append(loop)

            found_edge = False
            for f in bm.faces:
                if f.hide:
                    continue
                for l in f.loops:
                    luv = l[uv_layer]
                    if hasattr(luv, "select_edge") and luv.select_edge:
                        ln = l.link_loop_next
                        p = Vector(luv.uv)
                        q = Vector(ln[uv_layer].uv)

                        add_map_local(p, l)
                        add_map_local(q, ln)

                        a = uv_key_graph(p)
                        b = uv_key_graph(q)
                        graph.setdefault(a, set()).add(b)
                        graph.setdefault(b, set()).add(a)

                        found_edge = True

            if not found_edge:
                continue

            components = utils.connected_components_keys(graph)
            if not components:
                skipped += 1
                continue

            def _read_points_from_mesh(keys):
                pts_local = []
                for kk in keys:
                    loops = uv_to_loops.get(kk, [])
                    if not loops:
                        return None
                    pts_local.append(Vector(loops[0][uv_layer].uv))
                return pts_local

            for comp in components:
                subgraph = {k: set(nei for nei in graph.get(k, set()) if nei in comp) for k in comp}
                paths = utils.extract_paths_from_component(subgraph)
                if not paths:
                    skipped += 1
                    continue

                for ordered_keys, is_closed in paths:
                    if self.closed_loop == 'OPEN':
                        is_closed = False
                    elif self.closed_loop == 'CLOSED':
                        is_closed = True
                    else:
                        deg_vals = [len(subgraph.get(k, set())) for k in ordered_keys]
                        is_closed = (len(ordered_keys) >= 3 and all(d == 2 for d in deg_vals))

                    if len(set(ordered_keys)) <= 2:
                        skipped += 1
                        continue

                    moved_vis_keys_path = set()
                    total_paths += 1

                    pts = _read_points_from_mesh(ordered_keys)
                    if pts is None:
                        continue

                    def _need_unwrap(points):
                        if not is_closed or len(points) < 3:
                            return False
                        for i in range(len(points)):
                            a = points[i]
                            b = points[(i + 1) % len(points)]
                            if abs(b.x - a.x) > 0.5 or abs(b.y - a.y) > 0.5:
                                return True
                        return False

                    need_unwrap = _need_unwrap(pts)

                    endpoint_keys = set()
                    if not is_closed and len(ordered_keys) >= 2:
                        endpoint_keys.add(ordered_keys[0])
                        endpoint_keys.add(ordered_keys[-1])

                    degree_map = {k: len(subgraph.get(k, set())) for k in ordered_keys}
                    junction_keys = {k for k, d in degree_map.items() if d != 2}
                    endpoint_keys.update(junction_keys)
                    movable_mask = [(k not in endpoint_keys) for k in ordered_keys]

                    if self.iter_mode == 'COUNT':
                        default_max_iter = max(1, int(self.iter_count))
                        default_stop_on_converge = False
                    else:
                        default_max_iter = max(1, int(self.auto_max_iter))
                        default_stop_on_converge = True

                    if getattr(self, 'repeat_closed_only', False) and not is_closed:
                        max_iter = 1
                        stop_on_converge = False
                    else:
                        max_iter = default_max_iter
                        stop_on_converge = default_stop_on_converge

                    eps_pos = max(self.converge_epsilon, self.weld_tolerance * 0.5)
                    eps_cv = self.spacing_cv_tol

                    iters_used = 0
                    for it in range(max_iter):
                        pts = _read_points_from_mesh(ordered_keys)
                        if pts is None:
                            break
                        pts_proc = utils.unwrap_cycle01(pts) if (is_closed and need_unwrap) else pts

                        pts_dedup, idx_map = utils.dedup_with_map(pts_proc, closed=is_closed, eps=1e-9)
                        if (is_closed and len(pts_dedup) < 3) or ((not is_closed) and len(pts_dedup) < 2):
                            skipped += 1
                            break

                        new_pts = utils.redistribute_evenly(
                            pts_dedup,
                            preserve_ends=(not is_closed),
                            closed=is_closed,
                            eps=1e-9,
                        )
                        if is_closed and need_unwrap:
                            new_pts = utils.wrap01(new_pts)

                        new_uvs_by_key = [new_pts[idx_map[i]] for i in range(len(ordered_keys))]
                        current_uvs = pts

                        dmax = utils._max_displacement(current_uvs, new_uvs_by_key, movable_mask)
                        cv = utils._spacing_cv(new_pts, closed=is_closed)

                        for i, k in enumerate(ordered_keys):
                            if not movable_mask[i]:
                                continue
                            cur_key = uv_key_weld(current_uvs[i])
                            new_key = uv_key_weld(new_uvs_by_key[i])
                            if cur_key != new_key:
                                moved_vis_keys_path.add(cur_key)

                        applied = set()
                        for i, k in enumerate(ordered_keys):
                            if not movable_mask[i]:
                                continue
                            new_uv = new_uvs_by_key[i]
                            for loop in uv_to_loops.get(k, []):
                                for l2 in utils.gather_welded_uv_loops(loop, uv_layer, uv_key_weld):
                                    if l2 not in applied:
                                        l2[uv_layer].uv = new_uv
                                        applied.add(l2)

                        if stop_on_converge and ((dmax <= eps_pos) or (cv <= eps_cv)):
                            iters_used = it + 1
                            break

                    if iters_used == 0:
                        iters_used = max_iter
                    total_iters += iters_used

                    if is_closed:
                        count_closed += 1
                    else:
                        count_open += 1

                    moved_vis_total += len(moved_vis_keys_path)
                    processed += 1

            try:
                bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            except Exception:
                pass

        avg_iter = (total_iters / max(1, total_paths)) if total_paths > 0 else 0.0

        if processed == 0:
            if skipped > 0:
                self.report({'ERROR'}, "順序復元に失敗（分岐など）のため処理を中止しました。")
            else:
                self.report({'ERROR'}, "処理可能なエッジループが見つかりませんでした。")
            return {'CANCELLED'}

        msg = (f"エッジループ: 開 {count_open} / 閉 {count_closed} "
               f"繰り返し 合計 {total_iters} 回（平均 {avg_iter:.2f} 回/ループ） "
               f"移動頂点数 {moved_vis_total}")
        if skipped > 0:
            msg += f"  スキップ {skipped}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}

class UV_OT_loop_equalize_straight_open(bpy.types.Operator):
    bl_idname = "uv.loop_equalize_straight_open"
    bl_label = "UV開ループを直線均等配置"
    bl_description = "開ループのみを対象に、端点を結ぶ直線上へ等間隔で再配置します（閉ループは変更しません）"
    bl_options = {'REGISTER', 'UNDO'}

    weld_tolerance: bpy.props.FloatProperty(
        name="同一点判定の丸め",
        description="この精度でUV座標を丸めて同一点として扱います（溶接・移動判定に使用）",
        min=1e-8, max=1e-2, default=1e-6, subtype='FACTOR'
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.mode == 'EDIT'

    def invoke(self, context, event):
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="オプション")
        box.prop(self, "weld_tolerance")

    def execute(self, context):
        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            if context.object and context.object.type == 'MESH' and context.object.mode == 'EDIT':
                objs = [context.object]
            else:
                self.report({'WARNING'}, "編集モードにあるメッシュオブジェクトがありません。")
                return {'CANCELLED'}

        ts = getattr(context, "tool_settings", None)
        if ts and getattr(ts, "use_uv_select_sync", False):
            self.report({'WARNING'}, "UV選択同期がONのため実行できません。UVエディタのヘッダーで同期をOFFにしてください。")
            return {'CANCELLED'}

        moved_vis_total = 0
        skipped = 0
        count_open = 0
        count_closed = 0
        processed = 0

        for obj in objs:
            me = obj.data
            try:
                bm = bmesh.from_edit_mesh(me)
            except Exception:
                skipped += 1
                continue
            uv_layer = bm.loops.layers.uv.verify()

            graph_tol = min(self.weld_tolerance * 0.25, 5e-7)
            def uv_key_graph(v):
                s = int(round(1.0 / max(graph_tol, 1e-12)))
                return (int(round(v.x * s)), int(round(v.y * s)))
            def uv_key_weld(v):
                s = int(round(1.0 / max(self.weld_tolerance,1e-12)))
                return (int(round(v.x*s)), int(round(v.y*s)))

            graph = {}
            uv_to_loops = {}
            def add_map(pt, loop):
                k = uv_key_graph(pt)
                uv_to_loops.setdefault(k, []).append(loop)

            found = False
            for f in bm.faces:
                if f.hide: continue
                for l in f.loops:
                    luv = l[uv_layer]
                    if hasattr(luv,'select_edge') and luv.select_edge:
                        ln = l.link_loop_next
                        p = Vector(luv.uv); q = Vector(ln[uv_layer].uv)
                        add_map(p,l); add_map(q,ln)
                        a = uv_key_graph(p); b = uv_key_graph(q)
                        graph.setdefault(a,set()).add(b)
                        graph.setdefault(b,set()).add(a)
                        found = True
            if not found:
                continue

            comps = utils.connected_components_keys(graph)
            if not comps:
                skipped += 1
                continue

            def read_uvs(keys):
                pts=[]
                for k in keys:
                    L=uv_to_loops.get(k,[])
                    if not L: return None
                    pts.append(Vector(L[0][uv_layer].uv))
                return pts

            for comp in comps:
                subgraph = {k: set(nei for nei in graph.get(k, set()) if nei in comp) for k in comp}
                paths = utils.extract_paths_from_component(subgraph)
                if not paths:
                    skipped += 1
                    continue
                for ordered_keys, is_closed in paths:
                    deg_vals = [len(subgraph.get(k, set())) for k in ordered_keys]
                    is_closed = (len(ordered_keys) >= 3 and all(d == 2 for d in deg_vals))
                    if len(set(ordered_keys)) <= 2:
                        skipped += 1
                        continue
                    if is_closed:
                        count_closed += 1
                        skipped += 1
                        continue

                    pts = read_uvs(ordered_keys)
                    if pts is None:
                        continue

                    endpoint_keys = set()
                    endpoint_keys.add(ordered_keys[0]); endpoint_keys.add(ordered_keys[-1])
                    degree_map = {k: len(subgraph.get(k, set())) for k in ordered_keys}
                    junction_keys = {k for k, d in degree_map.items() if d != 2}
                    endpoint_keys.update(junction_keys)
                    movable_mask = [(k not in endpoint_keys) for k in ordered_keys]

                    pts_dedup, idx_map = utils.dedup_with_map(pts, closed=False, eps=1e-9)
                    if len(pts_dedup) < 2:
                        skipped += 1
                        continue

                    n = len(pts_dedup)
                    a = pts_dedup[0]; b = pts_dedup[-1]
                    if n <= 2:
                        new_pts = pts_dedup[:]
                    else:
                        step = 1.0 / (n - 1)
                        new_pts = [a.lerp(b, i * step) for i in range(n)]

                    new_uvs_by_key = [new_pts[idx_map[i]] for i in range(len(ordered_keys))]
                    current_uvs = pts

                    moved_vis_keys_path = set()
                    for i, k in enumerate(ordered_keys):
                        if not movable_mask[i]:
                            continue
                        cur_key = uv_key_weld(current_uvs[i])
                        new_key = uv_key_weld(new_uvs_by_key[i])
                        if cur_key != new_key:
                            moved_vis_keys_path.add(cur_key)

                    applied = set()
                    for i, k in enumerate(ordered_keys):
                        if not movable_mask[i]:
                            continue
                        new_uv = new_uvs_by_key[i]
                        for loop in uv_to_loops.get(k, []):
                            for l2 in utils.gather_welded_uv_loops(loop, uv_layer, uv_key_weld):
                                if l2 not in applied:
                                    l2[uv_layer].uv = new_uv
                                    applied.add(l2)

                    moved_vis_total += len(moved_vis_keys_path)
                    processed += 1
                    count_open += 1

            try:
                bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            except Exception:
                pass

        if processed == 0:
            if skipped > 0:
                self.report({'INFO'}, "閉ループのみ、または処理可能な開ループが見つかりませんでした（閉ループは無処理）。")
            else:
                self.report({'ERROR'}, "処理可能なエッジループが見つかりませんでした。")
            return {'CANCELLED'}

        msg = (f"直線均等: 開 {count_open} / 閉（無処理）{count_closed} "
               f"移動頂点数 {moved_vis_total}")
        if skipped > 0:
            msg += f" スキップ {skipped}"
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