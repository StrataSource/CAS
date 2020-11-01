from cas.common.models import BuildEnvironment
from typing import Mapping


class BaseCompiler:
    """
    Base compiler class from which all compilers should extend.
    """

    def __init__(self, env: BuildEnvironment, config: Mapping, platform: str):
        self._env = env
        self._config = config
        self._platform = platform

    def clean(self, solution: str):
        """
        Removes all output files of the project.
        """
        raise NotImplementedError()

    def configure(self, solution: str):
        """
        Generates the necessary files to build the project.
        """
        return NotImplementedError()

    def build(self, solution: str):
        """
        Compiles the project.
        """
        raise NotImplementedError()
