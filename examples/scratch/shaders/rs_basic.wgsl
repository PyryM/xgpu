struct GlobalUniforms {
  @align(16) view_proj_mat: mat4x4f
}

struct DrawUniforms {
  @align(16) model_mat: mat4x4f,
  @align(16) color: vec4f,
}

#visibility("fragment", "vertex")
@group(0) @binding(0) var<uniform> global_uniforms: GlobalUniforms;
@group(1) @binding(0) var<uniform> draw_uniforms: DrawUniforms;

struct VertexInput {
    @location(0) pos: vec4f,
};

struct VertexOutput {
    @builtin(position) pos: vec4<f32>,
    @location(0) color : vec4<f32>,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    let world_pos = draw_uniforms.model_mat * vec4f(in.pos.xyz, 1.0f);
    let clip_pos = global_uniforms.view_proj_mat * world_pos;
    let color = draw_uniforms.color * clamp(in.pos, vec4f(0.0f), vec4f(1.0f));
    return VertexOutput(clip_pos, color);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    return in.color;
}
