from __future__ import division,print_function
import math, os, json, sys, re

from glob import glob
import numpy as np
from matplotlib import pyplot as plt
from operator import itemgetter, attrgetter, methodcaller
from collections import OrderedDict
import itertools
from itertools import chain

import cv2

import pandas as pd
import PIL
from PIL import Image
from numpy.random import random, permutation, randn, normal, uniform, choice
from numpy import newaxis
import scipy
from scipy import misc, ndimage
from scipy.ndimage.interpolation import zoom
from scipy.ndimage import imread
from sklearn.metrics import confusion_matrix
import bcolz
from sklearn.preprocessing import OneHotEncoder
from sklearn.manifold import TSNE

from IPython.lib.display import FileLink

import theano
from theano import shared, tensor as T
from theano.tensor.nnet import conv2d, nnet
from theano.tensor.signal import pool

import keras
from keras import backend as K
from keras.utils.data_utils import get_file
from keras.utils import np_utils
from keras.utils.np_utils import to_categorical
from keras.models import Sequential, Model
from keras.layers import Input, Embedding, Reshape, merge, LSTM, Bidirectional
from keras.layers import SpatialDropout1D, Concatenate  # Keras2

from keras.layers import TimeDistributed, Activation, SimpleRNN, GRU
from keras.layers.core import Flatten, Dense, Dropout, Lambda

from keras.regularizers import l2, l1

from keras.layers.normalization import BatchNormalization
from keras.optimizers import SGD, RMSprop, Adam

from keras.layers import deserialize
from keras.layers.merge import dot, add, concatenate
from keras.metrics import categorical_crossentropy, categorical_accuracy
from keras.layers.convolutional import *
from keras.preprocessing import image, sequence
from keras.preprocessing.text import Tokenizer

def img_path_to_arr(p):
    with image.load_img(p) as img:
        img = image.img_to_array(img)
    return img
