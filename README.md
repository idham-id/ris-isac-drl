# Real-Time Deep Reinforcement Learning Control of RIS-Assisted ISAC under Partial Observations

Code and data for the paper *"Real-Time Deep Reinforcement Learning Control of
RIS-Assisted Integrated Sensing and Communication under Partial Observations"*
by Muhammad Idham Ananta Timur, Ahmad Ashari and Triyogatama Wahyu Widodo
(Universitas Gadjah Mada).

A reconfigurable intelligent surface (RIS) can extend integrated sensing and
communication (ISAC) into a street that buildings hide from the base station,
but configuring it needs decisions faster than an iterative optimiser delivers
and channel knowledge that is expensive to acquire. This repository trains and
evaluates a proximal-policy-optimisation (PPO) controller that, every 100 ms,
sets the RIS phases, the communication-sensing power split and the user weights
from partial observations only — effective channels, quantised SINR reports and
a Kalman tracker estimate — while the precoder and the sensing beam follow in
closed form. Channels come from a ray-traced digital twin built with NVIDIA
Sionna RT, with a hybrid per-element RIS model validated to within 0.015 dB of
the analytic cascade. On held-out trajectories the controller raises the
minimum user rate 1.95-fold and SCNR compliance from 0.32 to 0.96 against a
RIS-free system that has perfect channel knowledge, lands between perfect-CSI
optimisers whose decisions are 5 and 10 frames stale, and decides in 0.15 ms.

Everything in the paper is produced by the code in this repository from the
data archived on Zenodo. No number in the manuscript is typed by hand.

- **Single source of truth for the model, the MDP, the baselines and every
  parameter:** [`docs/EXPERIMENT_DESIGN.md`](docs/EXPERIMENT_DESIGN.md).
- **Dated record of every decision, failure and measured number:**
  [`docs/LOG.md`](docs/LOG.md). Phases and gates:
  [`docs/TASKS.md`](docs/TASKS.md).
- An older and more detailed Indonesian README is kept at
  [`README.id.md`](README.id.md).

## Repository layout

```
configs/            base.yaml plus one override file per experiment
docs/               EXPERIMENT_DESIGN.md (model), TASKS.md (phases), LOG.md (record)
envs/               requirements.txt
scripts/            one entry point per experiment and per gate check
src/risisac/
  scene/            synthetic L-shaped street, BS/RIS/user placement
  channels/         geometry, Sionna RT extraction, HDF5 database, analytic validation
  mobility/         target and user trajectories
  system/           signal model (E1-E9), precoding, RIS response
  tracking/         Kalman tracker
  env/              Gymnasium environment (never imports Sionna; reads HDF5 only)
  baselines/        random, geometric closed form, Oracle-GD
  train/            PPO training loop
  eval/             evaluate, metrics, plots, tables
tests/              unit tests, one per equation the design document numbers
data/channels/      ray-traced channel database (not in git; from Zenodo)
results/            every result file (not in git; from Zenodo, or regenerated)
```

Results are written to `results/<experiment>/<config_hash>/<seed>/` together
with a copy of the config and the git commit that produced them. The
`config_hash` is computed from the whole config, so adding even an irrelevant
key renames the output directory; `make_figures.py` handles that by comparing
each candidate `config_used.json` and accepting only one whose difference lies
entirely in keys declared irrelevant. It never silently uses a stale result.

## Installation

```bash
git clone https://github.com/idham-id/ris-isac-drl.git
cd ris-isac-drl
conda create -n sionna-drl python=3.12
conda activate sionna-drl
pip install -r envs/requirements.txt
pip install -e .
python scripts/check_env.py      # records versions and available VRAM
```

Recent Sionna RT has no RIS support, so the cascade is built per element with a
hybrid approach (design document section 4). There is **no Sionna 0.19.2
environment** in this version: the E0 validation uses an analytic model.

## Getting the data

The ray-traced channel database, the evaluation logs and the best-validation
checkpoints are archived separately, because they do not belong in git:

- **Code archive (this repository):** DOI `10.5281/zenodo.XXXXXXX` *(to follow)*
- **Data archive:** DOI `10.5281/zenodo.YYYYYYY` *(to follow)*

```bash
# download ris-isac-drl-data-v1.0.zip from the data DOI above, then:
unzip ris-isac-drl-data-v1.0.zip -d .     # extract at the repository root
sha256sum -c SHA256SUMS                   # verify
```

The archive unpacks into `data/channels/` and `results/`. With it in place you
can skip straight to step 8 below and rebuild every figure and table in the
paper in about one minute, without a GPU. `README_DATA.md` inside the archive
describes its contents and its licence (CC-BY-4.0).

## Reproducing the paper from scratch

Times are **measured** on the development machine (see *Hardware* below). Each
step writes its results to disk, so the next step never repeats the previous
one and any step can be rerun on its own. Every script takes `--seed`; all
random number generators derive from it.

| Step | Command | Time | Device |
|---|---|---|---|
| 1. Scene and feasibility (Gate 1) | `python scripts/run_e1_coverage.py --config base` | 3 min | GPU |
| 2. Channel database | `python scripts/precompute_channels.py --config base --split all` | 8.7 min | GPU |
| 3. Channel validation (Gate 2) | `python scripts/run_e0_validation.py --config base` | 1 min | GPU |
| 4. Signal model, tracker, baselines (Gate 3) | `python scripts/run_gate3_feasibility.py --config base` | 2 min | CPU |
| 5. RL environment smoke test (Gate 4) | `python scripts/run_gate4_smoke.py --config base` | 5 min | CPU |
| 6a. Training, main queue (21 runs) | `JOBS=3 bash scripts/run_all_training.sh` | 92 min | CPU |
| 6b. Training, ablation queue (9 runs) | `JOBS=3 bash scripts/run_phase8_training.sh` | 45 min | CPU |
| 6c. Training curves (Gate 5) | `python scripts/run_gate5_check.py --config base` | 1 min | CPU |
| 7a. Evaluation on the test set | `python -m risisac.eval.evaluate --config base` | 12 min | CPU + GPU |
| 7b. Trade-off and episode figures (Gate 6) | `python scripts/run_gate6_check.py` | 5 min | CPU |
| 7c. Robustness sweep (E4a) | `python scripts/run_e4a.py --config base` | 6 min | CPU |
| 7d. Ablation and decision cost (E5, E6) | `python scripts/run_e5_e6.py --precompute-seconds 520.1` | 2 min | CPU + GPU |
| 8. Figures and tables (Gate 7) | `python scripts/make_figures.py --config base` | 1 min | CPU |
| 9. All checks at once | `python scripts/run_gate7_check.py` | 1 min | CPU |

Steps 6c and 7a also run for the four sweep configs:

```bash
for c in gamma10 gamma16 kappa025 kappa050; do
    python scripts/run_gate5_check.py --config "$c" --methods ppo_po
    python -m risisac.eval.evaluate --config "$c"
done
```

Things that cost us time, so that they need not cost you any:

- **Do not run ray tracing and another GPU process at the same time.** Peak
  VRAM during precomputation is 4.40 GiB on a 12 GB card, but Oracle-GD and
  the evaluation want the GPU too.
- PPO trains on the **CPU** (small MLP, NumPy environment). Measured:
  `JOBS=1` gives 2069 steps/s, `JOBS=3` gives 5112 steps/s aggregate.
  **`JOBS=4` fails** — 36 processes times torch exceeds the Windows commit
  limit — and leaves orphaned processes that poison the next attempt.
- Each run writes `done.json` and is skipped when the queue is restarted, so a
  training queue is safe to stop halfway. Do not edit a training shell script
  while it is running: bash reads it by byte offset.
- `make_figures.py` **recomputes nothing** beyond re-aggregating existing
  evaluation logs. It reads result files, redraws, and writes to
  `results/paper/<config_hash>/` with a `manifest.json` recording where each
  artefact came from.

## Where each figure and table comes from

Every artefact below is written by `scripts/make_figures.py` into
`results/paper/2ac2654fe51c/` — PDF and PNG for figures, `.tex` for tables. The
third column is the file it is drawn from, where `<hash>` is the config hash
(`2ac2654fe51c` for the main configuration).

| Artefact | Produced from, by | Input file |
|---|---|---|
| F1 Scene layout | `run_e1_coverage.py` | `results/e1/<hash>/e1_coverage.npz` |
| F2 RIS gain and ideal SCNR coverage | `run_e1_coverage.py` | `results/e1/<hash>/e1_coverage.npz` |
| F3 Channel-model validation | `run_e0_validation.py` | `results/e0/<hash>/T1_e0.json`, `e0_synthetic_delta_db.npy` |
| F4 Training curves | `run_gate5_check.py` | `results/gate5/<hash>/gate5.json` |
| F5 Minimum-rate CDF | `risisac.eval.evaluate` | `results/eval/<hash>/steps.parquet` |
| F6 One episode in detail | `risisac.eval.evaluate` | `results/eval/<hash>/steps.parquet` |
| F7 Power and speed robustness | `run_e4a.py` | `results/eval/<hash>/E4a.csv` |
| F8 Rate-SCNR trade-off over Gamma | `run_gate6_check.py` | `results/eval/<hash>/F8_points.json` |
| T1 Channel validation | `run_e0_validation.py` | `results/e0/<hash>/T1_e0.json` |
| T2 Main results | `risisac.eval.evaluate` | `results/eval/<hash>/T2.csv` |
| T3 Observation and action ablation | `run_e5_e6.py` | `results/eval/<hash>/T3_e5_ablation.csv` |
| T4 Parameters | `configs/base.yaml`, `make_figures.py` | the config, plus `episodes.parquet` for the measured episode length |
| T5 Behaviour and Welch tests | `make_figures.py` | `results/eval/<hash>/steps.parquet`, `episodes.parquet` |
| T6 Decision latency | `run_e5_e6.py` | `results/eval/<hash>/T3_e6_cost.json` |
| T_baselines What each method knows | `make_figures.py` | none: a description of the methods, generated so that it cannot drift from the code |

`results/paper/<hash>/manifest.json` records, for each run of
`make_figures.py`, the git commit, the source directory of every artefact and
the numbers the captions quote (`caption_facts`), so a caption and its figure
can never come from different runs.

## Hardware

Measured on an Intel Core i5-13600KF (14 cores), 32 GB RAM, NVIDIA RTX 4070
12 GB, Windows 11, Python 3.12, PyTorch 2.14 (CUDA 13.0).

- A 12 GB NVIDIA GPU is enough for ray tracing and for Oracle-GD. On
  out-of-memory, lower `rx_batch_size` and `samples_per_src` in the config
  before anything else.
- A multi-core CPU matters more than the GPU: PPO training does not use the GPU.
- Disk: the channel database is 28 MB; the archived results are about 230 MB.
- Rebuilding the figures and tables from the archived data needs **no GPU**.

## Use of AI tools

The simulation and analysis code in this repository was developed with the
assistance of Claude Code (Anthropic). Every numerical result was produced by
the released code and checked against its own logs; the authors reviewed,
verified and edited all generated content, and take full responsibility for the
work. `docs/LOG.md` is the dated record of that process, including the
mistakes, the discarded designs and the measurements that overturned them.

## Licence

Code: Apache-2.0, see [`LICENSE`](LICENSE).
Data archive on Zenodo: CC-BY-4.0.

## Citing

Please cite the paper. Machine-readable metadata is in
[`CITATION.cff`](CITATION.cff); GitHub renders it under *Cite this repository*.

```bibtex
@article{timur2026ris,
  title   = {Real-Time Deep Reinforcement Learning Control of
             RIS-Assisted Integrated Sensing and Communication
             under Partial Observations},
  author  = {Timur, Muhammad Idham Ananta and Ashari, Ahmad and
             Widodo, Triyogatama Wahyu},
  year    = {2026},
  note    = {Under review}
}
```
