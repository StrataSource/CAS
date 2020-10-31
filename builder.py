from assetbuilder.models import BuildEnvironment, BuildSubsystem, Asset, AssetBuildContext, BaseDriver, SerialDriver, BatchedDriver
from assetbuilder.cache import AssetCache
from assetbuilder.config import DataResolverContext
import assetbuilder.utilities

from typing import List, Sequence
from pathlib import Path
import multiprocessing
import importlib
import logging
import pathlib
import signal
import os

from dotmap import DotMap

logger = None
def _async_mod_init():
    global logger
    logger = multiprocessing.log_to_stderr(logging.INFO)

def _run_async_serial(driver: SerialDriver, context: AssetBuildContext, asset: Asset) -> bool:
    relpath = os.path.relpath(asset.path, driver.env.root)

    context.logger = logger
    if not context.logger:
        context.logger = logging.getLogger()

    context.logger.info(f'(CC) {str(relpath)}')
    success = driver.compile(context, asset)

    if not success:
        context.logger.error(f'  Failed compile {str(relpath)}')
    return success

def _run_async_batched(driver: BatchedDriver, context: AssetBuildContext, assets: List[Asset]) -> bool:
    context.logger = logger
    for asset in assets:
        relpath = os.path.relpath(asset.path, driver.env.root)
        context.logger.info(f'(CC) {str(relpath)}')
    return driver.compile_all(context, assets)

class Builder():
    """
    Main class for the asset builder
    """
    def __init__(self, path: Path, config: dict):
        self._drivers = {}
        self._subsystems = {}

        self.env = BuildEnvironment(path, config)
        self.cache = AssetCache(path)

        self.args = self.env.config.get('args', {})
        self.dry_run = self.args.get('dry_run', False)
        self.show_status = self.args.get('cli', False)

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

    def _get_asset_driver(self, name: str, config: dict) -> BaseDriver:
        driver = self._drivers.get(name)
        if driver is not None:
            return driver

        mod = importlib.import_module(f'.drivers.{name}', __package__)
        if mod is None:
            raise Exception(f'Invalid type {name}')
        logging.debug(f'loaded \'{name}\' driver')

        driver = mod._driver(self.env, config)
        self._drivers[name] = driver
        return driver

    def _load_asset_context(self, config: dict) -> AssetBuildContext:
        srcpath = Path(config.src)
        if not srcpath.exists():
            raise Exception(f'The asset source folder \"{srcpath}\" does not exist.')

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

    def _run_asset_build(self, context: DataResolverContext) -> bool:
        logging.info('running asset build')

        contexts = []
        for entry in self.env.config.assets:
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
                    logging.error('Asset dependency error!')
                    return False

                if self.args.clean:
                    for f in result.outputs:
                        if not f.exists():
                            continue
                        f.unlink()
                    continue

                # check hashes
                invalidated = False
                for f in result.inputs:
                    if not os.path.exists(f):
                        logging.error(f'Required dependency \'{f}\' could not be located!')
                        return False
                    if not self.cache.validate(f):
                        invalidated = True

                for f in result.outputs:
                    if not self.cache.validate(f):
                        invalidated = True

                aid = asset.get_id()
                hash_inputs[aid] = result.inputs
                hash_outputs[aid] = result.outputs

                if invalidated:
                    total_build += 1
                    context.buildable.append(asset)

        if self.args.clean:
            logging.info('assets cleaned')
            return True

        logging.info(f'{len(hash_inputs)} input files, {len(hash_outputs)} output files')
        logging.info(f'{total_build} files total will be rebuilt')

        if self.dry_run or total_build == 0:
            return True

        # build
        # TODO: duplicated code here for singlethreaded mode, fix!
        if self.args.threads > 1:
            jobs = []
            logging.info(f'running multithreaded build with {self.args.threads} threads')
            pool = multiprocessing.Pool(self.args.threads, initializer=_async_mod_init)

            try:
                for context in contexts:
                    if len(context.buildable) <= 0:
                        logging.warning(f'no files found for a context with type {context.config.type}')
                        continue

                    driver = self._get_asset_driver(context.config.type, {})
                    if isinstance(driver, BatchedDriver):
                        jobs.append(pool.apply_async(_run_async_batched, (driver, context, context.buildable)))
                    elif isinstance(driver, SerialDriver):
                        for asset in context.buildable:
                            jobs.append(pool.apply_async(_run_async_serial, (driver, context, asset)))
                    else:
                        raise Exception('Unknown driver type')
                pool.close()
            except KeyboardInterrupt:
                pool.terminate()

            pool.join()

            for job in jobs:
                result = job.get()
                if not result:
                    logging.error('Build failed')
                    return False
        else:
            logging.info(f'running singlethreaded build')
            for context in contexts:
                if len(context.buildable) <= 0:
                    logging.warning(f'no files found for a context with type {context.config.type}')
                    continue

                driver = self._get_asset_driver(context.config.type, {})
                if isinstance(driver, BatchedDriver):
                    _run_async_batched(driver, context, context.buildable)
                elif isinstance(driver, SerialDriver):
                    for asset in context.buildable:
                        _run_async_serial(driver, context, asset)
                else:
                    raise Exception('Unknown driver type')

        logging.info('recalculating asset hashes...')
        for context in contexts:
            for asset in context.buildable:
                # save updated hashes
                aid = asset.get_id()
                for f in hash_inputs[aid]:
                    self.cache.put(f)
                for f in hash_outputs[aid]:
                    self.cache.put(f)

        self.cache.save()
        return True


    def _run_subsystem(self, context: DataResolverContext, name: str) -> bool:
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
        subsystem = subsystem.with_context(context)
        self._load_subsystem(name, subsystem.module, subsystem.get('options', {}))
        
        # run
        sys = self._subsystems[name]
        logging.info(f'running subsystem {name}')
        if self.args.clean:
            if not sys.clean():
                return False
        else:
            result = sys.build()
            context.results.subsystems[name] = result
            if not result.success:
                return False
        return True


    def _run_subsystems(self, context: DataResolverContext, subsystems: List[str], whitelist: List[str], blacklist: List[str]) -> bool:
        for sub in subsystems:
            if whitelist and not sub in whitelist:
                logging.debug(f'subsystem {sub} skipped (not whitelisted)')
                continue
            if blacklist and sub in blacklist:
                logging.debug(f'subsystem {sub} skipped (blacklisted)')
                continue
            if not self._run_subsystem(context, sub):
                return False
        return True


    def build(self) -> bool:
        self.cache.load()

        # skip asset build if we specify a different category explicitly
        skip_assets = self.args.skip_assets
        if self.env.build_categories is not None and not 'assets' in self.env.build_categories:
            logging.debug('asset build skipped (category mismatch)')
            skip_assets = True

        # build wl/bl
        whitelist = self.args.include_subsystems
        blacklist = self.args.exclude_subsystems
        if whitelist:
            whitelist = whitelist.split(',')
        if blacklist:
            blacklist = blacklist.split(',')

        # create the context
        context = DataResolverContext()

        # sort subsystems into before/after assets
        before_subs = []
        after_subs = []
        for k, v in self.env.config.subsystems.items():
            if v.before_assets is True:
                before_subs.append(k)
            else:
                after_subs.append(k)

        # first pass before assets
        if not self._run_subsystems(context, before_subs, whitelist, blacklist):
            return False

        # build assets
        if not skip_assets and not self._run_asset_build(context):
            logging.error('Asset build phase failed')
            return False

        # second pass after assets
        if not self._run_subsystems(context, after_subs, whitelist, blacklist):
            return False
        
        return True
