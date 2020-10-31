from assetbuilder.models import BuildEnvironment
from assetbuilder.config import LazyDynamicDotMap
from assetbuilder.common.buildsys.shared import BaseCompiler

import os
import logging
import subprocess
import multiprocessing
from typing import List, Dict
from pathlib import Path

class BaseDependencyHandler():
	"""
	Base class for all dependency handlers
	"""
	def __init__(self, config: LazyDynamicDotMap):
		self.config = config

	def build(self) -> int:
		raise NotImplementedError()

	@staticmethod
	def create_build_manifest(dir: str):
		with open(dir + "/build.manifest.json", "w+") as fs:
			fs.write("")

class BaseCompileEnvironment():
	"""
	Base compilation environment
	"""
	def __init__(self, config: LazyDynamicDotMap):
		self.config = config
		self.env_config = config.environment.config
		self.env_vars = frozenset(self._build_envvars())

	def _build_envvars(self) -> dict:
		env = os.environ.copy()
		env.update({
			'CC': self.config.cc,
			'CXX': self.config.cxx,
			'JOBS': self.config.get('jobs', multiprocessing.cpu_count()),
			'PLATFORM': self.config.platform
		})

		return env

	def run(self, args: List[str]) -> int:
		return NotImplementedError()

class NativeCompileEnvironment(BaseCompileEnvironment):
	"""
	Compilation environment that executes commands in a native shell
	"""
	def run(self, args: List[str]) -> int:
		return subprocess.run(args, env=self.env_vars).returncode

class ChrootCompileEnvironment(BaseCompileEnvironment):
	"""
	Compilation environment that executes commands using schroot
	"""
	def run(self, args: List[str]) -> int:
		defargs = ['schroot', '-c', self.env_config.name, '--', 'bash', '-c']
		return subprocess.run(defargs.extend(args), env=self.env_vars).returncode

class DockerCompileEnvironment(BaseCompileEnvironment):
	"""
	Compilation environment that executes commands using Docker
	"""
	def run(self, args: List[str]) -> int:
		defargs = ['docker', 'run', '--rm', '--name', self.env_config.image, '-i']
		for k, v in self.env_vars:
			defargs.append('-e')
			defargs.append(f'{k}={v}')

		return subprocess.run(defargs.extend(args)).returncode

_compile_environments = {
	'native': NativeCompileEnvironment,
	'chroot': ChrootCompileEnvironment,
	'docker': DockerCompileEnvironment
}

class PosixCompiler(BaseCompiler):
	"""
	Generic POSIX compiler, used to build via generated makefiles
	"""
	def __init__(self, env: BuildEnvironment, config: dict):
		self.env = env
		self.config = config

		self.compile_env = _compile_environments[self.config.environment.type](self.config)

	def _build_dependencies(self) -> bool:
		return True

	def _build_makefile(self) -> bool:
		return True

	def clean(self) -> bool:
		return None

	def configure(self) -> bool:
		if not super().configure():
			return False

		if not self._build_dependencies():
			logging.error('Posix dependency build failed')
			return False

		if not self._build_makefile():
			logging.error('Makefile build failed')
			return False

		return True

	def build(self) -> bool:
		return None
