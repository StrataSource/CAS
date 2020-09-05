import os
import sys
import pathlib
import functools
import struct


def paths_to_relative(root, paths):
    out = []
    for path in paths:
        out.append(os.path.relpath(path, root))
    return out


def resolve_platform_name():
    plat = sys.platform
    arch = struct.calcsize('P') * 8
    assert arch in [32, 64]

    if plat == 'win32':
        plat = 'win'
    elif plat.startswith('darwin'):
        plat = 'osx'
    elif plat.startswith('linux'):
        pass
    else:
        raise Exception(f'Unsupported platform {plat}')
    return f'{plat}{str(arch)}'


def set_dot_notation(target: dict, key: str, value):
    keys = key.split('.')
    pre = target
    pre_k = None
    last = target
    for key in keys:
        pre = last
        last = last[key]
        pre_k = key
    pre[pre_k] = value
