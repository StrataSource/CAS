from cas.common.models import BuildEnvironment
from typing import Mapping

import logging


class BaseCompiler:
    """
    Base compiler class from which all compilers should extend.
    """

    def __init__(self, env: BuildEnvironment, config: Mapping, platform: str):
        self._env = env
        self._config = config
        self._platform = platform
        self._logger = logging.getLogger(self.__class__.__module__)

    def bootstrap(self) -> bool:
        """
        Compiles any dependencies required for the configure stage.
        """
        return True

    def clean(self) -> bool:
        """
        Removes all output files of the project.
        """
        raise NotImplementedError()

    def configure(self) -> bool:
        """
        Generates the necessary files to build the project.
        """
        return NotImplementedError()

    def build(self) -> bool:
        """
        Compiles the project.
        """
        raise NotImplementedError()
