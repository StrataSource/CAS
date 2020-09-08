import assetbuilder.utilities as utilities

from typing import List, Set
from pathlib import Path
import os
import ast
import sys
import logging
import collections
from collections.abc import Mapping
from dotmap import DotMap

import json
import simpleeval

class ConfigurationResolver():
    def __init__(self, data: dict):
        self._data = data

    """
    A terrible lexical parser for interpolated globals.
    I.e. "build type: $(args.build)" returns "build type: trunk"
    """
    def _inject_config_str(self, config: str, literal: bool = False) -> str:
        prev = None
        inblock = False
        current = ''
        result = ''

        for c in config:
            if c == '$':
                prev = c
                continue
            if not inblock and c == '(' and prev == '$':
                # read to end for key
                inblock = True
            elif inblock and c == ')':
                result += str(self._data.get(current, 'None'))

                current = ''
                inblock = False
            elif inblock:
                current += c
            else:
                result += c
            prev = c
        return result

    def _eval_conditional_str(self, cond: str, parent: dict, context: dict) -> bool:
        injected = self._inject_config_str(cond)
        evaluator = simpleeval.EvalWithCompoundTypes(functions={
            # configuration getters
            'context': lambda k, d = None: context.get(k, d),
            'config': lambda k, d = None: self._data.get(k, d),
            'parent': lambda k, d = None: parent.get(k, d),

            # utility functions
            'relative_paths': utilities.relative_paths,
            'rglob_invert': utilities.rglob_invert
        })

        result = evaluator.eval(injected)

        #logging.debug(f'\"{cond}\" evaluated to: {result}')
        return result

    """
    Resolves the stored configuration into literal terms at runtime
    """
    def resolve(self, config, context: dict):
        result = config

        if isinstance(config, dict) or isinstance(config, Mapping):
            result = {}

            for k, v in config.items():
                if k == "@expressions" or k == "@conditions":
                    continue

                parsed = self.resolve(v, context)
                if not v or parsed is not None:
                    result[k] = parsed

            # evaluate @expressions
            expressions = config.get('@expressions', {})
            for k, v in expressions.items():
                econd = self._eval_conditional_str(v, config, context)
                result[k] = econd

            # evaluate @conditions
            conditions = config.get('@conditions', [])
            for cond in conditions:
                if isinstance(cond, str) and not self._eval_conditional_str(cond, config, context):
                    return None
            
        elif isinstance(config, list):
            result = []
            for k, v in enumerate(config):
                parsed = self.resolve(v, context)
                if not v or parsed is not None:
                    result.append(parsed)
        elif isinstance(config, str):
            result = self._inject_config_str(config)
        
        return result

class LazyDynamicBase():
    """
    Base object that allows lazy resolution of configuration data
    """
    def __init__(self, data, context, resolver: ConfigurationResolver):
        self._data = data
        self._context = context
        self._resolver = resolver

    @staticmethod
    def build(data, context, resolver: ConfigurationResolver):
        # if we have a dict, override it
        if isinstance(data, dict):
            return LazyDynamicDict(data, context, resolver)
        else:
            return resolver.resolve(data, context)

    def _transform_object(self, data):
        return LazyDynamicBase.build(data, self._context, self._resolver)


class LazyDynamicDict(LazyDynamicBase, Mapping):
    def __init__(self, data: dict, context, resolver: ConfigurationResolver):
        super().__init__(data, context, resolver)
    
    def __getitem__(self, key):
        return self._transform_object(self._data[key])

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter([self._transform_object(x) for x in self._data])

    def get(self, key, default = None):
        result = self._data.get(key, default)
        if result is None:
            return None

        return self._transform_object(result)


class ConfigurationManager():
    """
    Processes and resolves asset builder configuration blocks.
    """
    def __init__(self, root: Path, config: dict):
        self._config = config
        self._globals = {
            'path.root': root,
            'path.content': root.joinpath('content'),
            'path.game': root.joinpath('game'),
            'path.src': root.joinpath('src')
        }

        self._resolver = ConfigurationResolver(self)

        self._globals['path.devtools'] = self._globals['path.src'].joinpath('devtools')
        self._globals['path.secrets'] = self._globals['path.devtools'].joinpath('buildsys', 'secrets')
        assert self._globals['path.content'].exists()
        assert self._globals['path.game'].exists()

        if not config['defaults'].get('project'):
            raise Exception('The \"project\" default must be defined!')
        self._globals['path.vproject'] = self._globals['path.game'].joinpath(config['defaults']['project']).resolve()

    def _get_internal(self, key, default = None, context: dict = {}):
        result = None
        if key in ('assets', 'subsystems', 'args', 'defaults'):
            result = self._config[key]
        elif key.startswith('args.'):
            result = self._config['args'].get(key[5:])
        else:
            result = self._globals.get(key)

        if result is None:
            return default
        
        return LazyDynamicBase.build(result, context, self._resolver)

    def __getitem__(self, key):
        return self._get_internal(key)

    def get(self, key, default = None, context: dict = {}):
        return self._get_internal(key, default, context)

    def resolve(self, data, context: dict = {}):
        return self._resolver.resolve(data, context)
