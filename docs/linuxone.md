# LinuxONE Setup Guide

This guide documents how to prepare the IBM LinuxONE development VM, install the native model runtime, configure the model file and run Zero-Exposure RAG.

For observed VM specifications, measured inference latency and environment-specific findings, see [`environment.md`](environment.md). For architectural decisions, see [`decisions.md`](decisions.md).

## 1. Environment

The setup was verified on the following VM:

| Item | Verified value |
|---|---|
| Operating system | Ubuntu 24.04.5 LTS |
| Architecture | `s390x` |
| Python | 3.12.3 |
| CPUs | 3 |
| RAM | 7.8 GiB |
| Git | 2.43.0 |
| Docker | 29.8.0 |

Your VM may differ. Check the actual environment before applying architecture-specific instructions.

```bash
uname -m
lsb_release -a
python3.12 --version
nproc
free -h
df -h /
git --version
```

The native model build instructions in this guide are specific to the tested LinuxONE environment.

## 2. Get the repository

Clone the repository if you have not already done so:

```bash
git clone https://github.com/rohpod/zero-exposure-rag.git
cd zero-exposure-rag
```

If the repository is already present, update it using your team's normal branch and pull-request workflow:

```bash
git switch main
git pull --ff-only
```

Create a feature branch before making changes. Do not commit VM-specific secrets, local model weights, generated databases or environment files containing credentials.

## 3. Install system prerequisites

Update the Ubuntu package index and install the native build tools and OpenBLAS development libraries required by the tested build:

```bash
sudo apt update
sudo apt install -y \
  python3.12-venv \
  build-essential \
  cmake \
  make \
  pkg-config \
  libopenblas-dev \
  git
```

The VM also used Ubuntu's packaged scientific Python dependencies because pip builds failed in this environment:

```bash
sudo apt install -y python3-numpy python3-sklearn
```

These system packages are specific to Ubuntu. Check package availability before using these commands on another distribution.

## 4. Create and activate the virtual environment

The tested VM uses a virtual environment with system site packages enabled:

```bash
python3.12 -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
```

If `~/venv` already exists, activate it instead of recreating it.

Confirm the interpreter and pip being used:

```bash
which python
python --version
python -m pip --version
```

Using `--system-site-packages` makes the Ubuntu-installed NumPy and scikit-learn packages available inside the virtual environment. This is a workaround for the dependency installation issues observed on the tested VM, not a requirement for every Python environment.

## 5. Install project dependencies

Install the dependencies listed in the repository:

```bash
python -m pip install -r requirements.txt
```

Some dependencies may already be supplied by the Ubuntu system packages. If installation fails, inspect the first actual error rather than assuming every failure has the same cause.

In particular, `scikit-learn` was installed from Ubuntu packages on the tested VM because pip build dependencies failed. Avoid blindly upgrading NumPy or scikit-learn in the virtual environment, as doing so may replace or conflict with the system-provided versions.

## 6. Build llama-cpp-python on s390x

The tested VM could not build `llama-cpp-python` with its default CMake architecture detection. The build selected `-march=arch15`, which the installed compiler did not support.

The following command successfully built `llama-cpp-python` version `0.3.36` on the tested VM:

```bash
CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS=-march=z16 -DCMAKE_CXX_FLAGS=-march=z16" \
FORCE_CMAKE=1 \
python -m pip install --no-cache-dir llama-cpp-python==0.3.36
```

The explicit compiler flags and `FORCE_CMAKE=1` are important for reproducing the successful build. The required system prerequisites are documented in Section 3.

Verify the installed version:

```bash
python -c "import llama_cpp; print(llama_cpp.__version__)"
```

Expected output:

```text
0.3.36
```

The build succeeding does not prove that zDNN or NNPA acceleration is active. The tested build reported a CPU backend variant using `-march=arch15;-mvx;-mzvector`. See [`environment.md`](environment.md) for the recorded observations.

## 7. Obtain and place the Granite model

The tested application uses this GGUF model:

```text
granite-4.0-h-350m-base-be.f16.gguf
```

The file is approximately 654 MB. In the tested environment, it was copied from the supplied JupyterLab container to the host VM.

The expected repository-relative path is:

```text
models/granite-4.0-h-350m-base-be.f16.gguf
```

Create the directory if required:

```bash
mkdir -p models
```

Obtain the model through the team's approved lab-provided source and place it at the expected path. Do not commit the model file to Git. The repository's ignore rules exclude model artefacts.

Confirm that the file exists:

```bash
test -s models/granite-4.0-h-350m-base-be.f16.gguf \
  && echo "Model file exists" \
  || echo "Model file missing or empty"
```

The model source and transfer mechanism may vary depending on access to the lab environment. This guide does not assume that the reference JupyterLab container is available on every VM.

## 8. Verify real model inference

Run this check from the repository root with the virtual environment activated and the model in place:

```bash
python -c "from app.llm import generate; print(generate('What is an audit log?', max_tokens=40))"
```

A successful run should print a generated text completion.

The tested VM completed a short request for up to 20 tokens in 2.58 seconds and a request for up to 200 tokens in 104.19 seconds. These are individual observed timings, not guaranteed performance figures. Longer generations can be slow on the VM's three CPU cores.

If inference fails, check:

- The virtual environment is active.
- `llama-cpp-python` version `0.3.36` imports successfully.
- The model exists at the expected path.
- The current user can read the model file.
- The application is using the expected model path.
- The error is not caused by a missing native library or incompatible package version.

## 9. Configure and start the API

The application provides the FastAPI endpoints `/health`, `/ask`, `/audit` and `/dashboard`.

For normal development and demonstrations, keep the security-sensitive defaults:

```bash
export STUB_MODE=1
export EVAL_MODE=0
```

Stub mode allows API and integration work without real model inference. To test the real model-backed path, set `STUB_MODE=0` after verifying the model and its runtime.

Start the API bound to localhost for initial testing:

```bash
STUB_MODE=0 EVAL_MODE=0 \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This runs in the foreground. Stop it with `Ctrl+C`.

Do not bind the service to `0.0.0.0` on an externally reachable VM unless the team has deliberately configured appropriate network access controls.

## 10. Verify the API

With the API running, open another terminal on the VM.

Check health:

```bash
curl -sS http://127.0.0.1:8000/health
```

Inspect the response to confirm that the application is running and review the model status reported by the endpoint.

To test `/ask`, use a valid synthetic user token supplied through the team's approved local configuration. Do not commit tokens or paste them into shared logs.

```bash
read -rsp "User token: " USER_TOKEN
echo
curl -sS -X POST http://127.0.0.1:8000/ask \
  -H "X-User-Token: $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is an audit log?"}'
unset USER_TOKEN
```

Review the response and confirm that the request appears in the audit log using the project's documented audit interface.

The exact response depends on the configured user, pipeline state, model output and guard decisions.

## 11. Security requirements

- Keep `EVAL_MODE=0` for normal development, demonstrations and final submission.
- The `X-Guards` header must not disable guards when `EVAL_MODE=0`.
- Use synthetic data and synthetic user tokens for the datathon.
- Never commit access tokens, private keys, `.env` files containing secrets, local model weights or generated databases.
- Do not expose the development API or the reference JupyterLab service publicly without appropriate access controls.
- Prefer localhost binding and an SSH tunnel for remote development access.
- Treat audit logs as potentially sensitive, even when the application uses synthetic banking data.
- Do not claim zDNN or NNPA acceleration unless it has been independently verified.

## 12. Troubleshooting

| Symptom | Likely cause or next check |
|---|---|
| `llama-cpp-python` build selects `-march=arch15` and fails | Use the verified `CMAKE_ARGS` and `FORCE_CMAKE=1` command in Section 6. |
| CMake cannot find `PkgConfig` | Install `pkg-config` and retry the build. |
| CMake or compiler tools are missing | Install the prerequisites in Section 3. |
| NumPy or scikit-learn fails to build through pip | Check the Ubuntu packages used by the tested VM and avoid unnecessary upgrades to system-provided scientific dependencies. |
| Model file cannot be found | Check that the GGUF file is in `models/` and matches the configured model path. |
| Inference is slow | Reduce the generation token limit for tests and consult the measured timings in `environment.md`. Evaluate model alternatives before changing the demo configuration. |
| API returns an authentication error | Check the configured synthetic token and the `X-User-Token` header. |
| Guard behaviour differs during evaluation | Confirm `EVAL_MODE`; `X-Guards` is only honoured in controlled evaluation mode. |

## 13. Related documentation

- [`environment.md`](environment.md) — observed VM configuration, package versions, inference timings and known environment issues.
- [`decisions.md`](decisions.md) — project decisions and their rationale.
- [`schema.json`](schema.json) — shared data schema.
- [`data.md`](data.md) — data generation and dataset notes.
- [`../README.md`](../README.md) — project overview and main entry points.

Update this guide when the tested installation process changes. Record measured environment facts and benchmark results in `environment.md`, and record cross-team technical decisions in `decisions.md`.
