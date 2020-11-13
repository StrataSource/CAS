from cas.common.models import BuildResult, BuildSubsystem
from pathlib import Path

import cas.common.utilities as utilities

import os
import shutil


def _shutil_delete_force(action, name, exc):
    os.chmod(name, os.path.stat.S_IWRITE)
    os.remove(name)


class SyncFolderSubsystem(BuildSubsystem):
    def build(self) -> BuildResult:
        from_dir = Path(self.config["from"]).resolve()
        to_dir = Path(self.config.to).resolve()

        if self.config.clobber and to_dir.exists():
            shutil.rmtree(to_dir, onerror=_shutil_delete_force)

        if not to_dir.exists():
            to_dir.mkdir()

        files = utilities.rglob_multi(from_dir, self.config.files)
        self._logger.debug(f"{len(files)} file(s) to copy")

        for src in files:
            src = src.resolve()
            dest = to_dir.joinpath(src.relative_to(from_dir))
            os.makedirs(dest.parent, exist_ok=True)
            shutil.copy(src, dest)

        return BuildResult(True)

    def clean(self) -> bool:
        to_dir = Path(self.config.to).resolve()
        if to_dir.exists():
            shutil.rmtree(to_dir, onerror=_shutil_delete_force)
        return True


_subsystem = SyncFolderSubsystem
