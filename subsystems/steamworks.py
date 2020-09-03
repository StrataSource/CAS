from assetbuilder.models import BuildSubsystem
from typing import List
from pathlib import Path

import os
import subprocess
import hashlib
import logging

class SteamworksSubsystem(BuildSubsystem):
    """
    Subsystem that pushes app depots to Steamworks using the content builder.
    App and depot configurations are generated on the fly
    """
    def build(self) -> bool:
        return True
    
    def clean(self) -> bool:
        return True

_subsystem = SteamworksSubsystem
