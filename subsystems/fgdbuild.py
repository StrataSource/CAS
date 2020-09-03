from assetbuilder.models import BuildSubsystem
from typing import List
from pathlib import Path

import os
import sys
import subprocess
import hashlib
import shutil
import logging
import importlib.util
import contextlib

class FGDBuildSubsystem(BuildSubsystem):
    """
    Subsystem that builds FGDs and Hammer assets from HammerAddons
    """
    def build(self) -> bool:
        gamedir = self.config['gamedir']

        srcpath = Path(self.env.root).joinpath(self.config['source']).resolve()
        destpath = Path(self.env.root).joinpath(self.config['dest']).resolve()

        logging.info('Building FGD...')
        spec = importlib.util.spec_from_file_location('hammeraddons.unifyfgd', srcpath.joinpath('unify_fgd.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        outfile = srcpath.joinpath(f'build/{gamedir}.fgd')

        # redirect our output so logs aren't spammed on non-verbose mode
        log_dev = sys.stdout if self.env.verbose else None
        with contextlib.redirect_stdout(log_dev):
            mod.action_export(srcpath.joinpath('fgd'), None, frozenset({'SRCTOOLS', self.config['branch']}), outfile, False, False)

        logging.info('Copying output files...')
        shutil.copy(outfile, destpath.joinpath('bin', f'{gamedir}.fgd'))

        hammer_dir = destpath.joinpath('hammer')
        instance_dir = destpath.joinpath(gamedir, 'sdk_content/maps/instances')

        if hammer_dir.exists():
            shutil.rmtree(hammer_dir)
        if instance_dir.exists():
            shutil.rmtree(instance_dir)
        
        shutil.copytree(srcpath.joinpath('hammer'), hammer_dir)
        shutil.copytree(srcpath.joinpath('instances'), instance_dir)

        return True

    def clean(self) -> bool:
        return True

_subsystem = FGDBuildSubsystem
