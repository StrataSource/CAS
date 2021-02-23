from cas.common.models import BuildEnvironment
from cas.common.buildsys.shared import BaseCompiler
import cas.common.utilities as utilities

import os
from typing import List, Dict

winreg = None
if utilities.is_platform_windows():
    import winreg

# JM: todo: this should probably not be hardcoded
MSBUILD_PATH = "C:/Program Files (x86)/Microsoft Visual Studio/2019/Community/MSBuild/Current/Bin/amd64/MSBuild.exe"


class MSBuildCompiler(BaseCompiler):
    """
    MSBuild compiler, used on Windows
    """

    def __init__(self, env: BuildEnvironment, config: dict, platform: str):
        super().__init__(env, config.windows, platform)
        self._solution = f"{config.solution}_{config.group}_{platform}.sln"
        self._project = config.get("project")

        self._build_type = config.type
        self._setup_winsdk()

    def _setup_winsdk(self):
        sdk_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Microsoft SDKs\Windows\v10.0",
            0,
            winreg.KEY_READ,
        )
        sdk_path = winreg.QueryValueEx(sdk_key, "InstallationFolder")
        sdk_ver = winreg.QueryValueEx(sdk_key, "ProductVersion")

        winreg.CloseKey(sdk_key)
        self._winsdk_path = os.path.join(sdk_path[0], f"bin\\{sdk_ver[0]}.0\\x64")

    def _invoke_msbuild(self, targets: List[str], parameters: Dict[str, str]) -> bool:
        args = [MSBUILD_PATH, self._solution]
        args.append("-target:" + ";".join(targets))
        for k, v in parameters.items():
            args.append(f"/p:{k}={v}")

        self._logger.debug(f"Running MSBuild with parameters: {args}")
        returncode = self._env.run_tool(args, cwd=self._env.src)
        return returncode == 0

    def _build_default_parameters(self) -> Dict[str, str]:
        params = {}
        if self._config.type == "debug":
            params["Configuration"] = "Debug"
        else:
            params["Configuration"] = "Release"
            params["DebugSymbols"] = "false"
            params["DebugType"] = "None"
        return params

    def _build_internal(self, target: str) -> bool:
        params = self._build_default_parameters()
        if self._project:
            target = f"{self._project}:{target}"
        return self._invoke_msbuild([target], params)

    def clean(self) -> bool:
        return self._build_internal("Clean")

    def configure(self) -> bool:
        # msbuild doesn't need to do anything
        return True

    def build(self) -> bool:
        return self._build_internal("Build")
