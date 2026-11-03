"""SimpleHTR-inspired convolutional recurrent network with CTC output."""

from __future__ import annotations

import torch
from torch import nn


class CRNN(nn.Module):
    """CNN features become a left-to-right sequence for a bidirectional LSTM."""

    def __init__(self, num_characters: int, input_height: int = 32, input_width: int = 128, hidden_size: int = 256) -> None:
        super().__init__()
        if input_height < 32 or input_width < 32:
            raise ValueError("RxRead CRNN input must be at least 32 pixels high and wide.")
        self.input_height, self.input_width = input_height, input_width

        def block(in_channels: int, out_channels: int, kernel: int, pool: tuple[int, int]) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel, padding=kernel // 2, bias=False),
                nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True), nn.MaxPool2d(pool),
            )

        self.features = nn.Sequential(
            block(1, 32, 5, (2, 2)),
            block(32, 64, 5, (2, 2)),
            block(64, 128, 3, (2, 1)),
            block(128, 128, 3, (2, 1)),
            block(128, 256, 3, (2, 1)),
        )
        self.sequence = nn.LSTM(256, hidden_size, num_layers=2, dropout=0.25, bidirectional=True)
        self.classifier = nn.Linear(hidden_size * 2, num_characters)

    def time_steps(self, width: int | None = None) -> int:
        # The width is halved by the first two pooling layers only.
        return max(1, (width or self.input_width) // 4)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        features = self.features(image)
        # Collapse any remaining height (e.g. 64px configured inputs) while
        # retaining the horizontal sequence dimension for CTC decoding.
        features = features.mean(dim=2).permute(2, 0, 1)
        sequence, _ = self.sequence(features)
        return self.classifier(sequence).log_softmax(dim=2)


def write_summary(model: CRNN, path: str) -> None:
    from pathlib import Path
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    parameters = sum(parameter.numel() for parameter in model.parameters())
    target.write_text(
        f"CRNN input: 1×{model.input_height}×{model.input_width}\n"
        f"CNN output sequence steps: {model.time_steps()}\n"
        "CNN: conv blocks 32/64/128/128/256; height pooled to a sequence\n"
        "Sequence: 2-layer bidirectional LSTM\n"
        f"CTC classes including blank: {model.classifier.out_features}\nParameters: {parameters:,}\n",
        encoding="utf-8",
    )
