# __init__.py
bl_info = {
    "name": "UV Loop Tools",
    "author": "Luma",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "Image Editor > N-panel > ULT",
    "description": "UV spline / loop equalize / 3D match tools (modular)",
    "category": "UV",
}

# ルートに残すモジュール（非-operators）
from . import (
    properties,
    utils,
    panels,
    preferences,
)

# operators パッケージ側に移動した各モジュールを旧名でエイリアス
# operators パッケージを1つのモジュールとして扱う（内部で遅延読み込みされる）
from . import operators

MODULES = (
    properties,
    utils,
    operators,
    panels,
    preferences,
)

def register():
    """Register: 各サブモジュールの register() を順に呼ぶ（例外はそのまま上げる）"""
    import bpy
    for mod in MODULES:
        if hasattr(mod, "register"):
            mod.register()

def unregister():
    """Unregister: register と逆順に各サブモジュールの unregister() を呼ぶ"""
    import bpy
    for mod in reversed(MODULES):
        if hasattr(mod, "unregister"):
            mod.unregister()