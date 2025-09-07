import bpy

# import operators via the operators package to avoid circular imports from legacy module names
from . import properties, utils
from .operators import spline as operators_spline, equalize as operators_equalize, match3d as operators_3d

def _get_addon_prefs():
    """Try to find the addon preferences object for this package.
    We look for any installed addon whose module name contains 'uv_loop_tools'
    (robust for different install locations).
    """
    try:
        addons = bpy.context.preferences.addons
    except Exception:
        return None
    # try direct package match first
    pkg = __package__ or ""
    if pkg:
        # if package is like 'bl_ext.user_default.uv_loop_tools', try that key
        if pkg in addons:
            return addons.get(pkg)
        # try top-level package
        root = pkg.split('.', 1)[0]
        if root in addons:
            return addons.get(root)
    # fallback: find any addon key that contains 'uv_loop_tools'
    for key in addons.keys():
        if 'uv_loop_tools' in key:
            return addons.get(key)
    # last resort: return None
    return None

class UV_PT_spline_panel(bpy.types.Panel):
    bl_label = 'スプライン'
    bl_category = 'ULT'
    bl_order = 10
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        use_uv_sync = getattr(context.scene.tool_settings, "use_uv_select_sync", False)
        op_row = col.row(align=True)
        op_row.enabled = not bool(use_uv_sync)
        op_row.operator(operators_spline.UV_OT_spline_adjust_modal.bl_idname,
                        text='カーブで調整（モーダル）', icon='CURVE_BEZCURVE')
        if use_uv_sync:
            col.label(text="UV選択同期がオンのため実行できません。", icon='INFO')

        prefs = _get_addon_prefs()
        if prefs:
            try:
                apr = prefs.preferences
                box = col.box()
                # window manager prop is created in register(); guard access
                if hasattr(bpy.context.window_manager, "uv_spline_auto_ctrl_count"):
                    box.prop(bpy.context.window_manager, "uv_spline_auto_ctrl_count", text="制御点数")
            except Exception:
                pass

class UV_PT_loop_equalize_auto(bpy.types.Panel):
    bl_label = 'UVループの頂点を等間隔化'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'ULT'
    bl_order = 20

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.area and context.area.type == 'IMAGE_EDITOR'
                and obj and obj.type == 'MESH' and obj.mode == 'EDIT')

    def draw(self, context):
        layout = self.layout
        ts = getattr(context, 'tool_settings', None)
        sync_on = bool(ts) and getattr(ts, 'use_uv_select_sync', False)
        wm = context.window_manager

        # Ensure settings PointerProperty exists (registered in register(), but double-check)
        if not hasattr(bpy.types.WindowManager, 'uvlseq_settings'):
            try:
                bpy.types.WindowManager.uvlseq_settings = bpy.props.PointerProperty(type=properties.UVLSEQ_Settings)
            except Exception:
                pass

        if not hasattr(wm, 'uvlseq_settings'):
            layout.label(text='UVループ均等化を初期化しています…')
            return

        sel = wm.uvlseq_settings.iter_choice

        def _apply_iter(op):
            if sel == 'AUTO':
                op.iter_mode = 'AUTO'
            else:
                op.iter_mode = 'COUNT'
                op.iter_count = int(sel)

        col = layout.column(align=True)
        col.enabled = not sync_on

        op_auto = col.operator("uv.loop_equalize", text='自動判定して等間隔', icon="ALIGN_CENTER")
        op_auto.closed_loop = 'AUTO'
        op_auto.repeat_closed_only = wm.uvlseq_settings.repeat_closed_only
        _apply_iter(op_auto)

        row = col.row(align=True)
        op_open = row.operator("uv.loop_equalize", text='開ループ', icon="CURVE_PATH")
        op_open.closed_loop = 'OPEN'
        op_open.repeat_closed_only = wm.uvlseq_settings.repeat_closed_only
        _apply_iter(op_open)

        op_close = row.operator("uv.loop_equalize", text='閉ループ', icon="MOD_CURVE")
        op_close.closed_loop = 'CLOSED'
        op_close.repeat_closed_only = wm.uvlseq_settings.repeat_closed_only
        _apply_iter(op_close)

        box_iter = col.box()
        row_head = box_iter.row(align=True)
        row_head.label(text="繰り返し")
        row_head.prop(wm.uvlseq_settings, "repeat_closed_only", text="閉ループのみ")
        row_iter = box_iter.row(align=True)
        row_iter.prop(wm.uvlseq_settings, "iter_choice", expand=True)

        if sync_on:
            layout.label(text="UV選択同期がONのため実行できません。", icon='INFO')

class UV_PT_loop_equalize_straighten(bpy.types.Panel):
    bl_label = 'UVループを直線化して等間隔化'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'ULT'
    bl_order = 30

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.area and context.area.type == 'IMAGE_EDITOR'
                and obj and obj.type == 'MESH' and obj.mode == 'EDIT')

    def draw(self, context):
        layout = self.layout
        ts = getattr(context, "tool_settings", None)
        sync_on = bool(ts) and ts.use_uv_select_sync

        col = layout.column(align=True)
        col.enabled = not sync_on

        col.operator("uv.loop_equalize_straight_open",
                     text='直線化して等間隔',
                     icon="IPO_LINEAR")

        if sync_on:
            layout.label(text="UV選択同期がONのため実行できません。", icon='INFO')


class UV_PT_loop_match3d_ratio(bpy.types.Panel):
    bl_label = '3D比率で再配置'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'ULT'
    bl_order = 40

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.area and context.area.type=='IMAGE_EDITOR' and obj and obj.type=='MESH' and obj.mode=='EDIT')

    def draw(self, context):
        layout = self.layout
        ts = getattr(context,'tool_settings',None)
        sync_on = bool(ts) and ts.use_uv_select_sync
        col = layout.column(align=True); col.enabled = not sync_on
        row0 = col.row(align=True)
        op = row0.operator("uv.loop_match3d_ratio", text='自動判定して3D比率', icon='ALIGN_CENTER'); op.closed_loop='AUTO'
        row1 = col.row(align=True)
        op = row1.operator("uv.loop_match3d_ratio", text='開ループ', icon='CURVE_PATH'); op.closed_loop='OPEN'
        op = row1.operator("uv.loop_match3d_ratio", text='閉ループ', icon='MOD_CURVE'); op.closed_loop='CLOSED'
        if sync_on:
            layout.label(text="UV選択同期がONのため実行できません。", icon='INFO')


class UV_PT_loop_match3d_ratio_straight(bpy.types.Panel):
    bl_label = '3D比率で直線化（開のみ）'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'ULT'
    bl_order = 50

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.area and context.area.type=='IMAGE_EDITOR' and obj and obj.type=='MESH' and obj.mode=='EDIT')

    def draw(self, context):
        layout = self.layout
        ts = getattr(context,'tool_settings',None)
        sync_on = bool(ts) and ts.use_uv_select_sync
        col = layout.column(align=True); col.enabled = not sync_on
        col.operator("uv.loop_match3d_ratio_straight_open", text='直線化して3D比率', icon='IPO_LINEAR')
        if sync_on:
            layout.label(text="UV選択同期がONのため実行できません。", icon='INFO')


# --- registration helpers ---
classes = (
    UV_PT_spline_panel,
    UV_PT_loop_equalize_auto,
    UV_PT_loop_equalize_straighten,
    UV_PT_loop_match3d_ratio,
    UV_PT_loop_match3d_ratio_straight,
)

def register():
    # ensure the WindowManager setting exists if the settings class is available
    try:
        # register panel classes
        for cls in classes:
            bpy.utils.register_class(cls)
    except Exception:
        # if registration fails, try to unregister any that did register (best-effort)
        for cls in reversed(classes):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
        raise

    # create WindowManager pointer if the properties class exists
    try:
        if hasattr(properties, "UVLSEQ_Settings"):
            if not hasattr(bpy.types.WindowManager, "uvlseq_settings"):
                bpy.types.WindowManager.uvlseq_settings = bpy.props.PointerProperty(type=properties.UVLSEQ_Settings)
    except Exception:
        # non-fatal
        pass

def unregister():
    # remove pointer if we added it
    try:
        if hasattr(bpy.types.WindowManager, "uvlseq_settings"):
            try:
                delattr(bpy.types.WindowManager, "uvlseq_settings")
            except Exception:
                # safe to ignore if it wasn't ours
                pass
    except Exception:
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
