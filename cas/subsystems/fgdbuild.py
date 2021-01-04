from cas.common.models import BuildResult, BuildSubsystem
from pathlib import Path

import sys
import shutil
import importlib.util
import contextlib


class FGDBuildSubsystem(BuildSubsystem):
    """
    Subsystem that builds FGDs and Hammer assets from HammerAddons
    """

    def build(self) -> BuildResult:
        project = self.env.config.options.project

        srcpath = Path(self.env.root).joinpath(self.config.source).resolve()
        destpath = Path(self.env.root).joinpath(self.config.dest).resolve()

        spec = importlib.util.spec_from_file_location(
            "hammeraddons.unifyfgd", srcpath.joinpath("unify_fgd.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        build_dest = srcpath.joinpath("build")
        if not build_dest.exists():
            build_dest.mkdir()

        outfile = build_dest.joinpath(f"{project}.fgd")

        # redirect our output so logs aren't spammed on non-verbose mode
        log_dev = sys.stdout if self.env.verbose else None
        with contextlib.redirect_stdout(log_dev):
            mod.action_export(
                srcpath.joinpath("fgd"),
                None,
                frozenset({"SRCTOOLS", self.config.branch}),
                outfile,
                False,
                False,
            )

        hammer_dir = destpath.joinpath("hammer")

        shutil.copy(outfile, hammer_dir.joinpath("cfg", f"{project}.fgd"))
        
        self.override_folder(srcpath.joinpath("hammer", "materials"), hammer_dir.joinpath("materials"))
        self.override_folder(srcpath.joinpath("hammer", "models"), hammer_dir.joinpath("models"))
        self.override_folder(srcpath.joinpath("hammer", "scripts"), hammer_dir.joinpath("scripts"))

        return BuildResult(True)

    def clean(self) -> bool:
        return True

    def override_folder(self, src, dest):
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)


_subsystem = FGDBuildSubsystem
