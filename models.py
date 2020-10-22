import assetbuilder.utilities as utilities
from assetbuilder.common.steamtools import SteamInstance, SteamApp
from assetbuilder.config import ConfigurationManager

from typing import List, Set
from pathlib import Path
import os
import sys
import uuid
import json
import logging
import subprocess
import pprint


class BuildEnvironment():
    """
    Contains attributes about the current build environment
    """
    def __init__(self, path: str, config: dict):
        self.config = ConfigurationManager(path, config)

        self.build_type = self.config['args.build_type']
        self.build_categories = None

        categories = self.config['args.build_categories']
        if categories:
            categories = categories.split(',')
            self.build_categories = frozenset(categories)

        self.verbose = self.config['args.verbose']
        
        self.root = self.config['path.root']
        self.content = self.config['path.content']
        self.game = self.config['path.game']
        self.src = self.config['path.src']

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
        if not self.bindir.exists():
            logging.debug('appid autodetect skipped - could not find bindir')
            return False
        elif self.get_tool('chaos').exists():
            logging.debug('appid autodetect skipped - chaos executable exists')
            return False
        elif not self.get_tool('modwrapper').exists():
            logging.debug('appid autodetect skipped - modwrapper executable not found')
            return False
        return True

    def _setup_bindir(self):
        self.bindir = self.game.joinpath('bin', self.platform)
        override = self.config['defaults'].get('bin_path')

        # we have a bin path override
        if override is not None:
            self.bindir = Path(override).joinpath(self.platform)
        # we're a mod (modwrapper present but no game executable) - autodetect bin path from appid
        elif self._check_autodetect_appid():
            appid = self.config['defaults'].get('bin_appid')
            if appid is not None:
                logging.debug(f'mod detected - using base appid {appid}')
                self.bindir = self._get_appid_folder(int(appid)).joinpath('bin', self.platform)

        if not self.bindir.exists():
            raise Exception('Could not find the bin directory')

        logging.debug(f'using bin directory {self.bindir}')

    """
    Retrieves the absolute path to the tool at the specified source path.
    If the source path is None, it will default to self.bindir.
    """
    def get_tool(self, tool: str, src: Path = None) -> Path:
        if src is None:
            src = self.bindir
        assert not tool.endswith('.exe')
        if sys.platform == 'win32':
            tool += '.exe'
        return src.joinpath(tool).resolve()

    def get_lib(self, lib: str) -> Path:
        if sys.platform == 'win32':
            lib += '.dll'
        elif sys.platform == 'darwin':
            lib += '.dylib'
        elif sys.platform == 'linux':
            lib += '.so'
        else:
            raise NotImplementedError()
        return self.bindir.joinpath(lib).resolve()

    def run_tool(self, *args, **kwargs) -> int:
        predef = {}
        if not self.verbose:
            predef['stdout'] = subprocess.DEVNULL
        predef['stderr'] = subprocess.STDOUT
        
        predef['env'] = os.environ
        predef['env']['VPROJECT'] = str(self.config['path.vproject'])
        
        try:
            result = subprocess.run(*args, **dict(predef, **kwargs))
        except Exception as e:
            raise Exception(f'failed to execute tool with parameters: {args}') from e
        return result.returncode


class AssetBuildContext():
    """
    A collection of assets with shared configuration
    """
    def __init__(self, config: dict):
        self.assets = []
        self.buildable = []
        self.config = config


class BuildResult():
    """
    Represents a result returned from a subsystem
    """
    def __init__(self, success: bool, outputs: dict = {}):
        self.success = success
        self.outputs = outputs


class BuildSubsystem():
    """
    Represents a build system that implements custom behaviour.
    """
    def __init__(self, env: BuildEnvironment, config: dict):
        self.env = env
        self.config = config
    
    def build(self) -> BuildResult:
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


class PrecompileResult():
    def __init__(self, inputs: Set[Path], outputs: Set[Path]):
        self.inputs = inputs
        self.outputs = outputs


class Asset():
    """
    Represents an asset to be compiled
    """
    def __init__(self, path: Path, config: dict):
        self.id = uuid.uuid4()
        self.path = path
        self.config = config
    
    def get_id(self):
        """
        Returns the unique identifier for this asset
        """
        return self.id


class BaseDriver():
    """
    Represents an instance of a tool that compiles assets
    """
    def __init__(self, env: BuildEnvironment, config: dict):
        
        self.env = env
        self.config = config
        self.tool = str(self.env.get_tool(self._tool_name()))

    def _tool_name(self):
        raise NotImplementedError()
    
    def precompile(self, context: AssetBuildContext, asset: Asset) -> PrecompileResult:
        """
        Checks to ensure all required files are present
        Returns a list of source and output files to be hashed, or None if failure
        """
        raise NotImplementedError()


class SerialDriver(BaseDriver):
    def compile(self, context: AssetBuildContext, asset: Asset) -> bool:
        """
        Performs the compile
        Returns True if success, otherwise False.
        """
        raise NotImplementedError()


class BatchedDriver(BaseDriver):
    def compile_all(self, context: AssetBuildContext, assets: List[Asset]) -> bool:
        """
        Performs the compile
        Returns True if success, otherwise False.
        """
        raise NotImplementedError()
