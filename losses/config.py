# -*- coding: utf-8 -*-
from torch import nn
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler
from distances import CosineDistance, EuclideanDistance
from losses.center import CenterLinear, SoftmaxCenterLoss
from losses.wrappers import LossWrapper, STSBaselineClassifier
from losses.arcface import ArcLinear
from losses.coco import CocoLinear
from losses.contrastive import ContrastiveLoss
from losses.triplet import TripletLoss, BatchAll
import core.base as base
from models import MetricNet


class LossConfig:

    def __init__(self, name, param_desc, loss_module, loss, test_distance):
        self.name = name
        self.param_desc = param_desc
        self.loss_module = loss_module
        self.loss = loss
        self.test_distance = test_distance

    def optimizer(self, model: MetricNet, task: str, lr: tuple):
        # TODO remove 'task' parameter. Implement some sort of double dispatching or something
        # The problem is that optimizer configuration depends both on the loss and the model
        raise NotImplementedError


class KLDivergenceConfig(LossConfig):

    def __init__(self, device, nfeat):
        loss_module = STSBaselineClassifier(nfeat)
        loss = LossWrapper(nn.KLDivLoss().to(device))
        super(KLDivergenceConfig, self).__init__('KL-Divergence', None, loss_module, loss, CosineDistance())

    def optimizer(self, model: MetricNet, task: str, lr: tuple):
        return base.Optimizer([optim.RMSprop(model.parameters(), lr=lr[0])], [])


class SoftmaxConfig(LossConfig):

    def __init__(self, device, nfeat, nclass):
        self.loss_module = CenterLinear(nfeat, nclass)
        loss = LossWrapper(nn.NLLLoss().to(device))
        super(SoftmaxConfig, self).__init__('Cross Entropy', None, self.loss_module, loss, CosineDistance())

    def optimizer(self, model: MetricNet, task: str, lr: tuple):
        if task == 'mnist':
            # Was using lr=0.01
            optimizers = [optim.SGD(model.parameters(), lr=lr[0], momentum=0.9, weight_decay=0.0005)]
            schedulers = [lr_scheduler.StepLR(optimizers[0], 10, gamma=0.5)]
        elif task in ['sts', 'ami', 'sst2']:
            optimizers = [optim.RMSprop(model.parameters(), lr=lr[0])]
            schedulers = [lr_scheduler.ReduceLROnPlateau(optimizers[0], mode='max', factor=0.5,
                                                         patience=5, verbose=True)]
        else:
            raise ValueError('Task must be one of mnist/sts')
        return base.Optimizer(optimizers, schedulers)


class ArcFaceConfig(LossConfig):

    def __init__(self, device, nfeat, nclass, margin=0.2, s=7.0):
        self.loss_module = ArcLinear(nfeat, nclass, margin, s)
        loss = LossWrapper(nn.CrossEntropyLoss().to(device))
        super(ArcFaceConfig, self).__init__('ArcFace Loss', f"m={margin} s={s}", self.loss_module, loss, CosineDistance())

    def optimizer(self, model: MetricNet, task: str, lr: tuple):
        if task == 'mnist':
            # Was using lr0=0.005 and lr1=0.01
            params = model.all_params()
            optimizers = [optim.SGD(params[0], lr=lr[0], momentum=0.9, weight_decay=0.0005),
                          optim.SGD(params[1], lr=10 * lr[0])]
            schedulers = [lr_scheduler.StepLR(optimizers[0], 8, gamma=0.6),
                          lr_scheduler.StepLR(optimizers[1], 8, gamma=0.8)]
        elif task in ['sts', 'ami', 'sst2']:
            params = model.all_params()
            optimizers = [optim.RMSprop(params[0], lr=lr[0]),
                          optim.RMSprop(params[1], lr=10 * lr[0])]
            schedulers = [lr_scheduler.ReduceLROnPlateau(optimizers[0], mode='max', factor=0.5,
                                                         patience=5, verbose=True),
                          lr_scheduler.ReduceLROnPlateau(optimizers[1], mode='max', factor=0.5,
                                                         patience=5, verbose=True)]
        else:
            raise ValueError('Task must be one of mnist/sts')
        return base.Optimizer(optimizers, schedulers)


class CenterConfig(LossConfig):

    def __init__(self, device, nfeat, nclass, lweight=1, distance=EuclideanDistance()):
        loss_module = CenterLinear(nfeat, nclass)
        self.loss = SoftmaxCenterLoss(device, nfeat, nclass, lweight, distance)
        super(CenterConfig, self).__init__('Center Loss', f"λ={lweight} - {distance}", loss_module, self.loss, distance)

    def optimizer(self, model, task, lr: tuple):
        if task == 'mnist':
            # Was using lr0=0.001 and lr1=0.5
            optimizers = [optim.SGD(model.parameters(), lr=lr[0], momentum=0.9, weight_decay=0.0005),
                          optim.SGD(self.loss.center_parameters(), lr=10 * lr[0])]
            schedulers = [lr_scheduler.StepLR(optimizers[0], 20, gamma=0.8)]
        elif task in ['sts', 'ami', 'sst2']:
            params = model.all_params()
            optimizers = [optim.RMSprop(params[0], lr=lr[0]),
                          optim.RMSprop(params[1], lr=10 * lr[0])]
            schedulers = [lr_scheduler.ReduceLROnPlateau(optimizers[0], mode='max', factor=0.5,
                                                         patience=5, verbose=True),
                          lr_scheduler.ReduceLROnPlateau(optimizers[1], mode='max', factor=0.5,
                                                         patience=5, verbose=True)]
        else:
            raise ValueError('Task must be one of mnist/sts')
        return base.Optimizer(optimizers, schedulers)


class CocoConfig(LossConfig):

    def __init__(self, device, nfeat, nclass, alpha=6.25):
        loss_module = CocoLinear(nfeat, nclass, alpha)
        loss = LossWrapper(nn.CrossEntropyLoss().to(device))
        super(CocoConfig, self).__init__('CoCo Loss', f"α={alpha}", loss_module, loss, CosineDistance())

    def optimizer(self, model, task, lr: tuple):
        if task == 'mnist':
            # Was using lr0=0.001 and lr1=0.01
            params = model.all_params()
            optimizers = [optim.SGD(params[0], lr=lr[0], momentum=0.9, weight_decay=0.0005),
                          optim.SGD(params[1], lr=10 * lr[0], momentum=0.9)]
            schedulers = [lr_scheduler.StepLR(optimizers[0], 10, gamma=0.5)]
        elif task in ['sts', 'ami', 'sst2']:
            params = model.all_params()
            optimizers = [optim.RMSprop(params[0], lr=lr[0]),
                          optim.RMSprop(params[1], lr=10 * lr[0])]
            schedulers = [lr_scheduler.ReduceLROnPlateau(optimizers[0], mode='max', factor=0.5,
                                                         patience=5, verbose=True),
                          lr_scheduler.ReduceLROnPlateau(optimizers[1], mode='max', factor=0.5,
                                                         patience=5, verbose=True)]
        else:
            raise ValueError('Task must be one of mnist/sts')
        return base.Optimizer(optimizers, schedulers)


class ContrastiveConfig(LossConfig):

    def __init__(self, device, margin=2, distance=EuclideanDistance(), size_average=True, online=True):
        loss = ContrastiveLoss(device, margin, distance, size_average, online)
        super(ContrastiveConfig, self).__init__('Contrastive Loss', f"m={margin} - {distance}", None, loss, distance)

    def optimizer(self, model, task, lr: tuple):
        if task == 'mnist':
            # Was using lr=0.001
            optimizers = [optim.SGD(model.parameters(), lr=lr[0], momentum=0.9, weight_decay=0.0005)]
            schedulers = [lr_scheduler.StepLR(optimizers[0], 4, gamma=0.8)]
        elif task in ['sts', 'ami', 'snli', 'sst2']:
            optimizers = [optim.RMSprop(model.parameters(), lr=lr[0], momentum=0.9)]
            schedulers = [lr_scheduler.ReduceLROnPlateau(optimizers[0], mode='max', factor=0.5,
                                                         patience=5, verbose=True)]
        else:
            raise ValueError('Task must be one of mnist/sts/ami/snli')
        return base.Optimizer(optimizers, schedulers)


class TripletConfig(LossConfig):

    def __init__(self, device, margin: float = 2, scaling: float = 10, distance=EuclideanDistance(),
                 size_average: bool = True, online: bool = True, sampling=BatchAll()):
        loss = TripletLoss(device, margin, scaling, distance, size_average, online, sampling)
        super(TripletConfig, self).__init__('Triplet Loss', f"m={margin} - {distance}", None, loss, distance)

    def optimizer(self, model, task, lr: tuple):
        if task == 'mnist':
            # Was using lr=0.0001
            optimizers = [optim.SGD(model.parameters(), lr=lr[0], momentum=0.9, weight_decay=0.0005)]
            schedulers = [lr_scheduler.StepLR(optimizers[0], 5, gamma=0.8)]
        elif task in ['sts', 'ami', 'snli', 'sst2']:
            optimizers = [optim.RMSprop(model.parameters(), lr=lr[0], momentum=0.9)]
            schedulers = [lr_scheduler.ReduceLROnPlateau(optimizers[0], mode='max', factor=0.5,
                                                         patience=5, verbose=True)]
        else:
            raise ValueError('Task must be one of mnist/sts/ami/snli')
        return base.Optimizer(optimizers, schedulers)
