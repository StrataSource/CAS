import cas
from cas.common.config import DefaultValidatingDraft7Validator
from cas.common.models import BuildEnvironment, BuildResult, BuildSubsystem
from cas.common.cache import FileCache
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

from typing import Mapping, Sequence, Callable, Any
from pathlib import Path

_schema_path = Path(cas.__file__).parent.absolute().joinpath("schemas")

logger = None


def _async_mod_init():
    global logger
    logger = multiprocessing.log_to_stderr(logging.INFO)


def _run_async_serial(
    context: AssetBuildContext, driver: SerialDriver, asset: Asset
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
    context: AssetBuildContext, driver: BatchedDriver, assets: Sequence[Asset]
) -> bool:
    context.logger = logger
    for asset in assets:
        relpath = os.path.relpath(asset.path, driver.env.root)
        context.logger.info(f"(CC) {str(relpath)}")
    return driver.compile_all(context, assets)


class AssetSubsystem(BuildSubsystem):
    def __init__(self, env: BuildEnvironment, config: Mapping[str, Any]):
        super().__init__(env, config)

        self._drivers = {}
        self._validators = {}

        self._args = self.env.config.args
        self._dry_run = self._args.dry_run

        self._cache = FileCache(self.env.cache, self.env.cache["assets"])

    def _get_asset_driver(self, name: str) -> BaseDriver:
        driver = self._drivers.get(name)
        if driver is not None:
            return driver

        mod = importlib.import_module(f"cas.common.assets.drivers.{name}")
        if mod is None:
            raise Exception(f"Invalid type {name}")
        self._logger.debug(f"loaded '{name}' driver")

        driver = mod._driver(self.env)
        self._drivers[name] = driver
        return driver

    def _load_asset_context(self, config: Mapping[str, Any]) -> AssetBuildContext:
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

        # find everything by the patterns
        patterns = []
        if isinstance(config.files, str):
            patterns.append(config.files)
        elif isinstance(config.files, Sequence):
            patterns += config.files
        else:
            raise NotImplementedError()

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

    def _build_assets(
        self,
        contexts: Sequence[AssetBuildContext],
        callback: Callable[[Callable[[Mapping[str, Any]], bool], Sequence[Any]], None],
    ):
        for context in contexts:
            if len(context.assets) <= 0:
                self._logger.warning(
                    f"no files found for a context with type {context.config.type}"
                )
                continue

            if isinstance(context.driver, BatchedDriver):
                callback(_run_async_batched, (context, context.driver, context.assets))
            elif isinstance(context.driver, SerialDriver):
                for asset in context.assets:
                    callback(_run_async_serial, (context, context.driver, asset))
            else:
                raise Exception("Unknown driver type")

    def _build_assets_sync(self, contexts: Sequence[AssetBuildContext]) -> bool:
        """
        Builds assets synchronously.
        """
        jobs = []

        _async_mod_init()
        def callback(func: Callable[[Mapping[str, Any]], bool], params: Sequence[Any]):
            jobs.append(func(*params))

        self._build_assets(contexts, callback)
        return all(job for job in jobs)

    def _build_assets_async(self, contexts: Sequence[AssetBuildContext]) -> bool:
        """
        Builds assets asynchronously.
        """
        jobs = []
        pool = multiprocessing.Pool(self._args.threads, initializer=_async_mod_init)

        def callback(func: Callable[[Mapping[str, Any]], bool], params: Sequence[Any]):
            jobs.append(pool.apply_async(func, params))

        try:
            self._build_assets(contexts, callback)
            pool.close()
        except KeyboardInterrupt:
            pool.terminate()
        pool.join()

        return all(job.get() for job in jobs)

    def _run_asset_build(self, clean: bool = False) -> bool:
        contexts = []
        for entry in self.config.assets:
            contexts.append(self._load_asset_context(entry))

        hash_inputs = {}
        hash_outputs = {}
        total_build = 0

        # prebuild
        for context in contexts:
            assets = context.assets.copy()

            context.assets = []
            context.driver = self._get_asset_driver(context.config.type)

            for asset in assets:
                result = context.driver.precompile(context, asset)
                if not result:
                    self._logger.error("Asset dependency error!")
                    return False

                # clean outputs if requested
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
                    context.assets.append(asset)

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
        threaded = self._args.threads > 1
        if threaded:
            self._logger.info(
                f"running multithreaded build with {self._args.threads} threads"
            )
        else:
            self._logger.info("running singlethreaded build")

        # sort out drivers that should run synchronously regardless of threading
        sync_assets = [
            context
            for context in contexts
            if not context.driver.threadable() or not threaded
        ]
        async_assets = [
            context for context in contexts if context.driver.threadable() and threaded
        ]

        if not self._build_assets_sync(sync_assets):
            self._logger.error("Build failed")
            return False
        if not self._build_assets_async(async_assets):
            self._logger.error("Build failed")
            return False

        self._logger.info("recalculating asset hashes...")
        for context in contexts:
            for asset in context.assets:
                # save updated hashes
                aid = asset.get_id()
                for f in hash_inputs[aid]:
                    self._cache.put(f)
                for f in hash_outputs[aid]:
                    self._cache.put(f)

        self.env.cache.save()
        return True

    def build(self) -> BuildResult:
        return BuildResult(self._run_asset_build())

    def clean(self) -> bool:
        return self._run_asset_build(True)


_subsystem = AssetSubsystem
