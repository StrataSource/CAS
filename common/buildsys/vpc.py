from cas.common.models import BuildEnvironment
from cas.common.config import LazyDynamicDotMap

from typing import List

BUILD_TYPE_MAP = {
    "trunk": "CHAOS_TRUNK_BUILD",
    "staging": "CHAOS_STAGING_BUILD",
    "release": "CHAOS_REL_BUILD",
}


class VPCArguments:
    def __init__(
        self,
        args: List[str],
        args_raw: List[str],
        groups: List[str],
        defines: List[str],
    ):
        self.args = args
        self.raw = args_raw
        self.groups = groups
        self.defines = defines

    def to_string(self) -> str:
        params = []
        for x in self.raw:
            params.append(x)
        for x in self.args:
            params.append(f"/{x}")
        for x in self.groups:
            params.append(f"+{x}")
        for x in self.defines:
            params.append(f"/define:{x}")
        return " ".join(params)

    def to_list(self) -> List[str]:
        params = []
        for x in self.raw:
            params.append(x)
        for x in self.args:
            params.append(f"/{x}")
        for x in self.groups:
            params.append(f"+{x}")
        for x in self.defines:
            params.append(f"/define:{x}")
        return params


class VPCInstance:
    def __init__(self, env: BuildEnvironment, config: LazyDynamicDotMap, solution: str):
        self._env = env
        self._config = config
        self._solution = solution
        self._group = self._config.group

    def _process_vpc_args(self) -> VPCArguments:
        args = list(self._config.args)
        defines = list(self._config.defines)

        args.append(self._solution)
        args.append(self._env.platform)
        args.append(self._config.windows.toolchain)

        if self._config.ide_files:
            args.append("clangdb")
            args.append("cmake")

        raw = []
        raw.append("/mksln")
        raw.append(f"{self._group}_{self._env.platform}")

        build_type = self._env.build_type
        defines.append(BUILD_TYPE_MAP[build_type])

        if build_type == "trunk":
            defines.append("DEVELOPMENT_ONLY")

        return VPCArguments(args, raw, [self._group], defines)

    def run(self) -> bool:
        args = self._process_vpc_args()
        args = [
            self._env.get_tool("vpc", self._env.config.path.devtools.joinpath("bin"))
        ] + args.to_list()
        ret = self._env.run_tool(args, cwd=self._env.src)
        return ret == 0
