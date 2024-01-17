import os
import sys

import glfw

import xgpu
from xgpu import (
    ChainedStruct,
    Device,
    Instance,
    Surface,
    SurfaceDescriptor,
    cast_any_to_void,
    surfaceDescriptor,
)


def is_wayland():
    # Do checks to prevent pitfalls on hybrid Xorg/Wayland systems
    if not sys.platform.startswith("linux"):
        return False
    wayland = "wayland" in os.getenv("XDG_SESSION_TYPE", "").lower()
    if wayland and not hasattr(glfw, "get_wayland_window"):
        raise RuntimeError(
            "We're on Wayland but Wayland functions not available. "
            + "Did you apt install libglfw3-wayland?"
        )
    return wayland


def get_linux_window(window):
    if is_wayland():
        return glfw.get_wayland_window(window)
    else:
        return glfw.get_x11_window(window)


def get_linux_display():
    if is_wayland():
        return glfw.get_wayland_display()
    else:
        return glfw.get_x11_display()


WINDOW_GETTERS = [
    ("win", lambda: (glfw.get_win32_window, lambda: 0)),
    ("darwin", lambda: (glfw.get_cocoa_window, lambda: 0)),
    ("linux", lambda: (get_linux_window, get_linux_display)),
]


def get_handles(window):
    for prefix, maker in WINDOW_GETTERS:
        if sys.platform.lower().startswith(prefix):
            win_getter, display_getter = maker()
            return (win_getter(window), display_getter())
    raise RuntimeError(f"Coulnd't get window handles for platform {sys.platform}")


class GLFWWindow:
    def __init__(self, w: int, h: int, title="xgpu"):
        self.width = w
        self.height = h
        if is_wayland():
            glfw.init_hint(glfw.PLATFORM, glfw.PLATFORM_WAYLAND)
        print("GLFW init:", glfw.init())
        glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)
        glfw.window_hint(glfw.RESIZABLE, True)
        # see https://github.com/FlorianRhiem/pyGLFW/issues/42
        # Alternatively, from pyGLFW 1.10 one can set glfw.ERROR_REPORTING='warn'
        if is_wayland():
            glfw.window_hint(glfw.FOCUSED, False)  # prevent Wayland focus error
        self.window = glfw.create_window(w, h, title, None, None)
        (self.window_handle, self.display_id) = get_handles(self.window)
        print("window:", self.window_handle)
        print("display:", self.display_id)
        self._surface = None
        self._surf_config = None

    def poll(self) -> bool:
        glfw.poll_events()
        return bool(not glfw.window_should_close(self.window))

    def configure_surface(self, device: Device, format=xgpu.TextureFormat.BGRA8Unorm):
        print("Configuring surface?")
        if self._surface is None:
            return
        if self._surf_config is None:
            self._surf_config = xgpu.surfaceConfiguration(
                device=device,
                usage=xgpu.TextureUsageFlags([xgpu.TextureUsage.RenderAttachment]),
                viewFormats=[format],
                format=format,
                alphaMode=xgpu.CompositeAlphaMode.Auto,
                width=self.width,
                height=self.height,
                presentMode=xgpu.PresentMode.Fifo,
            )
        self._surf_config.width = self.width
        self._surf_config.height = self.height
        self._surface.configure(self._surf_config)
        print("Configured surface?")

    def get_surface(self, instance: Instance) -> Surface:
        print("Getting surface?")
        if self._surface is not None:
            return self._surface
        desc = self.get_surface_descriptor()
        print("Got surface descriptor?")
        self._surface = instance.createSurfaceFromDesc(desc)
        print("Got surface?")
        return self._surface

    def get_surface_descriptor(self) -> SurfaceDescriptor:
        if sys.platform.startswith("win"):  # no-cover
            inner = xgpu.surfaceDescriptorFromWindowsHWND(
                hinstance=xgpu.NULL_VOID_PTR,
                hwnd=cast_any_to_void(self.window_handle),
            )
        elif sys.platform.startswith("linux"):  # no-cover
            if is_wayland():
                print("WAYLAND???")
                # todo: wayland seems to be broken right now
                inner = xgpu.surfaceDescriptorFromWaylandSurface(
                    display=cast_any_to_void(self.display_id),
                    surface=cast_any_to_void(self.window_handle),
                )
            else:
                print("XLIB????")
                inner = xgpu.surfaceDescriptorFromXlibWindow(
                    display=cast_any_to_void(self.display_id), window=self.window_handle
                )
        else:  # no-cover
            raise RuntimeError("Get a better OS")

        return surfaceDescriptor(nextInChain=ChainedStruct([inner]))
