import cas.common.utilities as utilities
from cas.common.steamtools import SteamInstance
from cas.common.config import ConfigurationUtilities, LazyDynamicBase
from cas.common.cache import CacheManager

from pathlib import Path
from typing import Any, List, Union
import os
import logging
import subprocess


class BuildEnvironment:
    """
    Contains attributes about the current build environment
    """

    def __init__(self, path: str, config: dict):
        self.config = ConfigurationUtilities.parse_root_config(path, config)

        self.cache = CacheManager(path)
        self.cache.load()

        self.build_type = self.config.args.build_type
        self.build_categories = None

        categories = self.config.args.build_categories
        if categories:
            categories = categories.split(",")
            self.build_categories = frozenset(categories)

        self.verbose = self.config.args.verbose

        self.root = self.config.path.root
        self.content = self.config.path.content
        self.game = self.config.path.game
        self.src = self.config.path.src

        self.platform = utilities.resolve_platform_name()
        self.steam = None

        self._setup_bindir()

    def _get_appid_folder(self, appid: int) -> Path:
        if not self.steam:
            self.steam = SteamInstance()
        for app in self.steam.apps:
            if app.appid == appid:
                return app.path
        return None

    def _check_autodetect_appid(self) -> bool:
        if self.src.exists():
            logging.debug("appid autodetect skipped - src dir exists")
            return False
        elif self.get_tool("chaos").exists():
            logging.debug("appid autodetect skipped - chaos executable exists")
            return False

        return True

    def _setup_bindir(self):
        self.bindir = self.game.joinpath("bin", self.platform)
        override = self.config.options.get("bin_path")

        # we have a bin path override
        if override is not None:
            self.bindir = Path(override).joinpath(self.platform)
        # we're a mod (modwrapper present but no game executable) - autodetect bin path from appid
        elif self._check_autodetect_appid():
            appid = self.config.options.get("bin_appid")
            if appid is not None:
                logging.debug(f"mod detected - using base appid {str(appid)}")
                self.bindir = self._get_appid_folder(appid).joinpath(
                    "bin", self.platform
                )

        if not self.bindir.exists():
            raise Exception("Could not find the bin directory")

        logging.debug(f"using bin directory {self.bindir}")

    """
    Retrieves the absolute path to the tool at the specified source path.
    If the source path is None, it will default to self.bindir.
    """

    def get_tool(self, tool: str, src: Path = None) -> Path:
        if src is None:
            src = self.bindir
        assert not tool.endswith(".exe")
        if utilities.is_platform_windows():
            tool += ".exe"
        return src.joinpath(tool).resolve()

    def get_lib(self, lib: str) -> Path:
        if utilities.is_platform_windows():
            lib += ".dll"
        elif utilities.is_platform_osx():
            lib += ".dylib"
        elif utilities.is_platform_linux():
            lib += ".so"
        else:
            raise NotImplementedError()
        return self.bindir.joinpath(lib).resolve()

    def run_subprocess(self, *args, **kwargs):
        predef = {}
        if not self.verbose:
            predef["stdout"] = subprocess.DEVNULL
            predef["stderr"] = subprocess.DEVNULL
        return subprocess.run(*args, **dict(predef, **kwargs))

    def run_tool(
        self, args: List[str], source: bool = False, cwd: Union[str, Path] = None
    ) -> int:
        """
        High-level interface to run an executable with extra parameters
        """
        predef = {}
        predef["env"] = os.environ

        if source:
            predef["env"]["VPROJECT"] = str(self.config.path.vproject)
            predef["env"]["NOASSERT"] = "1"
        if cwd:
            predef["cwd"] = cwd

        try:
            result = self.run_subprocess(args, **predef)
        except Exception as e:
            raise Exception(f"failed to execute tool with parameters: {args}") from e
        return result.returncode


class BuildResult:
    """
    Represents a result returned from a subsystem
    """

    def __init__(self, success: bool, outputs: dict = {}):
        self.success = success
        self.outputs = outputs


class BuildSubsystem:
    """
    Represents a build system that implements custom behaviour.
    """

    def __init__(self, env: BuildEnvironment, config: dict):
        mod = self.__class__.__module__

        self.env = env
        self.config = config
        self._cache = env.cache["subsystems"][mod]
        self._logger = logging.getLogger(mod)

    def _get_config_raw(self) -> Any:
        # If we have a lazy config object then we need to extract its underlying raw data
        if isinstance(self.config, LazyDynamicBase):
            return self.config._data
        else:
            return self.config

    def needs_rebuild(self) -> bool:
        """
        Checks whether this subsystem needs to force a rebuild,
        based on whether its configuration hash has changed from the last successful build
        """
        old_hash = self._cache.get("config", None)
        new_hash = utilities.hash_object_sha256(self._get_config_raw())
        self._cache["config"] = new_hash

        if not old_hash:
            return False
        return old_hash != new_hash

    def rehash_config(self):
        """
        Rehashes the configuration and saves it in our cache
        """
        self._cache["config"] = utilities.hash_object_sha256(self._get_config_raw())

    def build(self, force: bool = False) -> BuildResult:
        """
        Invokes the build logic of the subsystem.
        Returns a BuildResult with the result.
        """
        raise NotImplementedError()

    def clean(self) -> bool:
        """
        Removes all the output files generated by this subsystem.
        """
        raise NotImplementedError()
