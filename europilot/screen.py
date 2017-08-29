"""
europilot.screen
~~~~~~~~~~~~~~~~

This module contains wrappers which help to read screen data from
local/remote machine.

"""

import os
import ast
import time
import traceback
from sys import platform
from itertools import count
from subprocess import Popen, PIPE

import numpy as np
from mss import mss

from europilot.exceptions import ScreenException


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

    @staticmethod
    def from_monitor(monitor):
        return Box(
            monitor.offset_x, monitor.offset_y,
            monitor.width, monitor.height
        )

    @staticmethod
    def from_tuple(tuple_):
        return Box(
            tuple_[0],
            tuple_[1],
            tuple_[2],
            tuple_[3]
        )

    @property
    def name(self):
        return self._name

    @property
    def width(self):
        return self._x2 - self._x1

    @property
    def height(self):
        return self._y2 - self._y1

    @property
    def channel(self):
        # Channel for RGB
        return 3

    @property
    def numpy_shape(self):
        return (self.height, self.width, self.channel)

    def to_tuple(self):
        return (self._x1, self._y1, self._x2, self._y2)


class Monitor(object):
    """This class holds monitor information.

    """
    def __init__(self, width, height, offset_x, offset_y, primary=False):
        """Constructor

        :param width: Monitor width
        :param height: Monitor height
        :param offset_x, offset_y:
        If there are multiple monitors, other monitors expect for primary
        one have a offsets according to os display config.
        :param primary: Whether it is a primary monitor or not.

        """
        self._width = width
        self._height = height
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._primary = primary

    @property
    def primary(self):
        return self._primary

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def offset_x(self):
        return self._offset_x

    @property
    def offset_y(self):
        return self._offset_y


class ScreenUtils(object):
    @staticmethod
    def select_screen_area():
        """Use opencv to select game window from entire screen and return
        `box` object corresponding to game window.
        This method uses `selectROI` method in opencv tracking api.
        See http://docs.opencv.org/master/d7/dfc/group__highgui.html
        NOTE that opencv 3.0 (or above) is required.

        """
        try:
            import cv2
            cv2.selectROI
        except ImportError:
            raise ScreenException('opencv is not Found')
        except AttributeError:
            raise ScreenException('`selectROI` not found.' +
                ' Try reinstalling opencv with `--with-contrib` option')

        # 1. Capture entire screen in primary monitor.
        monitors = ScreenUtils.get_local_monitors()
        # Use primary monitor to create box
        box = Box.from_monitor(monitors[0])
        local_grab = LocalScreenGrab(box)
        entire_screen = local_grab.grab()
        entire_screen = entire_screen.reshape(box.numpy_shape)

        # 2. Select game window from entire screen.
        window_name = 'select_screen_area'
        region = cv2.selectROI(window_name, entire_screen)

        # `region` is tuple for (x1, y1, x2 - x1, y2 - y1) according to `Box`
        # coordinate system.
        return Box(
            region[0], region[1],
            region[0] + region[2], region[1] + region[3]
        )

    @staticmethod
    def get_local_monitors():
        # We currently use mss().monitors to get monitor information.
        # mss().monitors[0] is a dict of all monitors together
        # mss().monitors[N] is a dict of the monitor N (with N > 0)
        # But we drop the first elem because it's sometimes wrong because of
        # the bug in mss module.
        # TODO: Need to cache this property somewhere.
        mss_monitors = mss().monitors[1:]
        monitors = []
        for idx, elem in enumerate(mss_monitors):
            monitors.append(Monitor(
                elem['width'],
                elem['height'],
                elem['left'],
                elem['top'],
                idx == 0
            ))
        return monitors


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
        """Reads screen and returns raw RGB `bytearray`.

        :param bounding_box: Read only given area of the screen.

        """
        raise NotImplementedError()

    def _post_process(self, raw):
        """Parses `bytearray` to `numpy.ndarray`

        """
        single_byte_uint = '|u1'
        return np.frombuffer(raw, dtype=single_byte_uint)


class MssImpl(_LocalImpl):
    def __init__(self, box):
        super(MssImpl, self).__init__(box)
        self._is_osx = platform == 'darwin'
        self._executor = mss()

        if self._is_osx:
            # XXX: `mss` passes wrong param when it calls
            # `coregraphics.CGWindowListCreateImage' resulting in doubled
            # image size in retina display.
            # We fix this by hooking that function directly.
            orig_func = self._executor.core.CGWindowListCreateImage

            def _hook(screen_bounds, list_option, window_id, image_option):
                norminal_resolution = 1 << 4
                return orig_func(
                    screen_bounds, list_option, window_id,
                    norminal_resolution
                )
            self._executor.core.CGWindowListCreateImage = _hook

    def _read(self, bounding_box):
        """FIXME: Currently taking a screenshot is not fast enough in
        retina-like display which has a very high pixel density.

        """
        # Coordinates need to be converted accordingly.
        x1, y1, x2, y2 = bounding_box.to_tuple()
        width = x2 - x1
        height = y2 - y1

        monitor_dict = {
            'left': x1,
            'top': y1,
            'width': width,
            'height': height
        }

        adjust_needed = self._is_osx and width % 16 != 0
        if adjust_needed:
            # XXX: When the width is not divisible by 16, extra padding is
            # added by macOS in the form of black pixels, which results
            # in a screenshot with shifted pixels.
            # To prevent this, `mss` reduces width to the closest smaller
            # multiple of 16.
            # But we don't want the width size to be reduced unexpectedly.
            # This is a little hack to get the exact size of image.
            adjusted_width = width + (16 - (width % 16))
            monitor_dict['width'] = adjusted_width

            # Now `adjusted_rgb_data` has a bigger width.
            # Let's cut the remaining width to get our desired width.
            adjusted_rgb_data = self._executor.grab(monitor_dict).rgb
            rgb_data = bytearray()
            num_channels = 3
            for idx in range(height):
                offset = idx * (adjusted_width * num_channels)
                rgb_data.extend(
                    adjusted_rgb_data[offset:offset + width * num_channels]
                )

            return rgb_data
        else:
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


def stream_local_game_screen(box=None, default_fps=10):
    """Convenient wrapper for local screen capture.
    This method wraps everything which is needed to get game screen data in
    primary monitor.
    It generates RGB numpy array with the shape of (height, width, 3)
    rather than raw 1 dimensional array because selected image size is not
    exposed to outside this method.

    :param box: If it's None, we first select game window area from screen
    and start streaming inside that box.
    :param default_fps: Target fps for screen capture. NOTE that this value
    can be adjusted from other coroutine.

    """
    if box is None:
        # Open a new process and get output from stdout
        # Due to bug in cv2.selectROI, area selection window sometime hangs
        # until main process exits preventing us from capturing right screen
        # data. We have to start subprocess to make sure the window to be
        # closed before we start capturing the screen.
        dir_path = os.path.dirname(os.path.realpath(__file__))
        subproc = Popen([
            'python', os.path.join(
                dir_path, '..', 'scripts/select_screen_area.py')
        ], stdout=PIPE)
        output, _ = subproc.communicate()

        try:
            box_tuple = ast.literal_eval(output.split('\n')[-2])
        except ValueError:
            # Something went wrong.
            traceback.print_exc()
            raise ScreenException('Failed to get screen area')

        box = Box.from_tuple(box_tuple)

    # We may need to use some epsilon value to meet fps more tightly.
    time_per_frame = 1.0 / default_fps
    local_grab = LocalScreenGrab(box)
    while True:
        start = time.time()

        screen = local_grab.grab()
        target_fps = yield screen.reshape(box.numpy_shape)
        if target_fps is not None:
            # Change fps accordingly
            time_per_frame = 1.0 / target_fps

        execution_time = time.time() - start
        if execution_time > time_per_frame:
            # Too high fps. No need to sleep.
            pass
        else:
            time.sleep(time_per_frame - execution_time)
