import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from rated_rip.engine import Analyzer, Lighting

import argparse
parser=argparse.ArgumentParser(description='Plot selected held-out vocal examples, including a false positive.')
parser.add_argument('--dataset',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args()
args.output_dir.mkdir(parents=True,exist_ok=True)
if any((args.output_dir / name).exists() for name in ['vocal_examples.png','vocal_runtime_examples.json']):
 parser.error('Choose a directory without existing plot artifacts')

names=['AM Contra - Heart Peripheral','M.E.R.C. Music - Knockout','Detsky Sad - Walkie Talkie']
fig,axes=plt.subplots(3,2,figsize=(12,8),sharex=True,sharey=True)
measurements=[]
for row,name in enumerate(names):
 p=(args.dataset / 'test')/(name+'.stem.mp4')
 command=['ffmpeg','-v','error','-threads','1','-i',str(p),'-filter_complex_threads','1','-filter_complex','[0:a:1][0:a:2][0:a:3]amix=inputs=3:normalize=0[b];[b][0:a:4]amerge=inputs=2[out]','-map','[out]','-ar','44100','-f','f32le','pipe:1']
 raw=subprocess.run(command,check=True,capture_output=True)
 data=np.frombuffer(raw.stdout,'<f4').reshape(-1,4).astype(float)
 backing,voice=data[:,:2],data[:,2:]
 for col,(variant,signal) in enumerate([('With vocal stem',backing+voice),('Accompaniment only',backing)]):
  gain=min(.1/max(np.sqrt(np.mean(signal**2)),1e-8),.95/max(np.max(np.abs(signal)),1e-8))
  signal=np.round(np.clip(signal*gain,-1,1)*32767)/32768
  analyzer=Analyzer();lighting=Lighting(seed=7); times=[]; scores=[]; states=[];last=0
  started=time.perf_counter()
  for start in range(0,len(signal)-255,256):
   features=analyzer.process(signal[start:start+256])
   lighting.update(features,256/44100)
   state=features.vocal
   if state.time>last:
    times.append(state.time);scores.append(state.score);states.append(state.active);last=state.time
  elapsed=time.perf_counter()-started
  measurements.append(dict(track=name,variant=variant,audio_seconds=len(signal)/44100,processing_seconds=elapsed,active_fraction_after_warmup=float(np.mean(np.array(states)[np.array(times)>=1]))))
  ax=axes[row,col]
  ax.plot(times,scores,color='#2563eb',lw=1.8,label='Smoothed model score')
  ax.fill_between(times,0,1,where=states,color='#f59e0b',alpha=.18,label='Lighting cue active')
  ax.axhline(.7,color='#475569',ls='--',lw=.8,label='Activation threshold')
  ax.axvspan(0,1,color='#94a3b8',alpha=.15)
  ax.set_title(name+'\n'+variant,fontsize=10)
  ax.set_ylim(0,1);ax.set_xlim(0,7);ax.grid(alpha=.15)
  if col==0:ax.set_ylabel('Model score')
  if row==2:ax.set_xlabel('Seconds')
handles,labels=axes[0,0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',ncol=3,frameon=False)
fig.suptitle('Vocal-activity examples: two useful distinctions and one false positive',fontsize=14)
fig.tight_layout(rect=[0,.05,1,.94])
fig.savefig(args.output_dir / 'vocal_examples.png',dpi=160)
(args.output_dir / 'vocal_runtime_examples.json').write_text(json.dumps(measurements,indent=2)+'\n')
print(json.dumps(measurements,indent=2))
