# operators/__init__.py
"""
operators パッケージ初期化。
サブモジュールは import 時にまとめて読み込むと循環参照の原因となるため、
register()/unregister() のタイミングで遅延読み込み (lazy import) します。
"""
import importlib
import sys

_SUBMODULE_NAMES = ("spline", "equalize", "match3d")

def _iter_submodules():
    """Yield imported module objects for known submodules, importing them if needed."""
    pkg = __package__ or "uv_loop_tools.operators"
    for name in _SUBMODULE_NAMES:
        fqname = f"{pkg}.{name}"
        if fqname in sys.modules:
            yield sys.modules[fqname]
        else:
            try:
                yield importlib.import_module(fqname)
            except Exception:
                # import failed; skip - registration will be best-effort
                continue

def register():
    """Register all operator submodules (import happens here)."""
    for mod in _iter_submodules():
        if hasattr(mod, "register"):
            try:
                mod.register()
            except Exception:
                # best-effort: continue registering others
                continue

def unregister():
    """Unregister submodules in reverse order."""
    mods = list(_iter_submodules())
    for mod in reversed(mods):
        if hasattr(mod, "unregister"):
            try:
                mod.unregister()
            except Exception:
                continue