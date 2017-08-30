"""
europilot.train
~~~~~~~~~~~~~~~

Utils for generating training data.

"""

import os
import re
import time
import hashlib
import datetime
import threading
import multiprocessing

from PIL import Image
from pynput import keyboard

from europilot.compat import Queue
from europilot.exceptions import TrainException
from europilot.screen import stream_local_game_screen
from europilot.controllerstate import ControllerOutput


class _ConfigType(type):
    def __getattr__(self, attr):
        raise TrainException('Invalid configuration: %s' % attr)


class Config(object):
    """Default configuration.
    Anyone who wants to use custom configuration should inherit this class.

    :attr BOX: `screen.Box` object indicating capture area.
    :attr DATA_PATH: Csv file path.
    :attr IMG_PATH: Image file path.
    :attr IMG_EXT: Image file extension.
    :attr TRAIN_UID: If it's not None, file existing csv file with a name
    starts with `train_uid` and add data to that file.
    :attr DEFAULT_FPS: Default target fps for screen capture.
    :attr WAIT_KEYPRESS: If this is True, do not start training until start
    key (keyboard `r`, wheel `left button 1`) is pressed.
    :attr DEBUG: If this is True, write debug msg to stdout.

    """
    __metaclass__ = _ConfigType
    BOX = None
    DATA_PATH = os.path.join('data', 'csv')
    IMG_PATH = os.path.join('data', 'img', 'raw')
    IMG_EXT = 'jpg'
    TRAIN_UID = None
    DEFAULT_FPS = 10
    WAIT_KEYPRESS = False
    DEBUG = True


_WORKER_BREAK_FLAG = 'stop_consuming'


def _print(text):
    if _global_config.DEBUG:
        print(text)


class Worker(multiprocessing.Process):

    def __init__(self, train_uid, inq, outq):
        """
        :param train_uid: This would be image filename prefix.
        :param inq: inbound multiprocessing.Queue (main process <-> worker)
        :param outq: outbound multiprocessing.Queue (worker <-> writer)

        """
        multiprocessing.Process.__init__(self)
        self._train_uid = train_uid
        self._inq = inq
        self._outq = outq
        self._img_path = _global_config.IMG_PATH
        self._img_ext = _global_config.IMG_EXT
        self.daemon = True

    @property
    def train_uid(self):
        return self._train_uid

    def run(self):
        while True:
            try:
                # Blocking `get`
                data = self._inq.get()

                if data == _WORKER_BREAK_FLAG:
                    break

                image_data, sensor_data = data
                filename = self._save_image(image_data)
                self._outq.put((filename, sensor_data))
            except KeyboardInterrupt:
                pass

    def _save_image(self, image_data):
        """Synchronously write image data to disk and returns filename.
        :param image_data: RGB numpy array

        """
        # filename example: '{self._train_uid}_2017_07_24_21_18_46_13.jpg'
        filename = self._train_uid + '_' + re.sub(
            '[-:.]', '_', datetime.datetime.now().isoformat('_')[:-4]) + \
            '.' + self._img_ext

        image = Image.fromarray(image_data, 'RGB')
        image.save(os.path.join(self._img_path, filename))
        return filename


class Writer(multiprocessing.Process):
    def __init__(self, train_uid, inq, csv_initialized=False):
        multiprocessing.Process.__init__(self)
        self._train_uid = train_uid
        self._inq = inq
        self._data_path = _global_config.DATA_PATH
        self._data_seq = 0
        self._csv_initialized = csv_initialized
        self._filename = self._train_uid + '.csv'

    @property
    def filename(self):
        return self._filename

    def run(self):
        f = os.path.join(self._data_path, self._filename)
        with open(f, 'a' if os.path.isfile(f) else 'w') as file_:
            while True:
                try:
                    data = self._inq.get()
                    if data == _WORKER_BREAK_FLAG:
                        break
                    image_filename, sensor_data = data

                    self._write(file_, image_filename, sensor_data)

                    if self._data_seq % 10 == 0:
                        _print('seq: %s, filename: %s, datetime: %s' %
                            (
                                self._data_seq,
                                image_filename,
                                str(datetime.datetime.now())
                            )
                        )
                except KeyboardInterrupt:
                    pass

    def _write(self, file_, image_filename, sensor_data):
        """Synchronously write sensor data to disk.
        :param image_filename: filename of corresponding training image
        :param sensor_data: `SensorData` object.

        CSV format
        seq_id,filename,sensor_data1,sensor_data2,sensor_data3,...

        Order of sensor data depends on `OrderedDict` defined in
        `controllerstate.ControllerState`.

        """
        if not self._csv_initialized:
            # Add headers
            sensor_header = ','.join(sensor_data.raw.keys())
            csv_header = 'img,' + sensor_header
            file_.write(csv_header + '\n')
            self._csv_initialized = True

        values = [image_filename] + [str(x) for x in sensor_data.raw.values()]
        data = ','.join(values)
        self._data_seq += 1
        file_.write(data + '\n')


_train_sema = threading.BoundedSemaphore(value=1)
_global_config = Config


def generate_training_data(config=Config):
    """Generate training data.

    :param config: Training configuration class

    """
    try:
        # Set global config so that other workers can access it directly.
        global _global_config
        _global_config = config

        # Check if data paths exist and are writable.
        if not os.access(config.DATA_PATH, os.W_OK):
            raise TrainException('Invalid data path: %s' % config.DATA_PATH)
        if not os.access(config.IMG_PATH, os.W_OK):
            raise TrainException('Invalid image path: %s' % config.IMG_PATH)

        streamer = stream_local_game_screen(
            box=config.BOX, default_fps=config.DEFAULT_FPS)

        worker_q = multiprocessing.Queue()
        writer_q = multiprocessing.Queue()
        num_workers = multiprocessing.cpu_count()
        workers = []

        train_uid = config.TRAIN_UID
        csv_initialized = train_uid is not None
        if train_uid is None:
            # Generate train_uid to start new data generation.
            # Call `encode` because hashlib in python3 doesn't accept unicode.
            d = str(datetime.datetime.now()).encode('utf8')
            train_uid = hashlib.md5(d).hexdigest()[:8]

        for i in range(num_workers):
            workers.append(
                Worker(train_uid, worker_q, writer_q)
            )

        # NOTE that these workers are daemonic processes
        for worker in workers:
            worker.start()

        # Start 1 process
        writer = Writer(train_uid, writer_q, csv_initialized)
        writer.start()

        # Start 1 thread
        control_q = Queue()
        flow_controller = FlowController(control_q)
        flow_controller.start()

        # Start 1 process and 1 thread.
        def _state_listener(sensor_data):
            _feed_control_signal(control_q, sensor_data=sensor_data)
        controller_output = ControllerOutput(state_listener=_state_listener)
        controller_output.start()

        # Start 1 thread
        keyboard_listener = KeyListener(control_q)
        keyboard_listener.start()

        fps_adjuster = FpsAdjuster()
        last_sensor_data = None

        if config.WAIT_KEYPRESS:
            if config.BOX is None:
                # Select area and drop first screen image.
                next(streamer)
            _train_sema.acquire()

        while True:
            if flow_controller.acquired:
                # Switch context and give flow_controller time to acquire sema.
                time.sleep(0.1)

            # TODO: Do something to resolve this in python 2.x
            # https://bugs.python.org/issue8844
            _train_sema.acquire()

            if last_sensor_data is None:
                # Start generator
                image_data = next(streamer)
            else:
                image_data = streamer.send(
                    fps_adjuster.get_next_fps(last_sensor_data))

            sensor_data = controller_output.get_latest_state_obj()
            last_sensor_data = sensor_data
            worker_q.put((image_data, sensor_data))

            try:
                _train_sema.release()
            except ValueError:
                pass
    except KeyboardInterrupt:
        try:
            _train_sema.release()
        except ValueError:
            # Already released.
            pass

        control_q.put(_WORKER_BREAK_FLAG)
        controller_output.terminate()

        # Gracefully stop workers
        for _ in range(num_workers):
            worker_q.put(_WORKER_BREAK_FLAG)
        writer_q.put(_WORKER_BREAK_FLAG)

        for worker in workers:
            worker.terminate()

        for worker in workers:
            worker.join()

        writer.terminate()
        writer.join()


def _feed_control_signal(q, key_value=None, sensor_data=None):
    """Parse device (keyboard, wheel) input to control signal and
    feed it into `FlowController` thread.
    If both devices put input simultaneously, key_value is ignored.

    :param q: `Queue` between main thread and `FlowController` thread.
    :param key_value: Keyboard input
    :param sensor_data: `SensorData` object

    """
    control_signal = None

    if key_value is not None:
        if key_value == 'r':
            control_signal = FlowController.RESUME_SIGNAL
        elif key_value == 'q':
            control_signal = FlowController.PAUSE_SIGNAL

    if sensor_data is not None:
        if sensor_data.resume_button_pressed:
            control_signal = FlowController.RESUME_SIGNAL
        elif sensor_data.pause_button_pressed:
            control_signal = FlowController.PAUSE_SIGNAL

    if control_signal is not None:
        q.put(control_signal)


class KeyListener(keyboard.Listener):
    def __init__(self, outq):
        """Constructor.
        :param outq: `Queue` between this thread and `FlowController` thread.

        `keyboard.Listener` is a daemon thread by default.

        """
        self._outq = outq
        super(KeyListener, self).__init__(on_press=self._on_press)

    def _on_press(self, key):
        try:
            _feed_control_signal(self._outq, key_value=key.char)
        except AttributeError:
            # Pressed key is not alphabet.
            pass


class FlowController(threading.Thread):
    """This thread controls data generation process by parsing signal from
    input devices.

    """
    PAUSE_SIGNAL = 'pause'
    RESUME_SIGNAL = 'resume'

    def __init__(self, inq):
        threading.Thread.__init__(self)
        self.daemon = True
        self._inq = inq
        self._acquired = False

    @property
    def acquired(self):
        return self._acquired

    def run(self):
        while True:
            signal = self._inq.get()
            if signal == self.RESUME_SIGNAL:
                self._resume_data_generation()
            elif signal == self.PAUSE_SIGNAL:
                self._pause_data_generation()
            elif signal == _WORKER_BREAK_FLAG:
                break

    def _pause_data_generation(self):
        _print('Data generation paused')
        if not self._acquired:
            self._acquired = True
            _train_sema.acquire()

    def _resume_data_generation(self):
        _print('Data generation resumed')
        try:
            _train_sema.release()
            self._acquired = False
        except ValueError:
            pass


class FpsAdjuster(object):
    def __init__(self):
        self._default_fps = _global_config.DEFAULT_FPS
        self._adjust_factor = 2
        self._duration_threshold = 2
        self._max_straight_wheel_axis = 10
        self._last_straight_time = None

    def get_next_fps(self, sensor_data):
        """Adjust fps according to wheel axis
        We want to reduce fps when the car is going straight longer than
        threshold seconds.

        :param sensor_data: `controllerstate.SensorData` object.

        """
        going_straight = self._going_straight(sensor_data.wheel_axis)
        if self._last_straight_time is None:
            self._update_last_straight_time(going_straight)
            return self._default_fps

        straight_duration = time.time() - self._last_straight_time
        if going_straight and \
                straight_duration > self._duration_threshold:
            # Adjust fps
            return max(self._default_fps / self._adjust_factor, 1)
        else:
            self._update_last_straight_time(going_straight)
            return self._default_fps

    def _going_straight(self, wheel_axis):
        return abs(int(wheel_axis)) < self._max_straight_wheel_axis

    def _update_last_straight_time(self, going_straight):
        if self._last_straight_time is None and going_straight:
            self._last_straight_time = time.time()
        elif not going_straight:
            self._last_straight_time = None
        # If last_controller_state is not None and going_straight, do nothing
