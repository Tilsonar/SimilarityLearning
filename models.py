#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from torch import nn
from sincnet import SincNet, MLP


class Flatten(nn.Module):
    def forward(self, x):
        return x.view(x.size(0), -1)


class SimNet(nn.Module):

    def __init__(self, loss_module=None):
        super(SimNet, self).__init__()
        self.loss_module = loss_module

    def layers(self):
        raise NotImplementedError

    def forward(self, x, y):
        for layer in self.layers():
            x = layer(x)
        logits = self.loss_module(x, y) if self.loss_module is not None else None
        return x, logits

    def all_params(self):
        params = [layer.parameters() for layer in self.layers()]
        if self.loss_module is not None:
            params.append(self.loss_module.parameters())
        return params


class MNISTNet(SimNet):

    def __init__(self, nfeat, loss_module=None):
        super(MNISTNet, self).__init__(loss_module)
        self.net = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=5, padding=2),
            nn.PReLU(),
            nn.Conv2d(32, 32, kernel_size=5, padding=2),
            nn.PReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=5, padding=2),
            nn.PReLU(),
            nn.Conv2d(64, 64, kernel_size=5, padding=2),
            nn.PReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=5, padding=2),
            nn.PReLU(),
            nn.Conv2d(128, 128, kernel_size=5, padding=2),
            nn.PReLU(),
            nn.MaxPool2d(2),
            Flatten(),
            nn.Linear(128 * 3 * 3, nfeat),
            nn.PReLU()
        )

    def layers(self):
        return [self.net]


class SpeakerNet(SimNet):

    def __init__(self, nfeat, sample_rate, window, loss_module=None):
        super(SpeakerNet, self).__init__(loss_module)
        wlen = int(sample_rate * window / 1000)
        self.cnn = SincNet({'input_dim': wlen,
                            'fs': sample_rate,
                            'cnn_N_filt': [80, 60, 60],
                            'cnn_len_filt': [251, 5, 5],
                            'cnn_max_pool_len': [3, 3, 3],
                            'cnn_use_laynorm_inp': True,
                            'cnn_use_batchnorm_inp': False,
                            'cnn_use_laynorm': [True, True, True],
                            'cnn_use_batchnorm': [False, False, False],
                            'cnn_act': ['leaky_relu', 'leaky_relu', 'leaky_relu'],
                            'cnn_drop': [0., 0., 0.],
                            })
        self.dnn = MLP({'input_dim': self.cnn.out_dim,
                        'fc_lay': [2048, 2048, nfeat],
                        'fc_drop': [0., 0., 0.],
                        'fc_use_batchnorm': [True, True, True],
                        'fc_use_laynorm': [False, False, False],
                        'fc_use_laynorm_inp': True,
                        'fc_use_batchnorm_inp': False,
                        'fc_act': ['leaky_relu', 'leaky_relu', 'leaky_relu'],
                        })

    def layers(self):
        return [self.cnn, self.dnn]


"""
if __name__ == '__main__':
    x = torch.rand(50, 3200)
    y = torch.randint(0, 1251, (50,))
    loss_module = ArcLinear(nfeat=2048, nclass=1251, margin=0.2, s=7.)
    net = SpeakerNet(nfeat=2048, sample_rate=16000, window=200, loss_module=loss_module)
    feat, logits = net(x, y)
    print(f"feat size = {feat.size()}")
    print(f"logits size = {logits.size() if logits is not None else None}")
"""
