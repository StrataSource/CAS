import os
import sys
import zlib
import pathlib
import hashlib
import functools
import struct
import logging

import tqdm

from pathlib import Path
from typing import List

class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


def relative_paths(root: Path, paths: list) -> List[str]:
    """
    Normalises paths from incoming configuration and ensures
    they are all strings relative to root
    """
    result = []
    for path in paths:
        # more hacks for exclusions I'm not happy about
        # maybe we should subclass Path to make this cleaner?
        exclusion = path.startswith('!')
        if exclusion:
            path = path[1:]

        # make sure paths are relative!
        if isinstance(path, Path):
            inp = str(path.relative_to(root))
        elif isinstance(path, str):
            inp = path
            if os.path.isabs(path):
                inp = os.path.relpath(path, root)
        else:
            raise NotImplementedError()

        if exclusion:
            inp = '!' + inp
        result.append(inp)
    return result


def rglob_invert(patterns: List[str]) -> List[str]:
    """
    Inverts a rglob condition.
    """
    result = []
    for pattern in patterns:
        if pattern.startswith('!'):
            result.append(pattern[1:])
        else:
            assert '!' not in pattern
            result.append('!' + pattern)
    return result


def rglob_multi(root: Path, patterns: List[str]) -> List[Path]:
    """
    Advanced recursive glob of a path collapsing multiple include/exclude patterns.
    """
    files = []
    for pattern in patterns:
        # patterns starting with ! are treated as exclusions
        exclusion = pattern.startswith('!')
        if exclusion:
            pattern = pattern[1:]

        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            if exclusion:
                if path in files:
                    files.remove(path)
            else:
                if path in files:
                    continue
                files.append(path)

    return files


def paths_to_relative(root, paths):
    out = []
    for path in paths:
        out.append(os.path.relpath(path, root))
    return out


def hash_file_sha256(path: Path):
    hash = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            hash.update(data)
    return hash.hexdigest()


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
