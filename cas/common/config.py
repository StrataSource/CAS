import cas
import cas.common.utilities as utilities

import re
import sys
import json
import simpleeval
import jsonschema
import multiprocessing

from dotmap import DotMap
from pathlib import Path
from typing import Any, Tuple
from collections.abc import Sequence, Mapping


def extend_validator_with_default(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(validator, properties, instance, schema):
        for property, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(property, subschema["default"])
        for error in validate_properties(validator, properties, instance, schema):
            yield error

    return jsonschema.validators.extend(validator_class, {"properties": set_defaults})


DefaultValidatingDraft7Validator = extend_validator_with_default(
    jsonschema.Draft7Validator
)

CONDITION_REGEX = re.compile(r"(?s)\${{(.*)}}")


class DataResolverScope(Mapping):
    def __init__(self):
        self._data = DotMap()

    def __getitem__(self, key):
        if key not in self._data:
            raise KeyError(key)
        return self._data[key]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)


class DataResolver:
    """
    Class that actually does the configuration resolution
    """

    def __init__(self, data: Mapping):
        self._data = data

    def _build_eval_locals(self, parent: Mapping, scope: Mapping) -> Mapping:
        return DotMap(
            {
                "parent": parent,
                "context": scope,
                "path": self._data.paths,
                "args": self._data.args,
                "assets": self._data.assets,
                "subsystems": self._data.subsystems,
                "env": {
                    "platform": sys.platform,
                    "cpu_count": multiprocessing.cpu_count(),
                },
            }
        )

    def _inject_config_str(self, config: str, scope: Mapping) -> str:
        """
        Injects variables into strings.
        ${{ foo.bar }} -> helloworld
        """
        search = CONDITION_REGEX.search(config)
        if not search:
            return config

        for i, group in enumerate(search.groups()):
            # evaluate the expression
            result = self.eval(group, None, scope)
            if not isinstance(result, str):
                raise Exception(
                    f"Expression '{group}' returned illegal value, expressions in strings must return strings"
                )
            config[search.start(i) : search.end(i)] = result
        return config

    def eval(self, condition: str, parent: Mapping, scope: Mapping) -> Any:
        # avoid infinite recusion
        if isinstance(parent, LazyDynamicMapping):
            parent = parent._data

        eval_locals = self._build_eval_locals(parent, scope)
        evaluator = simpleeval.EvalWithCompoundTypes(names=eval_locals)

        result = evaluator.eval(condition)
        # logging.debug(f'\"{cond}\" evaluated to: {result}')

        return result

    def resolve(self, config, scope: Mapping):
        """
        Resolves the stored configuration into literal terms at runtime
        """
        result = config

        if isinstance(config, list):
            result = []
            for _, v in enumerate(config):
                parsed = self.resolve(v, scope)
                if not v or parsed is not None:
                    result.append(parsed)
        elif isinstance(config, str):
            result = self._inject_config_str(config, scope)

        return result


class LazyDynamicBase:
    """
    Base object that allows lazy resolution of configuration data
    """

    def __init__(
        self,
        data=None,
        resolver: DataResolver = None,
        scope: DataResolverScope = None,
        parent=None,
    ):
        self._data = data
        self._resolver = resolver
        self._scope = scope
        self._parent = parent
        self._transform_map = {list: LazyDynamicSequence, dict: LazyDynamicDotMap}

    def _transform_object(self, data):
        eval_locals = self._resolver._build_eval_locals(self, self._scope)
        for k, v in self._transform_map.items():
            if isinstance(data, k):
                resolved = v(data, self._resolver, self._scope, self)
                return resolved
        return self._resolver.resolve(data, eval_locals)

    # transforms
    # test:
    #     {{ foobar == "abcde" }}:
    #         True
    # to
    # test: True
    def _eval_condition(self, toplevel: Mapping) -> Tuple[bool, Any]:
        # we should have a mapping
        if not isinstance(toplevel, Mapping):
            return True, None

        # mapping should only have one key, the cond
        keys = list(toplevel.keys())
        if len(keys) != 1:
            return True, None
        key = keys[0]

        # parse the key name as the expression
        search = CONDITION_REGEX.search(key)
        if not search:
            return True, None
        groups = search.groups()
        if len(groups) != 1:
            return True, None

        result = self._resolver.eval(groups[0], self, self._scope)
        if not isinstance(result, bool):
            raise Exception(
                "Expression '{group}' returned an illegal value, expressions treated as conditions must return a boolean value"
            )
        if result:
            return True, toplevel[key]
        else:
            return False, None


class LazyDynamicSequence(LazyDynamicBase, Sequence):
    """
    Lazy dynamic implementation of Sequence.
    """

    def __init__(
        self,
        data: Sequence = [],
        resolver: DataResolver = None,
        scope: DataResolverScope = None,
        parent=None,
    ):
        super().__init__(data, resolver, scope, parent)

        results = []
        for item in self._data.copy():
            result, value = self._eval_condition(item)
            if result and value:
                results.append(value)
            elif result:
                results.append(item)
        self._data = results

    def __getitem__(self, key):
        return self._transform_object(self._data[key])

    def __len__(self):
        return len(self._data)

    def with_scope(self, scope: DataResolverScope):
        return LazyDynamicSequence(self._data, self._resolver, scope)


class LazyDynamicMapping(LazyDynamicBase, Mapping):
    """
    Lazy dynamic implementation of Mapping.
    """

    def __init__(
        self,
        data: Mapping = {},
        resolver: DataResolver = None,
        scope: DataResolverScope = None,
        parent=None,
    ):
        super().__init__(data, resolver, scope, parent)

        # evaluate our key conditions
        results = {}
        for k, v in self._data.copy().items():
            result, value = self._eval_condition(v)
            if result and value:
                results[k] = value
            elif result:
                results[k] = v
        self._data = results

    def __getitem__(self, key):
        return self._transform_object(self._data.get(key))

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def get(self, key, default=None):
        result = self._data.get(key, default)
        if result is None:
            return None
        return self._transform_object(result)

    def with_scope(self, scope: DataResolverScope):
        return LazyDynamicMapping(self._data, self._resolver, scope)


class LazyDynamicDotMap(LazyDynamicMapping):
    """
    Lazy dynamic implementation of DotMap.
    """

    def __init__(
        self,
        data: Mapping = {},
        resolver: DataResolver = None,
        scope: DataResolverScope = None,
        parent=None,
    ):
        super().__init__(data, resolver, scope, parent)

        dmap = DotMap()
        dmap._map = self._data
        self._data = dmap

    def __getattr__(self, k):
        if k in {
            "_data",
            "_resolver",
            "_scope",
            "_transform_map",
            "_dotmap",
        }:
            return super(self.__class__, self).__getattribute__(k)
        return self._transform_object(self._data.__getattr__(k))

    def with_scope(self, scope):
        return LazyDynamicDotMap(self._data, self._resolver, scope)


class ConfigurationUtilities:
    @staticmethod
    def parse_root_config(root: Path, config: dict) -> dict:
        # validate the root schema
        schema_path = Path(cas.__file__).parent.absolute().joinpath("schemas")
        with open(schema_path.joinpath("root.json"), "r") as f:
            root_schema = json.load(f)
        DefaultValidatingDraft7Validator(root_schema).validate(config)

        # validate all subsystem options
        validators = {}
        for k, job in config.jobs.items():
            for step in job.steps:
                sub_name = step.uses

            if sub_name not in validators:
                sub_path = schema_path.joinpath("subsystems", f"{sub_name}.json")
                if not sub_path.exists():
                    raise Exception(f"unable to find schema for subsystem '{sub_name}'")
                with open(sub_path, "r") as f:
                    validators[sub_name] = DefaultValidatingDraft7Validator(
                        json.load(f)
                    )
            if step.get("with") is None:
                continue
            validators[sub_name].validate(step["with"])

        # setup the dotmap that we'll use to perform lazy resolution
        config = DotMap(config)

        # config.path.root = root # no more root path!!!
        # config.path.content = root.joinpath("content")
        # config.path.game = root.joinpath("game")
        # config.path.src = root.joinpath("src")

        # config.path.devtools = config.path.src.joinpath("devtools")
        # config.path.secrets = config.path.devtools.joinpath("buildsys", "secrets")
        # config.path.vproject = config.path.game.joinpath(
        #    config.options.project
        # ).resolve()

        # create the root resolver and the map
        resolver = DataResolver(config)
        return LazyDynamicDotMap(config.toDict(), resolver)
