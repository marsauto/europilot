from europilot.screen import Box
from europilot.train import generate_training_data, Config

class MyConfig(Config):
    # Screen area
    BOX = Box(0, 0, 500, 500)
    # Screen capture fps
    DEFAULT_FPS = 20

generate_training_data(config=MyConfig)
