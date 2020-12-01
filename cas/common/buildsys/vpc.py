import logging
import itertools
import cas.common.utilities as utilities
from cas.common.models import BuildEnvironment
from cas.common.config import LazyDynamicDotMap
from cas.common.cache import FileCache

import sys
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

        self._cache = self._env.cache.vpc
        self._file_cache = FileCache(self._env.cache, self._cache.files)
        self._logger = logging.getLogger(__name__)

    def _list_all_vpcs(self) -> list:
        return itertools.chain(
            self._env.src.rglob("*.vpc"), self._env.src.rglob("*.vgc")
        )

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

    def _clear_crc_files(self):
        # Don't do this on Windows, it's an unnecessary slowdown
        if sys.platform == "win32":
            return
        crc_files = self._env.src.rglob("*.vpc_crc")
        for f in crc_files:
            f.unlink()

    def _verify_argument_hash(self, args: List) -> bool:
        old_hash = self._cache.get("args", None)
        new_hash = utilities.hash_object_sha256(args)
        self._cache["args"] = new_hash

        if not old_hash:
            return False
        return old_hash == new_hash

    def run(self) -> bool:
        args = self._process_vpc_args()
        rebuild = False  # do we need to rebuild?

        # hash the arguments
        if not self._verify_argument_hash(args.to_list()):
            rebuild = True

        # hash the VPC files
        vpc_files = self._list_all_vpcs()
        for f in vpc_files:
            if not self._file_cache.validate(f):
                self._file_cache.put(f)
                rebuild = True

        if rebuild:
            self._file_cache.garbage_collect()
            self._env.cache.save()
            self._clear_crc_files()

        if not rebuild:
            self._logger.info("scripts are unchanged, not running VPC")
            return True

        args = [
            self._env.get_tool("vpc", self._env.config.path.devtools.joinpath("bin"))
        ] + args.to_list()
        ret = self._env.run_tool(args, cwd=self._env.src)

        # ensure cache is invalidated if vpc fails
        if not ret == 0:
            self._env.cache.vpc = {}
            self._env.cache.save()
            return False
        return True
