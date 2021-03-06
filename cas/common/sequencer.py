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
        self._logger = logging.getLogger(__name__)

    def _load_subsystem(self, module: str, config: dict) -> BuildSubsystem:
        mod = importlib.import_module(module)
        if mod is None:
            raise Exception(f"Failed to load subsystem {mod}")
        self._logger.debug(f"loaded '{module}' subsystem")

        return mod._subsystem(self.env, config)

    def _run_step(self, scope: DataResolverScope, step: Mapping) -> bool:
        if self._args.dry_run:
            return True

        # get the full configuration and run
        step = step.with_scope(scope)
        sys = self._load_subsystem(f"cas.subsystems.{step.uses}", step.get("with", {}))

        current_paths = set(self.env.paths.keys())
        required_paths = set(sys.required_paths())
        if len(required_paths.intersection(current_paths)) == 0:
            self._logger.error(
                f"the subsystem '{step.uses}' needs the paths {required_paths}, but only {current_paths} is present in the current environment"
            )
            return False

        force = self._args.force or sys.needs_rebuild()

        # self._logger.info(f"running subsystem {name}")
        self._logger.info(f"running subsystem {step.uses}")
        if self._args.clean:
            if not sys.clean():
                return False
        else:
            result = sys.build(force)
            if "id" in step:
                scope._data.steps[step["id"]] = result
            if not result.success:
                return False

        sys.rehash_config()
        return True

    def _run_job(self, job: Mapping) -> bool:
        # build whitelist/blacklist
        whitelist = self._args.include_subsystems
        blacklist = self._args.exclude_subsystems
        if whitelist:
            whitelist = whitelist.split(",")
        if blacklist:
            blacklist = blacklist.split(",")

        # create the scope
        scope = DataResolverScope()

        # run steps
        for num, step in enumerate(job.steps):
            if whitelist and num not in whitelist:
                self._logger.info(f"step {num} skipped (not whitelisted)")
                continue
            if blacklist and num in blacklist:
                self._logger.info(f"step {num} skipped (blacklisted)")
                continue
            if not self._run_step(scope, step):
                return False
        return True

    def run(self) -> bool:
        # run jobs
        for name, job in self.env.config.jobs.items():
            if self.env.build_jobs is not None and name not in self.env.build_jobs:
                self._logger.info(f"job '{name}' skipped (not enabled)")
                continue

            build_types = job.get("build_types")
            if build_types and self.env.build_type not in build_types:
                self._logger.info(f"job '{name}' skipped (build type mismatch)")
                return True

            if not self._run_job(job):
                return False

        # only save the cache if everything succeeds!
        self.env.cache.save()
        return True
