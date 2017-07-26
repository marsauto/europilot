"""Select screen area with opencv and write output to stdout.
This script will be executed from `europilot.screen.stream_local_game_screen`.

"""
import os
import sys
dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(dir_path, '..'))

from europilot.screen import ScreenUtils

# Select screen area and write selected output to stdout
box = ScreenUtils.select_screen_area()
print(box.to_tuple())
