import bpy

class UVSplineAdjusterPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    curve_color: bpy.props.FloatVectorProperty(
        name="Curve Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.15, 0.7, 1.0, 1.0)
    )
    curve_thickness: bpy.props.FloatProperty(
        name="Curve Thickness", default=2.0, min=0.5, max=20.0
    )
    def update_display_scale(self, context):
        scale = float(self.display_scale)
        # Base values (FHD standard): thickness=2.0, point_size=6.0
        self.curve_thickness = 2.0 * scale
        self.point_size = 6.0 * scale

    display_scale: bpy.props.EnumProperty(
        name="Display Scale",
        description="Scale factor for drawing spline and points (useful for HiDPI/4K)",
        items=[
            ('1.0', "FHD (100%)", "Standard scale"),
            ('1.5', "WQHD (150%)", "1.5x scale"),
            ('2.0', "UHD (200%)", "2x scale for 4K"),
        ],
        default='1.0',
        update=update_display_scale
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
        box = layout.box()
        box.label(text='Display')
        box.prop(self, "display_scale")
        
        box = layout.box()
        box.label(text='Curve')
        box.prop(self, 'curve_color', text='Curve Color')
        box.prop(self, 'curve_thickness', text='Curve Thickness')
        box.prop(self, 'insert_pick_threshold_px', text='Insert Pick Threshold (px)')
        box = layout.box()
        box.label(text='Control Points')
        row = box.row(align=True)
        row.prop(self, 'point_color_normal', text='Normal')
        row.prop(self, 'point_color_selected', text='Selected')
        row.prop(self, 'point_color_active', text='Active')
        box.prop(self, 'point_size', text='Control Point Size')
        box.prop(self, 'point_pick_threshold_px', text='Point Pick Threshold (px)')


classes = (UVSplineAdjusterPreferences,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
