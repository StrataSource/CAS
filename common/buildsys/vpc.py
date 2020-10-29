from assetbuilder.models import BuildEnvironment
from assetbuilder.config import LazyDynamicDotMap

import os
import sys
import subprocess
from typing import List, Dict
from pathlib import Path

BUILD_TYPE_MAP = {
    'trunk': 'CHAOS_TRUNK_BUILD',
    'staging': 'CHAOS_STAGING_BUILD',
    'release': 'CHAOS_REL_BUILD'
}


class VPCArguments():
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


class VPCInstance():
    def __init__(self, env: BuildEnvironment, config: LazyDynamicDotMap, project: str):
        self._env = env
        self._config = config
        self._project = project
        self._group = self._config.get('group', 'everything')

    def _process_vpc_args(self) -> VPCArguments:
        args = self._config.get('args', [])
        defines = self._config.get('defines', [])

        windows_args = self._config.get('windows', {})
        posix_args = self._config.get('posix', {})

        args.append(self._project)
        args.append(self._env.platform)
        args.append(windows_args.get('toolchain', '2019'))

        if self._config.get('ide_files', False):
            args.append('clangdb')
            args.append('cmake')
        
        raw = []
        raw.append('/mksln')
        raw.append(f'{self._group}_{self._env.platform}')
        
        build_type = self._env.build_type
        defines.append(BUILD_TYPE_MAP[build_type])

        if build_type == 'trunk':
            defines.append('DEVELOPMENT_ONLY')

        return VPCArguments(args, raw, [self._group], defines)

    def run(self) -> bool:
        args = self._process_vpc_args()
        args = [self._env.get_tool('vpc', self._env.config.path.devtools.joinpath('bin'))] + args.to_list()
        ret = self._env.run_tool(args, cwd=self._env.src)
        return ret == 0
