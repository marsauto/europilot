"""
europilot.train
~~~~~~~~~~~~~~~

Utils for generating training data.

"""

import os
import re
import hashlib
import datetime
import threading
import multiprocessing

import numpy as np
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
        self._train_uid = train_uid or hashlib.md5(
            str(datetime.datetime.now())).hexdigest()[:8]
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
        self._csv_initilized = False
        self._filename = self._train_uid + '.csv'

    @property
    def filename(self):
        return self._filename

    def run(self):
        with open(os.path.join(self._data_path, self._filename), 'w') as file_:
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
        :param sensor_data: `dict` containing sensor data.

        CSV format
        seq_id,filename,sensor_data1,sensor_data2,sensor_data3,...

        Order of sensor data depends on `OrderedDict` defined in
        `controllerstate.ControllerState`.

        """
        if not self._csv_initilized:
            # Add headers
            sensor_header = ','.join(sensor_data.keys())
            file_.write(sensor_header + '\n')
            self._csv_initilized = True

        values = [image_filename] + [str(x) for x in sensor_data.values()]
        data = ','.join(values)
        # Add seq id
        data = str(self._data_seq) + ',' + data
        self._data_seq += 1
        file_.write(data + '\n')


_train_sema = threading.BoundedSemaphore(value=1)


def generate_training_data(box=None, config=TrainConfig, fps=10):
    """Generate training data.

    """
    try:
        streamer = stream_local_game_screen(box=box, fps=fps)

        worker_q = multiprocessing.Queue()
        writer_q = multiprocessing.Queue()
        num_workers = multiprocessing.cpu_count()
        workers = []
        train_uid = hashlib.md5(str(datetime.datetime.now())).hexdigest()[:8]
        for i in range(num_workers):
            workers.append(
                Worker(train_uid, worker_q, writer_q)
            )

        # NOTE that these workers are daemonic processes
        for worker in workers:
            worker.start()

        # Start writer
        writer = Writer(train_uid, writer_q)
        writer.start()

        # This will start 1 process and 1 thread.
        controller_state = ControllerState()
        controller_state.start()

        train_controller = TrainController()
        train_controller.start()

        while True:
            _train_sema.acquire()
            image_data = next(streamer)
            sensor_data = controller_state.get_state()
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

        broken = False
        data_filepath = os.path.join(
            get_config_value(config, 'DATA_PATH'), writer.filename)
        with open(data_filepath, 'r') as f:
            chunk = f.read()
            # If worker process is interrupted while writing chunk to disk,
            # last row may or may not be broken. If it's broken, let's drop
            # it for data consistency. This can also happen in image data.
            # But we don't have to remove it because the image will never
            # be used if it's not in csv file.
            if chunk and chunk[-1] != '\n':
                # Broken.
                broken = True
                chunk = chunk[:chunk.rfind('\n') + 1]

        # XXX: Super inefficient way to remove lastline of a file
        if broken:
            with open(data_filepath, 'w') as f:
                f.write(chunk)


class TrainController(threading.Thread):
    """This thread monitors keyboard input.
    Keypress `q`: Pause training data generation
    Keypress `r`: Resume training data generation

    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self._acquired = False

    def run(self):
        # Watch keyboard input
        with keyboard.Listener(
                on_press=self._dispatcher) as listener:
            listener.join()

    def _dispatcher(self, key):
        try:
            if key.char == 'r':
                self._resume_data_generation()
            elif key.char == 'q':
                self._pause_data_generation()
        except AttributeError:
            # Pressed key is not alphabet.
            pass

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

