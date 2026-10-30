# First Raspberry Pi setup

This guide is for a Raspberry Pi 3 B+, an SSL USB audio interface, and three
ADJ Mega TRIPAR Profile Plus fixtures at d.001, d.005, and d.009. The code is Python
source: there is no special firmware to compile or custom SD-card image to build.

## What goes on the microSD?

First, Raspberry Pi Imager writes **Raspberry Pi OS Lite (64-bit)** to the card.
Then, after the Pi boots, you copy and install this program onto that same card
over your local network. The card stays in the Pi during installation and use.
Lite has no graphical desktop; you operate it through a terminal on your laptop.

You need a microSD card (32 GB is a convenient choice), a card reader, a suitable
Pi 3 B+ power supply (micro-USB, 5 V / 2.5 A), and network access. Internet access
is needed for installation; the lighting engine works offline after setup.

## 1. Flash Raspberry Pi OS on your regular computer

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Insert the microSD into your computer's card reader.
3. In Imager, choose **Raspberry Pi 3** as the device, then **Raspberry Pi OS
   Lite (64-bit)** (usually under Raspberry Pi OS (other)).
4. Choose the microSD as the storage device. Writing the image erases that card;
   check that you selected the right drive.
5. In the customization screens, set:
   - Hostname: `ratedpi`
   - Username: `dj` (the commands below use this name)
   - A password you choose
   - Your Wi-Fi network/password and country, unless using Ethernet
   - SSH enabled, with password authentication for this first setup
6. Write and verify the image, then eject the card.

Insert the card into the unpowered Pi, connect Ethernet if using it, and connect
power. Allow a few minutes for the first boot. Keep the Pi and computer on the
same local network; guest Wi-Fi can prevent them from reaching each other.

## 2. Connect to the Pi

On your computer, open Terminal (macOS/Linux) or PowerShell (Windows) and run:

```sh
ssh dj@ratedpi.local
```

Accept the first-connection host-key prompt for your Pi, then enter the password
you chose. Password characters are not displayed as you type. The terminal now
runs commands **on the Pi**. If you chose a different username or hostname,
substitute it throughout this guide; modern Raspberry Pi OS has no default
`pi` username to assume.

If `ratedpi.local` cannot be found, find the Pi's IP address in your router's
connected-device list and use it instead, for example `ssh dj@192.168.1.42`.
Use that same address in the copy command below. If Windows cannot find `ssh` or
`scp`, install the Windows OpenSSH Client optional feature.

Run these commands on the Pi:

```sh
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip alsa-utils unzip
sudo usermod -aG audio,dialout "$USER"
exit
```

The last command returns to your computer. The next login activates the new
audio and serial-device group permissions.

## 3. Copy the software from your computer

Download **[rated-rip-pi.zip from GitHub](https://github.com/briandal107/rated_rip/raw/refs/heads/main/downloads/rated-rip-pi.zip)** into your computer's Downloads
folder. It contains the current source, documentation, and fast tests. It deliberately
does not include the cloud machine's virtual environment or installed binaries;
the Pi installs its own compatible dependencies. The large MP3 test fixtures and
rendered previews stay in the repository/evaluation package and are not needed
on the Pi.

Run these commands **on your computer**, not inside an SSH session:

```sh
cd "$HOME/Downloads"
scp rated-rip-pi.zip dj@ratedpi.local:~/
ssh dj@ratedpi.local
```

If you saved the ZIP somewhere else, change to that folder first. `scp` copies
the archive onto the Pi's microSD over the network; it may ask for your Pi
password. The final `ssh` opens a new terminal session on the Pi.

This archive contains the same version 0.5 application as the GitHub repository.
The small archive avoids downloading the full-song MP3 fixtures onto the Pi.

## 4. Install and check the program on the Pi

For a first install, run these commands **on the Pi**:

```sh
unzip ~/rated-rip-pi.zip -d ~/
cd ~/rated_rip
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dmx]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/rated-rip --simulate --duration 10 --seed 7
```

If a `~/rated_rip` folder already exists from an earlier install, preserve any
local edits before extracting over it. The `.venv` directory is a private Python
environment for this program. It is created on the Pi; do not copy one from a PC.

Expect the test suite to pass and then lines containing `rms`, `loudness`, `density`,
`attacks`, and `rgb`. The simulation ends after ten seconds. It uses synthetic
audio and sends no DMX because no `--dmx-port` was supplied.
The console also prints `vocal_score` and `vocal_active`; these are experimental
music-vocal cues, not certain labels. Add `--no-vocals` to keep only attack-based
lighting. The bundled model adds no separate installation step.

## 5. Identify the connected hardware

Connect the SSL and ENTTEC through the powered USB hub, with the Pi on its own
power supply, and run:

```sh
arecord -l
arecord -L
ls -l /dev/serial/by-id/
```

`arecord` lists recording inputs; choose the SSL, not an unrelated audio device.
The last command lists stable serial-device paths for the DMX adapter. An absent
directory means no such serial device was detected; it does not mean OLA should
be installed. Share these outputs and the exact ENTTEC model if device selection
is unclear.

**OLA is not required.** This driver talks directly to a buffered ENTTEC **DMX
USB Pro-compatible** device using pyserial. ENTTEC **Open DMX USB** uses a
different protocol and is not supported by this version. Confirm the adapter's
model label before trying live output. Do not run another lighting application
or OLA against the same adapter at the same time.

## 6. Check live audio, then enable the lights

Connect a spare line-level master/booth output from the DJ controller to the SSL
line inputs and set gain so the inputs do not clip. See the README for wiring.

The following commands contain placeholders. Replace `SSL_CARD_ID` using the
`CARD=` identifier from the SSL's `plughw` entry in `arecord -L`; use its actual
`DEV=` value too if it is not 0. Replace `ENTTEC_DEVICE` with the filename listed
under `/dev/serial/by-id/`.

First check incoming audio without lighting output:

```sh
cd ~/rated_rip
.venv/bin/rated-rip --device plughw:CARD=SSL_CARD_ID,DEV=0 --duration 15
```

Play music. RMS and RGB values should respond; attack count should advance. Silence
should fade the RGB values to zero. If capture rejects 44.1 kHz, try adding
`--rate 48000`. ALSA `plughw` handles audio-format conversion.

Set all three **Mega TRIPAR Profile Plus** fixtures to **Ch04 (four-channel
RGB+UV DMX mode)**, keeping addresses **d.001, d.005, d.009**. At the address
display, SETUP accesses the `ChXX` setting; use UP/DOWN to select `Ch04`.
The address display alone does not confirm channel mode. The program sends RGB
on channels 1–3, 5–7 and 9–11 and leaves UV channels 4, 8 and 12 off. Do not use
Ch06: its shutter/dimmer channels and six-channel footprint conflict with this
configuration. For a different fixture model, verify its channel map first.
After confirming the fixture mode and adapter compatibility:

```sh
.venv/bin/rated-rip --device plughw:CARD=SSL_CARD_ID,DEV=0 \
  --dmx-port /dev/serial/by-id/ENTTEC_DEVICE --brightness 0.35
```

This runs until you press **Ctrl-C**, which attempts to black out the lights.
Version 0.5 rotates through Pulse, Chase, Split and Bloom about every 150 audible
seconds. The console reports the current `scheme`. Add `--scheme-seconds 20` for
a quick rehearsal, or `--scheme split` to hold one scheme. See
[scheme behavior and upgrading an existing installation](SCHEMES.md).
Start with this manual workflow; automatic startup on boot is not configured.
Keep the SSH session open while running it. Subsequent runs only need the last
command from `~/rated_rip`; you do not reinstall everything each time.

Before removing power, stop the program and shut down the Pi:

```sh
sudo shutdown -h now
```

Allow shutdown to finish before unplugging it. Sudden power loss or a disconnected
adapter cannot send a blackout message to the fixtures.

The cloud checks establish simulation and packet-format behavior. Physical audio
capture, DMX output, and performance still need to be verified on your Pi.
