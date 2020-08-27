from assetbuilder.models import BuildSubsystem
from typing import List
from pathlib import Path

import os
import subprocess
import hashlib
import logging

import vdf

class VPKBuildSubsystem(BuildSubsystem):
    def _pack_vpk(self, config: dict):
        if config.get('nobuild') is not None and config['nobuild'] == self.env.config['args']['build_type']:
            logging.info(f'VPK: Skipping archive as it is excluded for this build type')
            return

        prefix = config['prefix']

        files = set()
        assetpath = Path(os.path.join(self.env.root, self.env.game, config['folder']))

        for pattern in config.get('include', []):
            for path in assetpath.rglob(pattern):
                if not path.is_file():
                    continue
                files.add(path)
        for pattern in config.get('exclude', []):
            for path in assetpath.rglob(pattern):
                if not path.is_file():
                    continue
                if path in files:
                    files.remove(path)

        if len(files) == 0:
            logging.warning('VPK: No files to pack!')
            return
        
        logging.info(f'VPK: Packing {len(files)} files into {prefix}')

        vpk = VPKArchive(self, prefix, assetpath, files)
        vpk.pack()
        

    def build(self) -> bool:
        for vpk in self.config['packfiles']:
            self._pack_vpk(vpk)
        return True

    def clean(self) -> bool:
        for vpk in self.config['packfiles']:
            fpath = Path(os.path.join(self.env.root, self.env.game, vpk['folder']))
            for path in fpath.rglob(vpk['prefix'] + '*.vpk'):
                path.unlink()

            ctl = fpath.joinpath('control_' + vpk['prefix'] + '.vdf')
            if ctl.exists():
                ctl.unlink()
            
            ctl = ctl.with_suffix('.vdf.bak')
            if ctl.exists():
                ctl.unlink()

        return True


class VPKArchive():
    def __init__(self, sys: VPKBuildSubsystem, prefix: str, root: Path, files: List[Path]):
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
        with open(output, 'w') as f:
            vdf.dump(res, f, pretty=True)

    def pack(self) -> bool:
        cfile_path = Path(os.path.join(self.root, f'control_{self.prefix}.vdf'))
        self._gen_control_file(cfile_path, self.files)

        args = [self.sys.env.get_tool('vpk.exe'), '-M', '-P']
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

_subsystem = VPKBuildSubsystem
