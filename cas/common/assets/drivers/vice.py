from cas.common.assets.models import (
    Asset,
    AssetBuildContext,
    BatchedDriver,
    PrecompileResult,
)

from typing import List

EXT_MAP = {"kv": "ekv", "nut": "nuc"}


class ViceDriver(BatchedDriver):
    """
    Driver that encrypts files with an ICE key using VICE
    """

    def _tool_name(self):
        return "vice"

    def precompile(self, context: AssetBuildContext, asset: Asset) -> List[str]:
        asset.outpath = asset.path.with_suffix(".ekv")
        return PrecompileResult([asset.path], [asset.outpath])

    def compile_all(self, context: AssetBuildContext, assets: List[Asset]) -> bool:
        key = context.config.options.key
        if len(key) != 8:
            raise Exception("ICE key must be exactly 8 characters long")

        args = [str(self.tool), "-quiet", "-nopause", "-encrypt", key, "-newext", "ekv"]
        for asset in assets:
            args.append(str(asset.path))

        result = self.env.run_tool(args, source=True)
        return result == 0


_driver = ViceDriver
