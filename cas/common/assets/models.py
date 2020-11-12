from cas.common.models import BuildEnvironment

import uuid
from pathlib import Path
from typing import List, Set


class PrecompileResult:
    def __init__(self, inputs: Set[Path], outputs: Set[Path]):
        self.inputs = inputs
        self.outputs = outputs


class AssetBuildContext:
    """
    A collection of assets with shared configuration
    """

    def __init__(self, config: dict):
        self.assets = []
        self.config = config


class Asset:
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


class BaseDriver:
    """
    Represents an instance of a tool that compiles assets
    """

    def __init__(self, env: BuildEnvironment):
        self.env = env
        self.tool = str(self.env.get_tool(self._tool_name()))

    def _tool_name(self):
        raise NotImplementedError()

    def threadable(self) -> bool:
        """
        Whether this driver is capable of running asynchronously or not
        """
        return True

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
