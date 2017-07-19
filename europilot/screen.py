"""
europilot.screen
~~~~~~~~~~~~~~~~

This module contains wrappers which help to read screen data from
local/remote machine.

"""

from itertools import count

import numpy as np
from mss import mss


class Box(object):
    # Global counter which is used to name box
    _counter = count()

    def __init__(self, x1, y1, x2, y2, monitor=None):
        """Constructor

        (x1, y1) -> upper left point of the screen box
        (x2, y2) -> lower right point of the screen box

              |
              |
        ---(x1, y1)-----------------(x2, y1)
              |                        |
              |                        |
              |                        |
              |                        |
        ---(x1, y2)-----------------(x2, y2)

        :param monitor: `Monitor` object which adds proper offset
        according to target minitor.

        """
        self._name = 'Box %s' % str(next(self._counter))
        self._x1 = x1
        self._y1 = y1
        self._x2 = x2
        self._y2 = y2
        self._monitor = monitor

        if self._monitor is not None:
            # TODO: This is needed to support multiple monitors.
            pass

    @property
    def name(self):
        return self._name

    @property
    def width(self):
        return self._x2 - self._x1

    @property
    def height(self):
        return self._y2 - self._y1

    def to_tuple(self):
        return (self._x1, self._y1, self._x2, self._y2)


class ScreenUtils(object):
    @staticmethod
    def detect_game_window(screen):
        """Automatically detect game window in full screen capture.
        Use opencv to find rectangle areas and pick the most likely window.
        This method returns `Box` object.

        :param screen: `ndarray` containing RGB screen data.

        """
        pass

    @staticmethod
    def detect_primary_game_window():
        """Detect game window in primary monitor.
        This method returns `Box` object.

        """
        pass


class _LocalImpl(object):
    def __init__(self, box):
        self._box = box

    def read_screen(self):
        """Reads RGB screen data and returns corresponding 1 dimensional
        numpy array so that it can be reshaped later.

        """
        return self._post_process(
            self._read(self._box)
        )

    def _read(self, bounding_box):
        """Reads screen and returns raw RGB `bytesarray`.

        :param bounding_box: Read only given area of the screen.

        """
        raise NotImplementedError()

    def _post_process(self, raw):
        """Parses `bytesarray` to `numpy.ndarray`

        """
        single_byte_uint = '|u1'
        return np.frombuffer(raw, dtype=single_byte_uint)


class MssImpl(_LocalImpl):
    def __init__(self, box):
        super(MssImpl, self).__init__(box)
        self._executor = mss()

    def _read(self, bounding_box):
        """FIXME: Currently taking a screenshot is not fast enough in
        retina-like display which has a very high pixel density.

        """
        # Coordinates needs to be converted accordingly.
        x1, y1, x2, y2 = bounding_box.to_tuple()
        monitor_dict = {
            'left': x1,
            'top': y1,
            'width': x2 - x1,
            'height': y2 - y1
        }
        return self._executor.grab(monitor_dict).rgb


class PilImpl(_LocalImpl):
    pass


class ScreenGrab(object):
    def __init__(self, box):
        """Constructor

        :param box: This class will capture screen inside this `Box`.

        """
        self._box = box

    @property
    def box(self):
        return self._box

    @box.setter
    def box(self, x):
        self._box = x

    def prepare(self):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

    @property
    def ready(self):
        raise NotImplementedError()

    def grab(self):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self):
        self.close()

    def __repr__(self):
        return '<ScreenGrab [%s]>' % self._box.name


class LocalScreenGrab(ScreenGrab):
    def __init__(self, box, impl=MssImpl):
        self._impl = impl(box)

    def grab(self):
        return self._impl.read_screen()

