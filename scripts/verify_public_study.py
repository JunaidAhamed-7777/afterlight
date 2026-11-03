"""Recompute the proof and frozen choices of an explicitly released public Study.

Uses Python's standard library only. No private input path, simulator, browser,
model fitting, release action or unpublished-data fallback is supported.
"""
from __future__ import annotations

if not __debug__:
    raise SystemExit('Public Study verification refuses optimized Python: run without -O, -OO or PYTHONOPTIMIZE.')

import argparse
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import platform
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def seconds(value):
    return 'Unavailable' if value is None else f'{value:+.3f} s'


def main():
    # Preserve published labels in Windows pipes as well as native terminals.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True, help='Public HTTPS viewer URL, or HTTP loopback publication')
    parser.add_argument('--released-manifest-sha256', required=True, help='Exact manifest SHA recorded by the completed audited release')
    parser.add_argument('--output', type=Path, help='Optional fresh JSON report; never overwrites an existing path')
    args = parser.parse_args()
    try:
        address = urlsplit(args.base_url)
        address.port  # Reject malformed ports before importing or calling proof helpers.
        valid_url = (address.scheme == 'https' and address.hostname or
                     address.scheme == 'http' and address.hostname in {'localhost', '127.0.0.1', '::1'})
        if not valid_url or address.username or address.password or address.query or address.fragment:
            parser.error('Use an explicit public HTTPS or HTTP loopback base URL without credentials, query or fragment')
    except ValueError:
        parser.error('The base URL is malformed')
    manifest_sha = args.released_manifest_sha256.lower()
    if not re.fullmatch(r'[a-f0-9]{64}', manifest_sha): parser.error('The released manifest SHA-256 must contain exactly 64 hexadecimal characters')
    if args.output is not None and (args.output.exists() or args.output.is_symlink()): parser.error('The JSON output path already exists; choose a fresh path')
    output = args.output.resolve() if args.output else None
    if output is not None and (output.exists() or output.is_symlink()): parser.error('The JSON output path already exists; choose a fresh path')
    if output is not None and not output.parent.is_dir(): parser.error('The JSON output parent directory must already exist')

    helper_path = ROOT / 'web/tests/released_study_pack.py'
    spec = spec_from_file_location('afterlight_public_study_verifier', helper_path)
    if spec is None or spec.loader is None: parser.exit(1, 'Verification failed: local proof helper is unavailable\n')
    helper = module_from_spec(spec)
    try:
        helper_bytes = helper_path.read_bytes()
        # Execute the exact local source bytes recorded below, not a timestamp-
        # valid .pyc that could describe a different helper implementation.
        exec(compile(helper_bytes, str(helper_path), 'exec', dont_inherit=True), helper.__dict__)
        pack = helper.load_released_public_pack(args.base_url.rstrip('/') + '/', manifest_sha)
        summary = pack['summary']; verified = pack['verification']
        result = {'schema': 'afterlight.public-study-verification.v1', 'status': 'passed',
                  'verified_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                  'entrypoint_sha256': helper.sha(Path(__file__).read_bytes()), 'helper_sha256': helper.sha(helper_bytes),
                  'publication': pack}
        if output is not None:
            with output.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    except Exception as error:
        parser.exit(1, 'Verification failed: ' + str(error) + '\n')

    counts = summary['counts']
    print('Public Study proof verified: ' + pack['manifest_sha256'])
    print(f"Episodes train/validation/test: {counts['train']}/{counts['validation']}/{counts['test']}; test worlds: {counts['test_worlds']}; demand groups: {counts['test_demand_groups']}.")
    print(f"Mode: {summary['mode']}; simulation source: {summary['provenance']['source_commit']}.")
    for comparison in summary['comparisons']:
        print(f"{comparison['selected_label']} vs {comparison['comparator_label']}: {comparison['paired_feasible_episodes']}/{comparison['episodes']} paired; failures selected {comparison['selected_failures']}, comparator {comparison['comparator_failures']}; delta J {seconds(comparison['mean_delta_j_s'])}; ambulance {seconds(comparison['mean_delta_ambulance_s'])}; civilian {seconds(comparison['mean_delta_civilian_s'])}.")
        interval = comparison['interval_95_j_s']
        interval_text = (seconds(interval[0]) + ' to ' + seconds(interval[1])) if interval is not None else 'Unavailable: ' + comparison['interval_reason']
        print(f"  95% grouped interval: {interval_text}; independent groups: {comparison['interval_groups']}.")
    amended = verified['analysis_amendment']['present']
    grids = len(verified['public_reproduction']['decoded_grids'])
    print(f"Proof: {len(pack['companions'])} companion hashes, {grids} bounded original grids, exclusive claim metadata reconciled, frozen choices and statistics recomputed; analysis amendment {'verified' if amended else 'absent'}.")
    print('Scope: offline cached choices; deltas are selected minus comparator, conditional on both completing. Metadata does not independently prove test nonaccess.')
    if output is not None: print('JSON report: ' + str(output))


if __name__ == '__main__': main()
