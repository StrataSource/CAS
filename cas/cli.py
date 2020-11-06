import os
import json
import argparse
import logging
import multiprocessing
from pathlib import Path
from dotmap import DotMap

import cas.common.utilities as utilities
from cas.common.sequencer import Sequencer


def _resolve_root_path() -> Path:
    root = Path.cwd()
    while True:
        dirs = os.listdir(root)
        if "content" in dirs and "game" in dirs:
            # we may have a match, verify we have a valid path
            if Path(os.path.join(root, "content", "cas.json")).exists():
                return Path(root).resolve()
        if not root.parent or root.parent == root:
            break
        root = root.parent
    return None


def main():
    parser = argparse.ArgumentParser(description="Chaos Automation System CLI")

    parser.add_argument(
        "-p",
        "--path",
        type=str,
        help="Path to the root project folder. Should contain game and content subfolders. If this is not specified, it is autodetected.",
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="Forces a rebuild of all assets"
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=multiprocessing.cpu_count(),
        help="Number of threads to use to build assets. Defaults to the number of CPUs on the system.",
    )
    parser.add_argument(
        "-c", "--clean", action="store_true", help="Cleans the build environment."
    )
    parser.add_argument(
        "-b",
        "--build-type",
        type=str.lower,
        choices=["trunk", "staging", "release"],
        default="trunk",
        help="The type of the build.",
    )
    parser.add_argument(
        "-s",
        "--build-categories",
        type=str.lower,
        help="Comma-seperated list of categories to include in the build. If not specified, all categories will be assumed.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Write verbose output for debugging.",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Prints the arguments that would be passed to VPC and exits.",
    )

    parser.add_argument(
        "-o",
        "--override",
        action="append",
        help="Overrides the configuration path specified by x.",
    )

    parser.add_argument(
        "-i",
        "--include-subsystems",
        type=str.lower,
        help="Comma-seperated list of subsystems to include in the build.",
    )
    parser.add_argument(
        "-x",
        "--exclude-subsystems",
        type=str.lower,
        help="Comma-seperated list of subsystems to exclude from the build.",
    )

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger(__name__)

    # if the root path is not specified, try to autodetect it
    if args.path:
        root_path = Path(args.path).resolve()
    else:
        root_path = _resolve_root_path()
    if not root_path:
        logger.error(
            "Couldn't find the root path. Ensure you're running CAS from within a subdirectory of the root folder, or use the -p/--path argument to specify it."
        )
        exit(1)

    content_path = root_path.joinpath("content")

    config_file = content_path.joinpath("cas.json")
    if not config_file.exists():
        logger.error(
            "Couldn't find cas.json. If you don't yet have one, please see the documentation for a template."
        )
        exit(1)

    with config_file.open("rb") as f:
        config = DotMap(json.load(f))

    cache_path = content_path.joinpath(".cas_cache.json")
    if args.force and cache_path.exists():
        cache_path.unlink()

    # apply overrides
    if not args.override:
        args.override = []
    for x in args.override:
        assert x.count("=") <= 1, "invalid key-value operator"
        if "=" in x:
            spl = x.split("=", 1)
            val = spl[1]

            # if it starts with [ or {, parse as json
            if val.startswith("[") or val.startswith("{"):
                val = json.loads(val)
            elif val.isdigit():
                val = int(val)

            utilities.set_dot_notation(config, spl[0], val)
        else:
            utilities.set_dot_notation(config, x, True)

    config["args"] = {**config.get("args", {}), **vars(args)}
    config["args"]["cli"] = True

    sequencer = Sequencer(root_path, config)
    if not sequencer.run():
        exit(1)
