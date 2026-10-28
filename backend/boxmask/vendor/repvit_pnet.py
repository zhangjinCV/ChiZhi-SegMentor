#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RepViT-M1.1 + PNet 解码器的轻量 6 通道分割模型。

  x (6ch) = RGB ‖ RGB×box
      ↓
  RepViT-M1.1 单骨干（stem 首层 3→6 通道，预训练权重复制两份）
      ↓  4 个 stage：64/128/256/512 @ stride 4/8/16/32
  1×1 卷积统一到 64 通道 → 每个 stage 一个 ETM(64,64)
      ↓
  PNet 的 UNetDecoderWithEdges（4 级深监督，mask + boundary 双头）
      ↓
  pred_0 + 4 个 mask 输出 + 4 个 boundary 输出

与 PNet 的区别：没有双分支、没有 GCM3/ETM 特征融合；prior 由轻量头
（stride-32 特征 → 1×1 conv → 1 通道）生成，替代 GPM。

用法:
    python repvit_pnet.py      # 形状/参数量/速度自检
"""
# Vendored from the model6ch training repo (RepViTPNet).
# The RepViT backbone is Apache-2.0; see REPVIT_LICENSE in this directory.
# Only the inference-relevant code path is kept.
import logging
import os

import torch
import torch.nn as nn
import torch.nn.functional as F

from .repvit import repvit_m1_1

log = logging.getLogger(__name__)

# Inference always loads a full segmentation checkpoint explicitly.  Keeping the
# training-time ImageNet backbone path here would make PyInstaller depend on a
# file that is not shipped with the app.
WEIGHTS = None


# ---------------------------------------------------------------- PNet 解码器
class BasicConv2d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride=1, padding=0,
                 dilation=1, need_relu=True):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride,
                              padding, dilation, bias=False)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()
        self.need_relu = need_relu

    def forward(self, x):
        x = self.bn(self.conv(x))
        return self.relu(x) if self.need_relu else x


class BasicDeConv2d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride=1, padding=0,
                 dilation=1, out_padding=0, need_relu=True):
        super().__init__()
        self.conv = nn.ConvTranspose2d(in_channels, out_channels, kernel_size,
                                       stride=stride, padding=padding,
                                       output_padding=out_padding, dilation=dilation,
                                       bias=False)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()
        self.need_relu = need_relu

    def forward(self, x):
        x = self.bn(self.conv(x))
        return self.relu(x) if self.need_relu else x


class ETM(nn.Module):
    """PNet 的 ETM：多尺度条带卷积 + 残差，输入输出同宽。"""

    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.relu = nn.ReLU(True)
        self.branch0 = BasicConv2d(in_channels, out_channels, 3, 1, 1)
        self.branch1 = nn.Sequential(
            BasicConv2d(out_channels, out_channels, 1),
            BasicConv2d(out_channels, out_channels, kernel_size=(1, 3), padding=(0, 1)),
            BasicConv2d(out_channels, out_channels, kernel_size=(3, 1), padding=(1, 0)),
            BasicConv2d(out_channels, out_channels, kernel_size=(1, 5), padding=(0, 2)),
            BasicConv2d(out_channels, out_channels, kernel_size=(5, 1), padding=(2, 0)))
        self.branch2 = nn.Sequential(
            BasicConv2d(out_channels, out_channels, 1),
            BasicConv2d(out_channels, out_channels, kernel_size=(1, 5), padding=(0, 2)),
            BasicConv2d(out_channels, out_channels, kernel_size=(5, 1), padding=(2, 0)),
            BasicConv2d(out_channels, out_channels, kernel_size=(1, 7), padding=(0, 3)),
            BasicConv2d(out_channels, out_channels, kernel_size=(7, 1), padding=(3, 0)))
        self.branch3 = nn.Sequential(
            BasicConv2d(out_channels, out_channels, 1),
            BasicConv2d(out_channels, out_channels, kernel_size=(1, 7), padding=(0, 3)),
            BasicConv2d(out_channels, out_channels, kernel_size=(7, 1), padding=(3, 0)),
            BasicConv2d(out_channels, out_channels, kernel_size=(1, 9), padding=(0, 4)),
            BasicConv2d(out_channels, out_channels, kernel_size=(9, 1), padding=(4, 0)))
        self.conv_cat = BasicConv2d(4 * out_channels, out_channels, 1, padding=0)
        self.conv_res = BasicConv2d(in_channels, out_channels, 3, 1, 1)

    def forward(self, x):
        x0 = self.branch0(x)
        x1 = self.branch1(x0)
        x2 = self.branch2(x1)
        x3 = self.branch3(x2)
        x_cat = self.conv_cat(torch.cat((x0, x1, x2, x3), 1))
        return self.relu(x_cat + self.conv_res(x))


class UNetDecoderWithEdgesBlock(nn.Module):
    def __init__(self, in_channels, mid_channels):
        super().__init__()
        self.conv = nn.Conv2d(in_channels * 2, in_channels, kernel_size=1)
        self.out_y = nn.Sequential(
            BasicConv2d(in_channels * 2, mid_channels, kernel_size=3, padding=1),
            BasicConv2d(mid_channels, mid_channels // 2, kernel_size=3, padding=1),
            nn.Conv2d(mid_channels // 2, 1, kernel_size=3, padding=1))
        self.out_B = nn.Sequential(
            BasicDeConv2d(in_channels, mid_channels // 2, kernel_size=3, stride=2,
                          padding=1, out_padding=1),
            BasicConv2d(mid_channels // 2, mid_channels // 4, kernel_size=3, padding=1),
            nn.Conv2d(mid_channels // 4, 1, kernel_size=3, padding=1))
        self.ode = nn.Sequential(
            BasicConv2d(in_channels, in_channels, kernel_size=3, padding=1),
            BasicConv2d(in_channels, in_channels, kernel_size=3, padding=1))

    def forward(self, x, prior_cam):
        prior_cam = F.interpolate(prior_cam, size=x.size()[2:], mode='bilinear',
                                  align_corners=True)
        yt = self.conv(torch.cat([x, prior_cam.expand(-1, x.size()[1], -1, -1)], dim=1))
        ode_out = self.ode(yt)
        bound = self.out_B(ode_out)
        bound = self.edge_enhance(bound)

        r_prior_cam = -1 * (torch.sigmoid(prior_cam)) + 1
        y = r_prior_cam.expand(-1, x.size()[1], -1, -1).mul(x)
        cat2 = torch.cat([y, ode_out], dim=1)
        y = self.out_y(cat2)
        y = y + prior_cam
        return y, bound

    def edge_enhance(self, img):
        gradient = img.clone()
        gradient[:, :, :-1, :] = abs(gradient[:, :, :-1, :] - gradient[:, :, 1:, :])
        gradient[:, :, :, :-1] = abs(gradient[:, :, :, :-1] - gradient[:, :, :, 1:])
        return torch.clamp(img - gradient, 0, 1)


class UNetDecoderWithEdges(nn.Module):
    def __init__(self, in_channels, mid_channels):
        super().__init__()
        self.REU_f1 = UNetDecoderWithEdgesBlock(in_channels, mid_channels)
        self.REU_f2 = UNetDecoderWithEdgesBlock(in_channels, mid_channels)
        self.REU_f3 = UNetDecoderWithEdgesBlock(in_channels, mid_channels)
        self.REU_f4 = UNetDecoderWithEdgesBlock(in_channels, mid_channels)

    def forward(self, x, prior_0, pic):
        f1, f2, f3, f4 = x
        hw = pic.size()[2:]

        f4_out, bound_f4 = self.REU_f4(f4, prior_0)
        f4 = F.interpolate(f4_out, size=hw, mode='bilinear', align_corners=True)
        bound_f4 = F.interpolate(bound_f4, size=hw, mode='bilinear', align_corners=True)

        f3_out, bound_f3 = self.REU_f3(f3, f4_out)
        f3 = F.interpolate(f3_out, size=hw, mode='bilinear', align_corners=True)
        bound_f3 = F.interpolate(bound_f3, size=hw, mode='bilinear', align_corners=True)

        f2_out, bound_f2 = self.REU_f2(f2, f3_out)
        f2 = F.interpolate(f2_out, size=hw, mode='bilinear', align_corners=True)
        bound_f2 = F.interpolate(bound_f2, size=hw, mode='bilinear', align_corners=True)

        f1_out, bound_f1 = self.REU_f1(f1, f2_out)
        f1 = F.interpolate(f1_out, size=hw, mode='bilinear', align_corners=True)
        bound_f1 = F.interpolate(bound_f1, size=hw, mode='bilinear', align_corners=True)

        return f4, f3, f2, f1, bound_f4, bound_f3, bound_f2, bound_f1


# ------------------------------------------------------------------- 骨干
class RepViT6(nn.Module):
    """RepViT-M1.1，stem 改 6 通道，返回 stride 4/8/16/32 的特征。"""

    def __init__(self, weights=WEIGHTS):
        super().__init__()
        m = repvit_m1_1(distillation=True)
        if weights and os.path.exists(weights):
            sd = torch.load(weights, map_location='cpu', weights_only=False)['model']
            m.load_state_dict(sd)
        elif weights:
            log.warning('RepViT backbone weights not found: %s', weights)

        stem = m.features[0]                  # [Conv2d_BN(3,32,3,2,1), GELU, Conv2d_BN(32,64,3,2,1)]
        c0 = stem[0].c
        c6 = nn.Conv2d(6, c0.out_channels, c0.kernel_size, c0.stride,
                       c0.padding, bias=False)
        with torch.no_grad():
            c6.weight.copy_(torch.cat([c0.weight.data, c0.weight.data], dim=1))
        stem[0].c = c6
        self.stem = stem
        self.blocks = nn.Sequential(*list(m.features[1:]))
        self.out_channels = [64, 128, 256, 512]
        self._ends = (1, 5, 19, 22)           # blocks 里的 stage 末尾下标

    def forward(self, x):
        x = self.stem(x)
        outs = []
        for i, b in enumerate(self.blocks):
            x = b(x)
            if i in self._ends:
                outs.append(x)
        return outs


class RepViTPNet(nn.Module):
    def __init__(self, channels=64, mid=64, weights=WEIGHTS):
        super().__init__()
        self.backbone = RepViT6(weights)
        chs = self.backbone.out_channels
        self.proj = nn.ModuleList([nn.Conv2d(c, channels, 1) for c in chs])
        self.etm = nn.ModuleList([ETM(channels, channels) for _ in chs])
        self.prior = nn.Sequential(
            nn.Conv2d(chs[-1], channels, 1, bias=False),
            nn.BatchNorm2d(channels), nn.ReLU(inplace=True),
            nn.Conv2d(channels, 1, 1))
        self.decoder = UNetDecoderWithEdges(channels, mid)

    def forward(self, x, pic=None):
        if pic is None:
            pic = x
        feats = self.backbone(x)
        f1, f2, f3, f4 = [e(p(f)) for p, e, f in zip(self.proj, self.etm, feats)]
        prior_cam = self.prior(feats[-1])
        pred_0 = F.interpolate(prior_cam, size=pic.shape[-2:], mode='bilinear',
                               align_corners=False)
        f4o, f3o, f2o, f1o, b4, b3, b2, b1 = self.decoder(
            [f1, f2, f3, f4], prior_cam, pic)
        return pred_0, f4o, f3o, f2o, f1o, b4, b3, b2, b1


if __name__ == '__main__':
    net = RepViTPNet(weights=None).eval()
    n = sum(p.numel() for p in net.parameters())
    print('parameters: %.2f M' % (n / 1e6))
    with torch.inference_mode():
        x = torch.randn(1, 6, 512, 768)
        out = net(x)
        for i, o in enumerate(out):
            print('  out[%d] %s' % (i, tuple(o.shape)))
