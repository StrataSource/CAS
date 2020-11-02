import cas
from cas.common.config import DefaultValidatingDraft7Validator
from cas.common.models import BuildEnvironment, BuildResult, BuildSubsystem
from cas.common.assets.cache import AssetCache
from cas.common.assets.models import (
    Asset,
    AssetBuildContext,
    BaseDriver,
    SerialDriver,
    BatchedDriver,
)

import os
import json
import logging
import pathlib
import importlib
import multiprocessing

from typing import List, Sequence
from pathlib import Path

_schema_path = Path(cas.__file__).parent.absolute().joinpath("schemas")

logger = None


def _async_mod_init():
    global logger
    logger = multiprocessing.log_to_stderr(logging.INFO)


def _run_async_serial(
    driver: SerialDriver, context: AssetBuildContext, asset: Asset
) -> bool:
    relpath = os.path.relpath(asset.path, driver.env.root)

    context.logger = logger
    if not context.logger:
        context.logger = logging.getLogger(driver.__class__.__module__)

    context.logger.info(f"(CC) {str(relpath)}")
    success = driver.compile(context, asset)

    if not success:
        context.logger.error(f"  Failed compile {str(relpath)}")
    return success


def _run_async_batched(
    driver: BatchedDriver, context: AssetBuildContext, assets: List[Asset]
) -> bool:
    context.logger = logger
    for asset in assets:
        relpath = os.path.relpath(asset.path, driver.env.root)
        context.logger.info(f"(CC) {str(relpath)}")
    return driver.compile_all(context, assets)


class AssetSubsystem(BuildSubsystem):
    def __init__(self, env: BuildEnvironment, config: dict):
        super().__init__(env, config)

        self._drivers = {}
        self._validators = {}

        self._cache = AssetCache(self.env.root)
        self._cache.load()

        self._args = self.env.config.args
        self._dry_run = self._args.dry_run

    def _get_asset_driver(self, name: str, config: dict) -> BaseDriver:
        driver = self._drivers.get(name)
        if driver is not None:
            return driver

        mod = importlib.import_module(f"cas.common.assets.drivers.{name}")
        if mod is None:
            raise Exception(f"Invalid type {name}")
        self._logger.debug(f"loaded '{name}' driver")

        driver = mod._driver(self.env, config)
        self._drivers[name] = driver
        return driver

    def _load_asset_context(self, config: dict) -> AssetBuildContext:
        # validate the schema
        if config.type not in self._validators:
            driver_path = _schema_path.joinpath("drivers", f"{config.type}.json")
            if not driver_path.exists():
                raise Exception(
                    f"Unable to find schema for asset driver '{config.type}'"
                )
            with open(driver_path, "r") as f:
                self._validators[config.type] = DefaultValidatingDraft7Validator(
                    json.load(f)
                )
        if config.get("options") is not None:
            self._validators[config.type].validate(config.options._data)

        srcpath = Path(config.src)
        if not srcpath.exists():
            raise Exception(f'The asset source folder "{srcpath}" does not exist.')

        patterns = []
        if isinstance(config.files, str):
            patterns.append(config.files)
        elif isinstance(config.files, Sequence):
            patterns += config.files
        else:
            raise NotImplementedError()

        # find everything by the patterns
        files = []
        for pattern in patterns:
            for path in pathlib.Path(srcpath).absolute().rglob(pattern):
                if not path.is_file():
                    continue
                files.append(path)

        # create context and add assets
        context = AssetBuildContext(config)
        for f in files:
            context.assets.append(Asset(f, {}))
        return context

    def _run_asset_build(self, clean: bool = False) -> bool:
        contexts = []
        for entry in self.config.assets:
            contexts.append(self._load_asset_context(entry))

        hash_inputs = {}
        hash_outputs = {}
        total_build = 0

        # prebuild
        for context in contexts:
            driver = self._get_asset_driver(context.config.type, {})
            for asset in context.assets:
                result = driver.precompile(context, asset)
                if not result:
                    self._logger.error("Asset dependency error!")
                    return False

                if clean is True:
                    for f in result.outputs:
                        if not f.exists():
                            continue
                        f.unlink()
                    continue

                # check hashes
                invalidated = False
                for f in result.inputs:
                    f = f.resolve()
                    if not os.path.exists(f):
                        self._logger.error(
                            f"Required dependency '{f}' could not be located!"
                        )
                        return False
                    if not self._cache.validate(f):
                        invalidated = True

                for f in result.outputs:
                    f = f.resolve()
                    if not self._cache.validate(f):
                        invalidated = True

                aid = asset.get_id()
                hash_inputs[aid] = result.inputs
                hash_outputs[aid] = result.outputs

                if invalidated:
                    total_build += 1
                    context.buildable.append(asset)

        if clean is True:
            self._logger.info("assets cleaned")
            return True

        self._logger.info(
            f"{len(hash_inputs)} input files, {len(hash_outputs)} output files"
        )
        self._logger.info(f"{total_build} files total will be rebuilt")

        if self._dry_run or total_build == 0:
            return True

        # build
        # TODO: duplicated code here for singlethreaded mode, fix!
        if self._args.threads > 1:
            jobs = []
            self._logger.info(
                f"running multithreaded build with {self._args.threads} threads"
            )
            pool = multiprocessing.Pool(self._args.threads, initializer=_async_mod_init)

            try:
                for context in contexts:
                    if len(context.buildable) <= 0:
                        self._logger.warning(
                            f"no files found for a context with type {context.config.type}"
                        )
                        continue

                    driver = self._get_asset_driver(context.config.type, {})
                    if isinstance(driver, BatchedDriver):
                        jobs.append(
                            pool.apply_async(
                                _run_async_batched, (driver, context, context.buildable)
                            )
                        )
                    elif isinstance(driver, SerialDriver):
                        for asset in context.buildable:
                            jobs.append(
                                pool.apply_async(
                                    _run_async_serial, (driver, context, asset)
                                )
                            )
                    else:
                        raise Exception("Unknown driver type")
                pool.close()
            except KeyboardInterrupt:
                pool.terminate()

            pool.join()

            for job in jobs:
                result = job.get()
                if not result:
                    self._logger.error("Build failed")
                    return False
        else:
            self._logger.info(f"running singlethreaded build")
            for context in contexts:
                if len(context.buildable) <= 0:
                    self._logger.warning(
                        f"no files found for a context with type {context.config.type}"
                    )
                    continue

                driver = self._get_asset_driver(context.config.type, {})
                if isinstance(driver, BatchedDriver):
                    _run_async_batched(driver, context, context.buildable)
                elif isinstance(driver, SerialDriver):
                    for asset in context.buildable:
                        _run_async_serial(driver, context, asset)
                else:
                    raise Exception("Unknown driver type")

        self._logger.info("recalculating asset hashes...")
        for context in contexts:
            for asset in context.buildable:
                # save updated hashes
                aid = asset.get_id()
                for f in hash_inputs[aid]:
                    self._cache.put(f)
                for f in hash_outputs[aid]:
                    self._cache.put(f)

        self._cache.save()
        return True

    def build(self) -> BuildResult:
        return BuildResult(self._run_asset_build())

    def clean(self) -> bool:
        return self._run_asset_build(True)


_subsystem = AssetSubsystem
