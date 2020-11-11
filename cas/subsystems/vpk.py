from cas.common.models import BuildResult, BuildSubsystem
from typing import List
from pathlib import Path

import cas.common.utilities as utilities

import os
import hashlib

import vdf


class VPKArchive:
    def __init__(
        self,
        sys: BuildSubsystem,
        prefix: str,
        input_path: Path,
        output_path: Path,
        files: List[Path],
    ):
        self.sys = sys
        self.prefix = prefix
        self.input_path = input_path
        self.output_path = output_path
        self.files = files

    def _md5_file(self, path: str):
        hash = hashlib.md5()
        with open(path, "rb") as f:
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
            if (
                f.name == output.name
                or f.name == f"{output.name}.bak"
                or f.suffix == ".vpk"
            ):
                continue

            rel = str(os.path.relpath(f, self.input_path)).replace("\\", "/")
            entries[rel] = {"destpath": rel, "md5": self._md5_file(str(f))}

        # VPK needs the files to stay in the same order
        res = dict(sorted(entries.items()))
        with output.open("w") as f:
            vdf.dump(res, f, pretty=True)

    def pack(self) -> bool:
        vpk_path = self.output_path.joinpath(f"{self.prefix}_dir.vpk")
        cfile_path = self.output_path.joinpath(f"control_{self.prefix}.vdf")
        self._gen_control_file(cfile_path, self.files)

        args = [str(self.sys.env.get_tool("vpk")), "-M", "-P"]
        keypair = self.sys.config.get("keypair")
        if keypair:
            args.extend(
                [
                    "-K",
                    keypair["private"].replace("\\", "/"),
                    "-k",
                    keypair["public"].replace("\\", "/"),
                ]
            )
        args.extend(["k", str(vpk_path), str(cfile_path)])

        returncode = self.sys.env.run_tool(args, cwd=self.input_path)
        if returncode != 0:
            return False

        # handle the previous backup file
        bakfile = cfile_path.with_suffix(".vdf.bak")
        if os.path.exists(bakfile):
            os.remove(bakfile)
        os.rename(cfile_path, bakfile)
        return True


class VPKBuildSubsystem(BuildSubsystem):
    """
    Subsystem that packs one or more files into a VPK
    """

    def _get_vpk(self, config: dict) -> VPKArchive:
        prefix = config.prefix

        files = set()
        input_path = Path(config.input).resolve()
        output_path = config.get("output")
        if output_path:
            output_path = Path(output_path).resolve()
        else:
            output_path = input_path

        assert input_path.exists()
        assert output_path.exists()

        files = utilities.rglob_multi(input_path, config.get("files", []))
        if len(files) == 0:
            self._logger.warning("No files to pack!")
            return

        return VPKArchive(self, prefix, input_path, output_path, files)

    def build(self) -> BuildResult:
        outputs = {"files": []}
        for f in self.config.packfiles:
            vpk = self._get_vpk(f)
            pakid = f"{vpk.output_path.parts[-1]}/{vpk.prefix}"
            self._logger.info(f"Packing {len(vpk.files)} files into {pakid}")
            if not vpk.pack():
                self._logger.error(f"Failed to pack {pakid}!")
                return BuildResult(False)

            # capture the file patterns so we can pass them to other subsystems later
            for entry in f.get("files", []):
                # need to move the ! to the start of the pattern, since we're joining!
                exclude = entry.startswith("!")
                if exclude:
                    entry = entry[1:]
                entry = os.path.join(vpk.input_path, entry)
                if exclude:
                    entry = "!" + entry
                outputs["files"].append(entry)

        return BuildResult(True, outputs)

    def clean(self) -> bool:
        for vpk in self.config.packfiles:
            # dupe code here, fix
            input_path = Path(vpk["input"]).resolve()
            output_path = vpk.get("output")
            if output_path:
                output_path = Path(output_path).resolve()
            else:
                output_path = input_path

            for path in output_path.rglob(vpk["prefix"] + "*.vpk"):
                path.unlink()

            ctl = output_path.joinpath("control_" + vpk["prefix"] + ".vdf")
            if ctl.exists():
                ctl.unlink()

            ctl = ctl.with_suffix(".vdf.bak")
            if ctl.exists():
                ctl.unlink()

        return True


_subsystem = VPKBuildSubsystem
