from assetbuilder.models import BuildResult, BuildSubsystem
from typing import List
from pathlib import Path

import os
import subprocess
import hashlib
import logging

class PanZipSubsystem(BuildSubsystem):
    def build(self) -> BuildResult:
        return BuildResult(True)
    
    def clean(self) -> bool:
        return True

_subsystem = PanZipSubsystem
