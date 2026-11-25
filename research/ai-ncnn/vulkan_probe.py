"""Can this machine run the ncnn-vulkan engines? (research prototype, not wired in)

Talks to the Vulkan loader through ctypes - no SDK, no Python packages - and
prints one JSON line: loader found, instance created, every physical device
(name, type, vendor, API version, device-local memory, compute queue) and a
verdict for the planned AI module:

    ok        a hardware GPU with a compute queue (discrete preferred)
    software  only a CPU implementation (llvmpipe / SwiftShader): too slow for clips
    no-device the loader works but reports no usable GPU
    no-vulkan the loader is missing or the driver refuses an instance

The planned player runs this in a child process with a timeout, so a broken
driver can only fail the probe, never the player. A successful probe is still
followed by a real 64x64 self-test of the engine after download.
"""
from __future__ import annotations

import ctypes
import json
import os
import struct
import sys

TYPES = {0: 'other', 1: 'integrated', 2: 'discrete', 3: 'virtual', 4: 'cpu'}
VENDORS = {0x1002: 'AMD', 0x1010: 'ImgTec', 0x10DE: 'NVIDIA', 0x13B5: 'ARM', 0x5143: 'Qualcomm',
           0x8086: 'Intel', 0x106B: 'Apple', 0x10005: 'Mesa'}
RANK = {'discrete': 0, 'integrated': 1, 'virtual': 2, 'other': 3, 'cpu': 4}
VK_API_1_0 = 1 << 22
c_handle = ctypes.c_void_p


class AppInfo(ctypes.Structure):
    _fields_ = [('sType', ctypes.c_int32), ('pNext', ctypes.c_void_p), ('pApplicationName', ctypes.c_char_p),
                ('applicationVersion', ctypes.c_uint32), ('pEngineName', ctypes.c_char_p),
                ('engineVersion', ctypes.c_uint32), ('apiVersion', ctypes.c_uint32)]


class InstanceInfo(ctypes.Structure):
    _fields_ = [('sType', ctypes.c_int32), ('pNext', ctypes.c_void_p), ('flags', ctypes.c_uint32),
                ('pApplicationInfo', ctypes.POINTER(AppInfo)), ('enabledLayerCount', ctypes.c_uint32),
                ('ppEnabledLayerNames', ctypes.c_void_p), ('enabledExtensionCount', ctypes.c_uint32),
                ('ppEnabledExtensionNames', ctypes.c_void_p)]


def loader_names():
    if os.name == 'nt':
        return ['vulkan-1.dll']
    if sys.platform == 'darwin':
        return ['libvulkan.1.dylib', 'libMoltenVK.dylib']
    return ['libvulkan.so.1', 'libvulkan.so']


def api(v):
    return '%d.%d.%d' % ((v >> 22) & 0x7F, (v >> 12) & 0x3FF, v & 0xFFF)


def _device(lib, dev, index):
    props = ctypes.create_string_buffer(4096)            # VkPhysicalDeviceProperties is 824 bytes
    lib.vkGetPhysicalDeviceProperties(dev, props)
    api_v, driver, vendor, device_id, kind = struct.unpack_from('<IIIIi', props.raw, 0)
    name = props.raw[20:276].split(b'\0', 1)[0].decode('utf-8', 'replace')
    mem = ctypes.create_string_buffer(1024)              # VkPhysicalDeviceMemoryProperties is 520 bytes
    lib.vkGetPhysicalDeviceMemoryProperties(dev, mem)
    (heaps,) = struct.unpack_from('<I', mem.raw, 260)
    local = sum(size for size, flags in (struct.unpack_from('<QI', mem.raw, 264 + 16 * i) for i in range(min(heaps, 16)))
                if flags & 1)                             # VK_MEMORY_HEAP_DEVICE_LOCAL_BIT
    count = ctypes.c_uint32(0)
    lib.vkGetPhysicalDeviceQueueFamilyProperties(dev, ctypes.byref(count), None)
    fams = ctypes.create_string_buffer(24 * max(1, count.value))
    lib.vkGetPhysicalDeviceQueueFamilyProperties(dev, ctypes.byref(count), fams)
    compute = any(struct.unpack_from('<I', fams.raw, 24 * i)[0] & 2 for i in range(count.value))
    return {'index': index, 'name': name, 'type': TYPES.get(kind, 'other'),
            'vendor': VENDORS.get(vendor, '0x%04x' % vendor), 'api': api(api_v), 'driver': driver,
            'device_id': device_id, 'local_mb': local >> 20, 'compute': bool(compute)}


def probe():
    out = {'loader': None, 'instance': False, 'devices': [], 'best': None, 'verdict': 'no-vulkan', 'error': ''}
    lib = None
    for name in loader_names():
        try:
            lib = ctypes.CDLL(name)
            out['loader'] = name
            break
        except OSError:
            continue
    if lib is None:
        out['error'] = 'Vulkan loader not found: the GPU driver has no Vulkan support or is not installed'
        return out
    lib.vkCreateInstance.restype = ctypes.c_int32
    lib.vkCreateInstance.argtypes = [ctypes.POINTER(InstanceInfo), ctypes.c_void_p, ctypes.POINTER(c_handle)]
    lib.vkEnumeratePhysicalDevices.restype = ctypes.c_int32
    lib.vkEnumeratePhysicalDevices.argtypes = [c_handle, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    lib.vkGetPhysicalDeviceProperties.argtypes = [c_handle, ctypes.c_void_p]
    lib.vkGetPhysicalDeviceMemoryProperties.argtypes = [c_handle, ctypes.c_void_p]
    lib.vkGetPhysicalDeviceQueueFamilyProperties.argtypes = [c_handle, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    lib.vkDestroyInstance.argtypes = [c_handle, ctypes.c_void_p]
    app = AppInfo(0, None, b'Kryonyx Music probe', 1, b'kryonyx', 1, VK_API_1_0)
    info = InstanceInfo(1, None, 0, ctypes.pointer(app), 0, None, 0, None)
    inst = c_handle()
    res = lib.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(inst))
    if res != 0:
        out['error'] = 'vkCreateInstance failed (VkResult %d): no working Vulkan driver' % res
        return out
    out['instance'] = True
    try:
        n = ctypes.c_uint32(0)
        res = lib.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), None)
        handles = (c_handle * max(1, n.value))()
        if res == 0 and n.value:
            res = lib.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), handles)
        if res not in (0, 5):                            # VK_INCOMPLETE is fine
            out['error'] = 'vkEnumeratePhysicalDevices failed (VkResult %d)' % res
        out['devices'] = [_device(lib, handles[i], i) for i in range(n.value if res in (0, 5) else 0)]
    finally:
        lib.vkDestroyInstance(inst, None)
    usable = sorted((d for d in out['devices'] if d['compute']), key=lambda d: (RANK[d['type']], -d['local_mb']))
    if usable:
        out['best'] = usable[0]['index']
        out['verdict'] = 'software' if usable[0]['type'] == 'cpu' else 'ok'
    else:
        out['verdict'] = 'no-device'
        out['error'] = out['error'] or 'Vulkan works but no GPU with a compute queue was found'
    return out


if __name__ == '__main__':
    print(json.dumps(probe(), ensure_ascii=False))
