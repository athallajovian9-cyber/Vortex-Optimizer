# Vortex Optimizer

Windows tuning, with one genuinely uncommon part: **HAGS is decided per game.**

**Official source:** this repository, and the [Vortex Industries Discord](https://discord.gg/QtyBucygQ6). Anything found elsewhere is not ours and has not been checked.

## Install

1. Open [Releases](../../releases) and download the newest one.
2. Run **`Vortex_Optimizer.exe`** or **`RUN_VORTEX.bat`**.

No installer, no dependencies, and no admin unless the tool says it needs it.

## What it does

- Picks Hardware-Accelerated GPU Scheduling on or off from the game you are about to play and how much VRAM your card really has
- Reads true VRAM from the display class registry, not WMI's `AdapterRAM`, which saturates at 4 GB and cannot tell 6 GB from 4 GB
- Enables HAGS where the driver supports it: Turing or newer NVIDIA, RDNA on AMD, Arc on Intel
- Never enables it on pre-Turing NVIDIA, pre-RDNA AMD, or any card with 2 GB or less
- CPU, network, GPU and storage tweaks in the same place

## Notes

- Portable. Nothing is written outside your user profile.
- The source sits in this repo next to the build.
- Questions and bug reports: the [Discord](https://discord.gg/QtyBucygQ6), in `#help` and `#bug-reports`.

## Disclaimer

This is a system tweak. It changes real Windows settings. Read what it does before running it, and use the tool's own restore option if something behaves unexpectedly. Provided as is, with no warranty.
