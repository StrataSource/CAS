import sys
import os
# HACK how the fuck do you really do this
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import assetbuilder.builder
import json
import argparse
import logging
import multiprocessing
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Builds Source Engine assets'
    )

    parser.add_argument('--path', type=str, help='Path to the root project folder. Should contain game and content subfolders.', required=True)
    parser.add_argument('--force', action='store_true', help='Forces a rebuild of all assets')
    parser.add_argument('--threads', type=int, default=multiprocessing.cpu_count(), help='Number of threads to use to build assets. Defaults to the number of CPUs on the system.')
    parser.add_argument('--clean', action='store_true', help='Cleans the build environment.')
    parser.add_argument('--build-type', type=str.lower, choices=['trunk', 'staging', 'release'], default='trunk', help='The type of the build.')
    parser.add_argument('--verbose', action='store_true', help='Write verbose output for debugging.')
    parser.add_argument('--dry-run', action='store_true', help='Prints the arguments that would be passed to VPC and exits.')

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
        config = json.load(f)

    config['args'] = {**config.get('args', {}), **vars(args)}
    builder = assetbuilder.builder.Builder(Path(args.path).resolve(), config)
    if not builder.build():
        exit(1)
