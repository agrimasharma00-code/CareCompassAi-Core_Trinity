"""Custom SkinCNN and a guarded torchvision transfer-learning factory."""

from __future__ import annotations

import logging
from pathlib import Path

import torch
from torch import nn

logger = logging.getLogger(__name__)


class SkinCNN(nn.Module):
    """Four readable convolution blocks followed by global pooling and a small head."""

    def __init__(self, num_classes: int = 7) -> None:
        super().__init__()

        def block(in_channels: int, out_channels: int, dropout: float) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True),
                nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
                nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True),
                nn.MaxPool2d(2), nn.Dropout2d(dropout),
            )

        self.features = nn.Sequential(
            block(3, 32, 0.10), block(32, 64, 0.15),
            block(64, 128, 0.20), block(128, 256, 0.25),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(nn.Flatten(), nn.Linear(256, 128), nn.ReLU(inplace=True), nn.Dropout(0.4), nn.Linear(128, num_classes))

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.pool(self.features(image)))


class EfficientNetSkin(nn.Module):
    def __init__(self, backbone: nn.Module, num_classes: int) -> None:
        super().__init__()
        self.backbone = backbone
        features = backbone.classifier[1].in_features
        backbone.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(features, num_classes))

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.backbone(image)


class MobileNetSkin(nn.Module):
    def __init__(self, backbone: nn.Module, num_classes: int) -> None:
        super().__init__()
        self.backbone = backbone
        features = backbone.classifier[-1].in_features
        backbone.classifier[-1] = nn.Linear(features, num_classes)
        backbone.classifier.insert(0, nn.Dropout(0.3))

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.backbone(image)


def build_model(name: str, num_classes: int = 7, pretrained: bool = True) -> tuple[nn.Module, str]:
    if name == "custom":
        return SkinCNN(num_classes), "custom"
    try:
        from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
        weights = EfficientNet_B0_Weights.DEFAULT if pretrained else None
        return EfficientNetSkin(efficientnet_b0(weights=weights), num_classes), "efficientnet_b0"
    except Exception as error:
        logger.warning("EfficientNet initialization failed (%s); trying MobileNetV3 without pretrained weights.", error)
        try:
            from torchvision.models import mobilenet_v3_small
            return MobileNetSkin(mobilenet_v3_small(weights=None), num_classes), "mobilenet_v3_small_random_init"
        except Exception as fallback_error:
            logger.warning("MobileNetV3 fallback failed (%s); using SkinCNN.", fallback_error)
            return SkinCNN(num_classes), "custom_fallback"


def load_model(model_type: str, num_classes: int) -> nn.Module:
    if model_type == "custom" or model_type == "custom_fallback": return SkinCNN(num_classes)
    if model_type == "efficientnet_b0":
        from torchvision.models import efficientnet_b0
        return EfficientNetSkin(efficientnet_b0(weights=None), num_classes)
    if model_type == "mobilenet_v3_small_random_init":
        from torchvision.models import mobilenet_v3_small
        return MobileNetSkin(mobilenet_v3_small(weights=None), num_classes)
    return SkinCNN(num_classes)


def write_summary(model: nn.Module, path: str | Path, input_size: int = 224) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    shapes: list[str] = []
    hooks = []
    for name, layer in model.named_modules():
        if name and not any(layer.children()):
            hooks.append(layer.register_forward_hook(lambda _m, _i, out, n=name: shapes.append(f"{n}\t{tuple(out.shape) if hasattr(out, 'shape') else type(out).__name__}")))
    with torch.no_grad():
        model.eval()(torch.zeros(1, 3, input_size, input_size))
    for hook in hooks: hook.remove()
    params = sum(parameter.numel() for parameter in model.parameters())
    path.write_text("Layer\tOutput shape\n" + "\n".join(shapes) + f"\n\nTrainable parameters: {params:,}\n", encoding="utf-8")
