from assetbuilder.models import (
    BuildEnvironment, BuildContext, Asset, BatchedDriver, PrecompileResult
)
from typing import List
from pathlib import Path
import subprocess

EXT_MAP = {
    'kv': 'ekv',
    'nut': 'nuc'
}

class ViceDriver(BatchedDriver):
    """
    Driver that encrypts files with an ICE key using VICE
    """
    def _tool_name(self):
        return 'vice.exe'

    def precompile(self, context: BuildContext, asset: Asset) -> List[str]:
        asset.outpath = asset.path.with_suffix('.ekv')
        return PrecompileResult([asset.path], [asset.outpath])

    def compile_all(self, context: BuildContext, assets: List[Asset]) -> bool:
        key = context.config['options']['key']
        if len(key) != 8:
            raise Exception('ICE key must be exactly 8 characters long')

        args = [self.tool, '-quiet', '-nopause', '-encrypt', key, '-newext', 'ekv']
        for asset in assets:
            args.append(str(asset.path))
        
        result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return result.returncode == 0

_driver = ViceDriver