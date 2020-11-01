from cas.common.models import BuildEnvironment, BuildSubsystem
from cas.common.config import DataResolverScope
import cas.common.utilities

from typing import List, Sequence
from pathlib import Path

import importlib
import logging
import pathlib
import signal
import os

from dotmap import DotMap

class Sequencer():
    """
    Class that executes a number of discrete programs (subsystems) in order.
    """
    def __init__(self, path: Path, config: dict):
        self._drivers = {}
        self._subsystems = {}

        self.env = BuildEnvironment(path, config)

        self.args = self.env.config.get('args', {})
        self.dry_run = self.args.get('dry_run', False)

    def _load_subsystem(self, name: str, module: str, config: dict) -> BuildSubsystem:
        subsystem = self._subsystems.get(module)
        if subsystem is not None:
            return

        mod = importlib.import_module(module)
        if mod is None:
            raise Exception(f'Failed to load subsystem {mod}')
        logging.debug(f'loaded \'{module}\' subsystem')

        subsystem = mod._subsystem(self.env, config)
        self._subsystems[name] = subsystem

    def _run_subsystem(self, scope: DataResolverScope, name: str) -> bool:
        if self.dry_run:
            return True

        # get the unresolved configuration first to run checks
        subsystem = self.env.config.subsystems.get(name)
        if not subsystem:
            return True

        build_types = subsystem.get('build_types')
        if build_types and not self.env.build_type in build_types:
            logging.debug(f'subsystem {name} skipped (build type mismatch)')
            return True

        categories = subsystem.get('categories')
        if self.env.build_categories and categories and len(self.env.build_categories.intersection(set(categories))) == 0:
            logging.debug(f'subsystem {name} skipped (category mismatch)')
            return True

        # get the full configuration
        subsystem = subsystem.with_scope(scope)
        self._load_subsystem(name, subsystem.module, subsystem.get('options', {}))
        
        # run
        sys = self._subsystems[name]
        logging.info(f'running subsystem {name}')
        if self.args.clean:
            if not sys.clean():
                return False
        else:
            result = sys.build()
            scope.results.subsystems[name] = result
            if not result.success:
                return False
        return True

    def run(self) -> bool:
        # build whitelist/blacklist
        whitelist = self.args.include_subsystems
        blacklist = self.args.exclude_subsystems
        if whitelist:
            whitelist = whitelist.split(',')
        if blacklist:
            blacklist = blacklist.split(',')
        
        # create the scope
        scope = DataResolverScope()

        # run subsystems
        for sub in self.env.config.subsystems.keys():
            if whitelist and not sub in whitelist:
                logging.debug(f'subsystem {sub} skipped (not whitelisted)')
                continue
            if blacklist and sub in blacklist:
                logging.debug(f'subsystem {sub} skipped (blacklisted)')
                continue
            if not self._run_subsystem(scope, sub):
                return False
        return True
