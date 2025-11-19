# utils.py
import bpy

from mathutils import Vector
import math

def uv_edge_selected(l, uv_layer):
    """Blender 4.5〜と5.0以降でUVエッジ選択判定を切り替える"""
    if hasattr(l, "uv_select_edge"):
        # Blender 5.x
        return l.uv_select_edge
    else:
        # Blender 4.5.x
        luv = l[uv_layer]
        return getattr(luv, "select_edge", False)

def connected_components_keys(graph):
    """
    uv_key で構築した無向グラフから、連結成分（セット）を列挙。
    graph: dict[key, set[key]]
    return: [set_of_keys, ...]
    """
    comps = []
    visited = set()
    nodes = set(graph.keys())
    for nbrs in graph.values():
        nodes.update(nbrs)
    for n in nodes:
        if n in visited:
            continue
        stack = [n]
        comp = set()
        visited.add(n)
        while stack:
            cur = stack.pop()
            comp.add(cur)
            for nei in graph.get(cur, ()):
                if nei not in visited:
                    visited.add(nei)
                    stack.append(nei)
        comps.append(comp)
    return comps

def extract_paths_from_component(subgraph):
    """
    分岐を含む無向グラフ subgraph:{key -> set(nei_keys)} から、
    (ordered_keys, is_closed) の“道（チェーン／サイクル）”に分解して返す。
    """
    paths = []
    visited_edges = set()

    def ekey(a, b):
        return (a, b) if a <= b else (b, a)

    def neighbors(k):
        return subgraph.get(k, set())

    def walk_forward(cur, prev):
        order = [cur]
        p = prev
        c = cur
        while True:
            nxts = [n for n in neighbors(c) if ekey(c, n) not in visited_edges and n != p]
            if not nxts:
                break
            n = nxts[0]
            visited_edges.add(ekey(c, n))
            order.append(n)
            p, c = c, n
        return order

    # 端点（次数1）から開パスを回収
    endpoints = [k for k, ns in subgraph.items() if len(ns) == 1]
    for s in endpoints:
        ns = list(neighbors(s))
        if not ns:
            continue
        n = ns[0]
        if ekey(s, n) in visited_edges:
            continue
        visited_edges.add(ekey(s, n))
        right = walk_forward(n, s)
        order = [s] + right
        paths.append((order, False))

    # 残りエッジからパス／サイクルを回収
    for a in list(subgraph.keys()):
        for b in neighbors(a):
            e = ekey(a, b)
            if e in visited_edges:
                continue
            visited_edges.add(e)
            right = walk_forward(b, a)
            left = walk_forward(a, b)
            order = list(reversed(left)) + [a, b] + right
            is_closed = (len(order) >= 3 and (order[0] in neighbors(order[-1])))
            paths.append((order, is_closed))

    return paths

def gather_welded_uv_loops(loop, uv_layer, key_func):
    """
    同じ BMVert で、key_func 丸め後のUV座標が同じ BMLoop 群を列挙。
    （＝UV上で“同一点に溶接”されているループへ座標を伝播）
    """
    target_key = key_func(loop[uv_layer].uv)
    v = loop.vert
    group = []
    for l2 in v.link_loops:
        luv2 = l2[uv_layer]
        if key_func(luv2.uv) == target_key:
            group.append(l2)
    return group

def unwrap_cycle01(points):
    """0/1境界を跨ぐ閉ループを一時的に連続空間へ展開"""
    if not points:
        return points[:]
    out = [points[0].copy()]
    acc_u = 0.0
    acc_v = 0.0
    for i in range(1, len(points)):
        du = points[i].x - points[i - 1].x
        dv = points[i].y - points[i - 1].y
        if du > 0.5:
            acc_u -= 1.0
        elif du < -0.5:
            acc_u += 1.0
        if dv > 0.5:
            acc_v -= 1.0
        elif dv < -0.5:
            acc_v += 1.0
        out.append(Vector((points[i].x + acc_u, points[i].y + acc_v)))
    return out

def wrap01(points):
    """unwrap_cycle01 した座標を 0..1 に戻す"""
    out = []
    for p in points:
        out.append(Vector((p.x - round(p.x), p.y - round(p.y))))
    return out

def dedup_with_map(points, closed=False, eps=1e-9):
    """
    points から隣接重複(距離<=eps)を間引きつつ、
    元の各点が「間引き後のどのインデックス」を参照するかの対応表 idx_map を返す。
    閉ループの場合、先頭と末尾が同一点なら末尾を落として idx_map を 0 に張り替える。
    return: (dedup_points, idx_map)
    """
    dedup = []
    idx_map = []
    for p in points:
        if not dedup or (p - dedup[-1]).length > eps:
            dedup.append(p)
        # 現在の“間引き後の最後の要素”のインデックスをマップ
        idx_map.append(len(dedup) - 1)

    # 閉ループで先頭=末尾なら末尾を落とす
    if closed and len(dedup) >= 2 and (dedup[0] - dedup[-1]).length <= eps:
        last_idx = len(dedup) - 1
        dedup.pop()
        # 旧・末尾を指しているものは先頭(0)に付け替え
        idx_map = [0 if j == last_idx else j for j in idx_map]

    return dedup, idx_map

def redistribute_evenly(points, preserve_ends=True, closed=False, eps=1e-9):
    """
    弧長均等化。ゼロ長耐性と重複除去付き。
    """
    n0 = len(points)
    if n0 < 2:
        return points[:]

    # 前処理: 隣接重複の除去
    pts = [points[0]]
    for p in points[1:]:
        if (p - pts[-1]).length > eps:
            pts.append(p)
    if closed and len(pts) >= 2 and (pts[0] - pts[-1]).length <= eps:
        pts.pop()

    n = len(pts)
    if (closed and n < 3) or (not closed and n < 2):
        return points[:]

    # 累積長
    seg = []
    total = 0.0
    if closed:
        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]
            d = (b - a).length
            seg.append(d)
            total += d
    else:
        for i in range(n - 1):
            d = (pts[i + 1] - pts[i]).length
            seg.append(d)
            total += d

    if total <= 1e-20:
        return points[:]

    def sample_at(t):
        if closed:
            tt = t % total
            acc = 0.0
            for i in range(n):
                L = seg[i]
                if acc + L >= tt - 1e-15:
                    local = 0.0 if L <= 1e-20 else (tt - acc) / L
                    return pts[i].lerp(pts[(i + 1) % n], local)
                acc += L
            return pts[-1]
        else:
            tt = min(t, total - 1e-12)  # 端点誤差対策
            acc = 0.0
            for i in range(n - 1):
                L = seg[i]
                if acc + L >= tt - 1e-15:
                    local = 0.0 if L <= 1e-20 else (tt - acc) / L
                    return pts[i].lerp(pts[i + 1], local)
                acc += L
            return pts[-1]

    new_pts = [None] * n
    if closed:
        step = total / n
        for i in range(n):
            new_pts[i] = sample_at(i * step)
    else:
        step = total / (n - 1)
        if preserve_ends:
            new_pts[0] = pts[0]
            new_pts[-1] = pts[-1]
            for i in range(1, n - 1):
                new_pts[i] = sample_at(i * step)
        else:
            for i in range(n):
                new_pts[i] = sample_at(i * step)

    return new_pts

def _segment_lengths(points, closed=False):
    """連続点列の各区間長を返す"""
    n = len(points)
    if closed:
        pairs = ((points[i], points[(i+1) % n]) for i in range(n))
    else:
        pairs = ((points[i], points[i+1]) for i in range(n-1))
    return [(b - a).length for a, b in pairs]

def _spacing_cv(points, closed=False):
    """セグメント長の変動係数（標準偏差/平均）"""
    lens = _segment_lengths(points, closed=closed)
    if not lens:
        return 0.0
    m = sum(lens) / len(lens)
    if m <= 1e-20:
        return 0.0
    var = sum((l - m)*(l - m) for l in lens) / len(lens)
    sd = math.sqrt(var)
    return sd / m

def _max_displacement(current_uvs, new_uvs, movable_mask):
    """移動対象頂点の最大移動量を返す（同次元のUV配列 & ブールマスク）"""
    dmax = 0.0
    for cu, nu, move in zip(current_uvs, new_uvs, movable_mask):
        if not move:
            continue
        d = (nu - cu).length
        if d > dmax:
            dmax = d
    return dmax

def bezier_cubic(b0, b1, b2, b3, t):
    it = 1.0 - t
    return (it**3) * b0 + 3 * (it**2) * t * b1 + 3 * it * (t**2) * b2 + (t**3) * b3

def _is_closed_points(points, abs_eps=5e-4, rel_eps=1e-2):
    if len(points) < 3:
        return False
    p0, pN = points[0], points[-1]
    d = (p0 - pN).length
    xs = [p.x for p in points]; ys = [p.y for p in points]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    th = max(abs_eps, rel_eps * diag)
    return d <= th

def _dedupe_closed(points):
    if points and _is_closed_points(points):
        if (points[0] - points[-1]).length <= 1e-7:
            return points[:-1]
    return points

def sample_polyline(points, resolution=128, curve_type='BEZIER', closed=None):
    if len(points) < 2:
        return points[:], [0.0] * max(1, len(points))
    if closed is None:
        closed = _is_closed_points(points)
    P = _dedupe_closed(points[:]) if closed else points[:]
    samples = []
    if curve_type in {'CATMULL_ROM', 'CATMULL_ROM_C'}:
        samples = P[:]
    else:
        A = P; n = len(A)
        seg_count = n if closed else (n - 1)
        for i in range(seg_count):
            i0 = i
            i1 = (i + 1) % n if closed else (i + 1)
            im1 = (i - 1) % n if closed else max(0, i - 1)
            i2 = (i + 2) % n if closed else min(n - 1, i + 2)
            p0, p1, p2, p3 = A[im1], A[i0], A[i1], A[i2]
            h1 = p1 + (p2 - p0) / 6.0
            h2 = p2 - (p3 - p1) / 6.0
            steps = max(2, resolution // max(1, seg_count))
            for s in range(steps):
                t = s / float(steps)
                samples.append(bezier_cubic(p1, h1, h2, p2, t))
        if not closed:
            samples.append(A[-1].copy())
    if not samples:
        samples = P[:]
    lengths = [0.0]
    total = 0.0
    for i in range(1, len(samples)):
        d = (samples[i] - samples[i - 1]).length
        total += d
        lengths.append(total)
    params = [0.0 if total == 0 else L / total for L in lengths]
    return samples, params

def resample_by_length(points, count, closed=None):
    if not points:
        return []
    if closed is None:
        closed = _is_closed_points(points)
    P = _dedupe_closed(points[:]) if closed else points[:]
    pts = P + ([P[0]] if closed else [])
    cum = [0.0]
    total = 0.0
    for i in range(1, len(pts)):
        d = (pts[i] - pts[i - 1]).length
        total += d
        cum.append(total)
    if total == 0.0:
        return [P[0].copy() for _ in range(count)]
    out = []
    for j in range(count):
        t = j / float(count) if closed else j / float(max(1, count - 1))
        target = t * total
        i = 1
        while i < len(cum) and cum[i] < target:
            i += 1
        i = min(i, len(cum) - 1)
        seg_len = cum[i] - cum[i - 1]
        if seg_len == 0.0:
            p = pts[i].copy()
        else:
            s = (target - cum[i - 1]) / seg_len
            p = pts[i - 1].lerp(pts[i], s)
        out.append(p)
    return out

def closest_point_on_polyline(samples, p, closed=False):
    if not samples:
        return 0, samples[0] if samples else p, 0.0
    best_dist = 1e20
    best_point = samples[0]
    best_t = 0.0
    best_index = 0
    seg_count = (len(samples) - 1) + (1 if closed else 0)
    for s in range(seg_count):
        i0 = s
        i1 = (s + 1) % len(samples) if closed else (s + 1)
        if i1 >= len(samples):
            continue
        a = samples[i0]; b = samples[i1]
        ab = b - a
        ab2 = ab.length_squared
        if ab2 == 0.0:
            proj = a; t = 0.0
        else:
            t = max(0.0, min(1.0, (p - a).dot(ab) / ab2))
            proj = a + t * ab
        d2 = (p - proj).length_squared
        if d2 < best_dist:
            best_dist = d2; best_point = proj; best_t = t; best_index = i0
    return best_index, best_point, best_t

def _uv_key(v2, tol=1e-6):
    return (round(v2.x / tol) * tol, round(v2.y / tol) * tol)

def build_all_selected_uv_paths(bm, uv_layer):
    def _uv_key_graph(v, tol=5e-7):
        s = int(round(1.0 / max(tol, 1e-12)))
        return (int(round(v.x * s)), int(round(v.y * s)))

    graph = {}
    nodes = {}
    for f in bm.faces:
        if getattr(f, 'hide', False):
            continue
        for l in f.loops:
            luv = l[uv_layer]
            ln = l.link_loop_next
            luvn = ln[uv_layer]

            if uv_edge_selected(l, uv_layer):
                a = Vector(luv.uv)
                b = Vector(luvn.uv)
                ka = _uv_key_graph(a)
                kb = _uv_key_graph(b)
                nodes.setdefault(ka, a)
                nodes.setdefault(kb, b)
                graph.setdefault(ka, set()).add(kb)
                graph.setdefault(kb, set()).add(ka)

    if not graph:
        return []

    def _components(g):
        comps = []
        visited = set()
        nodes_all = set(g.keys())
        for nbrs in g.values():
            nodes_all.update(nbrs)
        for n in nodes_all:
            if n in visited:
                continue
            stack = [n]
            comp = set([n])
            visited.add(n)
            while stack:
                cur = stack.pop()
                for nei in g.get(cur, ( )):
                    if nei not in visited:
                        visited.add(nei)
                        comp.add(nei)
                        stack.append(nei)
            comps.append(comp)
        return comps

    def _extract_paths(subg):
        paths = []
        visited_edges = set()
        def ekey(a,b):
            return (a,b) if a <= b else (b,a)
        def nbrs(k):
            return subg.get(k, set())
        def walk_forward(cur, prev):
            order = [cur]
            p = prev
            c = cur
            while True:
                nxts = [n for n in nbrs(c) if ekey(c,n) not in visited_edges and n != p]
                if not nxts:
                    break
                n = nxts[0]
                visited_edges.add(ekey(c,n))
                order.append(n)
                p, c = c, n
            return order
        endpoints = [k for k, ns in subg.items() if len(ns) == 1]
        for s in endpoints:
            ns = list(nbrs(s))
            if not ns:
                continue
            n = ns[0]
            if ekey(s,n) in visited_edges:
                continue
            visited_edges.add(ekey(s,n))
            right = walk_forward(n, s)
            order = [s] + right
            paths.append((order, False))
        for a in list(subg.keys()):
            for b in nbrs(a):
                e = ekey(a,b)
                if e in visited_edges:
                    continue
                visited_edges.add(e)
                right = walk_forward(b, a)
                left  = walk_forward(a, b)
                order = list(reversed(left)) + [a, b] + right
                deg_vals = [len(subg.get(k,set())) for k in order]
                is_closed = (len(order) >= 3 and all(d == 2 for d in deg_vals))
                paths.append((order, is_closed))
        return paths

    out_paths = []
    for comp in _components(graph):
        sub = {k: set(nei for nei in graph.get(k,set()) if nei in comp) for k in comp}
        for keys_order, is_closed in _extract_paths(sub):
            if len(set(keys_order)) <= 2:
                continue
            pts = [nodes[k] for k in keys_order]
            out_paths.append((pts, bool(is_closed)))

    return out_paths

# 単一化された WM プロパティ確保関数（重複を除去）
def ensure_wm_props():
    wm = bpy.context.window_manager
    if not hasattr(wm, "uv_spline_auto_ctrl_count"):
        wm.__class__.uv_spline_auto_ctrl_count = bpy.props.IntProperty(
            name="制御点数", default=4, min=2, max=30
        )

# モーダルオペレータの invoke を差し替えるための共通実装
_orig_invoke = None
def _invoke_with_defaults(self, context, event):
    """invoke のラッパ — WM プロパティを初期化してから元の invoke を呼ぶ"""
    ensure_wm_props()
    try:
        # uv_spline_auto_ctrl_count があればオペレータのデフォルトに設定
        self.auto_ctrl_count = context.window_manager.uv_spline_auto_ctrl_count
    except Exception:
        pass
    # _orig_invoke は register() 時に設定される想定
    if _orig_invoke is not None:
        return _orig_invoke(self, context, event)
    # フォールバック: クラスの元々の invoke を呼ぶ (もし存在すれば)
    return type(self).invoke(self, context, event)

def _monkeypatch_modal_invoke():
    """operators_spline.UV_OT_spline_adjust_modal.invoke を安全に差し替える（存在すれば）"""
    global _orig_invoke
    try:
        from .operators.spline import UV_OT_spline_adjust_modal
    except Exception:
        UV_OT_spline_adjust_modal = None

    if UV_OT_spline_adjust_modal is None:
        _orig_invoke = None
        return

    # 保存してから差し替え
    _orig_invoke = getattr(UV_OT_spline_adjust_modal, "invoke", None)
    UV_OT_spline_adjust_modal.invoke = _invoke_with_defaults

def _restore_modal_invoke():
    """差し替えを元に戻す"""
    global _orig_invoke
    try:
        from .operators.spline import UV_OT_spline_adjust_modal
    except Exception:
        UV_OT_spline_adjust_modal = None

    if UV_OT_spline_adjust_modal is None:
        _orig_invoke = None
        return

    if _orig_invoke is not None:
        UV_OT_spline_adjust_modal.invoke = _orig_invoke
    else:
        # 元がなければ安全なデフォルトにしておく（オリジナルの実装を参照）
        try:
            delattr(UV_OT_spline_adjust_modal, "invoke")
        except Exception:
            pass
    _orig_invoke = None

# utils モジュール自体は「ユーティリティ集」であり、クラス登録は行わない方針にする
def register():
    """
    注意：utils.register() は基本的に軽い初期化のみ行います。
    - モーダルオペレータの invoke 差し替え（operators_spline に実装があれば行う）
    - 必要な WM プロパティの確保
    """
    ensure_wm_props()
    _monkeypatch_modal_invoke()

def unregister():
    # 差し替えを元に戻す
    _restore_modal_invoke()
    # WM プロパティはアンレジストリで消すことは避け、Blender 側で持たせたままでも良い
    # （削除したい場合はここで delattr を行ってください）
    return
