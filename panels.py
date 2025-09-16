# panels.py
import bpy

# import operators via the operators package to avoid circular imports from legacy module names
from . import properties, utils
from .operators import spline, equalize, match3d
from bpy.app.translations import pgettext_iface as iface_

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
    bl_label = iface_('Spline')
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
        op_row.operator(spline.UV_OT_spline_adjust_modal.bl_idname,
                        text=iface_('Adjust with Curve (Modal)'), icon='CURVE_BEZCURVE')
        if use_uv_sync:
            col.label(text=iface_("Cannot run while UV sync selection is on."), icon='INFO')

        prefs = _get_addon_prefs()
        if prefs:
            try:
                apr = prefs.preferences
                box = col.box()
                # window manager prop is created in register(); guard access
                if hasattr(bpy.context.window_manager, "uv_spline_auto_ctrl_count"):
                    box.prop(bpy.context.window_manager, "uv_spline_auto_ctrl_count", text=iface_("Control Points"))
            except Exception:
                pass


class UV_PT_loop_equalize_auto(bpy.types.Panel):
    bl_label = iface_('UV Loop Equalize')
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
            layout.label(text=iface_('Initializing UV Loop Equalize…'))
            return

        sel = wm.uvlseq_settings.iter_choice

        def _apply_iter(op):
            try:
                if sel == 'AUTO':
                    op.iter_mode = 'AUTO'
                else:
                    op.iter_mode = 'COUNT'
                    op.iter_count = int(sel)
            except Exception:
                # Operator may not expose iter_mode/iter_count properties; ignore in that case
                pass

        col = layout.column(align=True)
        col.enabled = not sync_on

        op_auto = col.operator("uv.loop_equalize", text=iface_('Auto Equalize'), icon="ALIGN_CENTER")
        try:
            op_auto.closed_loop = 'AUTO'
            op_auto.repeat_closed_only = wm.uvlseq_settings.repeat_closed_only
        except Exception:
            pass
        _apply_iter(op_auto)

        row = col.row(align=True)
        op_open = row.operator("uv.loop_equalize", text=iface_('Open Loop'), icon="CURVE_PATH")
        try:
            op_open.closed_loop = 'OPEN'
            op_open.repeat_closed_only = wm.uvlseq_settings.repeat_closed_only
        except Exception:
            pass
        _apply_iter(op_open)

        op_close = row.operator("uv.loop_equalize", text=iface_('Closed Loop'), icon="MOD_CURVE")
        try:
            op_close.closed_loop = 'CLOSED'
            op_close.repeat_closed_only = wm.uvlseq_settings.repeat_closed_only
        except Exception:
            pass
        _apply_iter(op_close)

        box_iter = col.box()
        row_head = box_iter.row(align=True)
        row_head.label(text=iface_("Iterations"))
        row_head.prop(wm.uvlseq_settings, "repeat_closed_only", text=iface_("Closed loops only"))
        row_iter = box_iter.row(align=True)
        row_iter.prop(wm.uvlseq_settings, "iter_choice", expand=True)

        if sync_on:
            layout.label(text=iface_("Cannot run while UV sync selection is on."), icon='INFO')


class UV_PT_loop_equalize_straighten(bpy.types.Panel):
    bl_label = iface_('Straighten and Equalize')
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
                     text=iface_('Straighten and Equalize'),
                     icon="IPO_LINEAR")

        if sync_on:
            layout.label(text=iface_("Cannot run while UV sync selection is on."), icon='INFO')


class UV_PT_loop_match3d_ratio(bpy.types.Panel):
    bl_label = iface_('Match 3D Ratio')
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
        op = row0.operator("uv.loop_match3d_ratio", text=iface_('Auto Match 3D Ratio'), icon='ALIGN_CENTER')
        try:
            op.closed_loop = 'AUTO'
        except Exception:
            pass
        row1 = col.row(align=True)
        op = row1.operator("uv.loop_match3d_ratio", text=iface_('Open Loop'), icon='CURVE_PATH')
        try:
            op.closed_loop = 'OPEN'
        except Exception:
            pass
        op = row1.operator("uv.loop_match3d_ratio", text=iface_('Closed Loop'), icon='MOD_CURVE')
        try:
            op.closed_loop = 'CLOSED'
        except Exception:
            pass
        if sync_on:
            layout.label(text=iface_("Cannot run while UV sync selection is on."), icon='INFO')


class UV_PT_loop_match3d_ratio_straight(bpy.types.Panel):
    bl_label = iface_('Straighten Match 3D Ratio (Open only)')
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
        col.operator("uv.loop_match3d_ratio_straight_open", text=iface_('Straighten and Match 3D Ratio'), icon='IPO_LINEAR')
        if sync_on:
            layout.label(text=iface_("Cannot run while UV sync selection is on."), icon='INFO')


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
