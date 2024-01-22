import numpy as np


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
