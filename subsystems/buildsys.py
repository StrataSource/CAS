from assetbuilder.models import BuildSubsystem

from typing import List
from pathlib import Path

import os
import sys
import subprocess
import hashlib
import logging

BUILD_TYPE_MAP = {
    'trunk': 'CHAOS_TRUNK_BUILD',
    'staging': 'CHAOS_STAGING_BUILD',
    'release': 'CHAOS_REL_BUILD'
}

class VPCArguments:
    def __init__(self, args: List[str], args_raw: List[str], groups: List[str], defines: List[str]):
        self.args = args
        self.raw = args_raw
        self.groups = groups
        self.defines = defines

    def to_string(self) -> str:
        params = []
        for x in self.raw:
            params.append(x)
        for x in self.args:
            params.append(f'/{x}')
        for x in self.groups:
            params.append(f'+{x}')
        for x in self.defines:
            params.append(f'/define:{x}')
        return ' '.join(params)

    def to_list(self) -> List[str]:
        params = []
        for x in self.raw:
            params.append(x)
        for x in self.args:
            params.append(f'/{x}')
        for x in self.groups:
            params.append(f'+{x}')
        for x in self.defines:
            params.append(f'/define:{x}')
        return params


class BuildsysSubsystem(BuildSubsystem):
    def _process_vpc_args(self) -> VPCArguments:
        args = self.config.get('args', [])
        group = self.config.get('group', 'everything')
        defines = self.config.get('defines', [])

        args.append(self.config['project'])
        args.append(self.env.platform)
        args.append(self.config.get('toolchain', '2019'))

        if self.config.get('ide_files', False):
            args.append('clangdb')
            args.append('cmake')
        
        raw = []
        raw.append('/mksln')
        raw.append(f'{group}_{self.env.platform}')
        
        build_type = self.env.build_type
        defines.append(BUILD_TYPE_MAP[build_type])
        
        if build_type == 'trunk':
            defines.append('DEVELOPMENT_ONLY')

        return VPCArguments(args, raw, [group], defines)

    def _build_vpc(self) -> bool:
        args = self._process_vpc_args()
        args = [self.env.get_tool('vpc', self.env.config['path.devtools'].joinpath('bin'))] + args.to_list()
        ret = self.env.run_tool(args, cwd=self.env.src)
        return ret == 0

    def _build_code(self) -> bool:
        return True

    def build(self) -> bool:
        if self.config.get('build_vpc', True) and not self._build_vpc():
            return False
        if self.config.get('build_code', True) and not self._build_code():
            return False
        return True
    
    def clean(self) -> bool:
        sln_ext = f'{self.env.platform}.sln'
        proj_ext = f'{self.env.platform}.vcxproj'
        for root, _, files in os.walk(self.env.src):
            for f in files:
                if (f.endswith('.vpc_crc') or f.endswith('.vpc_cache') 
                or f.endswith(sln_ext) or f.endswith(proj_ext)):
                    Path(root).joinpath(f).unlink()
                
        return True

_subsystem = BuildsysSubsystem
