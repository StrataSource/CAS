import assetbuilder.utilities as utilities

import os
import ast
import sys
import copy
import json
import logging
import collections
from collections.abc import Mapping
from typing import List, Set
from pathlib import Path

import simpleeval
import jsonschema
from dotmap import DotMap


class ConfigurationResolver():
    """
    Class that actually does the configuration resolution
    """
    def __init__(self, data: dict):
        self._data = data
    
    def _inject_config_str(self, config: str, literal: bool = False) -> str:
        """
        A terrible lexical parser for interpolated globals.
        I.e. "build type: $(args.build)" returns "build type: trunk"
        """

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
    
    def resolve(self, config, context: dict):
        """
        Resolves the stored configuration into literal terms at runtime
        """
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
    def __init__(self, data, resolver: ConfigurationResolver, context = None):
        self._data = data
        self._resolver = resolver
        self._context = context
        self._transform_map = {
            DotMap: LazyDynamicDotMap,
            dict: LazyDynamicDict
        }

    def _transform_object(self, data):
        for k, v in self._transform_map.items():
            if isinstance(data, k):
                return v(data, self._resolver, self._context)
        return self._resolver.resolve(data, self._context)

    def resolve(self):
        raise Exception()
        return self._resolver.resolve(self, self._context)


class LazyDynamicDict(LazyDynamicBase, Mapping):
    """
    Lazy dynamic implementation of dict.
    """
    def __init__(self, data: Mapping, resolver: ConfigurationResolver, context = None):
        super().__init__(data, resolver, context)
    
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

    def with_context(self, context):
        return LazyDynamicDict(self._data, self._resolver, context)


class LazyDynamicDotMap(LazyDynamicBase, DotMap):
    """
    Lazy dynamic implementation of DotMap. This is just a wrapper around a LazyDynamicDict.
    """
    def __init__(self, data: Mapping, resolver: ConfigurationResolver, context = None):
        LazyDynamicBase.__init__(self, data, resolver, context)
        DotMap.__init__(self)

        if not resolver:
            raise Exception()

        # Ensure any child dicts use DotMap for resolution
        self._map = LazyDynamicDict(data, resolver, context)
        self._map._transform_map[dict] = __class__
        self._transform_map[dict] = __class__

    def __setitem__(self, k, v):
        raise NotImplementedError()
    def __getitem__(self, k):
        return self._map[k]

    def __setattr__(self, k, v):
        if k in {'_data','_resolver','_context','_transform_map'}:
            LazyDynamicBase.__setattr__(self, k, v)
        else:
            DotMap.__setattr__(self, k, v)

    def __getattr__(self, k):
        if k in {'_data','_resolver','_context','_transform_map'}:
            print(k)
            return LazyDynamicBase.__getattr__(self, k)
        return DotMap.__getattr__(self, k)

    def with_context(self, context):
        return LazyDynamicDotMap(self._data, self._resolver, context)


class ConfigurationUtilities():
    @staticmethod
    def parse_root_config(root: Path, config: dict) -> dict:
        # validate the schema
        schema_path = Path(__file__).parent.absolute().joinpath('schemas')
        with open(schema_path.joinpath('root.schema.json'), 'r') as f:
            root_schema = json.load(f)
        jsonschema.validate(config, root_schema)

        config = DotMap(config)

        config.path.root = root
        config.path.content = root.joinpath('content')
        config.path.game = root.joinpath('game')
        config.path.src = root.joinpath('src')

        config.path.devtools = config.path.src.joinpath('devtools')
        config.path.secrets = config.path.devtools.joinpath('buildsys', 'secrets')
        config.path.vproject = config.path.game.joinpath(config.options.project).resolve()

        # create the root resolver and the map
        resolver = ConfigurationResolver(config)
        return LazyDynamicDotMap(config.toDict(), resolver)
