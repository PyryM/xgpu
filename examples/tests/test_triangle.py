import os

import harness

SHADER = """
struct VertexInput {
    @builtin(vertex_index) vertex_index : u32,
};
struct VertexOutput {
    @location(0) color : vec4f,
    @builtin(position) pos: vec4f,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var positions = array<vec2f, 3>(
        vec2f(0.0, -0.5),
        vec2f(0.5, 0.5),
        vec2f(-0.5, 0.75),
    );
    var colors = array<vec3f, 3>(  // srgb colors
        vec3f(1.0, 1.0, 0.0),
        vec3f(1.0, 0.0, 1.0),
        vec3f(0.0, 1.0, 1.0),
    );
    let index = i32(in.vertex_index);
    var out: VertexOutput;
    out.pos = vec4f(positions[index], 0.0, 1.0);
    out.color = vec4f(colors[index], 1.0);
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let physical_color = pow(in.color.rgb, vec3f(2.2));  // gamma correct
    return vec4f(physical_color, in.color.a);
}
"""


def runtest():
    app = harness.RenderHarness(os.path.basename(__file__))
    app.create_pipeline(shader_src=SHADER)
    renderpass = app.begin()
    renderpass.draw(3, 1, 0, 0)
    app.finish()


if __name__ == "__main__":
    runtest()
