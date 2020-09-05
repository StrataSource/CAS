from assetbuilder.models import BuildSubsystem
from typing import List
from pathlib import Path
from dirsync import sync

import os
import subprocess
import hashlib
import logging

class SyncFolderSubsystem(BuildSubsystem):
    def build(self) -> bool:
        from_dir = self.env.root.joinpath(self.config['from']).resolve()
        to_dir = self.env.root.joinpath(self.config['to']).resolve()

        sync(from_dir, to_dir, 'sync', purge = True, verbose = self.env.verbose)

        return True

    def clean(self) -> bool:
        return True

_subsystem = SyncFolderSubsystem
