import cas
import cas.common.utilities as utilities

import sys
import json
import multiprocessing
from collections.abc import Sequence, Mapping
from pathlib import Path

import simpleeval
import jsonschema
from dotmap import DotMap


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

    def get_subsystem_output(self, subsystem: str, output: str):
        return self._data.subsystems[subsystem].outputs[output]

    def exclude_subsystem_input_files(self, subsystem: str, root: Path):
        files = self.get_subsystem_output(subsystem, "files")
        return utilities.rglob_invert(utilities.relative_paths(root, files))


class DataResolver:
    """
    Class that actually does the configuration resolution
    """

    def __init__(self, data: Mapping):
        self._data = data

    def build_eval_locals(self, parent: Mapping, scope: DataResolverScope) -> Mapping:
        return DotMap(
            {
                "parent": parent,
                "context": scope,
                "path": self._data.path,
                "args": self._data.args,
                "assets": self._data.assets,
                "subsystems": self._data.subsystems,
                "env": {
                    "platform": sys.platform,
                    "cpu_count": multiprocessing.cpu_count(),
                },
            }
        )

    def _inject_config_str(self, config: str, eval_locals: Mapping) -> str:
        """
        A terrible lexical parser for interpolated globals.
        I.e. "build type: $(args.build)" returns "build type: trunk"
        """
        prev = None
        inblock = False
        current = ""
        result = ""

        for c in config:
            if c == "$":
                prev = c
                continue
            if not inblock and c == "(" and prev == "$":
                # read to end for key
                inblock = True
            elif inblock and c == ")":
                value = utilities.get_dotpath_value(current, eval_locals)
                if value is None:
                    raise Exception(
                        f"Value of configuration variable $({current}) was None"
                    )
                result += str(value)

                current = ""
                inblock = False
            elif inblock:
                current += c
            else:
                result += c
            prev = c
        return result

    def eval(self, condition: str, parent: Mapping, scope: DataResolverScope) -> bool:
        # avoid infinite recusion
        if isinstance(parent, LazyDynamicMapping):
            parent = parent._data

        eval_locals = self.build_eval_locals(parent, scope)

        injected = self._inject_config_str(condition, eval_locals)
        evaluator = simpleeval.EvalWithCompoundTypes(names=eval_locals)

        result = evaluator.eval(injected)
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
        eval_locals = self._resolver.build_eval_locals(self, self._scope)
        for k, v in self._transform_map.items():
            if isinstance(data, k):
                resolved = v(data, self._resolver, self._scope, self)
                return resolved
        return self._resolver.resolve(data, eval_locals)


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
        self._expressions = self._data.get("@expressions", {})
        self._conditions = self._data.get("@conditions", {})

        # strip special members and members that don't match conditions immediately
        self._data = {k: v for k, v in self._data.items() if self._eval_condition(k)}

    def _eval_condition(self, key: str):
        if key in {"@expressions", "@conditions"}:
            return False
        condition = self._conditions.get(key)
        if isinstance(condition, str) and not self._resolver.eval(
            condition, self, self._scope
        ):
            return False
        return True

    def _transform_kv(self, key: str, value):
        """
        Evaluates @expressions and @conditions on a key
        """
        expression = self._expressions.get(key)
        if isinstance(expression, str):
            value = self._resolver.eval(expression, self, self._scope)

        return self._transform_object(value)

    def __getitem__(self, key):
        return self._transform_kv(key, self._data.get(key))

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def get(self, key, default=None):
        result = self._data.get(key, default)
        if result is None:
            return None

        return self._transform_kv(key, result)

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
            "_expressions",
            "_conditionals",
            "_dotmap",
        }:
            return super(self.__class__, self).__getattribute__(k)
        return self._transform_kv(k, self._data.__getattr__(k))

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
        prefix = "cas.subsystems."
        for k, subsystem in config["subsystems"].items():
            if k in {"@conditions", "@expressions"}:
                continue

            module = subsystem.module

            # validating third-party subsystems is not supported yet
            if not module.startswith(prefix):
                continue
            sub_name = module[len(prefix) :]

            if sub_name not in validators:
                sub_path = schema_path.joinpath("subsystems", f"{sub_name}.json")
                if not sub_path.exists():
                    raise Exception(f"unable to find schema for subsystem '{sub_name}'")
                with open(sub_path, "r") as f:
                    validators[sub_name] = DefaultValidatingDraft7Validator(
                        json.load(f)
                    )
            if subsystem.get("options") is None:
                continue
            validators[sub_name].validate(subsystem.options)

        # setup the dotmap that we'll use to perform lazy resolution
        config = DotMap(config)

        config.path.root = root
        config.path.content = root.joinpath("content")
        config.path.game = root.joinpath("game")
        config.path.src = root.joinpath("src")

        config.path.devtools = config.path.src.joinpath("devtools")
        config.path.secrets = config.path.devtools.joinpath("buildsys", "secrets")
        config.path.vproject = config.path.game.joinpath(
            config.options.project
        ).resolve()

        # create the root resolver and the map
        resolver = DataResolver(config)
        return LazyDynamicDotMap(config.toDict(), resolver)
