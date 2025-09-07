# operators/spline.py (patched)
import bpy
import bmesh
import math
import blf

# mathutils の Vector / Color 等
from mathutils import Vector
import gpu
try:
    # batch_for_shader は gpu_extras.batch から
    from gpu_extras.batch import batch_for_shader
except Exception:
    # fallback: 定義が無ければ安全なダミーを返す（描画は noop）
    class _DummyBatch:
        def __init__(self, *a, **k):
            pass
        def draw(self, shader):
            # noop: 描画できない環境では何もしない
            return
    def batch_for_shader(shader, type, attrs):
        return _DummyBatch()

from .. import utils, properties

class CurveData:
    def __init__(self, orig_path, closed_locked):
        self.orig_path = [v.copy() for v in orig_path]
        self.closed_locked = bool(closed_locked)
        self.ctrl = []
        self.orig_fractions = []
        self.loops = []      # list of (obj, face_index, loop_index)
        self.orig_uvs = []
        self.active_idx = -1
        self.sel = set()
        self.obj = None
        self.uv_layer = None

class MultiSplineState:
    def __init__(self):
        self.curves = []
        self.active_curve = -1
        self.global_points = 0
    def all_closed_min(self):
        return 3 if any(c.closed_locked for c in self.curves) else 2
    def find_nearest_control(self, uv, threshold_px, view2d, region):
        best = 1e20; best_c = -1; best_i = -1
        px = Vector(view2d.view_to_region(uv.x, uv.y, clip=False))
        for ci, c in enumerate(self.curves):
            for i, v in enumerate(c.ctrl):
                cp = Vector(view2d.view_to_region(v.x, v.y, clip=False))
                d2 = (px - cp).length_squared
                if d2 < best:
                    best = d2; best_c = ci; best_i = i
        if best <= (threshold_px * threshold_px):
            return best_c, best_i
        return -1, -1
    def find_global_nearest_control(self, uv, view2d, region):
        best = 1e20; bc=-1; bi=-1
        px = Vector(view2d.view_to_region(uv.x, uv.y, clip=False))
        for ci, c in enumerate(self.curves):
            for i, v in enumerate(c.ctrl):
                cp = Vector(view2d.view_to_region(v.x, v.y, clip=False))
                d2 = (px - cp).length_squared
                if d2 < best:
                    best = d2; bc=ci; bi=i
        return bc, bi

class UV_OT_spline_adjust_modal(bpy.types.Operator):
    bl_idname = "uv.spline_adjust_modal"
    bl_label = 'UV：スプライン調整（モーダル）'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    auto_ctrl_count = bpy.props.IntProperty(default=4, min=2, max=30)

    weld_tolerance = bpy.props.FloatProperty(
        name="同一点判定の丸め",
        description="この精度でUV座標を丸めて同一点として扱います",
        min=1e-8, max=1e-2, default=1e-6, options={'HIDDEN'}
    )

    _handle = None
    _timer = None

    _curve_type_fixed = 'BEZIER'
    _resolution_fixed = 128

    def _region_to_uv(self, x, y):
        mu, mv = self.v2d.region_to_view(x, y)
        return Vector((mu, mv))

    def _snapshot_ctrl(self):
        self._ctrl_backup = [[v.copy() for v in c.ctrl] for c in self.ms.curves]

    def _restore_ctrl(self, context):
        if hasattr(self, '_ctrl_backup') and self._ctrl_backup is not None:
            for c, back in zip(self.ms.curves, self._ctrl_backup):
                c.ctrl[:] = [v.copy() for v in back]
            self._apply_preview_all(context)

    def _clamp_global(self, n):
        return max(self.ms.all_closed_min(), min(30, int(n)))

    def _resample_all_from_original(self, count):
        for c in self.ms.curves:
            c.ctrl[:] = utils.resample_by_length(c.orig_path, count, closed=c.closed_locked)
            c.sel = {i for i in c.sel if i < count}
        self.ms.global_points = count

    def _resample_all_from_current(self, count):
        for c in self.ms.curves:
            samples, _ = utils.sample_polyline(c.ctrl, resolution=self._resolution_fixed, curve_type=self._curve_type_fixed, closed=c.closed_locked)
            if len(samples) >= 2:
                c.ctrl[:] = utils.resample_by_length(samples, count, closed=c.closed_locked)
                c.sel = {i for i in c.sel if i < count}
        self.ms.global_points = count

    def _apply_preview_all(self, context):
        bm_cache = {}
        for c in self.ms.curves:
            obj = getattr(c, 'obj', context.object)
            if obj not in bm_cache:
                try:
                    bm = bmesh.from_edit_mesh(obj.data)
                    uv_layer = bm.loops.layers.uv.verify()
                    bm_cache[obj] = (bm, uv_layer)
                except Exception:
                    bm_cache[obj] = (None, None)
            bm, uv_layer = bm_cache[obj]
            if bm is None or uv_layer is None:
                continue
            if len(c.ctrl) < 2:
                for (o, fidx, lidx), uv0 in zip(c.loops, c.orig_uvs):
                    try:
                        loop = bm.faces[fidx].loops[lidx]
                        loop[uv_layer].uv = uv0
                    except Exception:
                        pass
                continue
            samples, _ = utils.sample_polyline(c.ctrl, resolution=self._resolution_fixed, curve_type=self._curve_type_fixed, closed=c.closed_locked)
            if len(samples) < 2:
                for (o, fidx, lidx), uv0 in zip(c.loops, c.orig_uvs):
                    try:
                        loop = bm.faces[fidx].loops[lidx]
                        loop[uv_layer].uv = uv0
                    except Exception:
                        pass
                continue
            seg_pairs = []; seg_lens = []
            n = len(samples)
            for i in range(n - 1):
                seg_pairs.append((i, i+1))
                seg_lens.append((samples[i+1] - samples[i]).length)
            if c.closed_locked:
                seg_pairs.append((n-1, 0))
                seg_lens.append((samples[0] - samples[-1]).length)
            cum=[0.0]
            for L in seg_lens:
                cum.append(cum[-1]+L)
            total = cum[-1] if cum[-1] > 0.0 else 1.0
            def point_at_fraction(frac: float):
                f = (frac % 1.0) if c.closed_locked else max(0.0, min(1.0, frac))
                target = f * total
                acc = 0.0
                for si, L in enumerate(seg_lens):
                    if acc + L >= target:
                        i0, i1 = seg_pairs[si]
                        t = 0.0 if L == 0.0 else (target - acc) / L
                        return samples[i0].lerp(samples[i1], t)
                    acc += L
                i0, i1 = seg_pairs[-1]
                return samples[i1]
            for (o, fidx, lidx), frac in zip(c.loops, c.orig_fractions):
                try:
                    loop = bm.faces[fidx].loops[lidx]
                    new_uv = point_at_fraction(frac)
                    key_func = lambda v: utils._uv_key(v, tol=self.weld_tolerance)
                    welded = utils.gather_welded_uv_loops(loop, uv_layer, key_func)
                    if not hasattr(self, '_welded_backup') or self._welded_backup is None:
                        self._welded_backup = {}
                    for l2 in welded:
                        k = (obj, l2.face.index, list(l2.face.loops).index(l2))
                        if k not in self._welded_backup:
                            try:
                                self._welded_backup[k] = l2[uv_layer].uv.copy()
                            except Exception:
                                pass
                        l2[uv_layer].uv = new_uv
                except Exception:
                    pass
        for obj, (bm, uv_layer) in bm_cache.items():
            if bm is None: continue
            try:
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            except Exception:
                pass

    @staticmethod
    def _get_prefs():
        try:
            addons = bpy.context.preferences.addons
        except Exception:
            return None

        pkg = __package__ or ""
        if pkg:
            # direct package match
            if pkg in addons:
                addon = addons.get(pkg)
                return addon.preferences if addon else None
            # try top-level package
            root = pkg.split('.', 1)[0]
            if root in addons:
                addon = addons.get(root)
                return addon.preferences if addon else None

        # fallback: find any addon key that contains 'uv_loop_tools'
        for key in addons.keys():
            if 'uv_loop_tools' in key:
                addon = addons.get(key)
                return addon.preferences if addon else None

        return None

    def _backend_is_opengl(self):
        be = bpy.context.preferences.system.gpu_backend
        return (be is None) or (str(be).upper() == "OPENGL")

    def _draw_segment_quad(self, x1, y1, x2, y2, thickness, color, shader):
        dx = x2 - x1; dy = y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return
        nx = -dy / length * (thickness * 0.5)
        ny = dx / length * (thickness * 0.5)
        verts = [(x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x2 - nx, y2 - ny), (x2 + nx, y2 + ny)]
        batch = batch_for_shader(shader, 'TRI_FAN', {"pos": verts})
        try:
            shader.bind(); shader.uniform_float("color", color); batch.draw(shader)
        except Exception:
            # drawing may not be available in some contexts; ignore
            pass

    def _draw_disc(self, cx, cy, radius_px, color, shader, segments=16):
        verts = [(cx, cy)]
        for i in range(segments + 1):
            a = (i / segments) * (math.pi * 2.0)
            verts.append((cx + math.cos(a) * radius_px, cy + math.sin(a) * radius_px))
        batch = batch_for_shader(shader, 'TRI_FAN', {"pos": verts})
        try:
            shader.bind(); shader.uniform_float("color", color); batch.draw(shader)
        except Exception:
            pass

    def draw_callback(self, context):
        if not hasattr(self, 'ms') or not self.ms.curves:
            return
        prefs = self._get_prefs()
        backend_is_gl = self._backend_is_opengl()

        v2d = self.v2d
        def uv_to_px(uv):
            return Vector(v2d.view_to_region(uv.x, uv.y, clip=False))

        # shader creation may also fail in headless/test envs - guard it
        try:
            shader2d = gpu.shader.from_builtin('UNIFORM_COLOR')
        except Exception:
            shader2d = None

        curve_color = prefs.curve_color if prefs else (0.15, 0.7, 1.0, 1.0)
        curve_thickness = prefs.curve_thickness if prefs else 2.0
        point_size = prefs.point_size if prefs else 8.0
        color_normal = prefs.point_color_normal if prefs else (0.8,0.8,0.8,1.0)
        color_sel = prefs.point_color_selected if prefs else (1.0,0.3,0.3,1.0)
        color_act = prefs.point_color_active if prefs else (1.0,1.0,0.0,1.0)

        if getattr(self, '_display_spline', True):
            if backend_is_gl:
                try:
                    gpu.state.line_width_set(max(1.0, curve_thickness))
                except Exception:
                    pass
            for c in self.ms.curves:
                if len(c.ctrl) < 2: continue
                samples, _ = utils.sample_polyline(c.ctrl, resolution=self._resolution_fixed, curve_type=self._curve_type_fixed, closed=c.closed_locked)
                if len(samples) < 2: continue
                pts_px = [uv_to_px(p) for p in samples]
                coords = [(p.x, p.y) for p in pts_px]
                if backend_is_gl and shader2d is not None:
                    try:
                        gpu.state.line_width_set(max(1.0, curve_thickness))
                    except Exception:
                        pass
                    try:
                        batch = batch_for_shader(shader2d, 'LINE_STRIP', {"pos": coords})
                        shader2d.bind(); shader2d.uniform_float("color", curve_color)
                        batch.draw(shader2d)
                    except Exception:
                        # drawing might fail (headless), ignore
                        pass
                else:
                    for i in range(len(coords)-1):
                        x1,y1 = coords[i]; x2,y2 = coords[i+1]
                        self._draw_segment_quad(x1,y1,x2,y2, curve_thickness, curve_color, shader2d)
                    if c.closed_locked:
                        x1,y1 = coords[-1]; x2,y2 = coords[0]
                        self._draw_segment_quad(x1,y1,x2,y2, curve_thickness, curve_color, shader2d)

        if getattr(self, '_box_selecting', False):
            x0, y0 = self._box_start
            x1, y1 = self._box_end
            rect = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            try:
                gpu.state.line_width_set(1.0)
            except Exception:
                pass
            try:
                gpu.state.blend_set('ALPHA')
                gpu.state.depth_test_set('NONE')
            except Exception:
                pass
            try:
                batch = batch_for_shader(shader2d, 'LINE_STRIP', {"pos": rect})
                shader2d.bind()
                shader2d.uniform_float("color", (1.0, 1.0, 1.0, 0.8))
                batch.draw(shader2d)
            except Exception:
                pass

        if getattr(self, '_display_points', True):
            for c in self.ms.curves:
                if not c.ctrl: continue
                ctrl_px = [uv_to_px(p) for p in c.ctrl]
                aidx = c.active_idx
                coords_inactive = [(p.x, p.y) for i,p in enumerate(ctrl_px) if i not in c.sel and i != aidx]
                if coords_inactive:
                    if backend_is_gl and shader2d is not None:
                        try:
                            gpu.state.point_size_set(max(1.0, point_size))
                        except Exception:
                            pass
                        try:
                            batch = batch_for_shader(shader2d, 'POINTS', {"pos": coords_inactive})
                            shader2d.bind(); shader2d.uniform_float("color", color_normal)
                            batch.draw(shader2d)
                        except Exception:
                            pass
                    else:
                        for x,y in coords_inactive:
                            self._draw_disc(x, y, point_size*0.5, color_normal, shader2d, segments=18)
                coords_sel = [(p.x, p.y) for i,p in enumerate(ctrl_px) if i in c.sel and i != aidx]
                if coords_sel:
                    if backend_is_gl and shader2d is not None:
                        try:
                            gpu.state.point_size_set(max(1.0, point_size*1.4))
                        except Exception:
                            pass
                        try:
                            batch = batch_for_shader(shader2d, 'POINTS', {"pos": coords_sel})
                            shader2d.bind(); shader2d.uniform_float("color", color_sel)
                            batch.draw(shader2d)
                        except Exception:
                            pass
                    else:
                        for x,y in coords_sel:
                            self._draw_disc(x, y, point_size*0.7, color_sel, shader2d, segments=18)
                if 0 <= aidx < len(ctrl_px):
                    px = ctrl_px[aidx]
                    if backend_is_gl and shader2d is not None:
                        try:
                            gpu.state.point_size_set(max(1.0, point_size*1.8))
                        except Exception:
                            pass
                        try:
                            batch = batch_for_shader(shader2d, 'POINTS', {"pos": [(px.x, px.y)]})
                            shader2d.bind(); shader2d.uniform_float("color", color_act)
                            batch.draw(shader2d)
                        except Exception:
                            pass
                    else:
                        self._draw_disc(px.x, px.y, point_size*0.9, color_act, shader2d, segments=20)

        try:
            blf.size(0, 12)
            hud = (f"[UVスプライン] カーブ: {len(self.ms.curves)} 制御点(各): {self.ms.global_points} "
                   "(H: 表示切替, Ctrl+ホイール: 現在形状±, Shift+ホイール: 原形状±)")
            blf.position(0, 14, 10, 0)
            blf.draw(0, hud)
        except Exception:
            pass

    def invoke(self, context, event):
        if getattr(context.scene.tool_settings, "use_uv_select_sync", False):
            self.report({'WARNING'}, "UV選択同期がONのため実行できません。UVエディタのヘッダーで同期をOFFにしてください。")
            return {'CANCELLED'}
        if context.area is None or context.area.type != 'IMAGE_EDITOR':
            self.report({'WARNING'}, "メッシュを編集モードにした状態でUVエディタから実行してください。")
            return {'CANCELLED'}
        if not context.object or context.object.type != 'MESH' or context.object.mode != 'EDIT':
            self.report({'WARNING'}, "アクティブオブジェクトは編集モード中のメッシュである必要があります。")
            return {'CANCELLED'}

        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == 'WINDOW'), None)
        if not self.region:
            self.report({'ERROR'}, "Image Editor に WINDOW リージョンが見つかりません。")
            return {'CANCELLED'}
        self.v2d = self.region.view2d

        objs = [o for o in context.selected_editable_objects if o.type == 'MESH' and o.mode == 'EDIT']
        if not objs:
            objs = [context.object]

        self.ms = MultiSplineState()
        temp_curves = []
        any_closed = False
        per_obj_loops = {}
        for obj in objs:
            me = obj.data
            bm = bmesh.from_edit_mesh(me)
            uv_layer = bm.loops.layers.uv.verify()
            loops = []
            orig_uvs = []
            seen = set()
            found_edge = False
            for f in bm.faces:
                if getattr(f, 'hide', False):
                    continue
                for l in f.loops:
                    luv = l[uv_layer]
                    if hasattr(luv, 'select_edge') and luv.select_edge:
                        ln = l.link_loop_next
                        luvn = ln[uv_layer]
                        li = (l.face.index, list(l.face.loops).index(l))
                        if li not in seen:
                            loops.append(l); orig_uvs.append(luv.uv.copy()); seen.add(li)
                        lni = (ln.face.index, list(ln.face.loops).index(ln))
                        if lni not in seen:
                            loops.append(ln); orig_uvs.append(luvn.uv.copy()); seen.add(lni)
                        found_edge = True
            if not found_edge:
                continue
            if len(loops) <= 2:
                continue
            paths = utils.build_all_selected_uv_paths(bm, uv_layer)
            def _uv_key_graph(v, tol=5e-7):
                s = int(round(1.0 / max(tol, 1e-12)))
                return (int(round(v.x * s)), int(round(v.y * s)))
            valid_keys = set()
            for _pts, _closed in paths:
                for _p in _pts:
                    valid_keys.add(_uv_key_graph(_p))
            if valid_keys:
                _loops_f = []
                _uvs_f = []
                for _l, _uv0 in zip(loops, orig_uvs):
                    if _uv_key_graph(_uv0) in valid_keys:
                        _loops_f.append(_l); _uvs_f.append(_uv0)
                loops, orig_uvs = _loops_f, _uvs_f
            per_obj_loops[obj] = (loops, orig_uvs, bm, uv_layer)

            for pts, closed in paths:
                if len(pts) <= 2:
                    continue
                cd = CurveData(pts, closed)
                cd.obj = obj; cd.uv_layer = uv_layer
                temp_curves.append(cd)
                if closed: any_closed = True
                
        if temp_curves:
            any_large = any(len(cd.orig_path) >= 3 for cd in temp_curves)
            if any_large:
                temp_curves = [cd for cd in temp_curves if len(cd.orig_path) >= 3]

        if not temp_curves:
            self.report({'WARNING'}, "No valid UV loops/paths found (possibly filtered out by <=2 rule).")
            return {'CANCELLED'}

        wm = bpy.context.window_manager
        init_pts = int(getattr(wm, 'uv_spline_auto_ctrl_count', self.auto_ctrl_count))
        global_min = 3 if any_closed else 2
        self.ms.global_points = max(global_min, init_pts)

        for c in temp_curves:
            c.ctrl = utils.resample_by_length(c.orig_path, self.ms.global_points, closed=c.closed_locked)

        for obj, (loops, orig_uvs, bm, uv_layer) in per_obj_loops.items():
            obj_curve_indices = [i for i, cd in enumerate(temp_curves) if getattr(cd, 'obj', None) == obj]
            path_samples = []
            for ci in obj_curve_indices:
                cd = temp_curves[ci]
                samples = cd.orig_path[:]
                seg_lens = []
                n = len(samples)
                if n >= 2:
                    for i in range(n - 1):
                        seg_lens.append((samples[i+1] - samples[i]).length)
                    if cd.closed_locked:
                        seg_lens.append((samples[0] - samples[-1]).length)
                cum = [0.0]
                for L in seg_lens:
                    cum.append(cum[-1] + L)
                total = cum[-1] if cum else 1.0
                path_samples.append((ci, samples, seg_lens, cum, total))

            for l, uv0 in zip(loops, orig_uvs):
                p = Vector((uv0.x, uv0.y))
                best_ci = None; best_d2 = 1e20; best_frac = 0.0
                for (ci, samples, seg_lens, cum, total) in path_samples:
                    if len(samples) < 2:
                        d2 = (p - samples[0]).length_squared if samples else 1e20
                        q = samples[0] if samples else p
                        frac = 0.0
                    else:
                        idx, q, tloc = utils.closest_point_on_polyline(samples, p, closed=temp_curves[ci].closed_locked)
                        if seg_lens:
                            seg_len = seg_lens[idx] if idx < len(seg_lens) else 0.0
                            dist = cum[idx] + (tloc * seg_len if seg_len > 0.0 else 0.0)
                            frac = (dist / total) if total > 0.0 else 0.0
                            if temp_curves[ci].closed_locked:
                                frac = frac % 1.0
                            else:
                                frac = max(0.0, min(1.0, frac))
                        else:
                            frac = 0.0
                        d2 = (p - q).length_squared
                    if d2 < best_d2:
                        best_d2 = d2; best_ci = ci; best_frac = frac
                if best_ci is not None:
                    cd = temp_curves[best_ci]
                    face_idx = l.face.index
                    loop_idx = list(l.face.loops).index(l)
                    cd.loops.append((obj, face_idx, loop_idx))
                    cd.orig_uvs.append(uv0.copy())
                    cd.orig_fractions.append(best_frac)

        self.ms.curves = [cd for cd in temp_curves if cd.loops]
        if not self.ms.curves:
            self.report({'WARNING'}, "No loops assigned to any path after assignment.")
            return {'CANCELLED'}

        self.ms.global_points = max(self.ms.all_closed_min(), self.ms.global_points)
        self._resample_all_from_original(self.ms.global_points)

        self._is_drag_mode = False
        self._drag_data = None
        self._display_spline = True
        self._display_points = True
        self._rmb_pressed = False
        self._rmb_was_for_cancel = False
        self._box_selecting = False
        self._box_start = (0,0); self._box_end = (0,0); self._box_add = False
        self._maybe_box_start = None; self._maybe_box_threshold_sq = 9

        sizes = [len(c.loops) for c in self.ms.curves]
        self.ms.active_curve = sizes.index(max(sizes)) if sizes else 0

        self._apply_preview_all(context)

        self._shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self._point_shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
        self._handle = bpy.types.SpaceImageEditor.draw_handler_add(self.draw_callback, (context,), 'WINDOW', 'POST_PIXEL')
        self._timer = context.window_manager.event_timer_add(0.03, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context, cancel=False):
        if cancel:
            wb = getattr(self, '_welded_backup', None)
            if wb:
                obj_cache = {}
                for (obj, fidx, lidx), uv in wb.items():
                    try:
                        if obj not in obj_cache:
                            bm = bmesh.from_edit_mesh(obj.data)
                            uv_layer = bm.loops.layers.uv.verify()
                            obj_cache[obj] = (bm, uv_layer)
                        bm, uv_layer = obj_cache[obj]
                        loop = bm.faces[fidx].loops[lidx]
                        loop[uv_layer].uv = uv
                    except Exception:
                        pass
                for obj, (bm, _) in obj_cache.items():
                    try:
                        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                    except Exception:
                        pass
                self._welded_backup = {}
            bm_cache = {}
            for c in self.ms.curves:
                obj = getattr(c, 'obj', context.object)
                if obj not in bm_cache:
                    try:
                        bm = bmesh.from_edit_mesh(obj.data)
                        uv_layer = bm.loops.layers.uv.verify()
                        bm_cache[obj] = (bm, uv_layer)
                    except Exception:
                        bm_cache[obj] = (None, None)
                bm, uv_layer = bm_cache[obj]
                if bm is None or uv_layer is None:
                    continue
                for (o, fidx, lidx), uv0 in zip(c.loops, c.orig_uvs):
                    try:
                        loop = bm.faces[fidx].loops[lidx]
                        loop[uv_layer].uv = uv0
                    except Exception:
                        pass

        if not cancel:
            counts = [len(c.ctrl) for c in self.ms.curves]
            if counts:
                if all(x == counts[0] for x in counts):
                    save = counts[0]
                else:
                    ac = getattr(self.ms, 'active_curve', -1)
                    if 0 <= ac < len(self.ms.curves):
                        save = len(self.ms.curves[ac].ctrl)
                    else:
                        save = counts[0]
                try:
                    bpy.context.window_manager.uv_spline_auto_ctrl_count = save
                except Exception:
                    pass

        if self._handle:
            bpy.types.SpaceImageEditor.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        objs = {getattr(c, 'obj', context.object) for c in self.ms.curves}
        if not objs:
            objs = {context.object}
        for obj in objs:
            try:
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            except Exception:
                pass
        try:
            if self.area: self.area.tag_redraw()
            if self.region: self.region.tag_redraw()
        except Exception:
            pass

    def _clear_selection(self):
        for c in self.ms.curves:
            c.sel.clear(); c.active_idx = -1

    def _set_active_single(self, cidx, pidx):
        for i, c in enumerate(self.ms.curves):
            if i == cidx:
                c.sel = {pidx}; c.active_idx = pidx
            else:
                c.sel.clear(); c.active_idx = -1
        self.ms.active_curve = cidx

    def _toggle_select(self, cidx, pidx):
        c = self.ms.curves[cidx]
        if pidx in c.sel:
            c.sel.remove(pidx)
            if c.active_idx == pidx:
                c.active_idx = next(iter(c.sel), -1)
        else:
            c.sel.add(pidx)
            c.active_idx = pidx
        self.ms.active_curve = cidx

    def _selected_points_snapshot(self):
        snap = []
        for ci, c in enumerate(self.ms.curves):
            for i in sorted(c.sel):
                if 0 <= i < len(c.ctrl):
                    snap.append((ci, i, c.ctrl[i].copy()))
        return snap

    def _start_drag_from_selection(self, event):
        self._snapshot_ctrl()
        if hasattr(self, 'mouse_uv') and self.mouse_uv is not None:
            self._drag_start_uv = self.mouse_uv.copy()
        else:
            try:
                self._drag_start_uv = self._region_to_uv(event.mouse_region_x, event.mouse_region_y)
            except Exception:
                self._drag_start_uv = Vector((0.0,0.0))
        self._drag_data = self._selected_points_snapshot()
        if not self._drag_data:
            cidx, pidx = self.ms.find_global_nearest_control(self._drag_start_uv, self.v2d, self.region)
            if cidx >= 0 and pidx >= 0:
                self._set_active_single(cidx, pidx)
                self._drag_data = self._selected_points_snapshot()
        if not self._drag_data:
            self._drag_start_uv = None
            return False
        self._is_drag_mode = True
        return True

    def _apply_drag(self, event):
        cur_uv = self._region_to_uv(event.mouse_region_x, event.mouse_region_y)
        delta = cur_uv - self._drag_start_uv
        if self._drag_data:
            for ci, i, base in self._drag_data:
                c = self.ms.curves[ci]
                if 0 <= i < len(c.ctrl):
                    c.ctrl[i] = base + delta
            self._apply_preview_all(self._context_for_restore)

    # modal loop
    def modal(self, context, event):
        if not hasattr(self, '_context_for_restore'):
            self._context_for_restore = context
        if context.area != self.area:
            self.finish(context, cancel=True)
            return {'CANCELLED'}
        if (event.alt and event.type in {"LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE"}) \
           or event.type in {"MIDDLEMOUSE", "EVT_TWEAK_M", "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "NDOF_MOTION"}:
            return {'PASS_THROUGH'}
        if event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE"} and not (event.ctrl or event.shift):
            return {'PASS_THROUGH'}

        if event.type in {'MOUSEMOVE','LEFTMOUSE','RIGHTMOUSE','EVT_TWEAK_L','EVT_TWEAK_R','G','H','B'}:
            mx = event.mouse_region_x; my = event.mouse_region_y
            mu, mv = self.v2d.region_to_view(mx, my)
            self.mouse_uv = Vector((mu, mv))

        if event.type == 'ESC':
            if self._box_selecting:
                self._box_selecting = False
                if self.area: self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self.finish(context, cancel=True)
            return {'CANCELLED'}

        if event.type in {'RET','NUMPAD_ENTER'} and event.value == 'PRESS':
            if self._is_drag_mode or getattr(self,'_drag_data',None):
                try:
                    self._apply_preview_all(context)
                except Exception:
                    self._restore_ctrl(context)
                self._is_drag_mode = False; self._drag_data = None; self._drag_start_uv = None
                if hasattr(self,'_ctrl_backup'): self._ctrl_backup = None
                if self.area: self.area.tag_redraw()
                if self.region: self.region.tag_redraw()
                return {'RUNNING_MODAL'}
            else:
                self.finish(context, cancel=False)
                return {'FINISHED'}

        if event.type == 'TAB' and event.value == 'PRESS':
            self.finish(context, cancel=False)
            return {'FINISHED'}

        if event.type == 'H' and event.value == 'PRESS':
            self._display_spline = not getattr(self, '_display_spline', True)
            self._display_points = not getattr(self, '_display_points', True)
            if self.area: self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'RIGHTMOUSE':
            if event.value == 'PRESS':
                self._rmb_pressed = True
                if self._is_drag_mode:
                    self._restore_ctrl(context)
                    self._is_drag_mode = False
                    self._rmb_was_for_cancel = True
                    if self.area: self.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE':
                self._rmb_pressed = False
                if self._rmb_was_for_cancel:
                    self._rmb_was_for_cancel = False
                    return {'RUNNING_MODAL'}
                if self._is_drag_mode:
                    self._restore_ctrl(context)
                    self._is_drag_mode = False
                    if self.area: self.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                else:
                    self.finish(context, cancel=False)
                    return {'FINISHED'}

        if event.type == 'EVT_TWEAK_R':
            if self._is_drag_mode:
                self._restore_ctrl(context); self._is_drag_mode = False
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}

        if event.type == 'B' and event.value == 'PRESS' and not self._is_drag_mode:
            self._box_selecting = True
            self._box_start = (event.mouse_region_x, event.mouse_region_y)
            self._box_end = self._box_start
            self._box_add = event.shift
            return {'RUNNING_MODAL'}
        if self._box_selecting:
            if event.type == 'MOUSEMOVE':
                self._box_end = (event.mouse_region_x, event.mouse_region_y)
                if self.area: self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                x0,y0 = self._box_start; x1,y1 = self._box_end
                xmin,xmax = min(x0,x1), max(x0,x1); ymin,ymax = min(y0,y1), max(y0,y1)
                if not self._box_add:
                    self._clear_selection()
                for ci, c in enumerate(self.ms.curves):
                    for i, v in enumerate(c.ctrl):
                        px = Vector(self.v2d.view_to_region(v.x, v.y, clip=False))
                        if xmin <= px.x <= xmax and ymin <= px.y <= ymax:
                            c.sel.add(i); c.active_idx = i; self.ms.active_curve = ci
                self._box_selecting = False
                if self.area: self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if getattr(self, '_is_drag_mode', False):
                try:
                    self._apply_preview_all(context)
                except Exception:
                    self._restore_ctrl(context)
                self._is_drag_mode = False; self._drag_data = None; self._drag_start_uv = None
                if self.area: self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            self._maybe_box_start = None
            if event.ctrl:
                cidx, pidx = self.ms.find_nearest_control(self.mouse_uv, int(getattr(self._get_prefs(), 'point_pick_threshold_px', 16)), self.v2d, self.region)
                if cidx >= 0 and pidx >= 0:
                    # delete only from that curve (do NOT resample all)
                    try:
                        self.ms.curves[cidx].ctrl.pop(pidx)
                    except Exception:
                        pass
                    c = self.ms.curves[cidx]
                    c.sel = {i if i < pidx else i-1 for i in c.sel if i != pidx and (i-1) >= 0}
                    # --- Active index maintenance after DELETE (Ctrl+LMB) ---
                    if c.active_idx == pidx:
                        c.active_idx = next(iter(sorted(c.sel)) , -1)
                    elif c.active_idx > pidx:
                        c.active_idx -= 1
                    self.ms.active_curve = cidx
                    # preview changed for that curve only
                    self._apply_preview_all(context)
                else:
                    # INSERT (strict, curve-based): pick nearest curve by polyline distance within threshold
                    _prefs = self._get_prefs()
                    _th_px = int(getattr(_prefs, 'insert_pick_threshold_px', 6))
                    _mouse_px = Vector(self.v2d.view_to_region(self.mouse_uv.x, self.mouse_uv.y, clip=False))
                    best_c = -1
                    best_d2 = 1e20
                    for ci, c in enumerate(self.ms.curves):
                        if len(c.ctrl) < 2:
                            continue
                        samples, _ = utils.sample_polyline(c.ctrl, resolution=self._resolution_fixed, curve_type=self._curve_type_fixed, closed=c.closed_locked)
                        if len(samples) < 2:
                            continue
                        seg_count = (len(samples) - 1) + (1 if c.closed_locked else 0)
                        for s in range(seg_count):
                            i0 = s
                            i1 = (s + 1) % len(samples) if c.closed_locked else (s + 1)
                            if i1 >= len(samples) and not c.closed_locked:
                                continue
                            a = Vector(self.v2d.view_to_region(samples[i0].x, samples[i0].y, clip=False))
                            b = Vector(self.v2d.view_to_region(samples[i1].x, samples[i1].y, clip=False))
                            ab = b - a
                            ab2 = ab.length_squared
                            if ab2 == 0.0:
                                d2 = (_mouse_px - a).length_squared
                            else:
                                t = max(0.0, min(1.0, (_mouse_px - a).dot(ab) / ab2))
                                q = a + t * ab
                                d2 = (_mouse_px - q).length_squared
                            if d2 < best_d2:
                                best_d2 = d2
                                best_c = ci
                    if best_c < 0 or best_d2 > float(_th_px * _th_px):
                        try:
                            self.report({'INFO'}, f"近傍にカーブがありません（{_th_px}px 以内）")
                        except Exception:
                            pass
                        return {'RUNNING_MODAL'}
                    ac = best_c
                    ac = max(0, min(ac, len(self.ms.curves)-1))
                    c = self.ms.curves[ac]
                    n = len(c.ctrl)
                    if n < 2:
                        c.ctrl.append(self.mouse_uv)
                    else:
                        best_i, best_d = 0, 1e20
                        seg_count = (n - 1) + (1 if c.closed_locked else 0)
                        for s in range(seg_count):
                            i0 = s
                            i1 = (s + 1) % n if c.closed_locked else (s + 1)
                            if i1 >= n and not c.closed_locked: continue
                            a = c.ctrl[i0]; b = c.ctrl[i1]
                            ab = b - a; ab2 = ab.length_squared
                            if ab2 == 0.0:
                                d2 = (self.mouse_uv - a).length_squared
                            else:
                                t = max(0.0, min(1.0, (self.mouse_uv - a).dot(ab) / ab2))
                                q = a + t * ab
                                d2 = (self.mouse_uv - q).length_squared
                            if d2 < best_d:
                                best_d = d2; best_i = i0
                        c.ctrl.insert(best_i+1, self.mouse_uv.copy())
                        c.sel = {i if i <= best_i else i+1 for i in c.sel}
                    # --- Selection/Active after INSERT (spec change): single-select new point and clear others ---
                    if n < 2:
                        new_idx = len(c.ctrl) - 1
                    else:
                        new_idx = best_i + 1
                    c.sel = {new_idx}
                    c.active_idx = new_idx
                    self.ms.active_curve = ac
                    for ci2, c2 in enumerate(self.ms.curves):
                        if ci2 != ac:
                            c2.active_idx = -1
                            c2.sel.clear()
                    self._apply_preview_all(context)
                    return {'RUNNING_MODAL'}

            else:
                if event.shift:
                    cidx, pidx = self.ms.find_nearest_control(self.mouse_uv, int(getattr(self._get_prefs(), 'point_pick_threshold_px', 12)), self.v2d, self.region)
                    if cidx >= 0 and pidx >= 0:
                        self._toggle_select(cidx, pidx)
                        if self.area: self.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                cidx, pidx = self.ms.find_nearest_control(self.mouse_uv, int(getattr(self._get_prefs(), 'point_pick_threshold_px', 12)), self.v2d, self.region)
                if cidx >= 0 and pidx >= 0:
                    # If clicked control is already in the current selection, keep the selection
                    # (so dragging moves all selected points). Otherwise select single.
                    c = self.ms.curves[cidx]
                    if pidx in c.sel:
                        # keep selection but set active index to clicked one
                        c.active_idx = pidx
                        self.ms.active_curve = cidx
                    else:
                        # click on an unselected control -> select single (old behavior)
                        self._set_active_single(cidx, pidx)
                    self._maybe_box_start = None
                    self._start_drag_from_selection(event)
                else:
                    self._clear_selection()
                    self._maybe_box_start = (event.mouse_region_x, event.mouse_region_y)
                return {'RUNNING_MODAL'}

        elif event.type == 'MOUSEMOVE':
            if self._maybe_box_start and not self._is_drag_mode and not self._box_selecting:
                sx,sy = self._maybe_box_start; dx = event.mouse_region_x - sx; dy = event.mouse_region_y - sy
                if dx*dx + dy*dy >= self._maybe_box_threshold_sq:
                    self._box_selecting = True
                    self._box_start = (sx, sy)
                    self._box_end = (event.mouse_region_x, event.mouse_region_y)
                    self._box_add = event.shift
                    self._maybe_box_start = None
                    if self.area: self.area.tag_redraw()
                    return {'RUNNING_MODAL'}
            if self._is_drag_mode:
                self._apply_drag(event)
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self._maybe_box_start:
                self._maybe_box_start = None
                return {'RUNNING_MODAL'}
            if self._is_drag_mode:
                self._is_drag_mode = False; self._drag_data = None
                try:
                    self._apply_preview_all(context)
                except Exception:
                    self._restore_ctrl(context)
                if self.area: self.area.tag_redraw()
                return {'RUNNING_MODAL'}

        elif event.type == 'G' and event.value == 'PRESS':
            any_sel = any(bool(c.sel) for c in self.ms.curves)
            if not any_sel:
                cidx,pidx = self.ms.find_nearest_control(self.mouse_uv, int(getattr(self._get_prefs(), 'point_pick_threshold_px', 24)), self.v2d, self.region)
                if cidx >= 0 and pidx >= 0:
                    self._set_active_single(cidx, pidx)
            if any(bool(c.sel) for c in self.ms.curves):
                started = self._start_drag_from_selection(event)
                if started and self.area: self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        elif event.type in {"WHEELUPMOUSE","WHEELDOWNMOUSE"} and (event.ctrl or event.shift):
            cur = int(self.ms.global_points); step = 1 if event.type=="WHEELUPMOUSE" else -1
            if event.ctrl:
                # Sync all curves to the new number (user explicitly requested sync with Ctrl+Wheel)
                new_num = self._clamp_global(cur + step)
                if new_num != cur:
                    self._resample_all_from_current(new_num)
                    try:
                        bpy.context.window_manager.uv_spline_auto_ctrl_count = new_num
                    except Exception:
                        pass
                    self._apply_preview_all(context)
            else:
                new_num = self._clamp_global(cur + step)
                if new_num != cur:
                    if event.shift:
                        self._resample_all_from_original(new_num)
                    else:
                        self._resample_all_from_current(new_num)
                    self._apply_preview_all(context)
            return {'RUNNING_MODAL'}

        elif event.type == 'R' and event.value == 'PRESS':
            bm_cache = {}
            for c in self.ms.curves:
                obj = getattr(c, 'obj', context.object)
                if obj not in bm_cache:
                    try:
                        bm = bmesh.from_edit_mesh(obj.data)
                        uv_layer = bm.loops.layers.uv.verify()
                        bm_cache[obj] = (bm, uv_layer)
                    except Exception:
                        bm_cache[obj] = (None, None)
                bm, uv_layer = bm_cache[obj]
                if bm is None or uv_layer is None:
                    continue
                for (o, fidx, lidx), uv in zip(c.loops, c.orig_uvs):
                    try:
                        loop = bm.faces[fidx].loops[lidx]
                        loop[uv_layer].uv = uv
                    except Exception:
                        pass
            for obj, (bm, uv_layer) in bm_cache.items():
                if bm is None: continue
                try:
                    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                except Exception:
                    pass
            self._resample_all_from_original(self.ms.global_points)
            self._apply_preview_all(context)
            return {'RUNNING_MODAL'}

        elif event.type == 'DEL' and event.value == 'PRESS':
            cidx,pidx = self.ms.find_nearest_control(self.mouse_uv, int(getattr(self._get_prefs(), 'point_pick_threshold_px', 16)), self.v2d, self.region)
            if cidx >= 0 and pidx >= 0:
                # delete only from that curve (do NOT resample all)
                try:
                    self.ms.curves[cidx].ctrl.pop(pidx)
                except Exception:
                    pass
                c = self.ms.curves[cidx]
                c.sel = {i if i < pidx else i-1 for i in c.sel if i != pidx and (i-1) >= 0}
                self._apply_preview_all(context)
            return {'RUNNING_MODAL'}

        if event.type in {'MOUSEMOVE','TIMER'}:
            if self.area: self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

# --- module registration helpers ---
classes = (
    UV_OT_spline_adjust_modal,
)

def register():
    import bpy
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    import bpy
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
