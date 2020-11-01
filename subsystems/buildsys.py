from cas.common.models import BuildResult, BuildSubsystem, BuildEnvironment
from cas.common.buildsys.msbuild import MSBuildCompiler
from cas.common.buildsys.posix import PosixCompiler
from cas.common.buildsys.vpc import VPCInstance

import os
import sys
import logging
from typing import List, Dict
from pathlib import Path

class BuildsysSubsystem(BuildSubsystem):
    def __init__(self, env: BuildEnvironment, config: dict):
        super().__init__(env, config)
        if sys.platform == 'win32':
            self._compiler = MSBuildCompiler(self.env, self.config.windows)
        else:
            self._compiler = PosixCompiler(self.env, self.config.posix)

    def build(self) -> BuildResult:
        # force clean for staging/release
        if self.env.build_type != 'trunk' and not self._compiler.clean():
            logging.error('Mandatory clean for staging/release builds failed!')
            return BuildResult(False)

        # configure stage (run VPC, build makefiles)
        if self.config.configure:
            vpc = VPCInstance(self.env, self.config.vpc, self.config.solution)
            if not vpc.run() or not self._compiler.configure():
                return BuildResult(False)
        
        # compile stage (compile dependencies and engine)
        if self.config.compile:
            if not self._compiler.build():
                return BuildResult(False)

        return BuildResult(True)
    
    def clean(self) -> bool:
        # clean output files before we delete project files!
        if not self._compiler.clean():
            logging.error('Output binary clean failed!')
            return False

        sln_ext = f'{self.env.platform}.sln'
        proj_ext = f'{self.env.platform}.vcxproj'
        for root, _, files in os.walk(self.env.src):
            for f in files:
                if (f.endswith('.vpc_crc') or f.endswith('.vpc_cache') 
                or f.endswith(sln_ext) or f.endswith(proj_ext)):
                    Path(root).joinpath(f).unlink()
                
        return True

_subsystem = BuildsysSubsystem
