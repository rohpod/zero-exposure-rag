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
| Model and size | `granite-4.0-h-350m-base-be.f16.gguf`, approximately 654 MB, copied from the JupyterLab container to `~/zero-exposure-rag/models/` on the host |
| Serving method | In-process via `llama-cpp-python` 0.3.36 in the project virtual environment, wrapped by `app/llm.py` (`generate(prompt, max_tokens, temperature)`); `n_ctx=2048` |
| Time for a short prompt | 2.58s for a prompt requesting up to 20 tokens (temperature 0) |
| Time for a long prompt | 104.19s for a prompt requesting up to 200 tokens (temperature 0); this is slow and may need a fallback (smaller/more quantised model, fewer max tokens) before the demo |

## Known problems

- The project virtual environment uses system packages (`--system-site-packages`) because installing scientific Python dependencies through pip failed in this environment.
- `llama-cpp-python` failed to build with pip's default CMake auto-detection (`-march=arch15`, which this GCC does not support). Fixed by forcing `CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS=-march=z16 -DCMAKE_CXX_FLAGS=-march=z16"`.
- The model has been verified to load and generate correctly in-process (outside the JupyterLab container) via `app/llm.py`. zDNN/NNPA acceleration has not been independently verified; the CPU backend variant selected by the build is `-march=arch15;-mvx;-mzvector` reported at build time, despite the compile flags above, so this should not be read as confirmation of any particular acceleration path.
- Long-prompt latency (104s for 200 tokens) is a concern for the live demo and needs a fallback decision before Stage 3 (see PROJECT.docx fallback table: smaller/more quantised model, fewer max tokens, fewer retrieved chunks).

## Installing llama-cpp-python on this VM

Plain `pip install llama-cpp-python` fails here: pip's CMake auto-detection selects `-march=arch15`, which this GCC does not support (max is `z16`/`arch14`). Install with:
CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS=-march=z16 -DCMAKE_CXX_FLAGS=-march=z16" pip install llama-cpp-python --no-cache-dir
