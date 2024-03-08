# ruff: noqa
# Largely adapted from https://github.com/pygfx/wgpu-py/blob/main/wgpu/gui/glfw.py
# wgpu-py: BSD-2 license

import os
import sys

import glfw

import xgpu
from xgpu import (
    ChainedStruct,
    Instance,
    SurfaceDescriptor,
    TextureView,
    surfaceDescriptor,
)
from xgpu.extensions import XDevice, XSurface


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
        # TODO: allow resizing after bother to deal with surface changes
        glfw.window_hint(glfw.RESIZABLE, False)
        # see https://github.com/FlorianRhiem/pyGLFW/issues/42
        # Alternatively, from pyGLFW 1.10 one can set glfw.ERROR_REPORTING='warn'
        if is_wayland():
            glfw.window_hint(glfw.FOCUSED, False)  # prevent Wayland focus error
        self.window = glfw.create_window(w, h, title, None, None)
        self.phys_width, self.phys_height = glfw.get_framebuffer_size(self.window)
        print("FB size:", self.phys_width, self.phys_height)
        cscale = glfw.get_window_content_scale(self.window)
        print("Content scale:", cscale[0], cscale[1])
        (self.window_handle, self.display_id) = get_handles(self.window)
        print("window:", self.window_handle)
        print("display:", self.display_id)
        self._surface = None
        self.depth_buffer = None
        glfw.set_key_callback(self.window, self.keyboard_callback)
        glfw.set_cursor_pos_callback(self.window, self.mouse_callback)
        glfw.set_window_size_callback(self.window, self.resize_callback)
        glfw.set_char_callback(self.window, self.char_callback)
        glfw.set_scroll_callback(self.window, self.scroll_callback)

    def keyboard_callback(self, window, key, scancode, action, mods):
        pass

    def char_callback(self, window, char):
        pass

    def resize_callback(self, window, width, height):
        pass

    def mouse_callback(self, *args, **kwargs):
        pass

    def scroll_callback(self, window, x_offset, y_offset):
        pass

    def poll(self) -> bool:
        glfw.poll_events()
        return bool(not glfw.window_should_close(self.window))

    def configure_surface(
        self,
        device: XDevice,
        format=xgpu.TextureFormat.BGRA8Unorm,
        depth_format=xgpu.TextureFormat.Depth24Plus,
    ):
        print("Configuring surface?")
        if self._surface is None:
            return
        self._surface.configure(
            device=device,
            usage=xgpu.TextureUsage.RenderAttachment,
            viewFormats=[format],
            format=format,
            alphaMode=xgpu.CompositeAlphaMode.Auto,
            width=self.phys_width,
            height=self.phys_height,
            presentMode=xgpu.PresentMode.Fifo,
        )
        self.depth_buffer = device.createTexture(
            usage=xgpu.TextureUsage.RenderAttachment,
            size=xgpu.extent3D(
                width=self.phys_width, height=self.phys_height, depthOrArrayLayers=1
            ),
            format=depth_format,
            viewFormats=[depth_format],
        )
        print("Configured surface?")

    def get_depth_buffer(self) -> xgpu.Texture:
        assert (
            self.depth_buffer is not None
        ), "No depth buffer created! Configure surface first!"
        return self.depth_buffer

    def get_surface(self, instance: Instance) -> XSurface:
        print("Getting surface?")
        if self._surface is not None:
            return self._surface
        desc = self.get_surface_descriptor()
        self._surface = XSurface(instance.createSurfaceFromDesc(desc))
        print("Got surface.")
        return self._surface

    def get_surface_descriptor(self) -> SurfaceDescriptor:
        if sys.platform.startswith("win"):
            inner = xgpu.surfaceDescriptorFromWindowsHWND(
                hinstance=xgpu.VoidPtr.NULL,
                hwnd=xgpu.VoidPtr.raw_cast(self.window_handle),
            )
        elif sys.platform.startswith("linux"):
            if is_wayland():
                print("WAYLAND?")
                inner = xgpu.surfaceDescriptorFromWaylandSurface(
                    display=xgpu.VoidPtr.raw_cast(self.display_id),
                    surface=xgpu.VoidPtr.raw_cast(self.window_handle),
                )
            else:
                print("XLIB?")
                inner = xgpu.surfaceDescriptorFromXlibWindow(
                    display=xgpu.VoidPtr.raw_cast(self.display_id),
                    window=self.window_handle,
                )
        elif sys.platform.startswith("darwin"):
            import ctypes

            from rubicon.objc.api import ObjCClass, ObjCInstance  # type: ignore

            window = ctypes.c_void_p(self.window_handle)

            cw = ObjCInstance(window)
            cv = cw.contentView

            if cv.layer and cv.layer.isKindOfClass(ObjCClass("CAMetalLayer")):
                # No need to create a metal layer again
                metal_layer = cv.layer
            else:
                metal_layer = ObjCClass("CAMetalLayer").layer()
                cv.setLayer(metal_layer)
                cv.setWantsLayer(True)

            inner = xgpu.surfaceDescriptorFromMetalLayer(
                layer=xgpu.VoidPtr.raw_cast(metal_layer.ptr.value)
            )
        else:
            raise RuntimeError("Unsupported windowing platform")

        return surfaceDescriptor(nextInChain=ChainedStruct([inner]))

    def begin_frame(self) -> TextureView:
        assert self._surface is not None, "Cannot begin_frame: no surface created!"
        self._cur_surf_tex = self._surface.getCurrentTexture2()
        self._cur_surf_view = self._cur_surf_tex.texture.createView(
            format=xgpu.TextureFormat.Undefined,
            dimension=xgpu.TextureViewDimension._2D,
            mipLevelCount=1,
            arrayLayerCount=1,
        )
        return self._cur_surf_view

    def end_frame(self, present=True):
        assert self._surface is not None, "Cannot end_frame: no surface created!"
        if present:
            self._surface.present()
        if self._cur_surf_view is not None:
            self._cur_surf_view.release()
            self._cur_surf_view = None
        if self._cur_surf_tex is not None:
            self._cur_surf_tex.texture.release()
            self._cur_surf_tex = None
