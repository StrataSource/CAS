from assetbuilder.models import BuildResult, BuildSubsystem
from typing import List
from pathlib import Path

import os
import sys
import subprocess
import hashlib
import logging
import getpass



class SteamworksSubsystem(BuildSubsystem):
    """
    Subsystem that pushes app depots to Steamworks using the content builder.
    App and depot configurations are generated on the fly
    """
    def _get_credentials(self):
        user = self.config.get('username')
        pwd = self.config.get('password')
        if not user or not pwd:
            print('Enter Steamworks Credentials')
            if not user:
                user = input('Username: ')
            if not pwd:
                pwd = getpass.getpass(prompt='Password: ')
        return user, pwd

    def _run_steamcmd(self) -> bool:
        tool_dir = Path(self.config['tooldir']).resolve()

        if sys.platform == 'win32':
            tool_path = tool_dir.joinpath('builder', 'steamcmd.exe')
        elif sys.platform == 'darwin':
            tool_path = tool_dir.joinpath('builder_osx', 'steamcmd.sh')
        elif sys.platform == 'linux':
            tool_path = tool_dir.joinpath('builder_linux', 'steamcmd.sh')
        else:
            raise NotImplementedError(f'unsupported platform {sys.platform}')
        
        appid = self.config['appid']

        script = tool_dir.joinpath('scripts', f'app_build_{appid}.vdf')
        if not script.exists():
            logging.error(f'Unable to find SteamCMD script at \"{script}\"!')
            return False

        user, pwd = self._get_credentials()
        args = [tool_path, '+login', user, pwd, '+run_app_build_http', script, '+quit']
        ret = self.env.run_tool(args, cwd=self.env.src)
        return ret == 0

    def build(self) -> BuildResult:
        return BuildResult(self._run_steamcmd())
    
    def clean(self) -> bool:
        return True

_subsystem = SteamworksSubsystem
