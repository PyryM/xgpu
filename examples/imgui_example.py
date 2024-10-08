"""
Imgui integration?
"""

import imgui

import xgpu as xg
from xgpu.extensions import get_preferred_format
from xgpu.extensions.imgui_renderer import ImguiWindow, XGPUImguiRenderer


class IgWindow:
    def __init__(self, title: str, open=True):
        self.open = open
        self.title = title
        self.expand = True

    def content(self):
        pass

    def render(self):
        if not self.open:
            return
        self.expand, self.open = imgui.begin(self.title, True)
        if self.expand:
            self.content()
        imgui.end()


def undent(text: str) -> str:
    return "\n".join(line.strip() for line in text.split("\n"))


def text_tab(title: str, content: str):
    with imgui.begin_tab_item(title) as item:
        if item.selected:
            imgui.text(undent(content))


class AboutWindow(IgWindow):
    def __init__(self, open=True):
        super().__init__("About XGPU", open)

    def content(self):
        with imgui.begin_tab_bar("MyTabBar") as tab_bar:
            if tab_bar.opened:
                text_tab(
                    "Typing",
                    """
                XGPU is fully typed
                """,
                )
                text_tab(
                    "Up-To-Date",
                    """
                XGPU is autogenerated from webgpu.h, and aims to
                always be up-to-date
                """,
                )
                text_tab(
                    "Performance",
                    """
                XGPU provides a low-overhead binding
                """,
                )


def main():
    WIDTH = 1024
    HEIGHT = 1024

    # xg.extensions.enable_logging(xg.LogLevel.Trace)
    imgui.create_context()
    print("VERTEX SIZE:", imgui.VERTEX_SIZE)

    window = ImguiWindow(WIDTH, HEIGHT, "IMGUI", font="assets/IBMPlexSans-Regular.ttf")

    # Enable shader debug if you want to have wgsl source available (e.g., in RenderDoc)
    _, adapter, device, surface = xg.extensions.startup(
        surface_src=window.get_surface, debug=False
    )
    assert surface is not None, "Failed to get surface!"

    window_tex_format = get_preferred_format(adapter, surface)
    print("Window tex format:", window_tex_format.name)
    window.configure_surface(device, window_tex_format)

    imgui_io = imgui.get_io()
    imgui_io.display_size = (WIDTH, HEIGHT)
    renderer = XGPUImguiRenderer(device, imgui_io, window_tex_format)

    about = AboutWindow()

    while window.poll():
        window.process_inputs()
        imgui.new_frame()
        about.render()
        imgui.render()
        color_view = window.begin_frame()
        renderer.render(imgui.get_draw_data(), color_view)
        window.end_frame()

    print("Window close requested.")


if __name__ == "__main__":
    main()
