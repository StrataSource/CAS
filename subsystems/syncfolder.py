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
        from_dir = Path(self.env.root).joinpath(self.config['from']).resolve()
        to_dir = Path(self.env.root).joinpath(self.config['to']).resolve()

        verbose_log = 'verbose' in self.config.keys() and self.config['verbose'].casefold() == 'true'

        print(from_dir)
        print(to_dir)

        sync(from_dir, to_dir, 'sync', purge = True, verbose = verbose_log)

        return True

    def clean(self) -> bool:
        return True

_subsystem = SyncFolderSubsystem
