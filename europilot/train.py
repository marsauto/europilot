"""
europilot.train
~~~~~~~~~~~~~~~

Utils for generating training data.

"""

import os
import re
import hashlib
import datetime
import multiprocessing

import numpy as np
from PIL import Image

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
            # Blocking `get`
            data = self._inq.get()

            if data == _WORKER_BREAK_FLAG:
                break

            image_data, sensor_data = data
            self._save_image(image_data)
            self._outq.put(sensor_data)

    def _save_image(self, image_data):
        """Synchronously write image data to disk.
        :param image_data: RGB numpy array

        CSV format
        filename,sensor_data1,sensor_data2,sensor_data3,...

        Order of sensor data depends on `OrderedDict` defined in
        `controllerstate.ControllerState`.

        """
        # filename example: '{self._train_uid}_2017_07_24_21_18_46_13.jpg'
        filename = self._img_path + self._train_uid + '_' + re.sub(
            '[-:.]', '_', datetime.datetime.now().isoformat('_')[:-4]) + \
            '.' + self._img_ext

        image = Image.fromarray(image_data, 'RGB')
        image.save(filename)


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
                sensor_data = self._inq.get()

                if sensor_data == _WORKER_BREAK_FLAG:
                    break

                self._write(file_, sensor_data)

    def _write(self, file_, sensor_data):
        """Synchronously write sensor data to disk.
        :param sensor_data: `dict` containing sensor data.

        CSV format
        seq_id,filename,sensor_data1,sensor_data2,sensor_data3,...

        Order of sensor data depends on `OrderedDict` defined in
        `controllerstate.ControllerState`.

        """
        if not self._csv_initilized:
            # Add headers
            sensor_header = ','.join(sensor_data.keys())

        data = ','.join([str(x) for x in sensor_data.values()])
        # Add seq id
        data = str(self._data_seq) + ',' + data
        self._data_seq += 1
        file_.write(data + '\n')


def generate_training_data(box=None, config=TrainConfig):
    """Generate training data.

    """
    streamer = stream_local_game_screen(box=box)

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

    try:
        while True:
            image_data = next(streamer)
            sensor_data = controller_state.get_state()
            worker_q.put((image_data, sensor_data))
    except KeyboardInterrupt:
        # Gracefully stop workers
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

