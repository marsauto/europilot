import os
import sys
import json
from subprocess import PIPE, Popen
from threading import Thread
from collections import OrderedDict


class ControllerOutput(object):
    """Reads stdout from joystick.py, to get the controller event outputs without
    blocking.

    """
    def __init__(self, state_listener=None):
        """Constructor.

        :param state_listener: Listener which takes single `SensorData` param.

        """
        self._controller_state = ControllerState()
        self._state_listener = state_listener

    def start(self):
        ON_POSIX = 'posix' in sys.builtin_module_names
        # use unbuffered output, since stdout will be generally small
        # https://stackoverflow.com/questions/1410849/bypassing-buffering-of-subprocess-output-with-popen-in-c-or-python
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # XXX: This `python` may not be our desired python bin
        self.p = Popen(
            ['python', '-u', os.path.join(dir_path, 'joystick.py')],
            bufsize=0,
            stdout=PIPE,
            close_fds=ON_POSIX
        )
        self.t = Thread(target=self.__update_state,
                        args=(self.p,))
        self.t.daemon = True  # thread dies with program
        self.t.start()

    def terminate(self):
        self.p.terminate()

    def get_latest_state_obj(self):
        return self._controller_state.get_state_obj()

    def __update_state(self, process):
        for line in iter(process.stdout.readline, ''):
            self._controller_state.update_state(line.strip())
            self._state_listener(self._controller_state.get_state_obj())

        process.stdout.close()


class ControllerState(object):
    """Thread-safe controller state.
    Holds the latest value of each of the controller output value.
        >>> c = ControllerState()
        >>> c.start()
        >>> c.get_state()
        OrderedDict([('wheel-axis', '1012'), ('clutch', '-27865'),...]
    """
    def __init__(self):
        self.state = self.__init_dict()

    def __init_dict(self):
        """Initialize the values for each of the controller output"""
        d = OrderedDict()
        d['wheel-axis'] = '0'
        d['clutch'] = '0'
        d['brake'] = '0'
        d['gas'] = '0'
        d['paddle-left'] = '0'
        d['paddle-right'] = '0'
        d['wheel-button-left-1'] = '0'
        d['wheel-button-left-2'] = '0'
        d['wheel-button-left-3'] = '0'
        d['wheel-button-right-1'] = '0'
        d['wheel-button-right-2'] = '0'
        d['wheel-button-right-3'] = '0'
        d['shifter-button-left'] = '0'
        d['shifter-button-right'] = '0'
        d['shifter-button-up'] = '0'
        d['shifter-button-down'] = '0'
        d['dpad-left/right'] = '0'
        d['dpad-up/down'] = '0'
        d['shifter-button-1'] = '0'
        d['shifter-button-2'] = '0'
        d['shifter-button-3'] = '0'
        d['shifter-button-4'] = '0'
        d['gear-1'] = '0'
        d['gear-2'] = '0'
        d['gear-3'] = '0'
        d['gear-4'] = '0'
        d['gear-5'] = '0'
        d['gear-6'] = '0'
        d['gear-R'] = '0'

        return d

    def update_state(self, msg):
        """Update ControllerState with the latest controller data"""
        k, v = msg.split()
        if k in self.state:
            self.state[k] = v

    def get_state(self):
        """Returns the latest state"""
        return self.state

    def get_state_obj(self):
        """Returns the latest `SensorData` object"""
        return SensorData.from_ordered_dict(self.get_state())

    def get_state_json(self):
        """Returns the latest state in json format"""
        j = json.dumps(self.state)
        return j


class SensorData(object):
    def __init__(self, data):
        """Constructor.
        :param data: `OrderedDict` containing sensor data.

        """
        self._data = data

    @staticmethod
    def from_ordered_dict(dict_):
        return SensorData(dict_)

    @property
    def raw(self):
        return self._data

    @property
    def wheel_axis(self):
        return self._data['wheel-axis']

    @property
    def resume_button_pressed(self):
        return self._data['wheel-button-right-1'] == '1'

    @property
    def pause_button_pressed(self):
        return self._data['wheel-button-left-1'] == '1'
