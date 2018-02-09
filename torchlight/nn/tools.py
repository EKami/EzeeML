from PIL import Image
import torch
from torch.autograd import Variable
import numpy as np
import torch.nn as nn
import PIL


class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self):
        self.val = 0
        self.sum = 0
        self.count = 0
        self.avg_mom = 0.98
        self.avg_loss_mom = 0.

    def reset(self):
        self.__init__()

    def update(self, val):
        self.val = val
        self.count += 1
        self.sum += val * self.count
        self.avg_loss_mom = self.avg_loss_mom * self.avg_mom + val * (1 - self.avg_mom)

    @property
    def avg(self):
        return self.sum / self.count

    @property
    def debias_loss(self):
        # More info: https://youtu.be/J99NV9Cr75I?t=2h4m
        return self.avg_loss_mom / (1 - self.avg_mom ** self.count)


def denormalize(image: np.ndarray, std, mean, channel_type="channel_first"):
    """
        Reverse the normalization done to an image.
    Args:
        image (np.ndarray): Image matrix
        std (np.ndarray, list): Standard deviation over channels
        mean (np.ndarray, list): Mean over channels
        channel_type (str): Either channel_first or channel_last
    Returns:
        np.ndarray: The image denormalized as (Height, Width, Channels)
    """
    if channel_type == "channel_first":
        image = np.transpose(image, (1, 2, 0))

    image = image * std + mean
    image = (image * 255).astype(np.uint8)
    return image


def image_to_tensor(image, mean=0, std=1.):
    """
    Transforms an image to a tensor and eventually normalize it
    Args:
        image (np.ndarray): A RGB array image
        mean: The mean of the image values
        std: The standard deviation of the image values
    Returns:
        tensor: A Pytorch tensor
    """
    image = image.astype(np.float32)
    image = (image - mean) / std
    image = image.transpose((2, 0, 1))
    tensor = torch.from_numpy(image)
    return tensor


def to_np(v):
    """

    Args:
        v (Variable, Tensor, PIL.Image.Image):
            Pytorch Variable/Tensor or Pillow image
    Returns:
        np.ndarray: A numpy array
    """
    if isinstance(v, Variable):
        v = v.data.cpu().numpy()
    elif isinstance(v, PIL.Image.Image):
        v = np.asarray(v)
    return v


def to_gpu(x, *args, **kwargs):
    """
    Moves torch tensor to gpu if possible

    Returns:
        torch.Tensor: Moved to the GPU or not
    """
    return x.cuda(*args, **kwargs) if torch.cuda.is_available() else x


def children(module: nn.Module):
    """
        Returns a list of an nn.Module children modules
        (in other terms the list of layers of a given model)
    Args:
        module (nn.Module):
            A Pytorch module
    Returns:
        list: A list of the module children
    """
    return module if isinstance(module, (list, tuple)) else list(module.children())


def to_onehot_tensor(y: np.ndarray):
    """
    Turn a numpy array with indices to a torch onehot tensor
    Args:
        y (np.ndarray): The numpy array with indices

    Returns:
        torch.IntTensor: The onehot tensor
    """
    y_onehot = torch.IntTensor(len(y), len(np.unique(y)))
    y_onehot.zero_()
    labels_tensors = torch.unsqueeze(torch.from_numpy(y.astype(np.long)), 1)
    y_onehot.scatter_(1, labels_tensors, 1)
    return y_onehot
