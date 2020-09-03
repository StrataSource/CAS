from assetbuilder.models import BuildEnvironment, BuildContext, BuildSubsystem, Asset, BaseDriver, SerialDriver, BatchedDriver
from assetbuilder.cache import AssetCache
import assetbuilder.utilities

from typing import List
from pathlib import Path
import multiprocessing
import importlib
import logging
import pathlib
import signal
import os

logger = None
def _async_mod_init():
    global logger
    logger = multiprocessing.log_to_stderr(logging.INFO)

def _run_async_serial(driver: SerialDriver, context: BuildContext, asset: Asset) -> bool:
    relpath = os.path.relpath(asset.path, driver.env.root)

    context.logger = logger
    context.logger.info(f'(CC) {str(relpath)}')

    success = driver.compile(context, asset)

    if not success:
        context.logger.error(f'  Failed compile {str(relpath)}')
    return success

def _run_async_batched(driver: BatchedDriver, context: BuildContext, assets: List[Asset]) -> bool:
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
        self.dryrun = self.args.get('dry_run', False)

    def _load_subsystem(self, module: str, config: dict) -> BuildSubsystem:
        subsystem = self._subsystems.get(module)
        if subsystem is not None:
            return

        mod = importlib.import_module(module)
        if mod is None:
            raise Exception(f'Failed to load subsystem {mod}')
        logging.debug(f'loaded \'{module}\' subsystem')

        subsystem = mod._subsystem(self.env, config)
        self._subsystems[module] = subsystem

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

    def _load_asset_context(self, config: dict) -> List[Asset]:
        srcpath = config['src'] if 'src' in config else self.env.config['path.content']
        srcpath = os.path.join(self.env.root, srcpath)
        if not os.path.exists(srcpath):
            raise Exception(f'The asset source folder \"{srcpath}\" does not exist.')

        patterns = []
        if isinstance(config['files'], list):
            patterns += config['files']
        else:
            patterns.append(config['files'])

        # find everything by the patterns
        files = []
        for pattern in patterns:
            for path in pathlib.Path(srcpath).absolute().rglob(pattern):
                if not path.is_file():
                    continue
                files.append(path)

        # create context and add assets
        context = BuildContext(config)
        for f in files:
            context.assets.append(Asset(f, {}))
        return context

    def _run_asset_build(self) -> bool:
        contexts = []
        for entry in self.env.config['assets']:
            contexts.append(self._load_asset_context(entry))

        hash_inputs = {}
        hash_outputs = {}
        total_build = 0

        # prebuild
        for context in contexts:
            driver = self._get_asset_driver(context.config['type'], {})
            for asset in context.assets:
                result = driver.precompile(context, asset)
                if not result:
                    logging.error('Asset dependency error!')
                    return False

                if self.args['clean']:
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

        if self.args['clean']:
            logging.info('assets cleaned')
            return True

        logging.info(f'{len(hash_inputs)} input files')
        logging.info(f'{len(hash_outputs)} output files')
        logging.info(f'{total_build} assets total will be rebuilt')

        if self.dryrun or total_build == 0:
            return True

        # build
        jobs = []
        logging.info(f'running build with {self.args["threads"]} threads')
        pool = multiprocessing.Pool(self.args['threads'], initializer=_async_mod_init)

        try:
            for context in contexts:
                if len(context.buildable) <= 0:
                    logging.warning(f'no files found for a context with type {context.config["type"]}')
                    continue

                driver = self._get_asset_driver(context.config['type'], {})
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


    def _run_subsystems(self) -> bool:
        if self.dryrun:
            return True

        for sys in self.env.config['subsystems']:
            self._load_subsystem(sys['module'], sys.get('options', {}))
        for name, sys in self._subsystems.items():
            logging.info(f'running subsystem {name}')
            if self.args['clean']:
                if not sys.clean():
                    return False
            else:
                if not sys.build():
                    return False
        return True


    def build(self) -> bool:
        logging.debug(f'build starting with arguments: {self.args}')

        self.cache.load()
        if not self._run_asset_build():
            logging.error('Asset build phase failed')
            return False
        if not self._run_subsystems():
            logging.error('Subsystem build phase failed')
            return False
        return True
