# Environment notes

Facts about the LinuxONE VM and our setup. Record what you observed, not what you expect. Update the date when a value changes.

## VM

| Item | Value | Checked by | Date |
|---|---|---|---|
| Distribution and version | | | |
| Architecture (`uname -m`) | | | |
| CPU count (`nproc`) | | | |
| Memory (`free -h`) | | | |
| Disk (`df -h`) | | | |
| Python version | | | |
| Git version | | | |
| Docker available | | | |
| Outbound internet works | | | |
| How the dashboard is reached (open port or SSH tunnel) | | | |
| VM expiry or reset behaviour | | | |

## Access

| Member | Can SSH in | Can clone the repo on the VM | Can open a pull request |
|---|---|---|---|
| Member 1 | | | |
| Member 2 | | | |
| Member 3 | | | |
| Member 4 | | | |

## Python packages tested on s390x

| Package | Installs with pip | Notes (build from source, distro package, fails) |
|---|---|---|
| numpy | | |
| scikit-learn | | |
| fastapi and uvicorn | | |
| rank_bm25 | | |
| faker | | |
| pytest | | |

## Model serving

| Item | Value |
|---|---|
| Model and size | |
| Serving method (from the provided lab) | |
| Time for a short prompt | |
| Time for a long prompt | |

## Known problems

<!-- Anything that does not work yet and what we do instead. -->
