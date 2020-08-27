from assetbuilder.models import BuildSubsystem
from typing import List
from pathlib import Path

import os
import subprocess
import hashlib
import logging

class ShaderCompileSubsystem(BuildSubsystem):
    def build(self) -> bool:
        return True

    def clean(self) -> bool:
        return True

_subsystem = ShaderCompileSubsystem
