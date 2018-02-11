import torch.nn as nn
import torch.nn.functional as F
import math
from torchlight.nn.losses.srgan import GeneratorLoss


class Generator(nn.Module):
    def __init__(self, scale_factor, res_blocks_count=16):
        """
        Generator for SRGAN
        Args:
            scale_factor (int): The new scale for the resulting image (x2, x4...)
            res_blocks_count (int): Number of residual blocks, the less there is,
            the faster the inference time will be but the network will capture
            less information.
        """
        upsample_block_num = int(math.log(scale_factor, 2))

        super(Generator, self).__init__()
        self.block1 = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=9, padding=4),
            nn.PReLU()
        )
        self.res_blocks = []
        for i in range(res_blocks_count):
            self.res_blocks.append(ResidualBlock(64))

        self.res_blocks = nn.Sequential(*self.res_blocks)
        self.block_x1 = nn.Sequential(
            nn.Conv2d(64, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64)
        )
        self.block_x2 = nn.Sequential(*[UpsampleBLock(64, 2) for _ in range(upsample_block_num)])
        self.block_x3 = nn.Conv2d(64, 3, kernel_size=9, padding=4)

    def forward(self, x):
        block1 = self.block1(x)
        res_blocks = self.res_blocks(block1)
        block_x1 = self.block_x1(res_blocks)
        block_x2 = self.block_x2(block1 + block_x1)  # ElementWise sum
        block_x3 = self.block_x3(block_x2)

        return (F.tanh(block_x3) + 1) / 2


class ResidualBlock(nn.Module):
    def __init__(self, channels):
        super(ResidualBlock, self).__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(channels)
        self.prelu = nn.PReLU()
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(channels)

    def forward(self, x):
        residual = self.conv1(x)
        residual = self.bn1(residual)
        residual = self.prelu(residual)
        residual = self.conv2(residual)
        residual = self.bn2(residual)

        return x + residual  # ElementWise sum


class UpsampleBLock(nn.Module):
    def __init__(self, in_channels, up_scale):
        super(UpsampleBLock, self).__init__()
        self.conv = nn.Conv2d(in_channels, in_channels * up_scale ** 2, kernel_size=3, padding=1)
        self.pixel_shuffle = nn.PixelShuffle(up_scale)
        self.prelu = nn.PReLU()

    def forward(self, x):
        x = self.conv(x)
        x = self.pixel_shuffle(x)
        x = self.prelu(x)
        return x


class Discriminator(nn.Module):
    def __init__(self):
        super(Discriminator, self).__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2),

            nn.Conv2d(64, 64, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(0.2),

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.2),

            nn.Conv2d(128, 128, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.2),

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.2),

            nn.Conv2d(256, 256, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.2),

            nn.Conv2d(256, 512, kernel_size=3, padding=1),
            nn.BatchNorm2d(512),
            nn.LeakyReLU(0.2),

            nn.Conv2d(512, 512, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(512),
            nn.LeakyReLU(0.2),

            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(512, 1024, kernel_size=1),
            nn.LeakyReLU(0.2),
            nn.Conv2d(1024, 1, kernel_size=1)
        )

    def forward(self, x):
        batch_size = x.size(0)
        return F.sigmoid(self.net(x).view(batch_size))


class SRGAN(nn.Module):
    def __init__(self, generator: nn.Module, discriminator: nn.Module, g_optim, d_optim):
        """
        The SRGAN module which takes as input a generator and a discriminator
        Args:
            g_optim (Optimizer): Generator optimizer
            d_optim (Optimizer): Discriminator optimizer
            generator (nn.Module): Model definition of the generator
            discriminator (nn.Module): Model definition of the discriminator
        """
        super().__init__()
        self.netG_optim = g_optim
        self.netD_optim = d_optim
        self.netD = discriminator
        self.netG = generator
        self.generator_loss = GeneratorLoss()  # TODO try with VGG54 as in the paper

    def _optimize(self, model, optim, loss, retain_graph=False):
        model.zero_grad()
        loss.backward(retain_graph=retain_graph)
        optim.step()

    def forward(self, data, target):
        ############################
        # (1) Update D network: maximize D(x)-1-D(G(z))
        ###########################
        gen_img = self.netG(data)
        d_real_out = self.netD(target).mean()
        d_fake_out = self.netD(gen_img).mean()
        d_loss = 1 - d_real_out + d_fake_out
        # TODO don't optimize in val/test pass
        self._optimize(self.netD, self.netD_optim, d_loss, retain_graph=True)

        ############################
        # (2) Update G network: minimize 1-D(G(z)) + Perception Loss + Image Loss + TV Loss
        ###########################
        g_loss = self.generator_loss(d_fake_out, gen_img, target)
        self._optimize(self.netG, self.netG_optim, g_loss)
        return gen_img, d_real_out, d_fake_out
