"""Minimal timm-compatible pieces used by the vendored RepViT.

The inference model only needs SqueezeExcite, trunc_normal_ and the
register_model decorator.  Vendoring these few pieces keeps timm/torchvision
(and their large dependency tree) out of the packaged application.  The code
follows timm 0.9.16 (Apache-2.0, Ross Wightman).
"""

from __future__ import annotations

import torch
import torch.nn as nn


def make_divisible(v, divisor=8, min_value=None, round_limit=0.9):
    min_value = min_value or divisor
    new_v = max(min_value, int(v + divisor / 2) // divisor * divisor)
    if new_v < round_limit * v:
        new_v += divisor
    return new_v


class SqueezeExcite(nn.Module):
    """Squeeze-and-Excitation module, matching timm's SEModule defaults."""

    def __init__(
        self,
        channels,
        rd_ratio=1.0 / 16,
        rd_channels=None,
        rd_divisor=8,
        add_maxpool=False,
        bias=True,
        act_layer=nn.ReLU,
        norm_layer=None,
        gate_layer="sigmoid",
    ):
        super().__init__()
        self.add_maxpool = add_maxpool
        if not rd_channels:
            rd_channels = make_divisible(channels * rd_ratio, rd_divisor, round_limit=0.0)
        self.fc1 = nn.Conv2d(channels, rd_channels, kernel_size=1, bias=bias)
        self.bn = norm_layer(rd_channels) if norm_layer else nn.Identity()
        self.act = act_layer(inplace=True)
        self.fc2 = nn.Conv2d(rd_channels, channels, kernel_size=1, bias=bias)
        self.gate = nn.Sigmoid() if gate_layer == "sigmoid" else nn.Hardsigmoid()

    def forward(self, x):
        x_se = x.mean((2, 3), keepdim=True)
        if self.add_maxpool:
            x_se = 0.5 * x_se + 0.5 * x.amax((2, 3), keepdim=True)
        x_se = self.fc1(x_se)
        x_se = self.act(self.bn(x_se))
        x_se = self.fc2(x_se)
        return x * self.gate(x_se)


def trunc_normal_(tensor, mean=0.0, std=1.0, a=-2.0, b=2.0):
    with torch.no_grad():
        return nn.init.trunc_normal_(tensor, mean=mean, std=std, a=a, b=b)


def register_model(fn):
    """No-op decorator; the application constructs repvit_m1_1 directly."""
    return fn
