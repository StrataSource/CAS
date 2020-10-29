# AssetBuilder

AssetBuilder is a Python toolkit for compiling Source Engine assets.

## Usage
AssetBuilder, by default, expects a certain folder structure to be present. You should have a root folder for your project, containing a `content` folder and a `game` folder. The latter contains your compiled assets, while the former contains your source content.

To configure which assets to build, an `assets.json` file must be present in your `content` folder. An example of this is present in the `examples` folder of this repository, which you can copy if you want to provide a template for your project.

You must run AssetBuilder from inside your root folder; if you need to run it from somewhere else, use the `--path` argument.

Example:
```
python3 ./cli.py --build-category assets
```

## Configuration

AssetBuilder is modular, and has two main types of components: drivers and subsystems.

### Drivers
Drivers handle building individual files that typically have a single input file and one or more output files. For speed, all input dependencies are hashed to avoid unnecessary rebuilds.

An example of a driver is `model` - this takes a .mc or .qc input file and outputs a .mdl file.

### Subsystems
Subsystems handle actions that are unpredictable, have many side effects, or behaviour that cannot be handled by drivers.

An example of a subsystem is `vpk` - this allows packing several files into one or more VPK archives.

### Build Types and Categories
The **build type** (`--build-type`) selects the type of the build you want to perform. This may be one of three values: trunk, staging, or release, and mirrors a multi-branch Git philosophy. The behaviour of this differs depending on the asset or subsystem implementation.

The **build categories** (`--build-categories`) define whether assets should be built and what subsystems should run, if any. The default is to build all categories if one is not explicitly specified. If a category different from `assets` is specified, assets will not be built. The categories of a subsystem can be defined with the `categories` key.

### Expressions and Conditions
AssetBuilder has support for conditional statements to include or exclude segments of configuration whenever a condition is met.

Specify the conditions inside the block you want to set as a list with the special `@conditions` key.
Inside, you may use Python expression syntax.

There are three special functions you can use to retrieve data for use in expressions:
- `context(key, default)`: gets the value of the a key in the current build context
- `config(key, default)`: gets the value of a key in the global configuration store
- `parent(key, default)`: gets the value of a key in the same configuration block

AssetBuilder also has support for custom expressions with `@expressions`, to dynamically modify parts of configuration on the fly. Specify this as a set with each key you want to modify. It uses the same syntax as conditions.

Example:
```json
"module": "assetbuilder.subsystems.syncfolder",
"category": "publish",
"options": {
    "from": "$(path.root)/game",
    "to": "$(path.root)/publish.tmp",

    "create": true,
    "files": [ "!.git" ],

    "@conditions": ["config('args.build_type') != 'trunk'"]
}
```

Note that expressions are always evaluated before conditions in the same block.

### Globals
There is a limited set of globals you can reference in conditional statements (with `R('foo.bar')`) and strings (with `$(foo.bar)`).
- `path.root`: The root path of your workspace.
- `path.content`: The content directory. Defaults to `$(path.root)/content`.
- `path.game`: The game directory. Defaults to `$(path.root)/game`.
- `path.src`: The source code directory. Defaults to `$(path.root)/src`.
- `path.secrets`: The directory that contains build secrets.
- `args`: All arguments passed in to the build system.
- `assets`: The value of the `assets` key in the configuration file.
- `subsystems`: The value of the `subsystems` key in the configuration file.

## Development
Run the setup script for your platform to install dependencies - either install_deps.bat or install_deps.sh.
