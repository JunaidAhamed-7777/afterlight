"""Print scoped Python/SUMO installation diagnostics; does not run an experiment."""
from __future__ import annotations
import importlib.metadata
import json
import os
import sys
from sim.network import binary_candidates


def inspect_environment() -> dict:
    versions = {}
    for name in ('eclipse-sumo','sumo-data','traci','sumolib'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {'python':sys.executable,'version':sys.version,'prefix':sys.prefix,'sumo_home':os.environ.get('SUMO_HOME'),'packages':versions,
            'executables':{name:[{'path':str(path),'exists':path.is_file()} for path in binary_candidates(name)]
                           for name in ('sumo','netconvert')}}


if __name__=='__main__':
    print(json.dumps(inspect_environment(),indent=2))
