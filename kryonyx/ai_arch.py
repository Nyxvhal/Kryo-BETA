"""Network definitions for the optional AI worker (imported only by ai_worker).

Vendored, inference-only copies; no training code, no remote code execution:
  * SRVGGNetCompact - Real-ESRGAN (c) 2021 Xintao Wang, BSD-3-Clause.
  * RRDBNet         - BasicSR (c) 2018-2022 Xintao Wang et al., Apache-2.0.
  * IFNet/Contextnet/Unet/warp - ECCV2022-RIFE (c) Megvii Inc., MIT.
Changes: device-agnostic warp grid, `is None` tests, the training-only
teacher/distillation branch of IFNet is removed (it never runs at inference).
"""
from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


# --------------------------------------------------------------- Real-ESRGAN
class SRVGGNetCompact(nn.Module):
    def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=16, upscale=4, act_type='prelu'):
        super().__init__()
        self.upscale = upscale
        def act():
            if act_type == 'relu': return nn.ReLU(inplace=True)
            if act_type == 'leakyrelu': return nn.LeakyReLU(negative_slope=0.1, inplace=True)
            return nn.PReLU(num_parameters=num_feat)
        self.body = nn.ModuleList([nn.Conv2d(num_in_ch, num_feat, 3, 1, 1), act()])
        for _ in range(num_conv):
            self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1)); self.body.append(act())
        self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
        self.upsampler = nn.PixelShuffle(upscale)

    def forward(self, x):
        out = x
        for layer in self.body:
            out = layer(out)
        out = self.upsampler(out)
        return out + F.interpolate(x, scale_factor=self.upscale, mode='nearest')


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat=64, num_grow_ch=32):
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat, num_grow_ch=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    """x4 only (RealESRGAN_x4plus); the x2/x1 pixel-unshuffle variants are unused."""
    def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32):
        super().__init__()
        self.upscale = 4
        self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(num_feat, num_grow_ch) for _ in range(num_block)])
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode='nearest')))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode='nearest')))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


# ---------------------------------------------------------------------- RIFE
_GRID = {}


def warp(tensor, flow):
    key = (str(flow.device), flow.dtype, tuple(flow.size()))
    grid = _GRID.get(key)
    if grid is None:
        if len(_GRID) > 16: _GRID.clear()
        n, _, h, w = flow.shape
        horizontal = torch.linspace(-1.0, 1.0, w, device=flow.device, dtype=flow.dtype).view(1, 1, 1, w).expand(n, -1, h, -1)
        vertical = torch.linspace(-1.0, 1.0, h, device=flow.device, dtype=flow.dtype).view(1, 1, h, 1).expand(n, -1, -1, w)
        grid = _GRID[key] = torch.cat([horizontal, vertical], 1)
    flow = torch.cat([flow[:, 0:1] / ((tensor.shape[3] - 1.0) / 2.0), flow[:, 1:2] / ((tensor.shape[2] - 1.0) / 2.0)], 1)
    g = (grid + flow).permute(0, 2, 3, 1)
    return F.grid_sample(input=tensor, grid=g, mode='bilinear', padding_mode='border', align_corners=True)


def _conv(cin, cout, kernel_size=3, stride=1, padding=1, dilation=1):
    return nn.Sequential(nn.Conv2d(cin, cout, kernel_size=kernel_size, stride=stride, padding=padding, dilation=dilation, bias=True), nn.PReLU(cout))


def _deconv(cin, cout):
    return nn.Sequential(nn.ConvTranspose2d(in_channels=cin, out_channels=cout, kernel_size=4, stride=2, padding=1, bias=True), nn.PReLU(cout))


class Conv2(nn.Module):
    def __init__(self, cin, cout, stride=2):
        super().__init__()
        self.conv1 = _conv(cin, cout, 3, stride, 1)
        self.conv2 = _conv(cout, cout, 3, 1, 1)

    def forward(self, x):
        return self.conv2(self.conv1(x))


_C = 16


class Contextnet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = Conv2(3, _C); self.conv2 = Conv2(_C, 2 * _C)
        self.conv3 = Conv2(2 * _C, 4 * _C); self.conv4 = Conv2(4 * _C, 8 * _C)

    def forward(self, x, flow):
        out = []
        for layer in (self.conv1, self.conv2, self.conv3, self.conv4):
            x = layer(x)
            flow = F.interpolate(flow, scale_factor=0.5, mode='bilinear', align_corners=False, recompute_scale_factor=False) * 0.5
            out.append(warp(x, flow))
        return out


class Unet(nn.Module):
    def __init__(self):
        super().__init__()
        self.down0 = Conv2(17, 2 * _C); self.down1 = Conv2(4 * _C, 4 * _C)
        self.down2 = Conv2(8 * _C, 8 * _C); self.down3 = Conv2(16 * _C, 16 * _C)
        self.up0 = _deconv(32 * _C, 8 * _C); self.up1 = _deconv(16 * _C, 4 * _C)
        self.up2 = _deconv(8 * _C, 2 * _C); self.up3 = _deconv(4 * _C, _C)
        self.conv = nn.Conv2d(_C, 3, 3, 1, 1)

    def forward(self, img0, img1, warped_img0, warped_img1, mask, flow, c0, c1):
        s0 = self.down0(torch.cat((img0, img1, warped_img0, warped_img1, mask, flow), 1))
        s1 = self.down1(torch.cat((s0, c0[0], c1[0]), 1))
        s2 = self.down2(torch.cat((s1, c0[1], c1[1]), 1))
        s3 = self.down3(torch.cat((s2, c0[2], c1[2]), 1))
        x = self.up0(torch.cat((s3, c0[3], c1[3]), 1))
        x = self.up1(torch.cat((x, s2), 1))
        x = self.up2(torch.cat((x, s1), 1))
        x = self.up3(torch.cat((x, s0), 1))
        return torch.sigmoid(self.conv(x))


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):
        super().__init__()
        self.conv0 = nn.Sequential(_conv(in_planes, c // 2, 3, 2, 1), _conv(c // 2, c, 3, 2, 1))
        self.convblock = nn.Sequential(*[_conv(c, c) for _ in range(8)])
        self.lastconv = nn.ConvTranspose2d(c, 5, 4, 2, 1)

    def forward(self, x, flow, scale):
        if scale != 1:
            x = F.interpolate(x, scale_factor=1. / scale, mode='bilinear', align_corners=False)
        if flow is not None:
            flow = F.interpolate(flow, scale_factor=1. / scale, mode='bilinear', align_corners=False) * 1. / scale
            x = torch.cat((x, flow), 1)
        x = self.conv0(x)
        x = self.convblock(x) + x
        tmp = F.interpolate(self.lastconv(x), scale_factor=scale * 2, mode='bilinear', align_corners=False)
        return tmp[:, :4] * scale * 2, tmp[:, 4:5]


class IFNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.block0 = IFBlock(6, c=240)
        self.block1 = IFBlock(13 + 4, c=150)
        self.block2 = IFBlock(13 + 4, c=90)
        self.block_tea = IFBlock(16 + 4, c=90)  # weights exist in the checkpoint; unused at inference
        self.contextnet = Contextnet()
        self.unet = Unet()

    def forward(self, img0, img1, scale=(4, 2, 1)):
        flow = mask = None
        warped_img0, warped_img1 = img0, img1
        for i, block in enumerate((self.block0, self.block1, self.block2)):
            if flow is not None:
                flow_d, mask_d = block(torch.cat((img0, img1, warped_img0, warped_img1, mask), 1), flow, scale=scale[i])
                flow = flow + flow_d; mask = mask + mask_d
            else:
                flow, mask = block(torch.cat((img0, img1), 1), None, scale=scale[i])
            warped_img0 = warp(img0, flow[:, :2]); warped_img1 = warp(img1, flow[:, 2:4])
        soft = torch.sigmoid(mask)
        merged = warped_img0 * soft + warped_img1 * (1 - soft)
        c0 = self.contextnet(img0, flow[:, :2]); c1 = self.contextnet(img1, flow[:, 2:4])
        res = self.unet(img0, img1, warped_img0, warped_img1, mask, flow, c0, c1)[:, :3] * 2 - 1
        return torch.clamp(merged + res, 0, 1)
