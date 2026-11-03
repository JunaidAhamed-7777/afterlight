"""Render a publication figure from the verified static study pack, never traffic.

Use the separate plot environment. Actual data must already have passed the
read-only study exporter; no fixture, default metric or result fallback exists.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import re
from statistics import mean


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def logical_sha256(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError('Figure input is a symlink or exceeds its declared byte bound')
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError('Figure input grew past its byte bound')
    return data


def load_verified_pack(directory: Path) -> dict:
    """Check source/report bindings and every plotted value, without a rollout."""
    directory = directory.resolve(strict=True)
    manifest_bytes = bounded(directory/'manifest.json', 16*1024)
    manifest = json.loads(manifest_bytes)
    if manifest['schema'] != 'afterlight.study-summary-manifest.v1' or manifest['url'] != 'summary.json':
        raise ValueError('Expected the read-only study summary manifest')
    summary_bytes = bounded(directory/'summary.json', 1024*1024)
    if sha256(summary_bytes) != manifest['sha256'] or len(summary_bytes) != manifest['bytes']:
        raise ValueError('Summary bytes differ from the verified pack manifest')
    summary = json.loads(summary_bytes)
    if (summary['schema'] != 'afterlight.study-summary.v1' or
            summary['status'] != 'audited_released_test_evidence' or
            summary['scope'] != 'offline_cached_candidate_selection' or
            summary['mode'] not in {'learned', 'baseline_only'} or
            summary['automatic_benefit_claim'] is not False):
        raise ValueError('Only an audited offline released study can be plotted')

    def companion(kind: str) -> tuple[dict, str]:
        matches = [item for item in summary['artifacts'] if item['kind'] == kind]
        if len(matches) != 1:
            raise ValueError('Missing or duplicate plot proof companion: '+kind)
        item = matches[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.json', item['url']):
            raise ValueError('Expected a flat local proof companion name')
        data = bounded(directory/item['url'], 4*1024*1024)
        if len(data) != item['bytes'] or sha256(data) != item['sha256']:
            raise ValueError('Proof companion checksum/length differs: '+kind)
        return json.loads(data), item['sha256']

    report, report_file_sha = companion('report')
    study, _ = companion('study')
    if (report['sha256'] != logical_sha256(report['report']) or
            report['sha256'] != summary['provenance']['report_sha256'] or
            report_file_sha != summary['provenance']['report_file_sha256'] or
            study['sha256'] != logical_sha256(study['study']) or
            study['sha256'] != summary['provenance']['study_sha256']):
        raise ValueError('Logical report/study or exact report-file identity differs')
    body = report['report']
    if body['mode'] != summary['mode'] or body['status'] != summary['status'] or body['automatic_benefit_claim'] is not False:
        raise ValueError('Summary release mode differs from the original report')
    for field in ('study_sha256', 'protocol_sha256', 'selection_sha256', 'release_sha256', 'test_attempt_sha256'):
        if body[field] != summary['provenance'][field]:
            raise ValueError('Summary identity differs from original report: '+field)
    splits = Counter(item['split'] for item in study['study']['episodes'])
    if any(summary['counts'][split] != splits[split] for split in ('train', 'validation', 'test')):
        raise ValueError('Summary split counts differ from frozen study inventory')
    expected_ids = ['learned-vs-fixed', 'learned-vs-analytical'] if summary['mode'] == 'learned' else ['analytical-vs-fixed']
    if [item['id'] for item in summary['comparisons']] != expected_ids or set(body['comparisons']) != set(expected_ids):
        raise ValueError('The plot requires the entire frozen comparator set')
    for comparison in summary['comparisons']:
        original = body['comparisons'][comparison['id']]
        mapping = {'mean_delta_j_s': 'conditional_mean_delta_j_s', 'episodes': 'episodes',
                   'paired_feasible_episodes': 'paired_feasible_episodes', 'selected_failures': 'selected_failures',
                   'comparator_failures': 'comparator_failures', 'demand_groups': 'demand_groups'}
        if any(comparison[key] != original[field] for key, field in mapping.items()):
            raise ValueError('A plotted summary statistic differs from the original report')
        if comparison['interval_95_j_s'] != original['uncertainty']['interval'] or comparison['interval_groups'] != original['uncertainty']['groups']:
            raise ValueError('A plotted interval differs from the original grouped bootstrap')
        for target, field in [('mean_delta_ambulance_s', 'conditional_delta_ambulance_s'), ('mean_delta_civilian_s', 'civilian_delta_s')]:
            values = [row[field] for row in original['records'] if row[field] is not None]
            if comparison[target] != (mean(values) if values else None):
                raise ValueError('A plotted time difference differs from the paired report records')
        finite_values = [comparison['mean_delta_j_s'], *(comparison['interval_95_j_s'] or [])]
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)) for value in finite_values):
            raise ValueError('Plot statistics must be finite or explicitly unavailable')
    return {'summary': summary, 'report': body, 'manifest_sha256': sha256(manifest_bytes),
            'summary_sha256': sha256(summary_bytes), 'report_file_sha256': report_file_sha}


def render(evidence: dict, output: Path, *, accent: str, background: str, ink: str) -> dict:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import is_color_like
    import numpy

    if not all(is_color_like(color) for color in (accent, background, ink)):
        raise ValueError('Figure palette must contain valid colors')
    summary = evidence['summary']
    matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                               'svg.hashsalt': evidence['summary_sha256'], 'figure.facecolor': background,
                               'axes.facecolor': background, 'text.color': ink,
                               'axes.labelcolor': ink, 'xtick.color': ink, 'ytick.color': ink})
    rows = summary['comparisons']
    figure, axes = plt.subplots(figsize=(12.4, 6.2), dpi=180)
    figure.subplots_adjust(left=.29, right=.69, top=.70, bottom=.28)
    figure.text(.045, .91, 'Held-out selector comparisons', fontsize=21, weight='bold')
    counts = summary['counts']
    figure.text(.045, .845, f"{counts['train']} training · {counts['validation']} validation · {counts['test']} test scenarios · {counts['test_demand_groups']} independent test groups", fontsize=10)
    values = [0.]
    for item in rows:
        values.extend(item['interval_95_j_s'] or [])
        if item['mean_delta_j_s'] is not None: values.append(item['mean_delta_j_s'])
    low, high = min(values), max(values)
    padding = max(1., (high-low)*.22)
    axes.set_xlim(low-padding, high+padding)
    axes.set_ylim(-.55, len(rows)-.45)
    axes.axvline(0, color=ink, alpha=.55, lw=1)
    axes.grid(axis='x', color=ink, alpha=.10, lw=.7)
    axes.set_axisbelow(True)
    for spine in axes.spines.values(): spine.set_visible(False)
    axes.tick_params(axis='y', length=0, pad=18)
    axes.tick_params(axis='x', length=0, pad=8)
    labels = []
    for index, item in enumerate(rows):
        y = len(rows)-1-index
        labels.append(f"{item['selected_label']}\nvs {item['comparator_label']}")
        value, interval = item['mean_delta_j_s'], item['interval_95_j_s']
        if value is not None:
            if interval is not None:
                axes.plot(interval, [y, y], color=accent, lw=3, solid_capstyle='round')
                axes.plot(interval, [y, y], '|', color=accent, markersize=12, markeredgewidth=1.5)
            axes.plot(value, y, 'o', color=accent, markersize=8, markeredgecolor=background, markeredgewidth=1.5)
            value_label = f"{value:+.2f} s"
            interval_label = f"95% interval [{interval[0]:+.2f}, {interval[1]:+.2f}]" if interval is not None else '95% interval unavailable'
        else:
            value_label, interval_label = 'No paired complete outcomes', '95% interval unavailable'
        y_min, y_max = axes.get_ylim()
        position = (y-y_min)/(y_max-y_min)
        axes.text(1.055, position+.055, value_label, transform=axes.transAxes, fontsize=13, weight='bold', va='center')
        axes.text(1.055, position-.025, interval_label, transform=axes.transAxes, fontsize=8.5, va='center')
        axes.text(1.055, position-.105,
                  f"Pairs {item['paired_feasible_episodes']}/{item['episodes']} · unavailable {item['selected_failures']} vs {item['comparator_failures']}",
                  transform=axes.transAxes, fontsize=8.5, va='center')
    axes.set_yticks(range(len(rows)), list(reversed(labels)), fontsize=10)
    axes.set_xlabel('Selected minus comparator objective (seconds)', labelpad=15)
    figure.text(.045, .15, 'Negative values favor the selected policy. Points and intervals are conditional on both outcomes completing validly.', fontsize=9)
    figure.text(.045, .095, 'Objective = ambulance journey + all-demand mean civilian excess time. Intervals use whole-demand-group resampling.', fontsize=8.3)
    figure.text(.045, .045, 'Offline selection among cached real SUMO outcomes · failures retained · no automatic improvement or safety claim', fontsize=8.3)
    output.mkdir(parents=True, exist_ok=False)
    try:
        figure.savefig(output/'study-comparisons.png', facecolor=background, metadata={'Software': 'AFTERLIGHT verified study figure'})
        figure.savefig(output/'study-comparisons.svg', facecolor=background, metadata={'Date': None})
        # Canonical text bytes keep the generated SVG hash stable under Git's
        # source LF policy; this does not change its vector shapes or values.
        svg = output/'study-comparisons.svg'
        svg.write_bytes(svg.read_bytes().replace(b'\r\n', b'\n'))
    finally:
        plt.close(figure)
    caption = f"Frozen offline study: {counts['test']} test scenarios / {counts['test_demand_groups']} independent demand groups. Signed conditional mean objective differences with 95% grouped intervals when eligible. Unavailable objectives and paired denominators are shown; no live controller or automatic benefit claim."
    (output/'caption.txt').write_text(caption+'\n', encoding='utf-8', newline='\n')
    manifest = {'schema': 'afterlight.study-figure.v1', 'scope': 'Visualization only; no simulation, fitting or selector tuning.',
                'renderer_source_sha256': sha256(Path(__file__).read_bytes()),
                'source_summary_sha256': evidence['summary_sha256'], 'source_pack_manifest_sha256': evidence['manifest_sha256'],
                'source_report_file_sha256': evidence['report_file_sha256'],
                'python': platform.python_version(), 'matplotlib': matplotlib.__version__, 'numpy': numpy.__version__,
                'palette': dict(accent=accent, background=background, ink=ink),
                'files': {name: {'sha256': sha256((output/name).read_bytes()), 'bytes': (output/name).stat().st_size}
                          for name in ('study-comparisons.png', 'study-comparisons.svg', 'caption.txt')}}
    (output/'render-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--accent', default='#167d73')
    parser.add_argument('--background', default='#f8f6f1')
    parser.add_argument('--ink', default='#193331')
    args = parser.parse_args()
    pack, output = args.pack.resolve(strict=True), args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    runtime = checkout/'local-runtime'
    if runtime.is_symlink() or not runtime.resolve().is_relative_to(checkout) or output.parent != runtime.resolve():
        raise ValueError('Figure output must be a fresh direct child of the main checkout local-runtime')
    if output == pack or output.is_relative_to(pack) or pack.is_relative_to(output):
        raise ValueError('Figure output cannot overlap the original verified proof pack')
    if output.exists(): raise FileExistsError('Figure output must be a new directory')
    evidence = load_verified_pack(pack)
    manifest = render(evidence, output, accent=args.accent, background=args.background, ink=args.ink)
    print(json.dumps({'output': str(output), **manifest}, indent=2))


if __name__ == '__main__': main()
