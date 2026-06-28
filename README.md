# zig-std-anki

Zig standard library as an Anki deck through AnkiConnect.

## What It Does

Builds Anki notes from Zig stdlib public methods and declarations.

Each note is meant to be small:

- front: module, method name, signature
- back: short description, usage example, source location, tags

## Fields

- `uid`
- `zig_version`
- `module`
- `fqn`
- `kind`
- `signature`
- `definition`
- `front`
- `back`
- `example`
- `source_path`
- `source_line`
- `tags`

## Usage

Start Anki with AnkiConnect enabled, then run:

Dry run:

```powershell
.\sync.ps1 --dry-run
```

Write to Anki:

```powershell
.\sync.ps1 --write
```

Limit to one module:

```powershell
.\sync.ps1 --write --module std.mem
```
