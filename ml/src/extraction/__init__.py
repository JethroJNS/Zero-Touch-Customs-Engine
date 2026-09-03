"""
ml.src.extraction — Extraction pipeline package.
"""

# Batasi thread SEBELUM torch di-import di submodule manapun
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("PYTORCH_NUM_THREADS", "1")

try:
    import torch
    torch.set_num_threads(1)
    torch.set_flush_denormal(True)  # Matikan denormal floats (lebih cepat & hemat memory)
except Exception:
    pass
