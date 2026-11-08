"""Three paired archive baselines on one machine, with explicit UX gates."""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BASELINE = '61754828a85e1cff099c3425e12e0496cb1ef2c1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default=BASELINE)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output-dir', type=Path, default=Path('build/workflow-polish/performance'))
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    before, after = [], []
    env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
    with tempfile.TemporaryDirectory(prefix='biliflow-paired-baseline-') as directory:
        snapshot = Path(directory)
        archive = snapshot / 'baseline.tar'
        with archive.open('wb') as handle:
            subprocess.run(['git', 'archive', '--format=tar', args.baseline_ref], cwd=root, stdout=handle, check=True)
        baseline = snapshot / 'source'
        baseline.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(baseline, filter='data')
        for n in range(1, args.runs + 1):
            for label, source_root, results in (('before', baseline, before), ('after', root, after)):
                report = output / f'{label}-{n}.json'
                print(f'Pair {n}/{args.runs}: {label}', flush=True)
                subprocess.run([sys.executable, '-m', 'scripts.benchmark_archive', '--output', str(report)], cwd=source_root, env=env, check=True)
                results.append(json.loads(report.read_text(encoding='utf-8')))
    medians = {key: round(statistics.median(row[key] for row in after), 1) for key in after[0] if isinstance(after[0][key], (int, float))}
    old_check = statistics.median(row['background_check_ms'] for row in before)
    improvement = 1 - medians['background_check_ms'] / old_check
    gates = {
        'queue_search_p95_ms': 300, 'queue_selection_p95_ms': 300,
        'batch_search_p95_ms': 300, 'batch_selection_p95_ms': 300,
        'queue_population_ms': 2000, 'batch_population_ms': 2000,
        'file_search_p95_ms': 300, 'file_selection_p95_ms': 300,
        'steady_heartbeat_max_ms': 250, 'file_population_ms': 2000,
        'final_refresh_ms': 2000, 'cancel_finish_ms': 1000, 'cancel_feedback_ms': 100,
    }
    worst = {key: max(row[key] for row in after) for key in gates}
    failures = [f'{key}: {worst[key]} ms > {limit} ms' for key, limit in gates.items() if worst[key] > limit]
    if sys.platform == 'win32' and improvement < .5:
        failures.append(f'Windows background-check reduction {improvement:.1%} < 50%')
    result = {
        'baseline': args.baseline_ref,
        'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root, text=True).strip()),
        'platform': platform.platform(), 'paired_runs': args.runs,
        'baseline_check_median_ms': round(old_check, 1),
        'after_medians': medians, 'check_reduction': round(improvement, 4),
        'worst_after_ms': worst, 'limits_ms': gates, 'failures': failures, 'passed': not failures,
        'fixture': 'Synthetic one-byte media; measures database/UI overhead, not real media throughput',
    }
    (output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
