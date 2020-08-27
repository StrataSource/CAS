# AssetBuilder

AssetBuilder is a Python toolkit for compiling Source Engine assets.

## Usage
AssetBuilder, by default, expects a certain folder structure to be present. You should have a root folder, containing a `content` folder and a `game` folder. The latter contains your compiled assets, while the former contains your source content.

To configure which assets to build, an `assets.json` file must be present in your `content` folder. An example of this is present in the `examples` folder of this repository.

Example:
```
python3 ./cli.py --path "path/to/your/root/dir" --threads 1
```