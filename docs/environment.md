# Environment notes

Facts about the LinuxONE VM and our setup. Record what you observed, not what you expect. Update the date when a value changes.

## VM

| Item | Value | Checked by | Date |
|---|---|---|---|
| Distribution and version | Ubuntu 24.04.5 LTS | Member 1 | 2026-10-17 |
| Architecture (`uname -m`) | `s390x` | Member 1 | 2026-10-17 |
| CPU count (`nproc`) | 3 | Member 1 | 2026-10-17 |
| Memory (`free -h`) | 7.8 GiB total; 5.2 GiB available at check | Member 1 | 2026-10-17 |
| Disk (`df -h`) | 50 GB total; 35 GB available on `/` | Member 1 | 2026-10-17 |
| Python version | System Python 3.12.3; project virtual environment at `~/venv` | Member 1 | 2026-10-17 |
| Git version | 2.43.0 | Member 1 | 2026-10-17 |
| Docker available | Docker 29.8.0 | Member 1 | 2026-10-17 |
| Outbound internet works | Yes; PyPI returned HTTP 200 | Member 1 | 2026-10-17 |
| How the dashboard is reached (open port or SSH tunnel) | Not yet decided | | |
| VM expiry or reset behaviour | Not yet verified | | |

## Access

| Member | Can SSH in | Can clone the repo on the VM | Can open a pull request |
|---|---|---|---|
| Member 1 | Yes | Yes | Yes |
| Member 2 | Not yet verified | Not yet verified | Not yet verified |
| Member 3 | Not yet verified | Not yet verified | Not yet verified |
| Member 4 | Not yet verified | Not yet verified | Not yet verified |

## Python packages tested on s390x

| Package | Installs with pip | Notes (build from source, distro package, fails) |
|---|---|---|
| numpy | Not tested independently | Available through system packages in the project virtual environment; version 1.26.4 |
| scikit-learn | No, pip build dependencies failed in this environment | Installed using Ubuntu package `python3-sklearn`; version 1.4.1.post1 |
| fastapi and uvicorn | Yes | Installed in the project virtual environment |
| rank_bm25 | Yes | Installed in the project virtual environment |
| faker | Yes | Installed in the project virtual environment |
| pytest | Yes | Installed in the project virtual environment |
| llama-cpp-python | Yes, built from source | Version 0.3.36; requires explicit CMake flags on this VM |

## Model serving

| Item | Value |
|---|---|
| Model and size | `granite-4.0-h-350m-base-be.f16.gguf`, approximately 654 MB, copied from the JupyterLab container to `~/zero-exposure-rag/models/` on the host |
| Serving method | In-process via `llama-cpp-python` 0.3.36 in the project virtual environment, wrapped by `app/llm.py` (`generate(prompt, max_tokens, temperature)`); `n_ctx=2048` |
| Time for a short prompt | 2.58s for a prompt requesting up to 20 tokens (temperature 0) |
| Time for a long prompt | 104.19s for a prompt requesting up to 200 tokens (temperature 0); this is slow and may need a fallback (smaller/more quantised model, fewer max tokens) before the demo |

## Known problems

- The project virtual environment uses system packages (`--system-site-packages`) because installing scientific Python dependencies through pip failed in this environment.
- `llama-cpp-python` failed to build with pip's default CMake auto-detection, which selected `-march=arch15`, unsupported by the installed compiler. The successful build used explicit `z16` compiler flags and `FORCE_CMAKE=1`.
- The model has been verified to load and generate correctly in-process (outside the JupyterLab container) via `app/llm.py`. zDNN/NNPA acceleration has not been independently verified; the CPU backend variant selected by the build was reported as `-march=arch15;-mvx;-mzvector`, despite the explicit compiler flags. This does not confirm any particular acceleration path.
- Long-prompt latency (104s for 200 tokens) is a concern for the live demo and needs a fallback decision before Stage 3 (see the project plan's fallback table: smaller/more quantised model, fewer max tokens, fewer retrieved chunks).
- The model weights are local setup artefacts and must not be committed to Git.

## Installing llama-cpp-python on this VM

These instructions describe the verified build on the Ubuntu 24.04.5 LTS `s390x` VM. They may need adjustment on other operating systems, compiler versions or LinuxONE environments.

### 1. Install system build prerequisites

```bash
sudo apt update
sudo apt install -y build-essential cmake make pkg-config libopenblas-dev
```

### 2. Activate the project virtual environment

From the repository root:

```bash
source ~/venv/bin/activate
```

The environment was created with system site packages enabled because some scientific Python dependencies were installed through Ubuntu packages:

```bash
python3.12 -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
```

If the environment already exists, do not recreate it unnecessarily.

### 3. Build and install llama-cpp-python

The following command successfully built version `0.3.36` on the VM:

```bash
CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS=-march=z16 -DCMAKE_CXX_FLAGS=-march=z16" \
FORCE_CMAKE=1 \
python -m pip install --no-cache-dir llama-cpp-python==0.3.36
```

The explicit flags prevent the failing default architecture selection observed on this VM. `FORCE_CMAKE=1` forces a source build rather than relying on a prebuilt wheel.

### 4. Verify the installation

```bash
python -c "import llama_cpp; print(llama_cpp.__version__)"
```

Expected version:

```text
0.3.36
```

### 5. Verify real model inference

From the repository root, with the virtual environment active and the model file present at `models/granite-4.0-h-350m-base-be.f16.gguf`:

```bash
python -c "from app.llm import generate; print(generate('What is an audit log?', max_tokens=40))"
```

The command should produce a text completion. Generation latency depends on the prompt, token limit and VM load.

## Runtime and security notes

- `STUB_MODE=1` enables stub mode by default. Set `STUB_MODE=0` only when testing the real model-backed pipeline.
- `EVAL_MODE=0` is the required default for normal operation, demonstrations and final submission. Enable it only for controlled red-team evaluation.
- The `X-Guards` header must not disable guards when `EVAL_MODE=0`.
- For initial testing, bind the API to `127.0.0.1` and access it through an SSH tunnel where needed. Do not expose development services or the reference JupyterLab environment publicly without appropriate access controls.
- Do not commit model weights, authentication tokens, private keys, environment files containing secrets or generated database files.
