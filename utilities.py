import os
import sys
import pathlib

def paths_to_relative(root, paths):
    out = []
    for path in paths:
        out.append(os.path.relpath(path, root))
    return out

def get_platform_bindir():
    plat = sys.platform

    if plat == 'win32':
        return 'win64'
    elif plat.startswith('darwin'):
        return 'osx64'
    elif plat.startswith('linux'):
        return 'linux64'
    else:
        raise Exception(f'Unsupported platform {plat}')
