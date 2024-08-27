"""Simple bindings to the RenderDoc in-application API"""

import sys
from enum import IntEnum, auto
from typing import Any

from cffi import FFI

ffi = FFI()


class RDCaptureOption(IntEnum):
    AllowVSync = 0
    AllowFullscreen = 1
    APIValidation = 2
    DebugDeviceMode = 2  # deprecated name of this enum
    CaptureCallstacks = 3
    CaptureCallstacksOnlyDraws = 4
    CaptureCallstacksOnlyActions = 4
    DelayForDebugger = 5
    VerifyBufferAccess = 6
    VerifyMapWrites = 6  # VerifyBufferAccess
    HookIntoChildren = 7
    RefAllResources = 8
    SaveAllInitials = 9
    CaptureAllCmdLists = 10
    DebugOutputMute = 11
    AllowUnsupportedVendorExtensions = 12
    SoftMemoryLimit = 13


class RDKey(IntEnum):
    # '0' - '9' matches ASCII values
    Digit_0 = 0x30
    Digit_1 = 0x31
    Digit_2 = 0x32
    Digit_3 = 0x33
    Digit_4 = 0x34
    Digit_5 = 0x35
    Digit_6 = 0x36
    Digit_7 = 0x37
    Digit_8 = 0x38
    Digit_9 = 0x39

    # 'A' - 'Z' matches ASCII values
    Char_A = 0x41
    Char_B = 0x42
    Char_C = 0x43
    Char_D = 0x44
    Char_E = 0x45
    Char_F = 0x46
    Char_G = 0x47
    Char_H = 0x48
    Char_I = 0x49
    Char_J = 0x4A
    Char_K = 0x4B
    Char_L = 0x4C
    Char_M = 0x4D
    Char_N = 0x4E
    Char_O = 0x4F
    Char_P = 0x50
    Char_Q = 0x51
    Char_R = 0x52
    Char_S = 0x53
    Char_T = 0x54
    Char_U = 0x55
    Char_V = 0x56
    Char_W = 0x57
    Char_X = 0x58
    Char_Y = 0x59
    Char_Z = 0x5A

    # leave the rest of the ASCII range free
    # in case we want to use it later
    NonPrintable = 0x100

    Divide = auto()
    Multiply = auto()
    Subtract = auto()
    Plus = auto()

    F1 = auto()
    F2 = auto()
    F3 = auto()
    F4 = auto()
    F5 = auto()
    F6 = auto()
    F7 = auto()
    F8 = auto()
    F9 = auto()
    F10 = auto()
    F11 = auto()
    F12 = auto()

    Home = auto()
    End = auto()
    Insert = auto()
    Delete = auto()
    PageUp = auto()
    PageDn = auto()

    Backspace = auto()
    Tab = auto()
    PrtScrn = auto()
    Pause = auto()

    Max = auto()


class RDOverlayBits(IntEnum):
    Overlay_Enabled = 0x1
    Overlay_FrameRate = 0x2
    Overlay_FrameNumber = 0x4
    Overlay_CaptureList = 0x8
    Overlay_Default = 0x1 | 0x2 | 0x4 | 0x8
    Overlay_All = 0xFFFFFFFF
    Overlay_None = 0


def device_ptr_from_vk_instance(inst: Any) -> None:
    """A helper macro for Vulkan, where the device handle cannot be used directly.
    Passing the VkInstance to this function will return the RENDERDOC_DevicePointer to use.

    Specifically, the value needed is the dispatch table pointer, which sits as the first
    pointer-sized object in the memory pointed to by the VkInstance. Thus we cast to a void** and
    indirect once.
    """
    return ffi.cast("void **", inst)[0]  # (*((void **)(inst)))


API_VERSION_1_6_0 = 10600

# /******************************************************************************
#  * The MIT License (MIT)
#  *
#  * Copyright (c) 2019-2023 Baldur Karlsson
#  *
#  * Permission is hereby granted, free of charge, to any person obtaining a copy
#  * of this software and associated documentation files (the "Software"), to deal
#  * in the Software without restriction, including without limitation the rights
#  * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  * copies of the Software, and to permit persons to whom the Software is
#  * furnished to do so, subject to the following conditions:
#  *
#  * The above copyright notice and this permission notice shall be included in
#  * all copies or substantial portions of the Software.
#  *
#  * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#  * THE SOFTWARE.
#  ******************************************************************************/
ffi.cdef(
    """
typedef enum RENDERDOC_CaptureOption {
  eRENDERDOC_Option_AllowVSync = 0,
  eRENDERDOC_Option_AllowFullscreen = 1,
  eRENDERDOC_Option_APIValidation = 2,
  eRENDERDOC_Option_DebugDeviceMode = 2,    // deprecated name of this enum
  eRENDERDOC_Option_CaptureCallstacks = 3,
  eRENDERDOC_Option_CaptureCallstacksOnlyDraws = 4,
  eRENDERDOC_Option_CaptureCallstacksOnlyActions = 4,
  eRENDERDOC_Option_DelayForDebugger = 5,
  eRENDERDOC_Option_VerifyBufferAccess = 6,
  eRENDERDOC_Option_VerifyMapWrites = eRENDERDOC_Option_VerifyBufferAccess,
  eRENDERDOC_Option_HookIntoChildren = 7,
  eRENDERDOC_Option_RefAllResources = 8,
  eRENDERDOC_Option_SaveAllInitials = 9,
  eRENDERDOC_Option_CaptureAllCmdLists = 10,
  eRENDERDOC_Option_DebugOutputMute = 11,
  eRENDERDOC_Option_AllowUnsupportedVendorExtensions = 12,
  eRENDERDOC_Option_SoftMemoryLimit = 13,
} RENDERDOC_CaptureOption;

typedef enum RENDERDOC_InputButton {
  eRENDERDOC_Key_0 = 0x30,
  eRENDERDOC_Key_1 = 0x31,
  eRENDERDOC_Key_2 = 0x32,
  eRENDERDOC_Key_3 = 0x33,
  eRENDERDOC_Key_4 = 0x34,
  eRENDERDOC_Key_5 = 0x35,
  eRENDERDOC_Key_6 = 0x36,
  eRENDERDOC_Key_7 = 0x37,
  eRENDERDOC_Key_8 = 0x38,
  eRENDERDOC_Key_9 = 0x39,
  eRENDERDOC_Key_A = 0x41,
  eRENDERDOC_Key_B = 0x42,
  eRENDERDOC_Key_C = 0x43,
  eRENDERDOC_Key_D = 0x44,
  eRENDERDOC_Key_E = 0x45,
  eRENDERDOC_Key_F = 0x46,
  eRENDERDOC_Key_G = 0x47,
  eRENDERDOC_Key_H = 0x48,
  eRENDERDOC_Key_I = 0x49,
  eRENDERDOC_Key_J = 0x4A,
  eRENDERDOC_Key_K = 0x4B,
  eRENDERDOC_Key_L = 0x4C,
  eRENDERDOC_Key_M = 0x4D,
  eRENDERDOC_Key_N = 0x4E,
  eRENDERDOC_Key_O = 0x4F,
  eRENDERDOC_Key_P = 0x50,
  eRENDERDOC_Key_Q = 0x51,
  eRENDERDOC_Key_R = 0x52,
  eRENDERDOC_Key_S = 0x53,
  eRENDERDOC_Key_T = 0x54,
  eRENDERDOC_Key_U = 0x55,
  eRENDERDOC_Key_V = 0x56,
  eRENDERDOC_Key_W = 0x57,
  eRENDERDOC_Key_X = 0x58,
  eRENDERDOC_Key_Y = 0x59,
  eRENDERDOC_Key_Z = 0x5A,
  eRENDERDOC_Key_NonPrintable = 0x100,
  eRENDERDOC_Key_Divide,
  eRENDERDOC_Key_Multiply,
  eRENDERDOC_Key_Subtract,
  eRENDERDOC_Key_Plus,
  eRENDERDOC_Key_F1,
  eRENDERDOC_Key_F2,
  eRENDERDOC_Key_F3,
  eRENDERDOC_Key_F4,
  eRENDERDOC_Key_F5,
  eRENDERDOC_Key_F6,
  eRENDERDOC_Key_F7,
  eRENDERDOC_Key_F8,
  eRENDERDOC_Key_F9,
  eRENDERDOC_Key_F10,
  eRENDERDOC_Key_F11,
  eRENDERDOC_Key_F12,
  eRENDERDOC_Key_Home,
  eRENDERDOC_Key_End,
  eRENDERDOC_Key_Insert,
  eRENDERDOC_Key_Delete,
  eRENDERDOC_Key_PageUp,
  eRENDERDOC_Key_PageDn,
  eRENDERDOC_Key_Backspace,
  eRENDERDOC_Key_Tab,
  eRENDERDOC_Key_PrtScrn,
  eRENDERDOC_Key_Pause,
  eRENDERDOC_Key_Max,
} RENDERDOC_InputButton;

typedef int( *pRENDERDOC_SetCaptureOptionU32)(RENDERDOC_CaptureOption opt, uint32_t val);
typedef int( *pRENDERDOC_SetCaptureOptionF32)(RENDERDOC_CaptureOption opt, float val);
typedef uint32_t( *pRENDERDOC_GetCaptureOptionU32)(RENDERDOC_CaptureOption opt);
typedef float( *pRENDERDOC_GetCaptureOptionF32)(RENDERDOC_CaptureOption opt);
typedef void( *pRENDERDOC_SetFocusToggleKeys)(RENDERDOC_InputButton *keys, int num);
typedef void( *pRENDERDOC_SetCaptureKeys)(RENDERDOC_InputButton *keys, int num);

typedef enum RENDERDOC_OverlayBits {
  eRENDERDOC_Overlay_Enabled = 0x1,
  eRENDERDOC_Overlay_FrameRate = 0x2,
  eRENDERDOC_Overlay_FrameNumber = 0x4,
  eRENDERDOC_Overlay_CaptureList = 0x8,
  eRENDERDOC_Overlay_Default = 0xf,
  eRENDERDOC_Overlay_All = 0xff,
  eRENDERDOC_Overlay_None = 0,
} RENDERDOC_OverlayBits;

typedef uint32_t( *pRENDERDOC_GetOverlayBits)();
typedef void( *pRENDERDOC_MaskOverlayBits)(uint32_t And, uint32_t Or);
typedef void( *pRENDERDOC_RemoveHooks)();
typedef pRENDERDOC_RemoveHooks pRENDERDOC_Shutdown;
typedef void( *pRENDERDOC_UnloadCrashHandler)();
typedef void( *pRENDERDOC_SetCaptureFilePathTemplate)(const char *pathtemplate);
typedef const char *( *pRENDERDOC_GetCaptureFilePathTemplate)();
typedef pRENDERDOC_SetCaptureFilePathTemplate pRENDERDOC_SetLogFilePathTemplate;
typedef pRENDERDOC_GetCaptureFilePathTemplate pRENDERDOC_GetLogFilePathTemplate;
typedef uint32_t( *pRENDERDOC_GetNumCaptures)();
typedef uint32_t( *pRENDERDOC_GetCapture)(uint32_t idx, char *filename,
                                                      uint32_t *pathlength, uint64_t *timestamp);
typedef void( *pRENDERDOC_SetCaptureFileComments)(const char *filePath,
                                                              const char *comments);
typedef uint32_t( *pRENDERDOC_IsTargetControlConnected)();
typedef pRENDERDOC_IsTargetControlConnected pRENDERDOC_IsRemoteAccessConnected;
typedef uint32_t( *pRENDERDOC_LaunchReplayUI)(uint32_t connectTargetControl,
                                                          const char *cmdline);
typedef void( *pRENDERDOC_GetAPIVersion)(int *major, int *minor, int *patch);
typedef uint32_t( *pRENDERDOC_ShowReplayUI)();

typedef void *RENDERDOC_DevicePointer;
typedef void *RENDERDOC_WindowHandle;

typedef void( *pRENDERDOC_SetActiveWindow)(RENDERDOC_DevicePointer device,
                                                       RENDERDOC_WindowHandle wndHandle);
typedef void( *pRENDERDOC_TriggerCapture)();
typedef void( *pRENDERDOC_TriggerMultiFrameCapture)(uint32_t numFrames);
typedef void( *pRENDERDOC_StartFrameCapture)(RENDERDOC_DevicePointer device,
                                                         RENDERDOC_WindowHandle wndHandle);
typedef uint32_t( *pRENDERDOC_IsFrameCapturing)();
typedef uint32_t( *pRENDERDOC_EndFrameCapture)(RENDERDOC_DevicePointer device,
                                                           RENDERDOC_WindowHandle wndHandle);
typedef uint32_t( *pRENDERDOC_DiscardFrameCapture)(RENDERDOC_DevicePointer device,
                                                               RENDERDOC_WindowHandle wndHandle);
typedef void( *pRENDERDOC_SetCaptureTitle)(const char *title);

typedef enum RENDERDOC_Version
{
  eRENDERDOC_API_Version_1_6_0 = 10600
} RENDERDOC_Version;

typedef struct RENDERDOC_API_1_6_0
{
  pRENDERDOC_GetAPIVersion GetAPIVersion;
  pRENDERDOC_SetCaptureOptionU32 SetCaptureOptionU32;
  pRENDERDOC_SetCaptureOptionF32 SetCaptureOptionF32;
  pRENDERDOC_GetCaptureOptionU32 GetCaptureOptionU32;
  pRENDERDOC_GetCaptureOptionF32 GetCaptureOptionF32;
  pRENDERDOC_SetFocusToggleKeys SetFocusToggleKeys;
  pRENDERDOC_SetCaptureKeys SetCaptureKeys;
  pRENDERDOC_GetOverlayBits GetOverlayBits;
  pRENDERDOC_MaskOverlayBits MaskOverlayBits;

  pRENDERDOC_RemoveHooks RemoveHooks;
  pRENDERDOC_UnloadCrashHandler UnloadCrashHandler;
  pRENDERDOC_SetCaptureFilePathTemplate SetCaptureFilePathTemplate;
  pRENDERDOC_GetCaptureFilePathTemplate GetCaptureFilePathTemplate;

  pRENDERDOC_GetNumCaptures GetNumCaptures;
  pRENDERDOC_GetCapture GetCapture;

  pRENDERDOC_TriggerCapture TriggerCapture;

  pRENDERDOC_IsTargetControlConnected IsTargetControlConnected;
  pRENDERDOC_LaunchReplayUI LaunchReplayUI;

  pRENDERDOC_SetActiveWindow SetActiveWindow;

  pRENDERDOC_StartFrameCapture StartFrameCapture;
  pRENDERDOC_IsFrameCapturing IsFrameCapturing;
  pRENDERDOC_EndFrameCapture EndFrameCapture;

  pRENDERDOC_TriggerMultiFrameCapture TriggerMultiFrameCapture;
  pRENDERDOC_SetCaptureFileComments SetCaptureFileComments;
  pRENDERDOC_DiscardFrameCapture DiscardFrameCapture;
  pRENDERDOC_ShowReplayUI ShowReplayUI;
  pRENDERDOC_SetCaptureTitle SetCaptureTitle;
} RENDERDOC_API_1_6_0;

typedef RENDERDOC_API_1_6_0* RENDERDOC_API_PTR;

// Entrypoint
// Note that renderdoc declares a function pointer type that you're supposed
// to dlsym to get the actual value, but with cffi just pretending it's a
// normal export should work
int RENDERDOC_GetAPI(RENDERDOC_Version version, RENDERDOC_API_1_6_0 **outAPIPointers);
"""
)

# type as Any because typing does not know about cdefs and will complain
api_ptrs: Any = None
try:
    ext = "dll" if sys.platform == "win32" else "so"
    lib: Any = ffi.dlopen(f"renderdoc.{ext}")
    _api_ptrs_array = ffi.new("RENDERDOC_API_PTR[1]")
    happy = lib.RENDERDOC_GetAPI(API_VERSION_1_6_0, _api_ptrs_array)
    assert happy == 1, f"Renderdoc GetAPI failure: {happy}"
    api_ptrs = _api_ptrs_array[0]
except:  # noqa: E722
    print("RenderDoc not loaded or failed to get API")

NOT_AVAILABLE = "Application has not been launched through RenderDoc."


def is_available() -> bool:
    return api_ptrs is not None


def trigger_capture() -> None:
    assert api_ptrs is not None, NOT_AVAILABLE
    api_ptrs.TriggerCapture()


def start_frame_capture() -> None:
    assert api_ptrs is not None, NOT_AVAILABLE
    api_ptrs.StartFrameCapture(ffi.NULL, ffi.NULL)


def end_frame_capture() -> None:
    assert api_ptrs is not None, NOT_AVAILABLE
    api_ptrs.EndFrameCapture(ffi.NULL, ffi.NULL)
