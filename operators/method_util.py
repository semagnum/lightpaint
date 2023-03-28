from typing import Iterable

import bpy
from mathutils import Vector

EMISSIVE_MAT_NAME = 'LightPaint_Emissive'
FLAG_MAT_NAME = 'LightPaint_Shadow'

NORMAL_ERROR = ('Mean of normals resulted in zero vector - '
                'avoid drawing equally on surfaces facing opposite directions!')


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


def has_strokes(context) -> bool:
    """Checks if there are grease pencil strokes on the active frame."""
    annot_layer = context.active_annotation_layer
    return hasattr(annot_layer, 'active_frame') and hasattr(annot_layer.active_frame,
                                                            'strokes') and annot_layer.active_frame.strokes


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


def generate_flag_material(color):
    """Generates an object shadow flag material.

    :param color: shader's surface color (1.0, 1.0, 1.0).
    :return: material data
    """
    material = bpy.data.materials.new(name=FLAG_MAT_NAME)

    material.use_nodes = True
    tree = material.node_tree

    # find PBR and set color
    pbr_node = tree.nodes['Principled BSDF']
    pbr_node.inputs[0].default_value = color

    return material


def assign_flag_material(obj, color):
    """Assigns a shadow flag material to a given object.

    :param obj: object to assign th material.
    :param color: shader's surface color (1.0, 1.0, 1.0).
    """
    material = bpy.data.materials.new(name=FLAG_MAT_NAME)

    material.use_nodes = True
    tree = material.node_tree

    # find PBR and set color
    pbr_node = tree.nodes['Principled BSDF']
    pbr_node.inputs[0].default_value = color

    # Assign the new material.
    obj.data.materials.append(material)
