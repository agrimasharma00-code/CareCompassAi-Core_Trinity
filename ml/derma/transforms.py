"""Evaluation preprocessing shared by training, evaluation and the service."""
def preprocess_eval(image, size=224):
    from torchvision import transforms
    from .config import IMAGENET_MEAN,IMAGENET_STD
    pipeline=transforms.Compose([transforms.Resize(size+16),transforms.CenterCrop(size),transforms.ToTensor(),transforms.Normalize(IMAGENET_MEAN,IMAGENET_STD)])
    return pipeline(image.convert("RGB"))

def training_transform(size=224):
    from torchvision import transforms
    from .config import IMAGENET_MEAN,IMAGENET_STD
    return transforms.Compose([transforms.RandomResizedCrop(size,scale=(.8,1)),transforms.RandomHorizontalFlip(),transforms.RandomVerticalFlip(),transforms.RandomRotation(20),transforms.ColorJitter(.2,.2,.2,.02),transforms.ToTensor(),transforms.Normalize(IMAGENET_MEAN,IMAGENET_STD)])
