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

## Model serving

| Item | Value |
|---|---|
| Model and size | `granite-4.0-h-350m-base-be.f16.gguf`, approximately 653.2 MB |
| Serving method (from the provided lab) | Preconfigured LinuxONE JupyterLab Docker image using `llama-cpp-python` 0.3.36 and `loan_demo.rag_utils` |
| Time for a short prompt | Not yet measured separately |
| Time for a long prompt | One test took 11.37 seconds for a prompt requesting up to 100 tokens; this is not a controlled benchmark |

## Known problems

- The project virtual environment uses system packages (`--system-site-packages`) because installing scientific Python dependencies through pip failed in this environment.
- The model loads and generates text in the provided JupyterLab container. zDNN acceleration has not been independently verified.
- The reference model environment is inside the JupyterLab container. Direct integration between that environment and the project virtual environment on the VM has not yet been verified.
