"""Fit/evaluate a small vocal-activity model on official MUSDB 7-second excerpts.

Audio stays outside the checkout. Requires ffmpeg and scikit-learn for research,
not runtime. Splits are by track; the official test subset is never used to fit
models or select the threshold. Labels come from stem energy, not human lead-
vocal annotations. Use --fit to create a new model; never overwrite an existing one.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rated_rip.vocals import VocalFeatureExtractor, VocalModel, VocalTracker

VALIDATION = {'Actions - One Minute Smile', 'Clara Berry And Wooldog - Waltz For My Victims',
              'Johnny Lokke - Promises & Lies', 'Patrick Talbot - A Reason To Leave',
              'Triviul - Angelsaint', 'Alexander Ross - Goodbye Bolero', 'Fergessen - Nos Palpitants',
              'Leaf - Summerghost', 'Skelpolu - Human Mistakes', 'Young Griffo - Pennies',
              'ANiMAL - Rockshow', 'James May - On The Line', 'Meaxic - Take A Step',
              'Traffic Experiment - Sirens'}
FEATURE_HASH = hashlib.sha256(inspect.getsource(VocalFeatureExtractor).encode()).hexdigest()


def extract(path, cache):
    identity = hashlib.sha256((path.parent.name + '/' + path.name + FEATURE_HASH).encode()).hexdigest()[:20]
    target = cache / (identity + '.npz')
    if target.exists():
        return target
    # Merge stereo accompaniment and stereo vocal into four interleaved channels.
    command = ['ffmpeg', '-v', 'error', '-threads', '1', '-i', str(path), '-filter_complex_threads', '1',
               '-filter_complex', '[0:a:1][0:a:2][0:a:3]amix=inputs=3:normalize=0[b];[b][0:a:4]amerge=inputs=2[out]',
               '-map', '[out]', '-ar', '44100', '-f', 'f32le', 'pipe:1']
    result = subprocess.run(command, check=True, capture_output=True)
    audio = np.frombuffer(result.stdout, '<f4').reshape(-1, 4).astype(float)
    backing, voice = audio[:, :2], audio[:, 2:]
    mix = backing + voice
    vp = np.r_[0.0, np.cumsum(np.mean(voice ** 2, axis=1))]
    mp = np.r_[0.0, np.cumsum(np.mean(mix ** 2, axis=1))]
    arrays = {}
    for name, signal in [('mix', mix), ('instrumental', backing)]:
        gain = min(0.1 / max(float(np.sqrt(np.mean(signal ** 2))), 1e-8),
                   0.95 / max(float(np.max(np.abs(signal))), 1e-8))
        signal = signal * gain
        extractor = VocalFeatureExtractor()
        vectors, baselines, times, labels, meta = [], [], [], [], []
        for start in range(0, len(signal) - 255, 256):
            observation = extractor.process(signal[start:start + 256])
            if observation is None:
                continue
            time, vector, baseline = observation
            end = start + 256
            begin = max(0, end - 8820)
            vocal_energy = (vp[end] - vp[begin]) / (end - begin)
            mix_energy = (mp[end] - mp[begin]) / (end - begin)
            fraction = vocal_energy / max(mix_energy, 1e-12)
            label = (1 if vocal_energy > 1e-6 and fraction > 0.01 else
                     0 if vocal_energy < 1e-8 or fraction < 1e-4 else -1)
            vectors.append(vector)
            baselines.append(baseline)
            times.append(time)
            labels.append(label if name == 'mix' else 0)
            meta.append([extractor.level_fast[0], extractor.level_slow[0], extractor.rms,
                         extractor.pitch, extractor.tonality])
        arrays.update({name + '_x': np.array(vectors), name + '_baseline': np.array(baselines),
                       name + '_t': np.array(times), name + '_y': np.array(labels),
                       name + '_meta': np.array(meta)})
    np.savez_compressed(target, **arrays)
    return target


def records(paths, cache_paths):
    output = []
    for path in paths:
        data = np.load(cache_paths[path], allow_pickle=False)
        for variant in ('mix', 'instrumental'):
            output.append(dict(track=path.name.removesuffix('.stem.mp4'), variant=variant,
                               x=data[variant + '_x'], baseline=data[variant + '_baseline'],
                               t=data[variant + '_t'], y=data[variant + '_y'], meta=data[variant + '_meta']))
    return output


def export(model, threshold):
    prior = model.init_.class_prior_
    return dict(schema='rated-rip-vocal-v1', feature_hash=FEATURE_HASH, threshold=threshold,
                feature_count=model.n_features_in_,
                bias=float(np.log(prior[1] / prior[0])), learning_rate=model.learning_rate,
                trees=[dict(left=e[0].tree_.children_left.tolist(), right=e[0].tree_.children_right.tolist(),
                            feature=e[0].tree_.feature.tolist(), threshold=e[0].tree_.threshold.tolist(),
                            value=e[0].tree_.value[:, 0, 0].tolist()) for e in model.estimators_])


def metrics(y, pred):
    y, pred = np.asarray(y), np.asarray(pred)
    tp, fp = int(np.sum((y == 1) & pred)), int(np.sum((y == 0) & pred))
    tn, fn = int(np.sum((y == 0) & ~pred)), int(np.sum((y == 1) & ~pred))
    return dict(tp=tp, fp=fp, tn=tn, fn=fn, precision=tp / max(1, tp + fp),
                recall=tp / max(1, tp + fn), false_positive_rate=fp / max(1, fp + tn),
                balanced_accuracy=0.5 * (tp / max(1, tp + fn) + tn / max(1, tn + fp)))


def predict_sequences(model, rows, baseline=False):
    field = 'baseline' if baseline else 'x'
    return [model.predict_proba(row[field])[:, 1] for row in rows]


def evaluate(rows, probabilities, threshold):
    labels, predictions, by_track = [], [], []
    for row, scores in zip(rows, probabilities):
        tracker = VocalTracker(float(row['t'][1] - row['t'][0]), threshold)
        pred = [tracker.update(float(t), float(p), *map(float, context)).active
                for t, p, context in zip(row['t'], scores, row['meta'])]
        mask = (row['t'] >= 1) & (row['y'] >= 0)
        y, p = row['y'][mask], np.array(pred)[mask]
        labels.extend(y)
        predictions.extend(p)
        by_track.append(dict(track=row['track'], variant=row['variant'], **metrics(y, p)))
    return dict(overall=metrics(labels, predictions), tracks=by_track)


def choose_threshold(rows, probabilities):
    candidates = []
    for threshold in np.arange(0.40, 0.951, 0.025):
        result = evaluate(rows, probabilities, float(threshold))['overall']
        if result['false_positive_rate'] <= 0.05:
            candidates.append((result['recall'], -threshold, float(threshold), result))
    if not candidates:
        return 0.975, evaluate(rows, probabilities, 0.975)['overall']
    _, _, threshold, result = max(candidates)
    return threshold, result


def main():
    from sklearn.ensemble import GradientBoostingClassifier
    import sklearn
    from threadpoolctl import threadpool_limits
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--fit', type=Path, required=True, help='New exported model path')
    parser.add_argument('--report', type=Path, required=True, help='New report path')
    args = parser.parse_args()
    if args.fit.exists() or args.report.exists():
        parser.error('Choose new model and report paths; existing artifacts are preserved')
    args.cache.mkdir(parents=True, exist_ok=True)
    paths = sorted(args.dataset.glob('*/*.stem.mp4'))
    if not paths:
        parser.error('No MUSDB stem files found')
    cache_paths = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(extract, path, args.cache): path for path in paths}
        for index, future in enumerate(as_completed(futures), 1):
            cache_paths[futures[future]] = future.result()
            if index % 10 == 0 or index == len(paths):
                print(f'Extracted {index}/{len(paths)} tracks', flush=True)
    train_paths = [p for p in paths if p.parent.name == 'train' and p.name.removesuffix('.stem.mp4') not in VALIDATION]
    validation_paths = [p for p in paths if p.parent.name == 'train' and p.name.removesuffix('.stem.mp4') in VALIDATION]
    test_paths = [p for p in paths if p.parent.name == 'test']
    train, validation = records(train_paths, cache_paths), records(validation_paths, cache_paths)
    train_x, train_b, train_y = [], [], []
    for row in train:
        selected = (row['t'] >= 1) & (row['y'] >= 0) & (np.arange(len(row['t'])) % 4 == 0)
        train_x.extend(row['x'][selected]); train_b.extend(row['baseline'][selected]); train_y.extend(row['y'][selected])
    y = np.array(train_y)
    weights = np.where(y == 1, len(y) / (2 * max(1, np.sum(y == 1))), len(y) / (2 * max(1, np.sum(y == 0))))
    fitted = {}
    report = dict(dataset='MUSDB18 official 7s excerpts v0.4.0',
                  archive_sha256='365f66acffc57282e474a4c24b32afec3678258c50b8d45646ac849b0a287df3',
                  feature_hash=FEATURE_HASH, sklearn_version=sklearn.__version__,
                  splits={name: [p.name.removesuffix('.stem.mp4') for p in group]
                          for name, group in [('train', train_paths), ('validation', validation_paths), ('test', test_paths)]},
                  label_rule='Past 200ms vocal power >1e-6 and >1% of mix power is positive; <1e-8 or <0.01% is negative; intermediate cases excluded. Instrumental counterfactual always negative. First second excluded.',
                  train_rows=len(y), results={})
    for name, x in [('ema_baseline', train_b), ('spectral_temporal', train_x)]:
        print('Fitting', name, 'with', len(y), 'rows', flush=True)
        model = GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.05,
                                          min_samples_leaf=40, random_state=7)
        with threadpool_limits(limits=2):
            model.fit(np.array(x), y, sample_weight=weights)
        validation_predictions = predict_sequences(model, validation, name == 'ema_baseline')
        threshold, result = choose_threshold(validation, validation_predictions)
        fitted[name] = (model, threshold)
        report['results'][name] = dict(threshold=threshold, validation=result)
        print(name, 'validation', result, 'threshold', threshold, flush=True)
    # Freeze the deployed model and threshold BEFORE reading/evaluating the held-out test data.
    model, threshold = fitted['spectral_temporal']
    exported = export(model, threshold)
    exported['training'] = {k: report[k] for k in ['dataset', 'archive_sha256', 'sklearn_version']}
    check = VocalModel(exported)
    x_check = np.asarray(train_x)[::100]
    np.testing.assert_allclose([check.predict(x) for x in x_check], model.predict_proba(x_check)[:, 1], atol=1e-12)
    args.fit.write_text(json.dumps(exported, separators=(',', ':')) + '\n')
    test = records(test_paths, cache_paths)
    for name, (model, threshold) in fitted.items():
        result = evaluate(test, predict_sequences(model, test, name == 'ema_baseline'), threshold)
        report['results'][name]['test'] = result
        print(name, 'TEST', result['overall'], flush=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('Saved model:', args.fit, 'and report:', args.report, flush=True)


if __name__ == '__main__':
    main()
