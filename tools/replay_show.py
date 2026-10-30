"""Run complete audio fixtures through the causal lighting engine and build previews.

Requires FFmpeg and research plotting tools. Source audio is never normalized.
The optional full-song suite is separate from fast unit tests.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rated_rip.engine import Analyzer, Lighting
from rated_rip.vocals import VocalState

FPS = 30


def longest_span(mask, dt):
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best * dt


def run_track(item, output, fingerprint):
    source = ROOT / item['file']
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != item['sha256']:
        raise ValueError(f'Fixture checksum mismatch: {source.name}')
    folder = output / item['id']
    folder.mkdir(exist_ok=True)
    summary_path = folder / 'summary.json'
    if summary_path.exists():
        saved = json.loads(summary_path.read_text())
        if saved.get('code_fingerprint') == fingerprint and saved.get('source_sha256') == digest:
            return saved
        raise ValueError(f'Use a new output directory for changed code or audio: {folder}')
    started = time.perf_counter()
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-i', str(source),
                          '-map', '0:a:0', '-ac', '2', '-ar', '44100', '-f', 's16le', 'pipe:1'],
                         check=True, capture_output=True).stdout
    audio = np.frombuffer(raw, '<i2').reshape(-1, 2)
    analyzer = Analyzer()
    lighting, plain = Lighting(seed=7), Lighting(seed=7)
    frames, attacks, changes, plain_changes, percussion = [], [], [], [], []
    previous = [0] * 23
    frame_index = 0
    count = 0
    old_target, old_plain = lighting.target_hue, plain.target_hue
    full_scale = int(np.sum(np.abs(audio.astype(np.int32)) >= round(0.995 * 32768)))
    for start in range(0, len(audio) - analyzer.size + 1, analyzer.size):
        end_time = (start + analyzer.size) / analyzer.rate
        # Show only a state available by this frame's audio time: no future samples.
        while frame_index / FPS < end_time:
            frames.append(previous)
            frame_index += 1
        samples = audio[start:start + analyzer.size].astype(float) / 32768
        features = analyzer.process(samples)
        rgb = lighting.update(features, analyzer.size / analyzer.rate)
        rgb_plain = plain.update(replace(features, vocal=VocalState()), analyzer.size / analyzer.rate)
        for attack in features.attacks:
            percussion.append([attack.time, attack.reported_at, attack.stage,
                               attack.percussiveness, attack.rise_db, attack.noisiness,
                               attack.tail_ratio, attack.overlapped])
            if attack.stage == 'onset':
                count += 1
                attacks.append([attack.time, attack.reported_at, list(attack.bands), attack.strength])
        if lighting.target_hue != old_target:
            changes.append(end_time); old_target = lighting.target_hue
        if plain.target_hue != old_plain:
            plain_changes.append(end_time); old_plain = plain.target_hue
        previous = [c for fixture in rgb for c in fixture] + [c for fixture in rgb_plain for c in fixture]
        previous += [round(features.vocal.score * 100), int(features.vocal.active),
                     round(features.loudness * 100), round(features.density * 100), count]
    data = np.asarray(frames, dtype=np.int32)
    np.savez_compressed(folder / 'trace.npz', frames=data)
    (folder / 'attacks.json').write_text(json.dumps(attacks, separators=(',', ':')))
    (folder / 'percussion.json').write_text(json.dumps(percussion, separators=(',', ':')))
    duration = len(audio) / analyzer.rate
    dt = 1 / FPS
    active = data[:, 19].astype(bool)
    audible = data[:, 20] > 5
    brightness = data[:, :9].reshape(-1, 3, 3).max(axis=2) / 255
    tail_scores = [p[3] for p in percussion if p[2] == 'tail']
    rate = np.histogram([a[0] for a in attacks], bins=np.arange(0, int(duration) + 2))[0]
    loud = np.array([np.mean(data[int(s * FPS):int((s + 1) * FPS), 20]) / 100
                     for s in range(int(duration))])
    contrast = np.zeros(len(loud))
    for s in range(10, len(loud) - 10):
        contrast[s] = abs(loud[s:s + 5].mean() - loud[s - 5:s].mean())
        contrast[s] += 0.035 * abs(rate[s:s + 5].mean() - rate[s - 5:s].mean())
    eligible = contrast[15:max(16, int(duration) - 30)]
    transition = int(np.argmax(eligible)) + 15
    clip_start = max(0, min(duration - 45, transition - 15))
    # Conditions here are mechanical invariants, not claims of musical accuracy.
    assert np.isfinite(data).all() and data[:, :18].min() >= 0 and data[:, :18].max() <= round(255 * 0.65)
    assert np.all(np.diff(data[:, 22]) >= 0)
    assert len(frames) >= int((duration - 0.02) * FPS)
    summary = dict(id=item['id'], title=item['title'], source_sha256=digest,
                   code_fingerprint=fingerprint, duration_seconds=duration,
                   trailing_samples_not_analyzed=len(audio) % analyzer.size,
                   processing_seconds=time.perf_counter() - started, frames=len(data),
                   attacks=count, attacks_per_second=count / duration,
                   maximum_attacks_in_one_second=int(rate.max()),
                   vocal_active_fraction=float(np.mean(active[audible])) if np.any(audible) else 0,
                   longest_vocal_active_seconds=longest_span(active, dt),
                   palette_changes=len(changes), palette_changes_without_vocals=len(plain_changes),
                   palette_change_times=changes, palette_change_times_without_vocals=plain_changes,
                   longest_palette_hold_seconds=float(np.diff([0] + changes + [duration]).max()),
                   mean_fixture_brightness=brightness.mean(axis=0).tolist(),
                   mean_brightness_step=float(np.abs(np.diff(brightness, axis=0)).mean()),
                   percussion_tail_median=float(np.median(tail_scores)) if tail_scores else None,
                   percussion_tail_below_045_fraction=float(np.mean(np.array(tail_scores) < 0.45)) if tail_scores else None,
                   brightness_p10_p90=np.quantile(brightness, [0.1, 0.9], axis=0).tolist(),
                   maximum_dmx_channel=int(data[:, :9].max()),
                   near_full_scale_audio_fraction=full_scale / audio.size,
                   selected_clip_start=clip_start, selected_clip_duration=min(45, duration),
                   attack_band_counts={b:sum(b in a[2] for a in attacks) for b in ['low','mid','high']},
                   darkest_audible_fraction=float(np.mean(brightness[audible].max(axis=1) < 0.05)))
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def compare_reference(summary, output, reference_dir):
    """Compare saved RGB commands from the same source and replay clock."""
    folder = output / summary['id']
    old_folder = reference_dir / summary['id']
    reference = json.loads((old_folder / 'summary.json').read_text())
    data = np.load(old_folder / 'trace.npz')['frames']
    if (reference['source_sha256'] != summary['source_sha256']
            or reference['frames'] != summary['frames'] or data.shape != (summary['frames'], 23)
            or abs(reference['duration_seconds'] - summary['duration_seconds']) > 1e-6):
        raise ValueError(f'Reference audio or replay clock mismatch: {summary["id"]}')
    brightness = data[:, :9].reshape(-1, 3, 3).max(axis=2) / 255
    reference['mean_brightness_step'] = float(np.abs(np.diff(brightness, axis=0)).mean())
    summary['reference'] = reference
    # Keep the same excerpt as the old report for a directly comparable preview.
    summary['selected_clip_start'] = reference['selected_clip_start']
    summary['selected_clip_duration'] = reference['selected_clip_duration']
    np.savez_compressed(folder / 'reference.npz', frames=data[:, :9])
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


def comparison_frames(summary, output, data):
    if 'reference' in summary:
        return np.load(output / summary['id'] / 'reference.npz')['frames'], 'Previous version 0.3'
    return data[:, 9:18], 'Vocal layer disabled'


def plot_track(summary, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder = output / summary['id']
    data = np.load(folder / 'trace.npz')['frames']
    times = np.arange(len(data)) / FPS
    attacks = json.loads((folder / 'attacks.json').read_text())
    fig, axes = plt.subplots(5, 1, figsize=(13, 8), sharex=True,
                             gridspec_kw={'height_ratios':[1, 1, 1, 0.7, 0.7]})
    axes[0].plot(times, data[:,20] / 100, label='Adaptive loudness', lw=0.8)
    axes[0].plot(times, data[:,21] / 100, label='Spectral density', lw=0.8, alpha=0.8)
    axes[0].legend(loc='upper right', ncol=2, fontsize=8); axes[0].set_ylim(0,1)
    bins = np.arange(0, int(summary['duration_seconds']) + 2)
    for band, color in [('low','#e87921'),('mid','#7c3aed'),('high','#0891b2')]:
        counts=np.histogram([a[0] for a in attacks if band in a[2]],bins=bins)[0]
        axes[1].plot(bins[:-1],counts,label=band,color=color,lw=0.8)
    axes[1].legend(loc='upper right',ncol=3,fontsize=8);axes[1].set_ylabel('Attacks/s')
    axes[2].plot(times,data[:,18]/100,color='#2563eb',lw=0.8,label='Vocal score (unverified)')
    axes[2].fill_between(times,0,1,where=data[:,19].astype(bool),alpha=0.15,color='#f59e0b')
    axes[2].axhline(.7,color='gray',ls='--',lw=.6);axes[2].set_ylim(0,1)
    axes[2].legend(loc='upper right',fontsize=8)
    comparison, label = comparison_frames(summary, output, data)
    for ax, rgb, label in [(axes[3],data[:, :9],'Version 0.4'),(axes[4],comparison,label)]:
        strips=rgb.reshape(-1,3,3).transpose(1,0,2)/255
        ax.imshow(strips,aspect='auto',extent=[0,times[-1],3,0],interpolation='nearest')
        ax.set_yticks([.5,1.5,2.5],['d.001','d.005','d.009']);ax.set_ylabel(label,fontsize=8)
    for ax in axes[:3]:ax.grid(alpha=.15)
    axes[-1].set_xlabel('Seconds')
    fig.suptitle(summary['title'] + '\nFull-song replay · seed 7 · brightness ceiling 65% · RGB is a monitor preview',fontsize=12)
    fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(folder/'overview.png',dpi=130);plt.close(fig)


def render_clip(item, summary, output):
    from PIL import Image, ImageDraw, ImageFont
    folder = output / summary['id']
    data = np.load(folder/'trace.npz')['frames']
    comparison, comparison_label = comparison_frames(summary, output, data)
    start, duration = summary['selected_clip_start'], summary['selected_clip_duration']
    path = folder/'preview.mp4'
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font=ImageFont.truetype(font_path,18); small=ImageFont.truetype(font_path,14)
    command=['ffmpeg','-y','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size','800x480',
             '-framerate',str(FPS),'-i','pipe:0','-ss',str(start),'-i',str(ROOT/item['file']),
             '-map','0:v:0','-map','1:a:0','-t',str(duration),'-c:v','libx264','-threads','2',
             '-preset','veryfast','-crf','24','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k',
             '-movflags','+faststart',str(path)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for frame_number in range(round(duration*FPS)):
            time_point=start+frame_number/FPS
            index=min(len(data)-1,int(time_point*FPS))
            values=data[index]
            image=Image.new('RGB',(800,480),(10,15,25));draw=ImageDraw.Draw(image)
            draw.text((24,14),summary['title'][:77],font=font,fill=(225,232,245))
            draw.text((24,45),f'{int(time_point)//60}:{int(time_point)%60:02d}  |  VOCAL CUE {"ON" if values[19] else "OFF"}  {values[18]/100:.2f}  |  {values[22]} attacks',font=small,fill=(155,175,200))
            for row,(rgb,label) in enumerate([(values[:9],'VERSION 0.4'),(comparison[index],comparison_label.upper())]):
                top=85+row*175
                draw.text((24,top),label,font=small,fill=(160,177,200))
                for fixture,x in enumerate([140,400,660]):
                    color=tuple(int(c) for c in rgb[fixture*3:fixture*3+3])
                    for radius,scale in [(55,.25),(48,.5),(40,1)]:
                        fill=tuple(int(c*scale) for c in color)
                        draw.ellipse((x-radius,top+70-radius,x+radius,top+70+radius),fill=fill)
                    draw.text((x-24,top+130),['d.001','d.005','d.009'][fixture],font=small,fill=(150,170,190))
            draw.text((24,456),'RGB visualization; fixture optics, brightness response and hardware latency are not modeled.',font=small,fill=(130,145,165))
            process.stdin.write(image.tobytes())
        process.stdin.close()
        errors=process.stderr.read().decode()
        if process.wait()!=0:raise RuntimeError(errors)
    except BaseException:
        process.kill();process.wait();raise
    finally:
        process.stderr.close()


def dashboard(summaries, manifest, output):
    records=[]
    for summary,item in zip(summaries,manifest):
        data=np.load(output/summary['id']/'trace.npz')['frames']
        comparison, label = comparison_frames(summary, output, data)
        records.append(dict(summary=summary,file=Path(item['file']).name,original=item['title']+'.mp3',
                            frames=data.tolist(), comparison=comparison.tolist(), comparisonLabel=label))
    encoded=json.dumps(records,separators=(',',':')).replace('<','\\u003c')
    template=(ROOT/'tools/show_dashboard.html').read_text()
    (output/'index.html').write_text(template.replace('__TRACK_DATA__',encoded))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'tests/audio/manifest.json')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=2,choices=[1,2,3])
    parser.add_argument('--clips',action='store_true')
    parser.add_argument('--reference-dir',type=Path,help='Previous report using the same source audio, seed 7 and 30 fps')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(args.manifest.read_text())
    fingerprint=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'rated_rip').glob('*.py')))
                               +(ROOT/'rated_rip/vocal_model.json').read_bytes()
                               +Path(__file__).read_bytes()).hexdigest()
    results={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(run_track,item,args.output_dir,fingerprint):item for item in manifest}
        for task in as_completed(tasks):
            result=task.result();results[result['id']]=result
            print(json.dumps({k:result[k] for k in ['id','duration_seconds','attacks','vocal_active_fraction','palette_changes','processing_seconds']}),flush=True)
    summaries=[results[item['id']] for item in manifest]
    if args.reference_dir:
        for summary in summaries:
            compare_reference(summary, args.output_dir, args.reference_dir)
    (args.output_dir/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    for summary in summaries:plot_track(summary,args.output_dir)
    dashboard(summaries,manifest,args.output_dir)
    if args.clips:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks=[pool.submit(render_clip,item,summary,args.output_dir) for item,summary in zip(manifest,summaries)]
            for index,task in enumerate(tasks,1):
                task.result();print(f'Rendered preview {index}/{len(tasks)}',flush=True)
    print('Report:',args.output_dir/'index.html',flush=True)


if __name__=='__main__':main()
