# AssetBuilder

AssetBuilder is a Python toolkit for compiling Source Engine assets.

## Usage
AssetBuilder, by default, expects a certain folder structure to be present. You should have a root folder, containing a `content` folder and a `game` folder. The latter contains your compiled assets, while the former contains your source content.

To configure which assets to build, an `assets.json` file must be present in your `content` folder. An example of this is present in the `examples` folder of this repository.

Example:
```
python3 ./cli.py --path "path/to/your/root/dir" --threads 1
```

## Configuration

AssetBuilder is modular, and has two main types of components: drivers and subsystems.

### Drivers
Drivers handle building individual files that typically have a single input file and one or more output files. For speed, all input dependencies are hashed to avoid unnecessary rebuilds.

An example of a driver is `model` - this takes a .mc or .qc input file and outputs a .mdl file.

### Subsystems
Subsystems handle actions that are unpredictable, have many side effects, or behaviour that cannot be handled by drivers.

An example of a subsystem is `vpk` - this allows packing several files into one or more VPK archives.