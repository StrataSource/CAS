from cas.common.models import BuildResult, BuildSubsystem, BuildEnvironment
from cas.common.buildsys.msbuild import MSBuildCompiler
from cas.common.buildsys.posix import PosixCompiler
from cas.common.buildsys.vpc import VPCInstance

import cas.common.utilities
import os
import sys
from pathlib import Path


class BuildsysSubsystem(BuildSubsystem):
    def __init__(self, env: BuildEnvironment, config: dict):
        super().__init__(env, config)

        # if a platform isn't specified,
        # default to the 64-bit version of our current platform
        self._platform = config.get("platform")
        if not self._platform:
            self._platform = cas.common.utilities.resolve_platform_name()

        if cas.common.utilities.is_platform_windows():
            self._compiler = MSBuildCompiler(self.env, self.config, self._platform)
        else:
            self._compiler = PosixCompiler(self.env, self.config, self._platform)

    def build(self) -> BuildResult:
        # configure stage (run VPC, build makefiles)
        if self.config.configure:
            # first we need to bootstrap VPC
            self._logger.info("bootstrapping VPC")
            if not self._compiler.bootstrap():
                return BuildResult(False)

            self._logger.info("running VPC")
            vpc = VPCInstance(self.env, self.config, self._platform)
            if not vpc.run() or not self._compiler.configure():
                return BuildResult(False)

        # compile stage (compile dependencies and engine)
        if self.config.compile:
            self._logger.info("compiling")
            if not self._compiler.build():
                return BuildResult(False)

        return BuildResult(True)

    def clean(self) -> bool:
        # clean output files before we delete project files!
        if not self._compiler.clean():
            self._logger.error("Output binary clean failed!")
            return False

        sln_ext = f"{self._platform}.sln"
        proj_ext = f"{self._platform}.vcxproj"
        for root, _, files in os.walk(self.env.src):
            for f in files:
                if (
                    f.endswith(".vpc_crc")
                    or f.endswith(".vpc_cache")
                    or f.endswith(sln_ext)
                    or f.endswith(proj_ext)
                ):
                    Path(root).joinpath(f).unlink()

        return True


_subsystem = BuildsysSubsystem
