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
    if not hasattr(bpy.types.WindowManager, "uvlseq_settings"):
        bpy.types.WindowManager.uvlseq_settings = bpy.props.PointerProperty(type=UVLSEQ_Settings)

    # Move uv_spline_auto_ctrl_count registration here (was monkey-patched in utils)
    if not hasattr(bpy.types.WindowManager, "uv_spline_auto_ctrl_count"):
        bpy.types.WindowManager.uv_spline_auto_ctrl_count = bpy.props.IntProperty(
            name="Control Points", default=4, min=2, max=30
        )


def unregister():
    # remove pointer
    if hasattr(bpy.types.WindowManager, "uvlseq_settings"):
        del bpy.types.WindowManager.uvlseq_settings

    if hasattr(bpy.types.WindowManager, "uv_spline_auto_ctrl_count"):
        del bpy.types.WindowManager.uv_spline_auto_ctrl_count

    # unregister classes in reverse order
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
