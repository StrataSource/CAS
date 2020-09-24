from assetbuilder.models import BuildResult, BuildSubsystem, BuildEnvironment

from typing import List, Dict
from pathlib import Path

import os
import sys
import subprocess
import hashlib
import logging
if sys.platform == 'win32':
	import winreg

BUILD_TYPE_MAP = {
    'trunk': 'CHAOS_TRUNK_BUILD',
    'staging': 'CHAOS_STAGING_BUILD',
    'release': 'CHAOS_REL_BUILD'
}

# JM: todo: this should probably not be hardcoded
MSBUILD_PATH = 'C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/MSBuild/Current/Bin/amd64/MSBuild.exe'

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


class BaseCompiler():
    """
    Base compiler class from which all compilers should extend.
    """
    def __init__(self, env: BuildEnvironment):
        self.env = env

    def clean(self, project: str):
        """
        Removes all output files of the project.
        """
        raise NotImplementedError()

    def build(self, project: str):
        """
        Compiles the project.
        """
        raise NotImplementedError()


class MSBuildCompiler(BaseCompiler):
    """
    MSBuild compiler, used on Windows
    """
    def __init__(self, env: BuildEnvironment):
        self._setup_winsdk()
        super().__init__(env)

    def _setup_winsdk(self):
        sdk_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Microsoft SDKs\Windows\v10.0', 0, winreg.KEY_READ)
        sdk_path = winreg.QueryValueEx(sdk_key, 'InstallationFolder')
        sdk_ver = winreg.QueryValueEx(sdk_key, 'ProductVersion')

        winreg.CloseKey(sdk_key)
        self.winsdk_path = os.path.join(sdk_path[0], f'bin\\{sdk_ver[0]}.0\\x64')
    
    def _invoke_msbuild(self, project: str, targets: List[str], parameters: Dict[str, str]) -> bool:
        args = [MSBUILD_PATH, f'{project}.sln']
        args.append('-target:' + ';'.join(targets))
        for k, v in parameters.items():
            args.append(f'/p:{k}={v}')

        logging.debug(f'Running MSBuild with parameters: {args}')
        returncode = self.env.run_tool(args, cwd=self.env.src)
        return returncode == 0

    def _build_default_parameters(self) -> Dict[str, str]:
        params = {}
        if self.env.build_type == 'trunk':
            params['Configuration'] = 'Debug'
        else:
            params['Configuration'] = 'Release'
            params['DebugSymbols'] = 'false'
            params['DebugType'] = 'None'
        return params

    def _build_internal(self, project: str, target: str) -> bool:
        params = self._build_default_parameters()
        return self._invoke_msbuild(project, [target], params)

    def clean(self, project: str) -> bool:
        return self._build_internal(project, 'Clean')

    def build(self, project: str) -> bool:
        return self._build_internal(project, 'Build')


class BuildsysSubsystem(BuildSubsystem):
    def _get_project_name(self) -> str:
        group = self.config.get('group', 'everything')
        return f'{group}_{self.env.platform}'

    def _get_platform_compiler(self) -> BaseCompiler:
        if sys.platform == 'win32':
            return MSBuildCompiler(self.env)
        else:
            raise NotImplementedError()

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
        raw.append(self._get_project_name())
        
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
        compiler = self._get_platform_compiler()

        # force clean for staging/release
        if self.env.build_type != 'trunk' and not compiler.clean(self._get_project_name()):
            logging.error('Mandatory clean for staging/release builds failed!')
            return False
        
        return compiler.build(self._get_project_name())

    def build(self) -> BuildResult:
        if self.config.get('build_vpc', True):
            if not self._build_vpc():
                return BuildResult(False)
        if self.config.get('build_code', False):
            if not self._build_code():
                return BuildResult(False)
        return BuildResult(True)
    
    def clean(self) -> bool:
        # clean output files before we delete project files!
        compiler = self._get_platform_compiler()
        if not compiler.clean(self._get_project_name()):
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
