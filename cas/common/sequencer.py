from cas.common.models import BuildEnvironment, BuildSubsystem
from cas.common.config import DataResolverScope

from pathlib import Path
from typing import Mapping

import importlib
import logging


class Sequencer:
    """
    Class that executes a number of discrete programs (subsystems) in order.
    """

    def __init__(self, path: Path, config: dict):
        self.env = BuildEnvironment(path, config)

        self._args = self.env.config.args
        self._subsystems: Mapping[str, BuildSubsystem] = {}
        self._logger = logging.getLogger(__name__)

    def _load_subsystem(self, name: str, module: str, config: dict) -> BuildSubsystem:
        subsystem = self._subsystems.get(name)
        if subsystem is not None:
            return

        mod = importlib.import_module(module)
        if mod is None:
            raise Exception(f"Failed to load subsystem {mod}")
        self._logger.debug(f"loaded '{module}' subsystem")

        subsystem = mod._subsystem(self.env, config)
        self._subsystems[name] = subsystem

    def _run_subsystem(self, scope: DataResolverScope, name: str) -> bool:
        if self._args.dry_run:
            return True

        # get the unresolved configuration first to run checks
        subsystem = self.env.config.subsystems.get(name)
        if not subsystem:
            return True

        build_types = subsystem.get("build_types")
        if build_types and self.env.build_type not in build_types:
            self._logger.debug(f"subsystem {name} skipped (build type mismatch)")
            return True

        categories = subsystem.get("categories")
        if (
            self.env.build_categories
            and categories
            and len(self.env.build_categories.intersection(set(categories))) == 0
        ):
            self._logger.debug(f"subsystem {name} skipped (category mismatch)")
            return True

        # get the full configuration
        subsystem = subsystem.with_scope(scope)
        self._load_subsystem(name, subsystem.module, subsystem.get("options", {}))

        # run
        sys = self._subsystems[name]
        force = self._args.force or sys.needs_rebuild()

        self._logger.info(f"running subsystem {name}")
        if self._args.clean:
            if not sys.clean():
                return False
        else:
            result = sys.build(force)
            scope._data.subsystems[name] = result
            if not result.success:
                return False

        sys.rehash_config()
        return True

    def run(self) -> bool:
        # build whitelist/blacklist
        whitelist = self._args.include_subsystems
        blacklist = self._args.exclude_subsystems
        if whitelist:
            whitelist = whitelist.split(",")
        if blacklist:
            blacklist = blacklist.split(",")

        # create the scope
        scope = DataResolverScope()

        # run subsystems
        for sub in self.env.config.subsystems.keys():
            if whitelist and sub not in whitelist:
                self._logger.debug(f"subsystem {sub} skipped (not whitelisted)")
                continue
            if blacklist and sub in blacklist:
                self._logger.debug(f"subsystem {sub} skipped (blacklisted)")
                continue
            if not self._run_subsystem(scope, sub):
                return False
        return True
