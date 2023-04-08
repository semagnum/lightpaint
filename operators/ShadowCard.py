#     Light Paint, Blender add-on that creates lights based on where the user paints.
#     Copyright (C) 2023 Spencer Magnusson
#     semagnum@gmail.com
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.


import bpy
from mathutils import Vector

from ..input import get_strokes
from .method_util import has_strokes, is_blocked

MAT_NAME = 'LightPaint_Shadow'
MESH_NAME = 'LightPaint_ShadowCard'


# active object is counted twice
def get_selected_lights(context) -> tuple:
    """Retrieves all selected lights, including the active object.
    Prevents duplicates if the active object is also selected.

    :param context: Blender context
    :return: a tuple of selected lights
    """
    light_objs_dict = {obj.name: obj for obj in context.selected_objects if obj.type == 'LIGHT'}
    if context.active_object:
        light_objs_dict.update({context.active_object.name: context.active_object})

    return tuple(light_objs_dict.values())


def assign_flag_material(obj, color, opacity):
    """Assigns a shadow flag material to a given object.

    :param obj: object to assign th material.
    :param color: shader's surface color (1.0, 1.0, 1.0).
    :param opacity: shader's opacity
    """
    material = bpy.data.materials.new(name=MAT_NAME)

    material.use_nodes = True
    tree = material.node_tree

    # find PBR and set color
    pbr_node = tree.nodes['Principled BSDF']
    pbr_node.inputs[0].default_value = color
    pbr_node.inputs[21].default_value = opacity

    material.blend_method = 'BLEND'
    material.shadow_method = 'HASHED'

    # Assign the new material.
    obj.data.materials.append(material)


def get_light_points(light_obj) -> list[Vector]:
    """Returns a list of points

    :param light_obj: object with light data
    :return: list of points
    """
    light_type = light_obj.data.type
    # if area, add all four corners
    if light_type == 'AREA':
        # rectangles and ellipses measure by length and width, the rest measure by area
        if light_obj.data.shape in ('RECTANGLE', 'ELLIPSE'):
            size_x = light_obj.data.size / 2
            size_y = light_obj.data.size_y / 2
        else:
            side_len = light_obj.data.size ** 0.5
            size_x, size_y = side_len, side_len

        corners = [Vector((x, y, 0))
                   for x in (size_x, size_x * -1)
                   for y in (size_y, size_y * -1)]
        return [light_obj.matrix_world @ v for v in corners]
    return [light_obj.location]


class LP_OT_ConvexShadow(bpy.types.Operator):
    bl_idname = 'semagnum.lp_shadow_card'
    bl_label = 'Paint Shadow Card'
    bl_description = 'Adds a shadow card positioned between a light and surfaces specified by annotations'
    bl_options = {'REGISTER', 'UNDO'}

    factor: bpy.props.FloatProperty(
        name='Factor',
        description='Position between light and surface (0 is at the light, 1 is at the surface)',
        min=0.0001,
        max=1.0,
        default=0.5,
        subtype='FACTOR',
    )

    offset: bpy.props.FloatProperty(
        name='Offset',
        description='Hull\'s offset towards the sun lamp',
        min=0.0,
        default=10.0,
        unit='LENGTH'
    )

    visible_to_camera: bpy.props.BoolProperty(
        name='Visible to Camera',
        description='If unchecked, object will not be directly visible by camera (although it will still emit light)',
        default=True
    )

    shadow_color: bpy.props.FloatVectorProperty(
        name='Shadow Card Color',
        description='Material color of the shadow card',
        size=4,
        default=[0.5, 0.5, 0.5, 1.0],
        min=0.0,
        soft_max=1.0,
        subtype='COLOR'
    )

    opacity: bpy.props.FloatProperty(
        name='Shadow Card Opacity',
        description='Material transparency of the shadow card',
        default=1.0,
        min=0.0,
        max=1.0
    )

    @classmethod
    def poll(cls, context):
        return has_strokes(context) and len(get_selected_lights(context)) > 0

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        light_objs = get_selected_lights(context)
        has_sun = any(obj.data.type == 'SUN' for obj in light_objs)
        has_other_lamps = any(obj.data.type != 'SUN' for obj in light_objs)
        if has_sun:
            layout.prop(self, 'offset')
        if has_other_lamps:
            layout.prop(self, 'factor')

        layout.prop(self, 'visible_to_camera')
        layout.prop(self, 'shadow_color')
        layout.prop(self, 'opacity')

    def add_card_for_lamp(self, context, light_obj, vertices):
        bpy.ops.object.select_all(action='DESELECT')

        mesh = bpy.data.meshes.new(MESH_NAME)
        obj = bpy.data.objects.new(mesh.name, mesh)
        col = context.collection
        col.objects.link(obj)
        context.view_layer.objects.active = obj

        scene = context.scene
        depsgraph = context.evaluated_depsgraph_get()
        if light_obj.data.type == 'SUN':
            direction = (light_obj.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
            direction.negate()
            mesh_vertices = tuple(v + direction * self.offset
                                  for v in vertices
                                  if not is_blocked(scene, depsgraph, v, direction))
        else:
            factor = self.factor
            if factor == 1.0:
                mesh_vertices = vertices
            else:
                mesh_vertices = tuple(light_v + (v - light_v) * factor
                                      for v in vertices
                                      for light_v in get_light_points(light_obj))

        mesh.from_pydata(mesh_vertices, [], [])

        # go into edit mode, convex hull, cleanup, then get out
        bpy.ops.object.editmode_toggle()

        bpy.ops.mesh.convex_hull()

        bpy.ops.object.editmode_toggle()

        obj.visible_camera = self.visible_to_camera
        assign_flag_material(obj, self.shadow_color, self.opacity)

    def execute(self, context):
        light_objs = get_selected_lights(context)

        try:
            strokes = get_strokes(context, 'X', 0.0)
            vertices = tuple(v for stroke in strokes for v in stroke)
        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        for light_obj in light_objs:
            self.add_card_for_lamp(context, light_obj, vertices)

        for obj in light_objs:
            obj.select_set(True)
        context.view_layer.objects.active = light_objs[-1]

        return {'FINISHED'}
