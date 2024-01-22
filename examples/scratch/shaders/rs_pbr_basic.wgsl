// ported from: https://github.com/samdauwe/webgpu-native-examples/blob/master/src/examples/pbr_basic.c
// apache 2

struct GlobalUniforms {
  @align(16) viewProj : mat4x4f,
  @align(16) camPos : vec3f,
};

struct ObjectUniforms {
  @align(16) model: mat4x4f,
  @align(16) roughnessMetallic: vec2f,
  @align(16) diffuse: vec3f,
};

struct Light {
  pos: vec4f,
  color: vec4f,
};

#visibility("fragment", "vertex")
@group(0) @binding(0) var<uniform> glob : GlobalUniforms;
@group(0) @binding(1) var<storage, read> lights: array<Light>; 
@group(1) @binding(0) var<uniform> object : ObjectUniforms;

struct Output {
  @builtin(position) position : vec4f,
  @location(0) outWorldPos : vec3f,
  @location(1) outNormal : vec3f,
};

@vertex
fn vs_main(
  @location(0) inPos: vec3f,
  @location(1) inNormal: vec3f
) -> Output {
  var output: Output;
  let locPos : vec3f = (object.model * vec4f(inPos, 1.0)).xyz;
  output.outWorldPos = locPos;
  output.outNormal = normalize((object.model * vec4f(inNormal, 0.0)).xyz);
  output.position = glob.viewProj * vec4f(output.outWorldPos, 1.0);

  return output;
}

const PI: f32 = 3.14159265359;

// Normal Distribution function ----------------------------------------------
fn D_GGX(dotNH : f32, roughness : f32) -> f32 {
  let alpha : f32 = roughness * roughness;
  let alpha2 : f32 = alpha * alpha;
  let denom : f32 = dotNH * dotNH * (alpha2 - 1.0) + 1.0;
  return (alpha2)/(PI * denom*denom);
}

// Geometric Shadowing function ----------------------------------------------
fn G_SchlicksmithGGX(dotNL : f32, dotNV : f32, roughness : f32) -> f32 {
  let r  : f32 = (roughness + 1.0);
  let k  : f32 = (r*r) / 8.0;
  let GL : f32 = dotNL / (dotNL * (1.0 - k) + k);
  let GV : f32 = dotNV / (dotNV * (1.0 - k) + k);
  return GL * GV;
}

// Fresnel function ----------------------------------------------------------
fn F_Schlick(cosTheta : f32, metallic : f32) -> vec3f {
  let F0 : vec3f = mix(vec3(0.04), object.diffuse, metallic);
  let F : vec3f = F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
  return F;
}

// Specular BRDF composition -------------------------------------------------
fn BRDF(L : vec3f, V : vec3f, N : vec3f, metallic : f32,
        roughness : f32, lightColor: vec3f) -> vec3f {
  // Precalculate vectors and dot products
  let H : vec3f = normalize(V + L);
  let dotNV : f32 = clamp(dot(N, V), 0.0, 1.0);
  let dotNL : f32 = clamp(dot(N, L), 0.0, 1.0);
  let dotLH : f32 = clamp(dot(L, H), 0.0, 1.0);
  let dotNH : f32 = clamp(dot(N, H), 0.0, 1.0);

  var color : vec3f = vec3(0.0);

  if (dotNL > 0.0) {
      let rroughness : f32 = max(0.05, roughness);
      // D = Normal distribution (Distribution of the microfacets)
      let D : f32 = D_GGX(dotNH, roughness);
      // G = Geometric shadowing term (Microfacets shadowing)
      let G : f32 = G_SchlicksmithGGX(dotNL, dotNV, roughness);
      // F = Fresnel factor (Reflectance depending on angle of incidence)
      let F : vec3f = F_Schlick(dotNV, metallic);
      let spec = D * F * G / (4.0 * dotNL * dotNV);
      color += spec * dotNL * lightColor;
  }

  return color;
}

// Main ----------------------------------------------------------------------
@fragment
fn fs_main(
  @location(0) inWorldPos: vec3f,
  @location(1) inNormal: vec3f
) -> @location(0) vec4f {
  let N : vec3f = normalize(inNormal);
  let V : vec3f = normalize(glob.camPos - inWorldPos);

  let roughness = object.roughnessMetallic.x;
  let metallic  = object.roughnessMetallic.y;

  // Specular contribution
  let lightCount: i32 = i32(arrayLength(&lights));
  var Lo : vec3f = vec3(0.0);
  for (var i : i32 = 0; i < lightCount; i++) {
      let light = lights[i];
      let L : vec3f = normalize(light.pos.xyz - inWorldPos);
      Lo += BRDF(L, V, N, metallic, roughness, light.color.rgb);
  };

  // Combine with ambient (seems wrong?)
  var color : vec3f = object.diffuse * 0.02;
  color += Lo;

  // Gamma correct
  color = pow(color, vec3f(0.4545));

  return vec4f(color, 1.0);
}