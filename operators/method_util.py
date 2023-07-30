#     Light Painter, Blender add-on that creates lights based on where the user paints.
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

from typing import Iterable

import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import box_fit_2d

EPSILON = 0.01

EMISSIVE_MAT_NAME = 'LightPaint_Emissive'
FLAG_MAT_NAME = 'LightPaint_Shadow'

NORMAL_ERROR = 'Average of normals results in a zero vector - unable to calculate average direction!'


def layout_group(layout, text=None):
    layout.separator()
    box = layout.box()
    if text is not None:
        box.label(text=text)
    return box


def get_average_normal(normals: Iterable[Vector]) -> Vector:
    """Calculates average normal. Handles zero vector edge case as an error.

    :param normals: list of normal vectors
    :return: single normalized Vector representing the average
    """
    avg_normal = sum(normals, start=Vector())
    avg_normal.normalize()
    if avg_normal == Vector((0, 0, 0)):
        raise ValueError(NORMAL_ERROR)

    return avg_normal


def get_box(vertices, normal):
    """Given a set of vertices flattened along a plane and their normal, return an aligned rectangle.

    :param vertices: list of vertex coordinates in world space
    :param normal: normal of vertices for rectangle to be projected to
    :return: tuple of (coordinate of rect center, matrix for rotation, rect length, and rect width
    """
    # rotate hull so normal is pointed up, so we can ignore Z
    # find angle of fitted box
    align_to_z = normal.rotation_difference(Vector((0.0, 0.0, 1.0))).to_matrix()
    flattened_2d = [align_to_z @ v for v in vertices]

    # rotate hull by angle
    # get length and width
    angle = box_fit_2d([(v[0], v[1]) for v in flattened_2d])
    box_mat = Matrix.Rotation(angle, 3, 'Z')
    aligned_2d = [(box_mat @ Vector((co[0], co[1], 0))) for co in flattened_2d]
    xs = tuple(co[0] for co in aligned_2d)
    ys = tuple(co[1] for co in aligned_2d)

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    length = x_max - x_min
    width = y_max - y_min

    center = align_to_z.inverted_safe() @ box_mat.inverted_safe() @ Vector((x_min + (length / 2),
                                                                            y_min + (width / 2),
                                                                            flattened_2d[0][2]))

    # return matrix, length and width of box
    return center, align_to_z.inverted_safe() @ box_mat.inverted_safe(), length, width


def has_strokes(context) -> bool:
    """Checks if there are grease pencil strokes on the active frame."""
    annot_layer = context.active_annotation_layer
    return hasattr(annot_layer, 'active_frame') and hasattr(annot_layer.active_frame,
                                                            'strokes') and annot_layer.active_frame.strokes


def is_blocked(scene, depsgraph, origin: Vector, direction: Vector, max_distance=1.70141e+38) -> bool:
    """Check if a given point is occluded in a given direction.

    :param scene: scene
    :param depsgraph: scene dependency graph
    :param origin: given point in world space as a Vector
    :param direction: given direction in world space as a Vector
    :param max_distance: maximum distance for raycast to check
    :return: True if anything is in that direction from that point, False otherwise
    """
    offset_origin = origin + direction * EPSILON
    is_hit, _, _, _idx, _, _ = scene.ray_cast(depsgraph, offset_origin, direction, distance=max_distance)
    return is_hit


def generate_emissive_material(color, emit_value: float):
    """Generates an object emissive material.

    :param color: shader's emission color (1.0, 1.0, 1.0).
    :param emit_value: shader's emission value.
    :return: material data
    """
    material = bpy.data.materials.new(name=EMISSIVE_MAT_NAME)

    material.use_nodes = True
    tree = material.node_tree

    tree.nodes.clear()

    output_node = tree.nodes.new(type='ShaderNodeOutputMaterial')
    emissive_node = tree.nodes.new(type='ShaderNodeEmission')

    # set emission color and value
    emissive_node.inputs[0].default_value = color
    emissive_node.inputs[1].default_value = emit_value

    # connect
    tree.links.new(emissive_node.outputs[0], output_node.inputs['Surface'])

    return material


def assign_emissive_material(obj, color, emit_value: float):
    """Assigns an emissive material to a given object.

    :param obj: object to assign the emissive material.
    :param color: shader's emission color (1.0, 1.0, 1.0).
    :param emit_value: shader's emission value.
    """
    mat = generate_emissive_material(color, emit_value)
    obj.data.materials.append(mat)  # Assign the new material.


def relative_power_prop():
    """Returns bool property to toggle relative lamp power."""
    return bpy.props.BoolProperty(
        name='Relative',
        description='Lamp power scales based on distance, relative to 1m',
        default=False
    )


def calc_power(power: float, distance: float) -> float:
    """Calculates relative light power based on inverse square law.
    relative power = initial power * squared distance

    :param power: light value at 1m.
    :param distance: distance from the light to the target object.
    :return: light power relative to distance
    """
    return power * (distance * distance)
