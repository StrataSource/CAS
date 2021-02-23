from cas.common.assets.models import (
    Asset,
    AssetBuildContext,
    SerialDriver,
    PrecompileResult,
)

from typing import List, Set
from pathlib import Path
import os


class ModelDriver(SerialDriver):
    """
    Driver that handles compiling studio model files
    with either mdlcompile or studiomdl
    """

    def _tool_name(self):
        return "mdlcompile"

    def _deps_searchline(self, token, line, set):
        line = line.strip()
        i = line.find(token)
        if i == -1:
            return
        s1 = line.rfind('"', 0, i) + 1
        s2 = line.find('"', i)

        path = line[s1:s2]
        set.append(path)

    def _parse_deps_from_vdf(self, path: Path):
        """
        Walks a QC/MC VDF file and extracts the input and output paths.
        """
        inputs = []
        outputs = []

        # parse the qc/mc and extract dependent paths
        with open(str(path), "r") as f:
            qc = f.readlines()

        for line in qc:
            # exclude comments and specific strings
            if line.startswith("//"):
                continue
            if "$includemodel" in line:
                continue
            self._deps_searchline("smd", line, inputs)
            self._deps_searchline("mdl", line, outputs)

        return set(inputs), set(outputs)

    def _convert_relpaths(self, root: Path, paths: Set[Path]) -> Set[Path]:
        result = set()
        for path in paths:
            result.add(root.joinpath(path))
        return result

    def precompile(self, context: AssetBuildContext, asset: Asset) -> List[str]:
        # TODO: perhaps we should have another way of doing this rather than jankily "autodetecting" the dest
        gamedir = os.path.relpath(asset.path.parent, self.env.root)
        gamedir = gamedir.replace("\\", "/").split("/")[1]

        inputs, outputs = self._parse_deps_from_vdf(asset.path)
        inputs = self._convert_relpaths(asset.path.parent, inputs)
        outputs = self._convert_relpaths(
            self.env.game.joinpath(gamedir, "models"), outputs
        )

        extra = set()
        for f in outputs:
            # also add a .dx90.vtx and .vvd for every .mdl
            if f.suffix == ".mdl":
                extra.add(f.with_suffix(".dx90.vtx"))
                extra.add(f.with_suffix(".vvd"))

        inputs.add(asset.path)
        return PrecompileResult(inputs, outputs | extra)

    def compile(self, context: AssetBuildContext, asset: Asset) -> bool:
        args = [str(self.tool), str(asset.path)]

        returncode = self.env.run_tool(args, source=True)
        return returncode == 0


_driver = ModelDriver
