from cas.common.models import BuildEnvironment
from cas.common.buildsys.shared import BaseCompiler

import os
import sys
import logging
from typing import List, Dict
from pathlib import Path

winreg = None
if sys.platform == 'win32':
	import winreg

# JM: todo: this should probably not be hardcoded
MSBUILD_PATH = 'C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/MSBuild/Current/Bin/amd64/MSBuild.exe'

class MSBuildCompiler(BaseCompiler):
    """
    MSBuild compiler, used on Windows
    """
    def __init__(self, env: BuildEnvironment, config: dict):
        self._setup_winsdk()
        super().__init__(env, config)

    def _setup_winsdk(self):
        sdk_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Microsoft SDKs\Windows\v10.0', 0, winreg.KEY_READ)
        sdk_path = winreg.QueryValueEx(sdk_key, 'InstallationFolder')
        sdk_ver = winreg.QueryValueEx(sdk_key, 'ProductVersion')

        winreg.CloseKey(sdk_key)
        self._winsdk_path = os.path.join(sdk_path[0], f'bin\\{sdk_ver[0]}.0\\x64')
    
    def _invoke_msbuild(self, project: str, targets: List[str], parameters: Dict[str, str]) -> bool:
        args = [MSBUILD_PATH, f'{project}.sln']
        args.append('-target:' + ';'.join(targets))
        for k, v in parameters.items():
            args.append(f'/p:{k}={v}')

        logging.debug(f'Running MSBuild with parameters: {args}')
        returncode = self._env.run_tool(args, cwd=self._env.src)
        return returncode == 0

    def _build_default_parameters(self) -> Dict[str, str]:
        params = {}
        if self._env.build_type == 'trunk':
            params['Configuration'] = 'Debug'
        else:
            params['Configuration'] = 'Release'
            params['DebugSymbols'] = 'false'
            params['DebugType'] = 'None'
        return params

    def _build_internal(self, target: str) -> bool:
        params = self._build_default_parameters()
        return self._invoke_msbuild(self._get_project_name(), [target], params)

    def clean(self) -> bool:
        return self._build_internal('Clean')

    def configure(self) -> bool:
        # msbuild doesn't need to do anything
        return True

    def build(self) -> bool:
        return self._build_internal('Build')
