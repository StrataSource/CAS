import assetbuilder.utilities as utilities
from assetbuilder.models import BuildEnvironment

import hashlib
import json
import os
from pathlib import Path

class AssetCache():
    """
    Implements a cache of asset file hashes
    """
    def __init__(self, path: Path):
        self.path = path
        self.file = path.joinpath(path, 'content', '.assets_c.json')
        self.hashes = {}

    def load(self):
        if os.path.exists(self.file):
            with open(self.file, 'r') as f:
                self.hashes = json.loads(f.read())

    def save(self):
        with open(self.file, 'w') as f:
            f.write(json.dumps(self.hashes))

    def validate(self, path: Path):
        if not path.exists():
            return False
        rel = path.relative_to(self.path)
        hash = self.hashes.get(str(rel))
        if not hash:
            return False
        return hash == utilities.hash_file_sha256(path)

    def put(self, path: Path):
        if not path.exists():
            raise Exception(f'Tried to insert the path \"{str(path)}\" into the cache, which does not exist!')
        rel = path.relative_to(self.path)
        self.hashes[str(rel)] = utilities.hash_file_sha256(path)
