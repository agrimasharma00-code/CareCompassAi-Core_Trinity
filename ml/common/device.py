import random
import numpy as np

def seed_everything(seed=17):
    random.seed(seed); np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    except ImportError: pass

def get_device():
    import torch
    if torch.cuda.is_available(): return torch.device("cuda")
    if hasattr(torch.backends,"mps") and torch.backends.mps.is_available(): return torch.device("mps")
    return torch.device("cpu")

def autocast_context(device):
    import torch
    return torch.autocast(device_type=device.type, enabled=device.type=="cuda")
