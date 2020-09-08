from assetbuilder.models import BuildResult, BuildSubsystem
from typing import List
from pathlib import Path

import assetbuilder.utilities as utilities

import os
import subprocess
import hashlib
import logging

import vdf

class VPKArchive():
    def __init__(self, sys: BuildSubsystem, prefix: str, root: Path, files: List[Path]):
        self.sys = sys
        self.root = root
        self.files = files
        self.prefix = prefix

    def _md5_file(self, path: str):
        hash = hashlib.md5()
        with open(path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                hash.update(data)
        return hash.hexdigest()

    def _gen_control_file(self, output: Path, files: List[Path]):
        entries = {}
        for f in files:
            # Ensure the control file itself and VPKs are excluded
            if f.name == output.name or f.name == f'{output.name}.bak' or f.suffix == '.vpk':
                continue

            rel = str(os.path.relpath(f, self.root)).replace('\\', '/')
            entries[rel] = {
                'destpath': rel,
                'md5': self._md5_file(str(f))
            }
        
        # VPK needs the files to stay in the same order
        res = dict(sorted(entries.items()))
        with output.open('w') as f:
            vdf.dump(res, f, pretty=True)

    def pack(self) -> bool:
        cfile_path = self.root.joinpath(f'control_{self.prefix}.vdf')
        self._gen_control_file(cfile_path, self.files)

        args = [str(self.sys.env.get_tool('vpk')), '-M', '-P']
        keypair = self.sys.config.get('keypair')
        if keypair:
            args.extend(['-K', keypair['private'].replace('\\', '/'), '-k', keypair['public'].replace('\\', '/')])
        args.extend(['k', f'{self.prefix}_dir.vpk', cfile_path])

        returncode = self.sys.env.run_tool(args, cwd=self.root)
        if returncode != 0:
            return False
        
        # handle the previous backup file
        bakfile = cfile_path.with_suffix('.vdf.bak')
        if os.path.exists(bakfile):
            os.remove(bakfile)
        os.rename(cfile_path, bakfile)
        return True


class VPKBuildSubsystem(BuildSubsystem):
    """
    Subsystem that packs one or more files into a VPK
    """
    def _get_vpk(self, config: dict) -> VPKArchive:
        if config.get('nobuild') is not None and config['nobuild'] == self.env.config['args']['build_type']:
            logging.info(f'VPK: Skipping archive as it is excluded for this build type')
            return

        prefix = config['prefix']

        files = set()
        assetpath = Path(config['folder']).resolve()

        files = utilities.rglob_multi(assetpath, config.get('files', []))
        if len(files) == 0:
            logging.warning('VPK: No files to pack!')
            return

        return VPKArchive(self, prefix, assetpath, files)

    def build(self) -> BuildResult:
        outputs = {'files': []}
        for f in self.config['packfiles']:
            vpk = self._get_vpk(f)
            logging.info(f'VPK: Packing {len(vpk.files)} files into {vpk.prefix}')
            if not vpk.pack():
                logging.error(f'VPK: Failed to pack {vpk.prefix}!')
                return BuildResult(False)

            # capture the file patterns so we can pass them to other subsystems later
            for entry in f.get('files', []):
                # need to move the ! to the start of the pattern, since we're joining!
                exclude = entry.startswith('!')
                if exclude:
                    entry = entry[1:]
                entry = os.path.join(vpk.root, entry)
                if exclude:
                    entry = '!' + entry
                outputs['files'].append(entry)
        
        return BuildResult(True, outputs)

    def clean(self) -> bool:
        for vpk in self.config['packfiles']:
            fpath = self.env.game.joinpath(vpk['folder'])
            for path in fpath.rglob(vpk['prefix'] + '*.vpk'):
                path.unlink()

            ctl = fpath.joinpath('control_' + vpk['prefix'] + '.vdf')
            if ctl.exists():
                ctl.unlink()
            
            ctl = ctl.with_suffix('.vdf.bak')
            if ctl.exists():
                ctl.unlink()

        return True


_subsystem = VPKBuildSubsystem
