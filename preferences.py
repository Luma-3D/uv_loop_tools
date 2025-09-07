import bpy

class UVSplineAdjusterPreferences(bpy.types.AddonPreferences):
    # bl_idname must match the addon module/package name used in Blender's addons dict.
    # Using __package__ is appropriate when this is a package like 'bl_ext.user_default.uv_loop_tools'.
    bl_idname = __package__

    curve_color: bpy.props.FloatVectorProperty(
        name="Curve Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.15, 0.7, 1.0, 1.0)
    )
    curve_thickness: bpy.props.FloatProperty(
        name="Curve Thickness",
        default=2.0, min=0.5, max=20.0
    )
    insert_pick_threshold_px: bpy.props.IntProperty(
        name="Insert Pick Threshold (px)", default=6, min=1, max=64
    )
    point_color_normal: bpy.props.FloatVectorProperty(
        name="Normal", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 0.0, 1.0)
    )
    point_color_selected: bpy.props.FloatVectorProperty(
        name="Selected", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 0.3, 0.3, 1.0)
    )
    point_color_active: bpy.props.FloatVectorProperty(
        name="Active", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )
    point_size: bpy.props.FloatProperty(
        name="Control Point Size", default=6.0, min=1.0, max=24.0
    )
    point_pick_threshold_px: bpy.props.IntProperty(
        name="Point Pick Threshold (px)", default=12, min=1, max=64
    )

    def draw(self, context):
        layout = self.layout
        # カーブ
        box = layout.box()
        box.label(text='カーブ')
        box.prop(self, 'curve_color', text='カーブの色')
        box.prop(self, 'curve_thickness', text='カーブの太さ')
        box.prop(self, 'insert_pick_threshold_px', text='制御点を追加する際のクリックしきい値 (px)')
        # 制御点
        box = layout.box()
        box.label(text='制御点')
        row = box.row(align=True)
        row.prop(self, 'point_color_normal', text='通常')
        row.prop(self, 'point_color_selected', text='選択')
        row.prop(self, 'point_color_active', text='アクティブ')
        box.prop(self, 'point_size', text='制御点の大きさ')
        box.prop(self, 'point_pick_threshold_px', text='制御点選択しきい値 (px)')


# registration helpers
classes = (UVSplineAdjusterPreferences,)

def register():
    import bpy
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    import bpy
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
