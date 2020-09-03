import assetbuilder.utilities

from typing import List, Set
from pathlib import Path
import os
import ast
import sys
import logging

import json
import simpleeval


class ConfigurationManager():
    """
    Processes and resolves asset builder configuration blocks.
    """
    def __init__(self, root: str, config: dict):
        self._config = config
        self._globals = {
            'path.root': root,
            'path.content': config['defaults'].get('content', 'content'),
            'path.game': config['defaults'].get('game', 'game'),
            'path.secrets': os.path.join(root, 'src/devtools/buildsys/secrets')
        }

        # config is only parsed once, on initialisation
        self._config = self._parse_config(self._config)

    def __getitem__(self, key):
        result = None
        if key in ('assets', 'subsystems', 'args'):
            result = self._config[key]
        elif key.startswith('args.'):
            result = self._config['args'].get(key[5:])
        else:
            result = self._globals.get(key)
        return self._resolve_config(result)

    def __setitem__(self, key, value):
        raise Exception('Configuration store is read-only!')

    def get(self, key, default = None):
        r = self[key]
        if r is None:
            return default
        return r

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
                result += self.get(current, 'None')

                current = ''
                inblock = False
            elif inblock:
                current += c
            else:
                result += c
            prev = c
        return result

    def _eval_conditional_str(self, cond: str) -> bool:
        injected = self._inject_config_str(cond)
        result = simpleeval.simple_eval(injected, functions={
            'R': lambda k: self[k]
        })

        logging.debug(f'\"{cond}\" evaluated to: {result}')
        return result

    """
    Does the initial parse of the config,
    removing any blocks that do not pass their conditions.
    """
    def _parse_config(self, config):
        result = config

        if isinstance(config, dict):
            result = {}

            # initial scan to eval @condition
            cond = config.get('@condition')
            if isinstance(cond, str) and not self._eval_conditional_str(cond):
                return None

            for k, v in config.items():
                if k == "@condition":
                    continue

                parsed = self._parse_config(v)
                if not v or parsed is not None:
                    result[k] = parsed
        elif isinstance(config, list):
            result = []
            for k, v in enumerate(config):
                parsed = self._parse_config(v)
                if not v or parsed is not None:
                    result.append(parsed)
        
        return result

    """
    Called when ready to resolve config into literal terms.
    """
    def _resolve_config(self, config):
        if isinstance(config, dict):
            for k, v in config.items():
                config[k] = self._resolve_config(v)
        elif isinstance(config, list):
            for k, v in enumerate(config):
                config[k] = self._resolve_config(v)
        elif isinstance(config, str):
            config = self._inject_config_str(config)
        return config
