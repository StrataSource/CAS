# Chaos Automation System

Chaos Automation System (CAS) is a toolkit for automating complex sequences of tasks; generally, Source engine tasks.

## Usage
CAS, by default, expects a certain folder structure to be present. You should have a root folder for your project, containing a `content` folder and a `game` folder. The former contains your source content, while your latter contains your compiled assets and binaries.

To configure which assets to build, an `assets.json` file must be present in your `content` folder. An example of this is present in the `examples` folder of this repository, which you can copy if you want to provide a template for your project.

You must run CAS from inside your project's root tree; if you need to run it from somewhere else, use the `--path` argument.

Example:
```
python3 -m cas --build-category assets
```

## Configuration

CAS is modular, and has two main types of components: drivers and subsystems.

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
CAS has support for conditional statements to include or exclude segments of configuration whenever a condition is met. Specify the conditions inside the block you want to set as a list with the special `@conditions` key.


CAS also has support for custom expressions with `@expressions`, to dynamically modify parts of configuration on the fly. Specify this as a set with each key you want to modify. It uses the same syntax as conditions.

Example:
```json
"module": "cas.subsystems.syncfolder",
"category": "publish",
"options": {
    "from": "$(path.root)/game",
    "to": "$(path.root)/publish.tmp",

    "create": true,
    "files": [ "!.git" ],

    "@conditions": ["args.build_type != 'trunk'"]
}
```

Note that expressions are always evaluated before conditions in the same block.

### Local scope
Inside conditions and macros a specific set of names are available in the local scope:
- `parent`, the parent object of this value
- `context`, the current resolver scope
- `path`, `args`, `assets`, and `subsystems` from the configuration file
- `env`, a dict containing `platform`, the system platform, and `cpu_count`, the number of system CPUs

## Development
Run the setup script for your platform to install dependencies - either install_deps.bat or install_deps.sh.
