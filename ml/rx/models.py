"""Custom RxCNN and ResNet18 transfer-learning model."""

from __future__ import annotations

import logging
from pathlib import Path

import torch
from torch import nn

logger = logging.getLogger(__name__)


class RxCNN(nn.Module):
    """A compact CNN that preserves the long horizontal shape of written words."""

    def __init__(self, num_classes: int) -> None:
        super().__init__()

        def convs(in_channels: int, out_channels: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False), nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True),
                nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False), nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True),
            )

        self.block1 = nn.Sequential(convs(1, 32), nn.MaxPool2d(2), nn.Dropout2d(0.10))
        self.block2 = nn.Sequential(convs(32, 64), nn.MaxPool2d(2), nn.Dropout2d(0.15))
        self.block3 = nn.Sequential(convs(64, 128), nn.MaxPool2d(2), nn.Dropout2d(0.20))
        self.block4 = nn.Sequential(convs(128, 256), nn.MaxPool2d((2, 1)), nn.Dropout2d(0.25))
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(nn.Flatten(), nn.Linear(256, 256), nn.ReLU(inplace=True), nn.Dropout(0.4), nn.Linear(256, num_classes))

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        x = self.block1(image); x = self.block2(x); x = self.block3(x); x = self.block4(x)
        return self.classifier(self.pool(x))


class ResNetRx(nn.Module):
    """ResNet18 wrapper that accepts grayscale words and repeats them to RGB."""

    def __init__(self, backbone: nn.Module, num_classes: int) -> None:
        super().__init__()
        self.backbone = backbone
        features = backbone.fc.in_features
        backbone.fc = nn.Sequential(nn.Dropout(0.3), nn.Linear(features, num_classes))

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.backbone(image.repeat(1, 3, 1, 1))


def build_model(name: str, num_classes: int, pretrained: bool = True) -> tuple[nn.Module, str]:
    if name == "custom":
        return RxCNN(num_classes), "custom"
    try:
        from torchvision.models import ResNet18_Weights, resnet18
        try:
            backbone = resnet18(weights=ResNet18_Weights.DEFAULT if pretrained else None)
        except Exception as error:
            logger.warning("ResNet18 pretrained weights unavailable (%s); using random initialization.", error)
            backbone = resnet18(weights=None)
        return ResNetRx(backbone, num_classes), "resnet18"
    except Exception as error:
        logger.warning("ResNet18 setup failed (%s); falling back to custom RxCNN.", error)
        return RxCNN(num_classes), "custom_fallback"


def load_model(model_type: str, num_classes: int) -> nn.Module:
    if model_type in {"custom", "custom_fallback"}: return RxCNN(num_classes)
    if model_type == "resnet18":
        from torchvision.models import resnet18
        return ResNetRx(resnet18(weights=None), num_classes)
    return RxCNN(num_classes)


def write_summary(model: nn.Module, path: str | Path, height: int = 64, width: int = 256) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    shapes: list[str] = []; hooks = []
    for name, layer in model.named_modules():
        if name and not any(layer.children()):
            hooks.append(layer.register_forward_hook(lambda _m, _i, out, n=name: shapes.append(f"{n}\t{tuple(out.shape) if hasattr(out, 'shape') else type(out).__name__}")))
    with torch.no_grad(): model.eval()(torch.zeros(1, 1, height, width))
    for hook in hooks: hook.remove()
    params = sum(parameter.numel() for parameter in model.parameters())
    path.write_text("Layer\tOutput shape\n" + "\n".join(shapes) + f"\n\nTrainable parameters: {params:,}\n", encoding="utf-8")
