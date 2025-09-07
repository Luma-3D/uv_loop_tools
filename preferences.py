import bpy

class UVSplineAdjusterPreferences(bpy.types.AddonPreferences):
    # bl_idname must match the addon module/package name used in Blender's addons dict.
    # Using __package__ is appropriate when this is a package like 'bl_ext.user_default.uv_loop_tools'.
    # Use explicit package id to avoid mismatch when installed as a namespaced package
    bl_idname = "uv_loop_tools"

    curve_color = bpy.props.FloatVectorProperty(
        name="Curve Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.15, 0.7, 1.0, 1.0)
    )
    curve_thickness = bpy.props.FloatProperty(
        name="Curve Thickness",
        default=2.0, min=0.5, max=20.0
    )
    insert_pick_threshold_px = bpy.props.IntProperty(
        name="Insert Pick Threshold (px)", default=6, min=1, max=64
    )
    point_color_normal = bpy.props.FloatVectorProperty(
        name="Normal", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 0.0, 1.0)
    )
    point_color_selected = bpy.props.FloatVectorProperty(
        name="Selected", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 0.3, 0.3, 1.0)
    )
    point_color_active = bpy.props.FloatVectorProperty(
        name="Active", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0, 1.0)
    )
    point_size = bpy.props.FloatProperty(
        name="Control Point Size", default=6.0, min=1.0, max=24.0
    )
    point_pick_threshold_px = bpy.props.IntProperty(
        name="Point Pick Threshold (px)", default=12, min=1, max=64
    )

    def draw(self, context):
        layout = self.layout
        # Curve
        box = layout.box()
        box.label(text='Curve')
        box.prop(self, 'curve_color', text='Curve Color')
        box.prop(self, 'curve_thickness', text='Curve Thickness')
        box.prop(self, 'insert_pick_threshold_px', text='Insert Pick Threshold (px)')
        # Control points
        box = layout.box()
        box.label(text='Control Points')
        row = box.row(align=True)
        row.prop(self, 'point_color_normal', text='Normal')
        row.prop(self, 'point_color_selected', text='Selected')
        row.prop(self, 'point_color_active', text='Active')
        box.prop(self, 'point_size', text='Control Point Size')
        box.prop(self, 'point_pick_threshold_px', text='Point Pick Threshold (px)')


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
