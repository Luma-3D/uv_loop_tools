# properties.py
import bpy
from bpy.props import *

# ==== F9用：Nパネルのプリセットと同じ選択肢 ====
_PRESET_COUNTS = ('1', '3', '5')  # 現在のNパネルと一致させる

class UVLSEQ_Settings(bpy.types.PropertyGroup):
    iter_choice: bpy.props.EnumProperty(
        name="繰り返し",
        description="実行時に参照される繰り返しの回数設定",
        items=[
            ('AUTO', "Auto", "収束まで自動で繰り返す（上限あり）"),
            ('1',    "1",    "1回だけ実行"),
            ('3',    "3",    "3回だけ実行"),
            ('5',    "5",    "5回だけ実行"),
        ],
        default='AUTO'
    )

    repeat_closed_only: bpy.props.BoolProperty(
        name="閉ループのみ",
        description="有効な場合、開ループは繰り返しを1回に固定し、閉ループのみで繰り返しオプションを適用します",
        default=True
    )

# --- registration helpers ---------------------------------------------------
classes = (UVLSEQ_Settings,)

def register():
    # register class(es)
    for cls in classes:
        bpy.utils.register_class(cls)

    # create WindowManager pointer property so panels/operators can access wm.uvlseq_settings
    try:
        if not hasattr(bpy.types.WindowManager, "uvlseq_settings"):
            bpy.types.WindowManager.uvlseq_settings = bpy.props.PointerProperty(type=UVLSEQ_Settings)
    except Exception:
        # non-fatal — if creation fails, panels guard for missing attribute
        pass

def unregister():
    # remove pointer (best-effort)
    try:
        if hasattr(bpy.types.WindowManager, "uvlseq_settings"):
            try:
                delattr(bpy.types.WindowManager, "uvlseq_settings")
            except Exception:
                # fallback: set to None if deletion not allowed
                try:
                    bpy.types.WindowManager.uvlseq_settings = None
                except Exception:
                    pass
    except Exception:
        pass

    # unregister classes in reverse order
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
