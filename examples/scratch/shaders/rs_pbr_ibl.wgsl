// Ported from:
// https://github.com/samdauwe/webgpu-native-examples/blob/master/src/examples/pbr_ibl.c
// Apache 2 license

struct UBO {
  @align(16) projection : mat4x4<f32>,
  @align(16) model : mat4x4<f32>,
  @align(16) view : mat4x4<f32>,
  @align(16) camPos : vec3<f32>,
  @align(16) camParams: vec2<f32>, // exposure, gamma
};

struct Output {
  @builtin(position) position : vec4<f32>,
  @location(0) worldPos : vec3<f32>,
  @location(1) normal : vec3<f32>,
  @location(2) uv : vec2<f32>,
};

@vertex
fn main(
  @location(0) inPos: vec3<f32>,
  @location(1) inNormal: vec3<f32>,
  @location(2) inUV: vec2<f32>
) -> Output {
  var output: Output;
  let locPos : vec3<f32> = (ubo.model * vec4<f32>(inPos, 1.0)).xyz;
  output.worldPos = locPos + object.objPos;
  output.normal = mat3x3(
      ubo.model[0].xyz,
      ubo.model[1].xyz,
      ubo.model[2].xyz,
    ) * inNormal;
  output.uv = inUV;
  output.uv.y = 1.0 - inUV.y;
  output.position = ubo.projection * ubo.view * vec4<f32>(output.worldPos, 1.0);
  return output;
}

struct MaterialParams {
  @align(16) rms: vec3f; // roughness, metallic, specular
  @align(16) rgb: vec3f;
};

@group(0) @binding(0) var<uniform> ubo : UBO;
@group(0) @binding(1) var<uniform> material : MaterialParams;
@group(0) @binding(2) var textureIrradiance: texture_cube<f32>;
@group(0) @binding(3) var samplerIrradiance: sampler;
@group(0) @binding(4) var textureBRDFLUT: texture_2d<f32>;
@group(0) @binding(5) var samplerBRDFLUT: sampler;
@group(0) @binding(6) var texturePrefilteredMap: texture_cube<f32>;
@group(0) @binding(7) var samplerPrefilteredMap: sampler;

const PI = 3.1415926535897932384626433832795;

fn ALBEDO() -> vec3f {
  return vec3<f32>(material.r, material.g, material.b);
}

// From http://filmicgames.com/archives/75
fn Uncharted2Tonemap(x : vec3<f32>) -> vec3f {
  let A : f32 = 0.15;
  let B : f32 = 0.50;
  let C : f32 = 0.10;
  let D : f32 = 0.20;
  let E : f32 = 0.02;
  let F : f32 = 0.30;
  return ((x*(A*x+C*B)+D*E)/(x*(A*x+B)+D*F))-E/F;
}

// Normal Distribution function ----------------------------------------------
fn D_GGX(dotNH : f32, roughness : f32) -> f32 {
  let alpha : f32 = roughness * roughness;
  let alpha2 : f32 = alpha * alpha;
  let denom : f32 = dotNH * dotNH * (alpha2 - 1.0) + 1.0;
  return (alpha2)/(PI * denom*denom);
}

// Geometric Shadowing function ----------------------------------------------
fn G_SchlicksmithGGX(dotNL : f32, dotNV : f32, roughness : f32) -> f32 {
  let r : f32 = (roughness + 1.0);
  let k : f32 = (r*r) / 8.0;
  let GL : f32 = dotNL / (dotNL * (1.0 - k) + k);
  let GV : f32 = dotNV / (dotNV * (1.0 - k) + k);
  return GL * GV;
}

// Fresnel function ----------------------------------------------------------
fn F_Schlick(cosTheta : f32, F0 : vec3<f32>) -> vec3f {
  return F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
}

fn F_SchlickR(cosTheta : f32, F0 : vec3<f32>, roughness : f32) -> vec3f {
  return F0 + (max(vec3(1.0 - roughness), F0) - F0) * pow(1.0 - cosTheta, 5.0);
}

fn prefilteredReflection(R : vec3<f32>, roughness : f32) -> vec3f {
  let MAX_REFLECTION_LOD : f32 = 9.0; // todo: param/const
  let lod : f32 = roughness * MAX_REFLECTION_LOD;
  let lodf : f32 = floor(lod);
  let lodc : f32 = ceil(lod);
  let a : vec3<f32> = textureSampleLevel(texturePrefilteredMap, samplerPrefilteredMap, R, lodf).rgb;
  let b : vec3<f32> = textureSampleLevel(texturePrefilteredMap, samplerPrefilteredMap, R, lodc).rgb;
  return mix(a, b, lod - lodf);
}

fn specularContribution(L : vec3<f32>, V : vec3<f32>, N : vec3<f32>, F0 : vec3<f32>,
                        metallic : f32, roughness : f32) -> vec3f {
  // Precalculate vectors and dot products
  let H : vec3<f32> = normalize(V + L);
  let dotNH : f32 = clamp(dot(N, H), 0.0, 1.0);
  let dotNV : f32 = clamp(dot(N, V), 0.0, 1.0);
  let dotNL : f32 = clamp(dot(N, L), 0.0, 1.0);

  // Light color fixed
  let lightColor : vec3<f32> = vec3(1.0);

  var color : vec3<f32> = vec3(0.0);

  if (dotNL > 0.0) {
    // D = Normal distribution (Distribution of the microfacets)
    let D : f32 = D_GGX(dotNH, roughness);
    // G = Geometric shadowing term (Microfacets shadowing)
    let G : f32 = G_SchlicksmithGGX(dotNL, dotNV, roughness);
    // F = Fresnel factor (Reflectance depending on angle of incidence)
    let F : vec3<f32> = F_Schlick(dotNV, F0);
    let spec : vec3<f32> = D * F * G / (4.0 * dotNL * dotNV + 0.001);
    let kD : vec3<f32> = (vec3<f32>(1.0) - F) * (1.0 - metallic);
    color += (kD * ALBEDO() / PI + spec) * dotNL;
  }

  return color;
}

@fragment
fn main(
  @location(0) inWorldPos: vec3<f32>,
  @location(1) inNormal: vec3<f32>,
  @location(2) inUV: vec2<f32>
) -> @location(0) vec4<f32> {
  let N : vec3<f32> = normalize(inNormal);
  let V : vec3<f32> = normalize(ubo.camPos - inWorldPos);
  let R : vec3<f32> = reflect(-V, N);

  let metallic : f32 = material.metallic;
  let roughness : f32 = material.roughness;

  var F0 : vec3<f32> = vec3(0.04);
  F0 = mix(F0, ALBEDO(), metallic);

  var Lo : vec3<f32> = vec3(0.0);
  for (var i : u32 = 0; i < LIGHTS_ARRAY_LENGTH; i++) {
    let L : vec3<f32> = normalize(uboParams.lights[i].xyz - inWorldPos);
    Lo += specularContribution(L, V, N, F0, metallic, roughness);
  }

  let brdf : vec2<f32> = textureSample(textureBRDFLUT, samplerBRDFLUT, vec2<f32>(max(dot(N, V), 0.0), roughness)).rg;
  let reflection : vec3<f32> = prefilteredReflection(R, roughness).rgb;
  let irradiance : vec3<f32> = textureSample(textureIrradiance, samplerIrradiance, N).rgb;

  // Diffuse based on irradiance
  let diffuse : vec3<f32> = irradiance * ALBEDO();

  let F : vec3<f32> = F_SchlickR(max(dot(N, V), 0.0), F0, roughness);

  // Specular reflectance
  let specular : vec3<f32> = reflection * (F * brdf.x + brdf.y);

  // Ambient part
  var kD : vec3<f32> = 1.0 - F;
  kD *= 1.0 - metallic;
  let ambient : vec3<f32> = (kD * diffuse + specular);

  var color : vec3<f32> = ambient + Lo;

  // Tone mapping
  color = Uncharted2Tonemap(color * uboParams.exposure);
  color = color * (1.0f / Uncharted2Tonemap(vec3<f32>(11.2f)));
  // Gamma correction
  color = pow(color, vec3<f32>(1.0f / uboParams.gamma));

  return vec4<f32>(color, 1.0);
}

struct UBO {
  projection : mat4x4<f32>,
  model : mat4x4<f32>,
  view : mat4x4<f32>,
  camPos : vec3<f32>,
};

@group(0) @binding(0) var<uniform> ubo : UBO;

struct Output {
  @builtin(position) position : vec4<f32>,
  @location(0) outUVW : vec3<f32>
};

@vertex
fn main(
  @location(0) inPos: vec3<f32>,
  @location(1) inNormal: vec3<f32>,
  @location(2) inUV: vec2<f32>
) -> Output {
  var output: Output;
  output.outUVW = inPos;
  output.position = ubo.projection * ubo.model * vec4<f32>(inPos.xyz, 1.0);
  return output;
}
);
