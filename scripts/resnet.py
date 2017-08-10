# https://github.com/flyyufelix/cnn_finetune
# http://www.cv-foundation.org/openaccess/content_cvpr_2016/papers/He_Deep_Residual_Learning_CVPR_2016_paper.pdf

import keras
from keras import layers
from keras.models import Sequential, Model
from keras.layers import Input, Dense, Conv2D, Convolution2D, MaxPooling2D, AveragePooling2D, ZeroPadding2D
from keras.layers import Dropout, Flatten, merge, Reshape, Lambda, BatchNormalization, Activation
from keras.preprocessing import image
from keras.preprocessing.image import ImageDataGenerator

# define building block for resnet
def identity_block(input_tensor, kernel_size, filters, stage, block):
    """The identity block is the block that has no conv layer at shortcut.
    # Arguments
        input_tensor: input tensor
        kernel_size: default 3, the kernel size of middle conv layer at main path
        filters: list of integers, the filters of 3 conv layer at main path
        stage: integer, current stage label, used for generating layer names
        block: 'a','b'..., current block label, used for generating layer names
    # Returns
        Output tensor for the block.
    """
    conv_name_base = 'res' + str(stage) + block + '_branch'
    bn_name_base = 'bn' + str(stage) + block + '_branch'

    x = Conv2D(filters, kernel_size, padding='same', name=conv_name_base + '2a')(input_tensor)
    x = BatchNormalization(axis=1, name=bn_name_base + '2a')(x)
    x = Activation('relu')(x)

    x = Conv2D(filters, kernel_size, padding='same', name=conv_name_base + '2b')(x)
    x = BatchNormalization(axis=1, name=bn_name_base + '2b')(x)
    x = Activation('relu')(x)

    x = layers.add([x, input_tensor])
    x = Activation('relu')(x)
    return x


def conv_block(input_tensor, kernel_size, filters, stage, block, strides=(2, 2)):
    """conv_block is the block that has a conv layer at shortcut
    # Arguments
        input_tensor: input tensor
        kernel_size: defualt 3, the kernel size of middle conv layer at main path
        filters: list of integers, the filterss of 3 conv layer at main path
        stage: integer, current stage label, used for generating layer names
        block: 'a','b'..., current block label, used for generating layer names
    # Returns
        Output tensor for the block.
    Note that from stage 3, the first conv layer at main path is with strides=(2,2)
    And the shortcut should have strides=(2,2) as well
    """
    conv_name_base = 'res' + str(stage) + block + '_branch'
    bn_name_base = 'bn' + str(stage) + block + '_branch'

    x = Conv2D(filters, kernel_size, padding='same', strides=strides,
               name=conv_name_base + '2a')(input_tensor)
    x = BatchNormalization(axis=1, name=bn_name_base + '2a')(x)
    x = Activation('relu')(x)

    x = Conv2D(filters, kernel_size, padding='same',
               name=conv_name_base + '2b')(x)
    x = BatchNormalization(axis=1, name=bn_name_base + '2b')(x)
    x = Activation('relu')(x)

    shortcut = Conv2D(filters, (1, 1), strides=strides,
                      name=conv_name_base + '1')(input_tensor)
    shortcut = BatchNormalization(axis=1, name=bn_name_base + '1')(shortcut)

    x = layers.add([x, shortcut])
    x = Activation('relu')(x)
    return x

def resnet(input_shape, filter_size=64):
    img_input = Input(shape=input_shape)

    x = ZeroPadding2D((3, 3))(img_input)
    x = Conv2D(64, (7, 7), strides=(2, 2), name='conv1')(x)
    x = BatchNormalization(axis=1, name='bn_conv1')(x)
    x = Activation('relu')(x)
    x = MaxPooling2D((3, 3), strides=(2, 2))(x)

    x = conv_block(x, 3, filter_size, stage=2, block='a', strides=(1, 1))
    x = identity_block(x, 3, filter_size, stage=2, block='b')

    x = conv_block(x, 3, filter_size*2, stage=3, block='a')
    x = identity_block(x, 3, filter_size*2, stage=3, block='b')

    x = conv_block(x, 3, filter_size*4, stage=4, block='a')
    x = identity_block(x, 3, filter_size*4, stage=4, block='b')
        
    x = conv_block(x, 3, filter_size*8, stage=5, block='a')
    x = identity_block(x, 3, filter_size*8, stage=5, block='b')
    
    x = AveragePooling2D((7, 7), name='avg_pool')(x)
    x = Flatten()(x)
    x = Dense(1, name='fc')(x)

    # Create model
    model = Model(img_input, x, name='resnet')
    return model