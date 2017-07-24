import time

from europilot.screen import stream_local_game_screen, Box

box = Box(0, 0, 500, 500)
streamer = stream_local_game_screen(box=box)
while True:
    arr = next(streamer)
    print((type(arr), arr.shape))
    # Do something with arr
    time.sleep(0.5)

