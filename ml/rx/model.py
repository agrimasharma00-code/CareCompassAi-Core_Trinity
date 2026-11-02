def build_model(num_chars, height=32, width=128):
    try: import torch.nn as nn
    except ImportError as exc: raise RuntimeError("Install ml/requirements-ml.txt in an isolated environment") from exc
    class CRNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.cnn=nn.Sequential(nn.Conv2d(1,32,5,padding=2),nn.BatchNorm2d(32),nn.ReLU(),nn.MaxPool2d(2,2),nn.Conv2d(32,64,5,padding=2),nn.BatchNorm2d(64),nn.ReLU(),nn.MaxPool2d(2,2),nn.Conv2d(64,128,3,padding=1),nn.BatchNorm2d(128),nn.ReLU(),nn.MaxPool2d((2,1)),nn.Conv2d(128,128,3,padding=1),nn.BatchNorm2d(128),nn.ReLU(),nn.MaxPool2d((2,1)),nn.Conv2d(128,256,3,padding=1),nn.BatchNorm2d(256),nn.ReLU(),nn.AdaptiveAvgPool2d((1,None)))
            self.rnn=nn.LSTM(256,256,num_layers=2,bidirectional=True,dropout=.25)
            self.head=nn.Linear(512,num_chars)
        def forward(self,x):
            f=self.cnn(x).squeeze(2).permute(2,0,1); y,_=self.rnn(f); return self.head(y).log_softmax(-1)
    return CRNN()
