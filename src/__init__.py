"""
ml.src — Zero-Touch Customs Engine ML package root.
"""

# Batasi thread SEBELUM torch di-import DI MANAPUN
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("PYTORCH_NUM_THREADS", "1")

try:
    import torch
    torch.set_num_threads(1)
    torch.set_flush_denormal(True)
except Exception:
    pass
