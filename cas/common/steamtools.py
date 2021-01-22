from pathlib import Path
import sys
import logging
import cas.common.utilities

import vdf

if cas.common.utilities.is_platform_windows():
    import winreg


def get_steam_path() -> Path:
    if cas.common.utilities.is_platform_windows():
        steam_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam",
            0,
            winreg.KEY_READ,
        )
        steam_path = winreg.QueryValueEx(steam_key, "InstallPath")
        winreg.CloseKey(steam_key)

        return Path(steam_path[0]).resolve()
    else:
        raise NotImplementedError(
            "TODO: implement platforms other than Windows for autodetection!"
        )


class SteamApp:
    """
    Represents a singular Steam application.
    """

    @staticmethod
    def from_acf(library: Path, path: Path):
        with open(path, "r") as f:
            parsed = vdf.load(f)
        state = parsed["AppState"]

        result = SteamApp()
        result.appid = int(state["appid"])
        result.name = state.get("name")
        result.path = library.joinpath("common", state["installdir"])
        return result


class SteamInstance:
    """
    Represents an instance of Steam.
    """

    def __init__(self):
        self._path = get_steam_path()
        self._load_apps()

    def _load_apps(self):
        root_apps = self._path.joinpath("steamapps")
        fpath = root_apps.joinpath("libraryfolders.vdf")
        if not fpath.exists():
            raise Exception("Unable to find libraryfolders.vdf!")
        with open(fpath, "r") as f:
            lib_vdf = vdf.load(f)

        logging.debug("libraryfolders.vdf found")

        libraries = []
        folders = lib_vdf["LibraryFolders"]
        for k, v in folders.items():
            if not k.isdigit():
                continue
            libraries.append(Path(v).joinpath("steamapps").resolve())

        libraries.append(root_apps.resolve())
        logging.debug(f"{len(libraries)} num libraries detected")

        apps = []
        for l in libraries:
            for path in l.glob("appmanifest_*.acf"):
                if not path.is_file():
                    continue
                app = SteamApp.from_acf(l, path)
                if not app.path.exists():
                    logging.warn(
                        f"Skipping steam app {app.appid} as ACF reported as installed but we cannot locate the folder"
                    )
                    continue
                apps.append(app)
        self.apps = apps
