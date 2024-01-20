import xgpu as xg


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
