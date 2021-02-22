import cas.common.utilities as utilities

import json
import os
from pathlib import Path
from typing import Mapping

from dotmap import DotMap


class CacheManager:
    def __init__(self, root: Path):
        self._root = root
        self._file = root.joinpath("content", ".cas_cache.json")
        self._caches = DotMap()

    def load(self):
        if os.path.exists(self._file):
            with open(self._file, "r") as f:
                self._caches = DotMap(json.loads(f.read()))

    def save(self):
        with open(self._file, "w") as f:
            f.write(json.dumps(self._caches.toDict()))

    def __getitem__(self, key):
        if key not in self._caches:
            self._caches[key] = DotMap()
        return self._caches[key]

    def __setitem__(self, key, value):
        self._caches[key] = value


class FileCache:
    """
    Implements a cache of file hashes relative to the root of the cache manager
    """

    def __init__(self, manager: CacheManager, cache: Mapping):
        self._manager = manager
        self._cache = cache

    def garbage_collect(self):
        # garbage collect paths that no longer exist
        self._cache = {
            k: v
            for k, v in self._cache.items()
            if self._manager._root.joinpath(k).exists()
        }

    def validate(self, path: Path):
        if not path.exists():
            return False
        rel = path.relative_to(self._manager._root)
        hash = self._cache.get(str(rel))
        if not hash:
            return False
        return hash == utilities.hash_file_sha256(path)

    def put(self, path: Path):
        if not path.exists():
            raise Exception(
                f'Tried to insert the path "{str(path)}" into the cache, which does not exist!'
            )
        rel = path.relative_to(self._manager._root)
        self._cache[str(rel)] = utilities.hash_file_sha256(path)

    def clear(self):
        self._cache.clear()
