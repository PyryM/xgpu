# ruff: noqa

import numpy as np
from numpy.typing import NDArray
from typing import Tuple
import trimesh
import xgpu
from xgpu.extensions import auto_vertex_layout

def euler_matrix(rx: float, ry: float, rz: float) -> NDArray:
    return trimesh.transformations.euler_matrix(rx, ry, rz)[0:3, 0:3]

def mesh_to_struct(mesh: trimesh.Trimesh) -> Tuple[NDArray, NDArray]:
    """
    Convert a trimesh to expected vertex format
    """

    VFMT_DTYPE = np.dtype(
        {
            "names": ["position", "color", "normal", "texcoord"],
            "formats": [
                np.dtype((np.float32, 3)),
                np.dtype((np.float32, 3)),
                np.dtype((np.float32, 3)),
                np.dtype((np.float32, 2)),
            ],
            "offsets": [0, 12, 24, 36],
            "itemsize": 44,
        }
    )

    # todo : cheaper smoooth shading
    vertices = mesh.vertices  # mesh.vertices[mesh.faces.ravel()]
    faces = mesh.faces  # np.arange(len(vertices)).reshape((-1, 3))
    normals = mesh.vertex_normals
    # np.tile(mesh.face_normals, (1, 3)).reshape((-1, 3))

    count = len(vertices)
    # colors = np.full((count, 3), [0.9, 0.9, 0.9])

    vertex_data = np.zeros(count, dtype=VFMT_DTYPE)
    vertex_data["position"] = vertices[:, 0:3]
    vertex_data["normal"] = normals[:, 0:3]
    # vertex_data["color"] = colors[:, 0:3]

    face_data = faces.astype(np.uint32).flatten()

    return vertex_data, face_data


def simple_vertex_layout() -> xgpu.VertexBufferLayout:
    return auto_vertex_layout(
        [
            xgpu.VertexFormat.Float32x3,  # position
            xgpu.VertexFormat.Float32x3,  # color
            xgpu.VertexFormat.Float32x3,  # normal
            xgpu.VertexFormat.Float32x2,  # texcoord
        ]
    )

def load_mesh_simple(fn: str) -> Tuple[NDArray, NDArray, xgpu.VertexBufferLayout]:
    mesh: trimesh.Trimesh = trimesh.load_mesh(fn)
    vbuff, ibuff = mesh_to_struct(mesh)
    return vbuff, ibuff, simple_vertex_layout()
