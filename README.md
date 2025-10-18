
# UV Loop Tools

UV Loop Tools is a Blender add-on that provides utilities for working with UV loops,
including equalize, match3D, and spline-based operations. This repository contains
the add-on source, preferences, and operator implementations.

## Features

- Equalize UV loops (closed and straight-open variants)
- Match 3D ratio distribution for UV loops
- Interactive spline-based UV editing tools

## Installation

1. Copy this folder into Blender's add-ons directory or install via Preferences → Add-ons → Install...
2. Enable the add-on in Blender's Preferences → Add-ons.

## Usage

Open the UV Editor and select faces/edges as required for each operator. Use the
UV menu to run UV Loop Tools operations (Equalize, Match3D, Spline).

## Development

This project is organized as a Python package. To work on it locally:

```powershell
git clone https://github.com/Luma-3D/uv_loop_tools.git
cd uv_loop_tools
# make changes, then
git add -A
git commit -m "Describe changes"
git push
```

## Contributing

If you want to contribute: fork the repository, create a feature branch, and
open a pull request with clear description and screenshots if relevant.

## License

This project is GPL-3.0 or later. See the `LICENSE` file for details.

---

*This README was updated locally and pushed to the repository.*
