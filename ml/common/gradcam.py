"""Hooks-based Grad-CAM utility for a selected convolution layer."""
def gradcam(model, image_tensor, target_layer):
    import torch
    activations=[]; gradients=[]
    def forward(_module,_inputs,output): activations.append(output)
    def backward(_module,_grad_input,grad_output): gradients.append(grad_output[0])
    h1=target_layer.register_forward_hook(forward); h2=target_layer.register_full_backward_hook(backward)
    try:
        model.zero_grad(set_to_none=True); logits=model(image_tensor); logits.gather(1,logits.argmax(1,keepdim=True)).sum().backward()
        weights=gradients[-1].mean(dim=(-2,-1),keepdim=True);cam=torch.relu((weights*activations[-1]).sum(1,keepdim=True))
        cam=torch.nn.functional.interpolate(cam,size=image_tensor.shape[-2:],mode="bilinear",align_corners=False);cam=cam[0,0].detach().cpu().numpy();cam=(cam-cam.min())/(cam.max()-cam.min()+1e-8);return cam
    finally: h1.remove();h2.remove()
