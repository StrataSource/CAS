from cas.common.assets.models import (
    Asset,
    AssetBuildContext,
    SerialDriver,
    PrecompileResult,
)

from typing import List


class CaptionDriver(SerialDriver):
    """
    Driver that handles compiling closed captions
    """

    def _tool_name(self):
        return "captioncompiler"

    def precompile(self, context: AssetBuildContext, asset: Asset) -> List[str]:
        asset.outpath = asset.path.with_suffix(".dat")
        return PrecompileResult([asset.path], [asset.outpath])

    def compile(self, context: AssetBuildContext, asset: Asset) -> bool:
        args = [str(self.tool), str(asset.path)]

        returncode = self.env.run_tool(args, source=True)
        return returncode == 0


_driver = CaptionDriver
