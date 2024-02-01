"""
Imgui integration?
"""

import imgui
from imgui_renderer import ImguiWindow, XGPUImguiRenderer

import xgpu as xg


def main():
    WIDTH = 1024
    HEIGHT = 1024

    # xg.helpers.enable_logging(xg.LogLevel.Trace)
    imgui.create_context()
    print("VERTEX SIZE:", imgui.VERTEX_SIZE)

    window = ImguiWindow(WIDTH, HEIGHT, "IMGUI")

    # Enable shader debug if you want to have wgsl source available (e.g., in RenderDoc)
    _, adapter, device, surface = xg.helpers.startup(
        surface_src=window.get_surface, debug=False
    )
    assert surface is not None, "Failed to get surface!"

    window_tex_format = xg.TextureFormat.BGRA8Unorm  # surface.getPreferredFormat(adapter)
    print("Window tex format:", window_tex_format.name)
    window.configure_surface(device, window_tex_format)

    imgui_io = imgui.get_io()
    imgui_io.display_size = (WIDTH, HEIGHT)
    renderer = XGPUImguiRenderer(device, imgui_io, window_tex_format)

    show_custom_window = True
    is_expand = True

    while window.poll():
        window.process_inputs()
        imgui.new_frame()
        if show_custom_window:
            is_expand, show_custom_window = imgui.begin("Custom window", True)
            if is_expand:
                imgui.text("Bar")
                imgui.text_ansi("B\033[31marA\033[mnsi ")
                imgui.text_ansi_colored("Eg\033[31mgAn\033[msi ", 0.2, 1.0, 0.0)
                imgui.extra.text_ansi_colored("Eggs", 0.2, 1.0, 0.0)
            imgui.end()

            imgui.begin("Custom window2", True)
            imgui.end()
        imgui.render()
        color_view = window.begin_frame()
        renderer.render(imgui.get_draw_data(), color_view)
        window.end_frame()

    print("Window close requested.")


if __name__ == "__main__":
    main()
