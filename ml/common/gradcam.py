"""Minimal Grad-CAM with PyTorch forward/backward hooks."""

from __future__ import annotations

import io

import numpy as np
import torch
from PIL import Image


def gradcam_overlay(model, image: torch.Tensor, class_index: int, layer_name: str) -> Image.Image:
    layers=dict(model.named_modules())
    if layer_name not in layers: raise ValueError(f"Grad-CAM layer not found: {layer_name}")
    activations=[]; gradients=[]
    def forward_hook(_module, _inputs, output):
        activations.append(output)
        output.register_hook(lambda gradient: gradients.append(gradient))
    handle=layers[layer_name].register_forward_hook(forward_hook)
    model.zero_grad(set_to_none=True); logits=model(image); logits[0,class_index].backward(); handle.remove()
    weights=gradients[-1].mean(dim=(2,3),keepdim=True); heat=(weights*activations[-1]).sum(1).relu()[0].detach().cpu().numpy()
    heat=(heat-heat.min())/(heat.max()-heat.min()+1e-8); heat=Image.fromarray(np.uint8(heat*255)).resize((image.shape[-1],image.shape[-2]))
    return heat


def overlay_png(model, image: torch.Tensor, class_index: int, layer_name: str, unnormalize=None) -> bytes:
    heat=gradcam_overlay(model,image,class_index,layer_name)
    base=image[0].detach().cpu().float()
    if unnormalize: base=unnormalize(base)
    if base.shape[0]==1: base=base.repeat(3,1,1)
    array=base.permute(1,2,0).numpy(); array=np.clip(array,0,1); original=Image.fromarray(np.uint8(array*255))
    color=Image.new("RGB",original.size,(255,0,0)); import PIL.ImageChops as image_chops
    mask=heat.point(lambda value: min(160,max(0,int(value*.55))))
    blended=Image.composite(color,original,mask); output=Image.blend(original,blended,0.55); buffer=io.BytesIO(); output.save(buffer,format="PNG"); return buffer.getvalue()
