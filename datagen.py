'''Load image/labels/boxes from an annotation file.

The list file is like:

    img.jpg width height xmin ymin xmax ymax label xmin ymin xmax ymax label ...
'''
from __future__ import print_function

import os
import sys
import os.path

import random
import numpy as np

import torch
import torch.utils.data as data
import torchvision.transforms as transforms

from utils import box_iou
from encoder import DataEncoder
from PIL import Image, ImageOps


class ListDataset(data.Dataset):
    def __init__(self, root, list_file, train, transform, input_size, max_size):
        '''
        Args:
          root: (str) ditectory to images.
          list_file: (str) path to index file.
          train: (boolean) train or test.
          transform: ([transforms]) image transforms.
          input_size: (int) image shorter side size.
          max_size: (int) maximum image longer side size.
        '''
        self.root = root
        self.train = train
        self.transform = transform
        self.input_size = input_size
        self.max_size = max_size

        self.fnames = []
        self.boxes = []
        self.labels = []

        self.data_encoder = DataEncoder()

        with open(list_file) as f:
            lines = f.readlines()
            self.num_samples = len(lines)

        for line in lines:
            splited = line.strip().split()
            self.fnames.append(splited[0])
            num_boxes = (len(splited) - 3) // 5
            box = []
            label = []
            for i in range(num_boxes):
                xmin = splited[3+5*i]
                ymin = splited[4+5*i]
                xmax = splited[5+5*i]
                ymax = splited[6+5*i]
                c = splited[7+5*i]
                box.append([float(xmin),float(ymin),float(xmax),float(ymax)])
                label.append(int(c))
            self.boxes.append(torch.Tensor(box))
            self.labels.append(torch.LongTensor(label))

    def __getitem__(self, idx):
        '''Load image.

        Args:
          idx: (int) image index.

        Returns:
          img: (tensor) image tensor.
          loc_targets: (tensor) location targets.
          cls_targets: (tensor) class label targets.
        '''
        # Load image and bbox locations.
        fname = self.fnames[idx]
        img = Image.open(os.path.join(self.root, fname))
        boxes = self.boxes[idx]
        labels = self.labels[idx]

        # Data augmentation while training.
        if self.train:
            img, boxes = self.random_flip(img, boxes)

        img = self.resize(img)
        img = self.transform(img)
        return img, boxes, labels

    def resize(self, img):
        '''Resize the image shorter side to input_size.

        Args:
          img: (PIL.Image) image.

        Returns:
          (PIL.Image) resized image.

        Reference:
          https://github.com/rbgirshick/py-faster-rcnn/blob/master/lib/utils/blob.py
        '''
        im_size_min = min(img.size)
        im_size_max = max(img.size)
        im_scale = float(self.input_size) / float(im_size_min)
        if round(im_scale*im_size_max) > self.max_size:  # limit the longer side to MAX_SIZE
            im_scale = float(self.max_size) / float(im_size_max)
        return img.resize((int(img.width*im_scale), int(img.height*im_scale)))

    def random_flip(self, img, boxes):
        '''Randomly flip the image and adjust the bbox locations.

        For bbox (xmin, ymin, xmax, ymax), the flipped bbox is:
        (w-xmax, ymin, w-xmin, ymax).

        Args:
          img: (PIL.Image) image.
          boxes: (tensor) bbox locations, sized [#obj, 4].

        Returns:
          img: (PIL.Image) randomly flipped image.
          boxes: (tensor) randomly flipped bbox locations, sized [#obj, 4].
        '''
        if random.random() < 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            w = img.width
            xmin = w - boxes[:,2]
            xmax = w - boxes[:,0]
            boxes[:,0] = xmin
            boxes[:,2] = xmax
        return img, boxes

    def collate_fn(self, batch):
        '''Pad images and encode targets.

        As for images are of different sizes, we need to pad them to the same size.

        Args:
          batch: (list) of images, cls_targets, loc_targets.

        Returns:
          (list) of padded images, stacked cls_targets, stacked loc_targets.

        Reference:
          https://github.com/rbgirshick/py-faster-rcnn/blob/master/lib/utils/blob.py
        '''
        images = [x[0] for x in batch]
        boxes  = [x[1] for x in batch]
        labels = [x[2] for x in batch]

        max_size, _ = torch.IntTensor([im.size() for im in images]).max(0)
        max_h, max_w = max_size[1], max_size[2]
        num_images = len(images)
        inputs = torch.zeros(num_images, 3, max_h, max_w)

        loc_targets = []
        cls_targets = []
        for i in range(num_images):
            im = images[i]
            imh, imw = im.size(1), im.size(2)
            inputs[i,:,:imh,:imw] = im

            # Scale box to range [0, max_size].
            w_scale = 1.*max_w/imw
            h_scale = 1.*max_h/imh
            boxes[i] *= torch.Tensor([w_scale,h_scale,w_scale,h_scale]).expand_as(boxes[i])

            # Encode data.
            loc_target, cls_target = self.data_encoder.encode(boxes[i], labels[i], input_size=(max_h,max_w))
            loc_targets.append(loc_target)
            cls_targets.append(cls_target)
        return inputs, torch.stack(loc_targets), torch.stack(cls_targets)

    def __len__(self):
        return self.num_samples


def test():
    import torchvision

    transform = transforms.Compose([transforms.ToTensor()])
    dataset = ListDataset(root='/mnt/hgfs/D/download/PASCA_VOC/voc_all_images',
                          list_file='./voc_data/test.txt', train=False, transform=transform, input_size=600, max_size=1000)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=4, shuffle=True, num_workers=1, collate_fn=dataset.collate_fn)

    for images, loc_targets, cls_targets in dataloader:
        print(images.size())
        print(loc_targets.size())
        print(cls_targets.size())
        grid = torchvision.utils.make_grid(images, 1)
        torchvision.utils.save_image(grid,'a.jpg')
        break

# test()
