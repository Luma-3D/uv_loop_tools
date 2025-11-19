# operators/match3d.py
import bpy
import bmesh

# mathutils の Vector / Color 等
from mathutils import Vector
from bpy.app.translations import pgettext as pgett
from .. import utils, properties

class UV_OT_loop_match3d_ratio(bpy.types.Operator):
    bl_idname = "uv.loop_match3d_ratio"
    bl_label = "Match 3D Ratio (Preserve Shape)"
    bl_description = "Redistribute selected UV edge loops so spacing matches 3D edge ratios while preserving shape"
    bl_options = {'UNDO'}
    closed_loop = bpy.props.EnumProperty(
        name="Loop Type",
        description="Specify if auto-detection fails",
        items=[('AUTO','Auto','Auto detect'),('OPEN','Open','Treat as open loop'),('CLOSED','Closed','Treat as closed loop')],
        default='AUTO'
    )
    weld_tolerance = bpy.props.FloatProperty(
        name="Weld tolerance",
        description="Round UV coordinates to this precision for welding",
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
        box0 = layout.box()
        box0.label(text="Loop Type / Options")
        row = box0.row(align=True)
        row.prop(self, "closed_loop", expand=True)
        box0.prop(self, "weld_tolerance")

    def execute(self, context):
        # normalize props to avoid _PropertyDeferred proxies
        try:
            weld_tolerance = float(self.weld_tolerance)
        except Exception:
            weld_tolerance = 1e-6

        ts = getattr(context, "tool_settings", None)
        if ts and getattr(ts, "use_uv_select_sync", False):
            self.report({'WARNING'}, "Cannot run while UV sync selection is on. Please disable sync in the UV editor header.")
            return {'CANCELLED'}

        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            if context.object and context.object.type=='MESH' and context.object.mode=='EDIT':
                objs = [context.object]
            else:
                self.report({'WARNING'}, "No editable mesh objects in edit mode.")
                return {'CANCELLED'}

        moved_vis_total = 0
        skipped = 0
        processed = 0
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

            graph_tol = min(weld_tolerance*0.25, 5e-7)
            def uv_key_graph(v):
                s = int(round(1.0/max(graph_tol,1e-12)))
                return (int(round(v.x*s)), int(round(v.y*s)))
            def uv_key_weld(v):
                s = int(round(1.0/max(weld_tolerance,1e-12)))
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
                    ln = l.link_loop_next
                    luvn = ln[uv_layer]

                    # Blender 5.0: select_edge は無効。両方のUVが選択されているかで判定する
                    if l.uv_select_edge:
                        ln = l.link_loop_next
                        p = Vector(luv.uv); q = Vector(luvn.uv)
                        add_map(p, l)
                        add_map(q, ln)
                        a = uv_key_graph(p); b = uv_key_graph(q)
                        graph.setdefault(a, set()).add(b)
                        graph.setdefault(b, set()).add(a)
                        found = True
            if not found:
                continue

            comps = utils.connected_components_keys(graph)
            if not comps:
                self.report({'ERROR'}, "Internal error: no connected components found.")
                return {'CANCELLED'}

            def read_uvs(keys):
                pts=[]
                for k in keys:
                    L = uv_to_loops.get(k,[])
                    if not L: return None
                    pts.append(Vector(L[0][uv_layer].uv))
                return pts
            def read_v3(keys):
                pts=[]
                for k in keys:
                    L = uv_to_loops.get(k,[])
                    if not L: return None
                    pts.append(Vector(L[0].vert.co))
                return pts
            def need_unwrap(points, is_closed):
                if not is_closed or len(points)<3: return False
                for i in range(len(points)):
                    a=points[i]; b=points[(i+1)%len(points)]
                    if abs(b.x-a.x)>0.5 or abs(b.y-a.y)>0.5: return True
                return False
            def resample_poly(points, fractions, closed=False):
                if not points: return []
                n=len(points)
                if (closed and n<3) or ((not closed) and n<2): return points[:]
                seg=[]; total=0.0
                if closed:
                    for i in range(n):
                        d=(points[(i+1)%n]-points[i]).length
                        seg.append(d); total+=d
                else:
                    for i in range(n-1):
                        d=(points[i+1]-points[i]).length
                        seg.append(d); total+=d
                if total<=1e-20: return points[:]
                def sample_at(dist):
                    if closed:
                        tt=dist%total; acc=0.0
                        for i in range(n):
                            L=seg[i]
                            if acc+L>=tt-1e-15:
                                tloc=0.0 if L<=1e-20 else (tt-acc)/L
                                return points[i].lerp(points[(i+1)%n], tloc)
                            acc+=L
                        return points[-1]
                    else:
                        tt=min(dist,total-1e-12); acc=0.0
                        for i in range(n-1):
                            L=seg[i]
                            if acc+L>=tt-1e-15:
                                tloc=0.0 if L<=1e-20 else (tt-acc)/L
                                return points[i].lerp(points[i+1], tloc)
                            acc+=L
                        return points[-1]
                out=[]
                for f in fractions:
                    fclamp=(f%1.0) if closed else max(0.0, min(1.0,f))
                    out.append(sample_at(fclamp*total))
                return out

            for comp in comps:
                sub = {k:set(nei for nei in graph.get(k,set()) if nei in comp) for k in comp}
                paths = utils.extract_paths_from_component(sub)
                if not paths:
                    skipped+=1
                    continue

                for ordered_keys, path_is_closed in paths:
                    # ignore trivial
                    if len(set(ordered_keys))<=2:
                        skipped+=1
                        continue

                    # ユーザ指定が優先。AUTOなら path_is_closed を尊重。
                    if self.closed_loop == 'OPEN':
                        is_closed = False
                    elif self.closed_loop == 'CLOSED':
                        is_closed = True
                    else:
                        is_closed = bool(path_is_closed)

                    # 保険：degrees による判定が必要ならここで確認（extract が怪しい場合）
                    deg = [len(sub.get(k, set())) for k in ordered_keys]
                    if len(ordered_keys) >= 3 and all(d == 2 for d in deg):
                        is_closed = True

                    pts_uv = read_uvs(ordered_keys)
                    pts3   = read_v3(ordered_keys)
                    if pts_uv is None or pts3 is None:
                        self.report({'ERROR'}, "Internal error: failed to read corresponding UVs/vertices.")
                        return {'CANCELLED'}

                    uw = need_unwrap(pts_uv, is_closed)
                    proc = utils.unwrap_cycle01(pts_uv) if (is_closed and uw) else pts_uv
                    dedup, idx_map = utils.dedup_with_map(proc, closed=is_closed, eps=1e-9)
                    m=len(dedup)
                    if (is_closed and m<3) or ((not is_closed) and m<2):
                        skipped+=1
                        continue

                    pts3_aligned=[]; seen=set()
                    for j in range(m):
                        pick=None
                        for i,jm in enumerate(idx_map):
                            if jm==j and i not in seen:
                                pick=i; seen.add(i); break
                        if pick is None: pick=0
                        pts3_aligned.append(pts3[pick].copy())

                    seg3=[]; total3=0.0; n3=len(pts3_aligned)
                    if is_closed:
                        for i in range(n3):
                            d=(pts3_aligned[(i+1)%n3]-pts3_aligned[i]).length
                            seg3.append(d); total3+=d
                    else:
                        for i in range(n3-1):
                            d=(pts3_aligned[i+1]-pts3_aligned[i]).length
                            seg3.append(d); total3+=d
                    if total3<=1e-20:
                        skipped+=1
                        continue

                    fracs=[0.0]; acc=0.0
                    if is_closed:
                        for i in range(n3-1): acc+=seg3[i]; fracs.append(acc/total3)
                    else:
                        for i in range(n3-2): acc+=seg3[i]; fracs.append(acc/total3)
                        fracs.append(1.0)

                    new_pts = resample_poly(dedup, fracs, closed=is_closed)
                    if is_closed and uw:
                        new_pts = utils.wrap01(new_pts)

                    new_uvs = [new_pts[idx_map[i]] for i in range(len(ordered_keys))]
                    moved_vis=set()
                    for i,k in enumerate(ordered_keys):
                        if uv_key_weld(proc[i]) != uv_key_weld(new_uvs[i]):
                            moved_vis.add(uv_key_weld(proc[i]))
                    applied=set()
                    for i,k in enumerate(ordered_keys):
                        nv = new_uvs[i]
                        for loop in uv_to_loops.get(k,[]):
                            for l2 in utils.gather_welded_uv_loops(loop, uv_layer, uv_key_weld):
                                if l2 not in applied:
                                    l2[uv_layer].uv = nv
                                    applied.add(l2)
                    if is_closed:
                        count_closed+=1
                    else:
                        count_open+=1
                    moved_vis_total+=len(moved_vis)
                    processed+=1

            try:
                bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            except Exception:
                pass

        if processed==0:
            if skipped>0:
                self.report({'INFO'}, "No valid loops found or skipped due to zero 3D length.")
            else:
                self.report({'ERROR'}, "No valid edge loops found.")
            return {'CANCELLED'}
        msg=pgett("3D Ratio (preserve shape): Open {count_open} / Closed {count_closed} Moved verts {moved_vis_total}").format(
            count_open=count_open, 
            count_closed=count_closed, 
            moved_vis_total=moved_vis_total
        )
        if skipped>0: msg+=pgett(" Skipped {skipped}").format(skipped=skipped)
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class UV_OT_loop_match3d_ratio_straight_open(bpy.types.Operator):
    bl_idname = "uv.loop_match3d_ratio_straight_open"
    bl_label = "Match 3D Ratio Straighten (Open loops only)"
    bl_description = "For open loops, redistribute along the endpoint line according to 3D spacing ratios (closed loops unchanged)"
    bl_options = {'UNDO'}

    weld_tolerance = bpy.props.FloatProperty(
        name="Weld tolerance",
        description="Round UV coordinates to this precision for welding",
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
        box.label(text="Options")
        box.prop(self, "weld_tolerance")

    def execute(self, context):
        # normalize props to avoid _PropertyDeferred proxies
        try:
            weld_tolerance = float(self.weld_tolerance)
        except Exception:
            weld_tolerance = 1e-6

        ts = getattr(context, "tool_settings", None)
        if ts and getattr(ts, "use_uv_select_sync", False):
            self.report({'WARNING'}, "Cannot run while UV sync selection is on. Please disable sync in the UV editor header.")
            return {'CANCELLED'}

        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            if context.object and context.object.type=='MESH' and context.object.mode=='EDIT':
                objs = [context.object]
            else:
                self.report({'WARNING'}, "No editable mesh objects in edit mode.")
                return {'CANCELLED'}

        moved_vis_total = 0
        skipped = 0
        processed = 0
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

            graph_tol = min(weld_tolerance*0.25, 5e-7)
            def uv_key_graph(v):
                s = int(round(1.0/max(graph_tol,1e-12)))
                return (int(round(v.x*s)), int(round(v.y*s)))
            def uv_key_weld(v):
                s = int(round(1.0/max(weld_tolerance,1e-12)))
                return (int(round(v.x*s)), int(round(v.y*s)))

            graph={}; uv_to_loops={}
            def add_map(pt, loop):
                k = uv_key_graph(pt)
                uv_to_loops.setdefault(k, []).append(loop)

            found=False
            for f in bm.faces:
                if f.hide: continue
                for l in f.loops:
                    luv = l[uv_layer]
                    ln = l.link_loop_next
                    luvn = ln[uv_layer]

                    # Blender 5.0: select_edge は無効。両方のUVが選択されているかで判定する
                    if l.uv_select_edge:
                        ln = l.link_loop_next
                        p = Vector(luv.uv); q = Vector(luvn.uv)
                        add_map(p, l)
                        add_map(q, ln)
                        a = uv_key_graph(p); b = uv_key_graph(q)
                        graph.setdefault(a, set()).add(b)
                        graph.setdefault(b, set()).add(a)
                        found = True
            if not found:
                continue

            comps = utils.connected_components_keys(graph)
            if not comps:
                self.report({'ERROR'}, "内部エラー：連結成分が見つかりません。")
                return {'CANCELLED'}

            def read_uvs(keys):
                pts=[]
                for k in keys:
                    L=uv_to_loops.get(k,[])
                    if not L: return None
                    pts.append(Vector(L[0][uv_layer].uv))
                return pts
            def read_v3(keys):
                pts=[]
                for k in keys:
                    L=uv_to_loops.get(k,[])
                    if not L: return None
                    pts.append(Vector(L[0].vert.co))
                return pts

            for comp in comps:
                sub = {k:set(nei for nei in graph.get(k,set()) if nei in comp) for k in comp}
                paths = utils.extract_paths_from_component(sub)
                if not paths:
                    skipped += 1
                    continue

                for ordered_keys, path_is_closed in paths:
                    # use returned path_is_closed as primary判定
                    is_closed = bool(path_is_closed)

                    # trivial path guard
                    if len(set(ordered_keys)) <= 2:
                        skipped += 1
                        continue

                    # --- Additional safety checks to *force skip* closed loops ---
                    # 1) degree-based check (all deg==2 and length>=3 -> closed)
                    deg_vals = [len(sub.get(k, set())) for k in ordered_keys]
                    if len(ordered_keys) >= 3 and all(d == 2 for d in deg_vals):
                        is_closed = True

                    # 2) coordinate-based check: first/last UV nearly equal -> closed
                    uv_coords = read_uvs(ordered_keys)
                    if uv_coords is None:
                        skipped += 1
                        continue
                    coord_tol = max(weld_tolerance * 10.0, 1e-6)
                    if len(uv_coords) >= 3 and (uv_coords[0] - uv_coords[-1]).length <= coord_tol:
                        is_closed = True

                    # If determined closed by any check, skip (this operator targets open loops only)
                    if is_closed:
                        count_closed += 1
                        skipped += 1
                        continue
                    # --- end safety checks ---

                    # proceed with open-loop straightening (unchanged logic below)
                    pts_uv = uv_coords
                    pts3   = read_v3(ordered_keys)
                    if pts3 is None:
                        self.report({'ERROR'}, "内部エラー：対応UV/頂点が読み取れませんでした。")
                        return {'CANCELLED'}

                    # dedup + guard
                    dedup, idx_map = utils.dedup_with_map(pts_uv, closed=False, eps=1e-9)
                    m=len(dedup)
                    if m<2:
                        skipped+=1
                        continue

                    pts3_aligned=[pts3[next((i for i,jm in enumerate(idx_map) if jm==j),0)].copy() for j in range(m)]
                    seg3=[]; total3=0.0
                    for i in range(m-1):
                        d=(pts3_aligned[i+1]-pts3_aligned[i]).length
                        seg3.append(d); total3+=d
                    if total3<=1e-20:
                        skipped+=1
                        continue
                    fracs=[0.0]; acc=0.0
                    for i in range(m-2): acc+=seg3[i]; fracs.append(acc/total3)
                    fracs.append(1.0)

                    a=dedup[0]; b=dedup[-1]
                    new_pts=[a.lerp(b, f) for f in fracs]

                    new_uvs=[new_pts[idx_map[i]] for i in range(len(ordered_keys))]
                    moved_vis=set()
                    for i,k in enumerate(ordered_keys):
                        if uv_key_weld(pts_uv[i]) != uv_key_weld(new_uvs[i]):
                            moved_vis.add(uv_key_weld(pts_uv[i]))
                    applied=set()
                    for i,k in enumerate(ordered_keys):
                        nv = new_uvs[i]
                        for loop in uv_to_loops.get(k,[]):
                            for l2 in utils.gather_welded_uv_loops(loop, uv_layer, uv_key_weld):
                                if l2 not in applied:
                                    l2[uv_layer].uv = nv
                                    applied.add(l2)
                    moved_vis_total+=len(moved_vis); processed+=1; count_open+=1

            # update mesh per-object
            try:
                bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            except Exception:
                pass

        if processed==0:
            if skipped>0:
                self.report({'INFO'}, "Only closed loops, or no valid open loops were found (closed loops left unchanged).")
            else:
                self.report({'ERROR'}, "No valid edge loops found.")
            return {'CANCELLED'}
        msg=pgett("3D Ratio Straighten: Open {count_open} Moved verts {moved_vis_total}").format(
            count_open=count_open, 
            moved_vis_total=moved_vis_total
        )
        if skipped>0: msg+=pgett(" Skipped {skipped}").format(skipped=skipped)
        self.report({'INFO'}, msg)
        return {'FINISHED'}
    

classes = (
    UV_OT_loop_match3d_ratio,
    UV_OT_loop_match3d_ratio_straight_open,
)

def register():
    import bpy
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    import bpy
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
