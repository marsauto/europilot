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
from Queue import Queue

from PIL import Image
from pynput import keyboard

from europilot.exceptions import TrainException
from europilot.screen import stream_local_game_screen
from europilot.controllerstate import ControllerState


class TrainConfig:
    DATA_PATH = 'data/'
    IMG_PATH = DATA_PATH + 'img/raw/'
    IMG_EXT = 'jpg'


def get_config_value(config, key):
    try:
        return getattr(config, key)
    except AttributeError as e:
        raise TrainException('Invalid configuration: %s' % e.args[0])


_WORKER_BREAK_FLAG = 'stop_consuming'


class Worker(multiprocessing.Process):

    def __init__(self, train_uid, inq, outq, config=TrainConfig):
        """
        :param train_uid: This would be image filename prefix.
        :param inq: inbound multiprocessing.Queue (main process <-> worker)
        :param outq: outbound multiprocessing.Queue (worker <-> writer)
        :param config: Config class. Anyone who wants to put custom config
        class should implement attributes in `TrainConfig`.

        """
        multiprocessing.Process.__init__(self)
        self._train_uid = train_uid
        self._inq = inq
        self._outq = outq
        self._img_path = get_config_value(config, 'IMG_PATH')
        self._img_ext = get_config_value(config, 'IMG_EXT')

        # Unique id for each train.
        self._train_uid = train_uid
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
    def __init__(self, train_uid, inq, config=TrainConfig):
        multiprocessing.Process.__init__(self)
        self._train_uid = train_uid
        self._inq = inq
        self._data_path = get_config_value(config, 'DATA_PATH')
        self._data_seq = 0
        self._csv_initialized = False
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
            csv_header = 'id,img,' + sensor_header
            file_.write(csv_header + '\n')
            self._csv_initialized = True

        values = [image_filename] + [str(x) for x in sensor_data.raw.values()]
        data = ','.join(values)
        # Add seq id
        data = str(self._data_seq) + ',' + data
        self._data_seq += 1
        file_.write(data + '\n')


_train_sema = threading.BoundedSemaphore(value=1)


def generate_training_data(
        box=None, train_uid=None, config=TrainConfig,
        default_fps=10, wait_keypress=False):
    """Generate training data.

    :param wait_keypress: If this is True, do not start training until start
    key (keyboard `r`, wheel `left button 1`) is pressed.

    """
    try:
        streamer = stream_local_game_screen(box=box, default_fps=default_fps)

        worker_q = multiprocessing.Queue()
        writer_q = multiprocessing.Queue()
        num_workers = multiprocessing.cpu_count()
        workers = []

        if train_uid is None:
            d = str(datetime.datetime.now())
            train_uid = hashlib.md5(d).hexdigest()[:8]

        for i in range(num_workers):
            workers.append(
                Worker(train_uid, worker_q, writer_q)
            )

        # NOTE that these workers are daemonic processes
        for worker in workers:
            worker.start()

        # Start 1 process
        writer = Writer(train_uid, writer_q)
        writer.start()

        # Start 1 process and 1 thread.
        controller_state = ControllerState()
        controller_state.start()

        # Start 1 thread
        control_q = Queue()
        train_controller = TrainController(control_q)
        train_controller.start()

        # Start 1 thread
        keyboard_listener = KeyListener(control_q)
        keyboard_listener.start()

        fps_adjuster = FpsAdjuster(default_fps)
        last_sensor_data = None

        if wait_keypress:
            if box is None:
                # Select area and drop first screen image.
                next(streamer)
            _train_sema.acquire()

        while True:
            # TODO: Do something to resolve this in python 2.x
            # https://bugs.python.org/issue8844
            _train_sema.acquire()

            if last_sensor_data is None:
                # Start generator
                image_data = next(streamer)
            else:
                image_data = streamer.send(
                    fps_adjuster.get_next_fps(last_sensor_data))

            sensor_data = controller_state.get_state_obj()
            last_sensor_data = sensor_data
            worker_q.put((image_data, sensor_data))

            _feed_control_signal(control_q, sensor_data=sensor_data)

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
    feed it into `TrainController` thread.
    If both devices put input simultaneously, key_value is ignored.

    :param q: `Queue` between main thread and `TrainController` thread.
    :param key_value: Keyboard input
    :param sensor_data: `SensorData` object

    """
    control_signal = None

    if key_value is not None:
        if key_value == 'r':
            control_signal = TrainController.RESUME_SIGNAL
        elif key_value == 'q':
            control_signal = TrainController.PAUSE_SIGNAL

    if sensor_data is not None:
        if sensor_data.resume_button_pressed:
            control_signal = TrainController.RESUME_SIGNAL
        elif sensor_data.pause_button_pressed:
            control_signal = TrainController.PAUSE_SIGNAL

    if control_signal is not None:
        q.put(control_signal)


class KeyListener(keyboard.Listener):
    def __init__(self, outq):
        """Constructor.
        :param outq: `Queue` between this thread and `TrainController` thread.

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


class TrainController(threading.Thread):
    """This thread monitors keyboard input.
    Keypress `q`: Pause training data generation
    Keypress `r`: Resume training data generation

    """
    PAUSE_SIGNAL = 'pause'
    RESUME_SIGNAL = 'resume'

    def __init__(self, inq):
        threading.Thread.__init__(self)
        self.daemon = True
        self._inq = inq
        self._acquired = False

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
        if not self._acquired:
            _train_sema.acquire()
            self._acquired = True

    def _resume_data_generation(self):
        try:
            _train_sema.release()
            self._acquired = False
        except ValueError:
            pass


class FpsAdjuster(object):
    def __init__(self, default_fps):
        self._default_fps = default_fps
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
