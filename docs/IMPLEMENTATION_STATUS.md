# Implementation checkpoints

This document distinguishes source implementation from execution evidence. All
acceptance testing and simulation experiments are performed on the owner's Omen
Windows PC; cloud code review/build is not an acceptance result.

## Initial source checkpoint

- Shared frozen-lead scheduling and conservative legal transition state machine.
- Local-only recordings API with catalog allow-list and path confinement.
- Unit checks written for timing, finite hold, ordinary-world isolation and API boundaries.
- Official SUMO 1.28.0 dependencies pinned for the Python 3.12 acceptance environment.
- **Not yet executed:** unit tests, SUMO conversion/runs, product browser acceptance.
- **Not yet available:** measured benchmark, trained model, real replay catalog.

The API currently serves recordings only; generation requests explicitly fail as
unimplemented rather than returning fictional progress. Subsequent checkpoints
will wire the real runner and record actual Omen results.

## Omen commands — pending execution

From `C:\Github\afterlight` in PowerShell:

```powershell
& 'C:\Users\Junaid\AppData\Roaming\uv\python\cpython-3.12.15-windows-x86_64-none\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sim.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests/sim -v
.\.venv\Scripts\python.exe -m unittest discover -s tests/api -v
```

Do not infer success from these instructions. Record command, source commit,
environment, output, pass/fail and untested scope after real execution.

Official package source: https://pypi.org/project/eclipse-sumo/1.28.0/

## Local acceptance evidence

See [Omen validation log](validation/OMEN_LOG.md) for scoped actual results and
known failures. A newer source commit does not inherit a prior test pass. The
first real fixture/city run remains blocked until packaged SUMO executable
discovery and local regression checks succeed.
