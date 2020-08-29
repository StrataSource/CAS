from assetbuilder.models import (
    BuildEnvironment, BuildContext, Asset, SerialDriver, PrecompileResult
)
from typing import List, Set
from pathlib import Path
import subprocess
import os

class ModelDriver(SerialDriver):
    def _tool_name(self):
        return 'mdlcompile.exe'

    def _deps_searchline(self, token, line, set):
        line = line.strip()
        i = line.find(token)
        if i == -1:
            return
        s1 = line.rfind('"', 0, i) + 1
        s2 = line.find('"', i)

        # exclusions
        if '$includemodel' in line:
            return

        path = line[s1:s2]
        set.append(path)
    
    def _parse_deps_from_vdf(self, path: Path):
        """
        Walks a QC/MC VDF file and extracts the input and output paths.
        """
        inputs = []
        outputs = []

        # parse the qc/mc and extract dependent paths
        with open(str(path), 'r') as f:
            qc = f.readlines()
        
        for line in qc:
            self._deps_searchline('smd', line, inputs)
            self._deps_searchline('mdl', line, outputs)
        
        return set(inputs), set(outputs)

    def _convert_relpaths(self, root: Path, paths: Set[Path]) -> Set[Path]:
        result = set()
        for path in paths:
            result.add(root.joinpath(path))
        return result

    def precompile(self, context: BuildContext, asset: Asset) -> List[str]:
        # TODO: move gamedir to build context so we don't have to do this jank-ass stuff here?
        dest_root = Path(os.path.join(self.env.root, self.env.game))
        gamedir = os.path.relpath(asset.path.parent, os.path.join(self.env.root, self.env.content))
        gamedir = gamedir.replace('\\', '/').split('/')[0]

        inputs, outputs = self._parse_deps_from_vdf(asset.path)
        inputs = self._convert_relpaths(asset.path.parent, inputs)
        outputs = self._convert_relpaths(dest_root.joinpath(gamedir, 'models'), outputs)

        extra = set()
        for f in outputs:
            # also add a .dx90.vtx and .vvd for every .mdl
            if f.suffix == '.mdl':
                extra.add(f.with_suffix('.dx90.vtx'))
                extra.add(f.with_suffix('.vvd'))

        inputs.add(asset.path)
        return PrecompileResult(inputs, outputs | extra)

    def compile(self, context: BuildContext, asset: Asset) -> bool:
        args = [self.tool, str(asset.path)]

        returncode = self.env.run_tool(args)
        return returncode == 0

_driver = ModelDriver