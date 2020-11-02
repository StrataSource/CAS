import logging
from cas.common.models import BuildEnvironment
from cas.common.config import LazyDynamicDotMap
from cas.common.cache import FileCache

import json
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
    def __init__(self, env: BuildEnvironment, config: LazyDynamicDotMap, platform: str):
        self._env = env
        self._config = config.vpc
        self._solution = config.solution
        self._group = config.group
        self._platform = platform
        self._cache = FileCache(self._env.cache, "vpc")
        self._logger = logging.getLogger(__name__)

    def _requires_rebuild(self) -> bool:
        # build a list of all VPC scripts in the project
        for f in self._env.src.rglob("*.vpc"):
            if not self._env.cache.validate(f):
                return True
            return

    def _process_vpc_args(self) -> VPCArguments:
        args = list(self._config.args)
        defines = list(self._config.defines)

        args.append(self._solution)
        args.append(self._platform)
        args.append(self._config.windows.toolchain)

        if self._config.ide_files:
            args.append("clangdb")
            args.append("cmake")

        raw = []
        raw.append("/mksln")
        raw.append(f"{self._solution}_{self._group}_{self._platform}")

        build_type = self._env.build_type
        defines.append(BUILD_TYPE_MAP[build_type])

        if build_type == "trunk":
            defines.append("DEVELOPMENT_ONLY")

        return VPCArguments(args, raw, [self._group], defines)

    def run(self) -> bool:
        # hash the VPC files and see if we need to rebuild
        rebuild = False
        vpc_files = self._env.src.rglob("*.vpc")
        for f in vpc_files:
            if not self._cache.validate(f):
                self._cache.put(f)
                rebuild = True
        if rebuild:
            self._cache.save()

        if not rebuild:
            self._logger.info("scripts are unchanged, not running VPC")
            return True

        args = self._process_vpc_args()
        args = [
            self._env.get_tool("vpc", self._env.config.path.devtools.joinpath("bin"))
        ] + args.to_list()
        ret = self._env.run_tool(args, cwd=self._env.src)
        return ret == 0
