import os
import sys
import json
import hashlib
import struct
import logging

import tqdm

from pathlib import Path
from dotmap import DotMap
from typing import List, Mapping, Any


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
        except Exception:
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
        exclusion = path.startswith("!")
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
            inp = "!" + inp
        result.append(inp)
    return result


def rglob_invert(patterns: List[str]) -> List[str]:
    """
    Inverts a rglob condition.
    """
    result = []
    for pattern in patterns:
        if pattern.startswith("!"):
            result.append(pattern[1:])
        else:
            assert "!" not in pattern
            result.append("!" + pattern)
    return result


def rglob_multi(root: Path, patterns: List[str]) -> List[Path]:
    """
    Advanced recursive glob of a path collapsing multiple include/exclude patterns.
    """
    files = []
    for pattern in patterns:
        # patterns starting with ! are treated as exclusions
        exclusion = pattern.startswith("!")
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


def paths_to_relative(root, paths) -> List:
    out = []
    for path in paths:
        out.append(os.path.relpath(path, root))
    return out


def hash_file_sha256(path: Path) -> str:
    hash = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            hash.update(data)
    return hash.hexdigest()


def hash_object_sha256(obj: Any) -> str:
    # DotMap must be converted to dict before serialisation
    if isinstance(obj, DotMap):
        obj = obj.toDict()

    data = json.dumps(obj, sort_keys=True)
    hash = hashlib.sha256()
    hash.update(data.encode())

    return hash.hexdigest()


def resolve_platform_name() -> str:
    plat = sys.platform
    arch = struct.calcsize("P") * 8
    assert arch in [32, 64]

    if plat == "win32" or plat.startswith("msys") or plat.startswith("cygwin"):
        plat = "win"
    elif plat.startswith("freebsd"):
        plat = "freebsd"
    elif plat.startswith("openbsd"):
        plat = "openbsd"
    elif plat.startswith("darwin"):
        plat = "osx"
    elif plat.startswith("linux"):
        pass
    else:
        raise Exception(f"Unsupported platform {plat}")
    return f"{plat}{str(arch)}"


# Simply resolves the OS name, doesn't care about the actual arch
# Possible returns: win, osx, linux, freebsd, openbsd
def resolve_os_name() -> str:
    plat = sys.platform
    if plat == "win32" or plat.startswith("msys") or plat.startswith("cygwin"):
        plat = "win"
    elif plat.startswith("freebsd"):
        plat = "freebsd"
    elif plat.startswith("openbsd"):
        plat = "openbsd"
    elif plat.startswith("darwin"):
        plat = "osx"
    elif plat.startswith("linux"):
        plat = "linux"
    return plat


def is_platform_windows() -> bool:
    plat = sys.platform
    if plat == "win32" or plat.startswith("msys") or plat.startswith("cygwin"):
        return True
    return False


def is_platform_linux() -> bool:
    return sys.platform.startswith("linux")


def is_platform_osx() -> bool:
    return sys.platform.startswith("osx")


def get_dotpath_value(key: str, mapping: Mapping) -> Any:
    keys = key.split(".")
    current = mapping
    for k in keys:
        if k not in current:
            raise KeyError(k)
        current = current[k]
        if k != keys[-1] and not isinstance(current, Mapping):
            raise KeyError(k)
    return current


def set_dot_notation(target: dict, key: str, value):
    keys = key.split(".")
    pre = target
    pre_k = None
    last = target
    for key in keys:
        pre = last
        last = last[key]
        pre_k = key
    pre[pre_k] = value


def map_to_envvars(envvars: Mapping) -> Mapping[str, str]:
    result = {}
    for k, v in envvars.items():
        if isinstance(v, bool):
            result[k] = "1" if v else "0"
        else:
            result[k] = str(v)
    return result
