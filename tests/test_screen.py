"""Tests for screen modules

"""

import time

from europilot.screen import Box, LocalScreenGrab


class TestScreenGrab(object):
    def setup_method(self, method):
        start_x, start_y = 0, 0
        width, height = 800, 600
        self._box = Box(start_x, start_y, width, height)

    def test_local_mss_grab_image_size(self):
        screen_grab = LocalScreenGrab(self._box)
        rgb_arr = screen_grab.grab()
        assert len(rgb_arr) == self._box.width * self._box.height * 3

    def test_local_mss_performance(self):
        fps = 0

        screen_grab = LocalScreenGrab(self._box)
        now = time.time()
        cur = now
        while cur - now < 1:
            screen_grab.grab()
            fps += 1
            cur = time.time()

        # We want fps to be larger than 30
        MIN_FPS = 30
        assert fps > MIN_FPS

