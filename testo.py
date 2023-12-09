from webgoo import (
    Adapter,
    AdapterProperties,
    BackendType,
    PowerPreference,
    RequestAdapterCallback,
    RequestAdapterStatus,
    createInstance,
    instanceDescriptor,
    requestAdapterOptions,
)

instance = createInstance(instanceDescriptor())

adapter_req = requestAdapterOptions(
    powerPreference=PowerPreference.HighPerformance,
    backendType=BackendType.Undefined,
    forceFallbackAdapter=False,
)

def adapterCB(status: RequestAdapterStatus, adapter: Adapter, msg: str):
    print("Got adapter with msg:", msg)
    props = AdapterProperties()
    adapter.getProperties(props)
    print("Vendor?", props.vendorName)
    print("Backend?", props.backendType)
    print("Architecture?", props.architecture)
    print("Driver desc?", props.driverDescription)
    pass


cb = RequestAdapterCallback(adapterCB)

instance.requestAdapter(adapter_req, cb)
print("Requested?")
