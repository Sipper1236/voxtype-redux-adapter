#!/usr/bin/env python3
"""Summarize available benchmark JSON records without prescribing a winner."""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def median(values):
    values = [v for v in values if number(v)]
    return statistics.median(values) if values else None


def records(document, fallback):
    """Yield model/case rows from completed runs, partial runs or tuning lists."""
    if isinstance(document, list):
        for index, item in enumerate(document):
            if isinstance(item, dict):
                if 'cases' in item:
                    yield from records(item, fallback)
                elif isinstance(item.get('seconds'), list):
                    name = item.get('name', fallback)
                    if 'pool_threads' in item:
                        name += f" [pool_threads={item['pool_threads']}]"
                    for seconds in item['seconds']:
                        yield name, dict(item, id=item.get('id', 'thread-sweep'),
                                         inference_seconds=seconds), None
                else:
                    yield item.get('name', 'stock-verify-'+item['model'] if 'model' in item else fallback), item, None
    elif isinstance(document, dict):
        name = document.get('name', fallback)
        peak = document.get('sampled_peak_rss_mib', document.get('peak_rss_mib'))
        if isinstance(document.get('cases'), list):
            for case in document['cases']:
                if isinstance(case, dict):
                    yield name, case, peak
        elif any(key in document for key in ('inference_seconds', 'wall_seconds')):
            yield name, document, peak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path,
                        default=Path(os.environ.get('VOXTYPE_BENCH_RESULTS_DIR', str(ROOT / 'results'))))
    parser.add_argument('--output-dir', type=Path, help='Write reports here instead of changing the input directory')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_dir():
        parser.error(f'results directory does not exist: {directory}')
    output = args.output_dir.resolve() if args.output_dir else directory
    output.mkdir(parents=True, exist_ok=True)
    rows, notes = [], []
    for path in sorted(directory.glob('*.json')):
        if path.name.endswith('.partial.json') and path.with_name(path.name.replace('.partial.json', '.json')).exists():
            continue  # Final run includes its checkpoint rows; never count both.
        try:
            document = json.loads(path.read_text())
        except (ValueError, OSError) as error:
            notes.append(f'Skipped {path.name}: {error}')
            continue
        if isinstance(document, dict) and document.get('error'):
            notes.append(f"{path.name} reports an error: {document['error']}")
        count = 0
        for name, case, peak in records(document, path.stem.removesuffix('.partial')):
            latency = case.get('inference_seconds', case.get('wall_seconds'))
            if case.get('ok') is False or case.get('exit_code', 0) != 0 or not number(latency) or latency < 0:
                continue
            wer = case.get('wer')
            if not number(wer) and number(case.get('word_errors')) and number(case.get('reference_words')) and case['reference_words'] > 0:
                wer = case['word_errors'] / case['reference_words']
            peak = case.get('sampled_peak_rss_mib', case.get('peak_rss_mib', peak))
            rows.append({'configuration': str(name), 'case': str(case.get('id', 'unspecified')),
                         'audio_seconds': case.get('audio_seconds'), 'latency_seconds': latency,
                         'word_errors': case.get('word_errors'), 'reference_words': case.get('reference_words'),
                         'wer': wer if number(wer) else None,
                         'peak_rss_mib': peak if number(peak) else None,
                         'text': case.get('text', ''), 'source': path.name})
            count += 1
        if not count:
            notes.append(f'No successful timed case records in {path.name}.')
    groups = {}
    for row in rows:
        groups.setdefault((row['configuration'], row['case']), []).append(row)
    summary = []
    for (configuration, case), trials in sorted(groups.items()):
        peaks = [r['peak_rss_mib'] for r in trials if number(r['peak_rss_mib'])]
        summary.append({'configuration': configuration, 'case': case, 'runs': len(trials),
                        'audio_seconds_median': median([r['audio_seconds'] for r in trials]),
                        'latency_seconds_median': median([r['latency_seconds'] for r in trials]),
                        'wer_median': median([r['wer'] for r in trials]),
                        'wer_runs': sum(number(r['wer']) for r in trials),
                        'peak_rss_mib': max(peaks) if peaks else None})
    measurement_fields = ['configuration', 'case', 'audio_seconds', 'latency_seconds', 'word_errors',
                          'reference_words', 'wer', 'peak_rss_mib', 'text', 'source']
    summary_fields = ['configuration', 'case', 'runs', 'audio_seconds_median', 'latency_seconds_median',
                      'wer_median', 'wer_runs', 'peak_rss_mib']
    for filename, values, fields in [('measurements.csv', rows, measurement_fields), ('summary.csv', summary, summary_fields)]:
        with (output / filename).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    def fmt(value):
        return '—' if value is None else f'{value:.3f}'
    def escape(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# Benchmark results', '', f'{len(rows)} successful timed trials across {len(groups)} configuration/case pairs.', '',
             'Medians summarize only the records present. Missing WER/RSS remains blank in CSV and is shown as — below. '
             'Peak RSS is the maximum reported peak; run-level peaks apply to every case in that run. '
             'Timing boundaries, loading policy and memory scope can differ between runners; inspect source JSON before comparing. '
             'Partial checkpoints are included only when no matching final JSON exists.', '',
             '| Configuration | Case | Runs | Audio s | Median latency s | Median WER | WER runs | Peak RSS MiB |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in summary:
        wer = '—' if row['wer_median'] is None else f"{row['wer_median'] * 100:.2f}%"
        cells = [escape(row['configuration']), escape(row['case']), str(row['runs']),
                 fmt(row['audio_seconds_median']), fmt(row['latency_seconds_median']), wer,
                 str(row['wer_runs']), fmt(row['peak_rss_mib'])]
        lines.append('| ' + ' | '.join(cells) + ' |')
    if notes:
        lines += ['', '## Input notes', ''] + ['- ' + escape(note) for note in notes]
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(f'Wrote REPORT.md, measurements.csv and summary.csv in {output}')
    for note in notes:
        print(note, file=sys.stderr)


if __name__ == '__main__':
    main()
