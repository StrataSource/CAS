import sys
import os
# HACK how the fuck do you really do this
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import assetbuilder.builder
import assetbuilder.utilities as utilities
import json
import argparse
import logging
import multiprocessing
from pathlib import Path

from dotmap import DotMap

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Builds Source Engine assets'
    )

    parser.add_argument('-p', '--path', type=str, help='Path to the root project folder. Should contain game and content subfolders.', required=True)
    parser.add_argument('-f', '--force', action='store_true', help='Forces a rebuild of all assets')
    parser.add_argument('-t', '--threads', type=int, default=multiprocessing.cpu_count(), help='Number of threads to use to build assets. Defaults to the number of CPUs on the system.')
    parser.add_argument('-c', '--clean', action='store_true', help='Cleans the build environment.')
    parser.add_argument('-b', '--build-type', type=str.lower, choices=['trunk', 'staging', 'release'], default='trunk', help='The type of the build.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Write verbose output for debugging.')
    parser.add_argument('-d', '--dry-run', action='store_true', help='Prints the arguments that would be passed to VPC and exits.')

    parser.add_argument('-o', '--override', action='append', help='Overrides the configuration path specified by x.')

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    cache_path = os.path.join(args.path, 'content', '.assets_c.json')
    if args.force and os.path.exists(cache_path):
        os.remove(cache_path)

    config_file = os.path.join(args.path, 'content', 'assets.json')
    with open(config_file, 'rb') as f:
        config = DotMap(json.load(f))

    # apply overrides
    for x in args.override:
        assert x.count('=') <= 1, 'invalid key-value operator'
        if '=' in x:
            spl = x.split('=', 1)
            utilities.set_dot_notation(config, spl[0], spl[1])
        else:
            utilities.set_dot_notation(config, x, True)

    config['args'] = {**config.get('args', {}), **vars(args)}
    builder = assetbuilder.builder.Builder(Path(args.path).resolve(), config)
    if not builder.build():
        exit(1)
