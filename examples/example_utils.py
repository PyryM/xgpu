import numpy as np

import xgpu as xg


def proj_frustum(left, right, bottom, top, near, far):
    """Produce a perspective projection matrix from
    a frustrum
    """
    xs = 2.0 * near / (right - left)
    ys = 2.0 * near / (top - bottom)
    xz = (right + left) / (right - left)
    yz = (top + bottom) / (top - bottom)
    zs = -far / (far - near)
    z0 = -far * near / (far - near)
    return np.array(
        [
            [xs, 0.0, xz, 0.0],
            [0.0, ys, yz, 0.0],
            [0.0, 0.0, zs, z0],
            [0.0, 0.0, -1.0, 0.0],
        ]
    )


def proj_perspective(fov_y_radians, aspect_ratio, near, far):
    """Produce a perspective projection matrix from a field of view and aspect ratio"""
    vheight = 2.0 * near * np.tan(fov_y_radians * 0.5)
    vwidth = vheight * aspect_ratio

    return proj_frustum(
        -vwidth / 2.0, vwidth / 2.0, -vheight / 2.0, vheight / 2.0, near, far
    )

def buffer_layout_entry(binding, visibility, bind_type, dynamic_offset=False, min_size=0):
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.buffer = xg.bufferBindingLayout(
        type=bind_type,
        hasDynamicOffset=dynamic_offset,
        minBindingSize=min_size,
    )
    return entry


def texture_layout_entry(
    binding, visibility, sample_type, view_dimension, multisampled=False
):
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.texture = xg.textureBindingLayout(
        sampleType=sample_type,
        viewDimension=view_dimension,
        multisampled=multisampled,
    )
    return entry


def storage_texture_layout_entry(
    binding, visibility, format, view_dimension, access=xg.StorageTextureAccess.WriteOnly
):
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.storageTexture = xg.storageTextureBindingLayout(
        format=format,
        viewDimension=view_dimension,
        access=access,
    )
    return entry


def sampler_layout_entry(binding, visibility, type=xg.SamplerBindingType.Filtering):
    entry = xg.BindGroupLayoutEntry(cdata=None, parent=None)
    entry.binding = binding
    entry.visibility = visibility
    entry.sampler = xg.samplerBindingLayout(
        type=type,
    )
    return entry
