import sys
import os

# HACK how the fuck do you really do this
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import cas.common.utilities as utilities
from cas.common.sequencer import Sequencer

import ast
import json
import argparse
import logging
import multiprocessing
from pathlib import Path

from dotmap import DotMap

def _resolve_root_path() -> Path:
    root = Path.cwd()
    while True:
        dirs = os.listdir(root)
        if 'content' in dirs and 'game' in dirs:
            # we may have a match, verify we have a valid path
            if Path(os.path.join(root, 'content', 'assets.json')).exists():
                return Path(root).resolve()
        if not root.parent or root.parent == root:
            break
        root = root.parent
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Builds Source Engine assets'
    )

    parser.add_argument('-p', '--path', type=str, help='Path to the root project folder. Should contain game and content subfolders. If this is not specified, it is autodetected.')
    parser.add_argument('-f', '--force', action='store_true', help='Forces a rebuild of all assets')
    parser.add_argument('-t', '--threads', type=int, default=multiprocessing.cpu_count(), help='Number of threads to use to build assets. Defaults to the number of CPUs on the system.')
    parser.add_argument('-c', '--clean', action='store_true', help='Cleans the build environment.')
    parser.add_argument('-b', '--build-type', type=str.lower, choices=['trunk', 'staging', 'release'], default='trunk', help='The type of the build.')
    parser.add_argument('-g', '--build-categories', type=str.lower, help='Comma-seperated list of categories to include in the build. If not specified, all categories will be assumed.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Write verbose output for debugging.')
    parser.add_argument('-d', '--dry-run', action='store_true', help='Prints the arguments that would be passed to VPC and exits.')

    parser.add_argument('-o', '--override', action='append', help='Overrides the configuration path specified by x.')

    parser.add_argument('--include-subsystems', type=str.lower, help='Comma-seperated list of subsystems to include in the build.')
    parser.add_argument('--exclude-subsystems', type=str.lower, help='Comma-seperated list of subsystems to exclude from the build.')

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # if the root path is not specified, try to autodetect it
    if args.path:
        root_path = Path(args.path).resolve()
    else:
        root_path = _resolve_root_path()
    if not root_path:
        logging.error('Couldn\'t find the root path. Ensure you\'re running assetbuilder from within a subdirectory of the root folder, or use the -p/--path argument to specify it.')
        exit(1)

    content_path = root_path.joinpath('content')

    cache_path = content_path.joinpath('.assets_c.json')
    if args.force and cache_path.exists():
        cache_path.unlink()

    config_file = content_path.joinpath('assets.json')
    with config_file.open('rb') as f:
        config = DotMap(json.load(f))

    # apply overrides
    if not args.override:
        args.override = []
    for x in args.override:
        assert x.count('=') <= 1, 'invalid key-value operator'
        if '=' in x:
            spl = x.split('=', 1)
            val = spl[1]
            literal = val.lower()

            # evaluate boolean expressions
            if literal == 'true':
                val = True
            elif literal == 'false':
                val = False

            utilities.set_dot_notation(config, spl[0], val)
        else:
            utilities.set_dot_notation(config, x, True)

    config['args'] = {**config.get('args', {}), **vars(args)}
    config['args']['cli'] = True

    sequencer = Sequencer(root_path, config)
    if not sequencer.run():
        exit(1)
