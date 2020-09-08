from assetbuilder.models import (
    BuildEnvironment, Asset, AssetBuildContext, SerialDriver, PrecompileResult
)
from typing import List, Set
from pathlib import Path
import subprocess
import os

class CaptionDriver(SerialDriver):
    """
    Driver that handles compiling closed captions
    """
    def _tool_name(self):
        return 'captioncompiler'

    def precompile(self, context: AssetBuildContext, asset: Asset) -> List[str]:
        asset.outpath = asset.path.with_suffix('.dat')
        return PrecompileResult([asset.path], [asset.outpath])

    def compile(self, context: AssetBuildContext, asset: Asset) -> bool:
        args = [self.tool, str(asset.path)]

        returncode = self.env.run_tool(args)
        return returncode == 0

_driver = CaptionDriver