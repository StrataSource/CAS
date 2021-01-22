from cas.common.models import BuildResult, BuildSubsystem
from pathlib import Path

import cas.common.utilities
import sys
import getpass


class SteamworksSubsystem(BuildSubsystem):
    """
    Subsystem that pushes app depots to Steamworks using the content builder.
    App and depot configurations are generated on the fly
    """

    def _get_credentials(self):
        user = self.config.username
        pwd = self.config.password
        if not user or not pwd:
            print("Enter Steamworks Credentials")
            if not user:
                user = input("Username: ")
            if not pwd:
                pwd = getpass.getpass(prompt="Password: ")
        return user, pwd

    def _run_steamcmd(self) -> bool:
        tool_dir = Path(self.config.tooldir).resolve()
        tool_path = None

        if cas.common.utilities.is_platform_windows():
            tool_path = tool_dir.joinpath("builder", "steamcmd.exe")
        elif cas.common.utilities.is_platform_osx():
            tool_path = tool_dir.joinpath("builder_osx", "steamcmd.sh")
        elif cas.common.utilities.is_platform_linux():
            tool_path = tool_dir.joinpath("builder_linux", "steamcmd.sh")
        else:
            raise NotImplementedError(f"unsupported platform {sys.platform}")

        script_cmd = []
        for script in self.config.scripts:
            script_file = tool_dir.joinpath("scripts", f"app_build_{script}.vdf")
            if not script_file.exists():
                self._logger.error(
                    f'Unable to find SteamCMD script at "{script_file}"!'
                )
                return False
            script_cmd.append("+run_app_build_http")
            script_cmd.append(script_file)

        user, pwd = self._get_credentials()
        args = [tool_path, "+login", user, pwd] + script_cmd + ["+quit"]
        ret = self.env.run_tool(args, cwd=self.env.src)
        return ret == 0

    def build(self) -> BuildResult:
        return BuildResult(self._run_steamcmd())

    def clean(self) -> bool:
        return True


_subsystem = SteamworksSubsystem
