def build_model(name="custom", pretrained=True):
    try:
        import torch.nn as nn
        from torchvision import models
    except ImportError as exc:
        raise RuntimeError("Install the isolated ML environment from ml/requirements-ml.txt") from exc
    if name == "custom":
        class Block(nn.Module):
            def __init__(self, a, b, dropout):
                super().__init__()
                self.layers = nn.Sequential(nn.Conv2d(a,b,3,padding=1,bias=False),nn.BatchNorm2d(b),nn.ReLU(inplace=True),nn.Conv2d(b,b,3,padding=1,bias=False),nn.BatchNorm2d(b),nn.ReLU(inplace=True),nn.MaxPool2d(2),nn.Dropout2d(dropout))
            def forward(self,x): return self.layers(x)
        class DermaCNN(nn.Module):
            def __init__(self):
                super().__init__()
                self.features=nn.Sequential(Block(3,32,.1),Block(32,64,.15),Block(64,128,.2),Block(128,256,.25),nn.AdaptiveAvgPool2d(1))
                self.classifier=nn.Sequential(nn.Flatten(),nn.Linear(256,128),nn.ReLU(inplace=True),nn.Dropout(.4),nn.Linear(128,7))
            def forward(self,x): return self.classifier(self.features(x))
        return DermaCNN()
    if name not in {"effnet", "resnet50"}: raise ValueError(f"Unknown model: {name}")
    enum = models.EfficientNet_B0_Weights.DEFAULT if name == "effnet" else models.ResNet50_Weights.DEFAULT
    constructor = models.efficientnet_b0 if name == "effnet" else models.resnet50
    try: model = constructor(weights=enum if pretrained else None)
    except Exception as exc:
        print(f"Pretrained weights unavailable for {name}: {exc}; using random initialization.")
        model = constructor(weights=None)
    if name == "effnet": model.classifier[1] = nn.Linear(model.classifier[1].in_features,7)
    else: model.fc = nn.Linear(model.fc.in_features,7)
    return model
