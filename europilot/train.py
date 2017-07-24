"""
europilot.train
~~~~~~~~~~~~~~~

Utils for generating training data.
This module will start training immediately if it's executed in command line.

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
    DATA_PATH = ''
    IMG_EXT = 'jpg'


class Worker(multiprocessing.Process):
    BREAK_FLAG = 'stop_consuming'

    def __init__(self, inq, train_uid=None, config=TrainConfig):
        """
        :param inq: inbound multiprocessing.Queue
        :param train_uid: If it's not None, csv data will be appended to
        existing data file.
        :param config: Config class. Anyone who wants to put custom config
        class should implement attributes in `TrainConfig`.

        """
        multiprocessing.Process.__init__(self)
        self._inq = inq
        try:
            self._data_path = getattr(config, 'DATA_PATH')
            self._img_ext = getattr(config, 'IMG_EXT')
        except AttributeError as e:
            raise TrainException('Invalid configuration: %s' % e.args[0])

        self._datafile_mode = 'a' if train_uid is not None else 'w'
        # Unique id for each train.
        self._train_uid = train_uid or hashlib.md5(
            str(datetime.datetime.now())).hexdigest()[:8]
        self.daemon = True

    @property
    def train_uid(self):
        return self._train_uid

    def run(self):
        # Init training data csv file.
        with open(os.path.join(
                self._data_path, self._train_uid + '.csv'),
                self._datafile_mode) as datafile:
            while True:
                # Blocking `get`
                data = self._inq.get()
                if data == self.BREAK_FLAG:
                    break

                image_data, sensor_data = data
                self._save_data(datafile, image_data, sensor_data)

    def _save_data(self, datafile, image_data, sensor_data):
        """Synchronously write data to disk.

        :parma datafile: This method will write sensor data to this file.
        :param image_data: RGB numpy array
        :param sensor_data: `OrderedDict` containing sensor data

        CSV format
        filename,sensor_data1,sensor_data2,sensor_data3,...

        Order of sensor data depends on `OrderedDict` defined in
        `controllerstate.ControllerState`.

        """
        # filename example: '{self._train_uid}_2017_07_24_21_18_46_13.jpg'
        filename = self._train_uid + '_' + re.sub(
            '[-:.]', '_', datetime.datetime.now().isoformat('_')[:-4])

        image = Image.fromarray(image_data, 'RGB')
        image.save(filename + '.' + self._img_ext)

        data = [str(x) for x in sensor_data.values()]
        data.insert(0, filename)
        datafile.write(','.join(data) + '\n')


def generate_training_data(box=None):
    """Generate training data.

    """
    streamer = stream_local_game_screen(box=box)
    q = multiprocessing.Queue()
    num_workers = multiprocessing.cpu_count()
    first_worker = Worker(q)
    workers = [first_worker]
    # We should share train_uid between multiple workers
    for _ in range(num_workers - 1):
        workers.append(Worker(q, train_uid=first_worker.train_uid))

    # NOTE that these workers are daemonic processes
    for worker in workers:
        worker.start()

    # This will start 1 process and 1 thread.
    controller_state = ControllerState()
    controller_state.start()

    try:
        while True:
            image_data = next(streamer)
            sensor_data = controller_state.get_state()
            q.put((image_data, sensor_data))
    except KeyboardInterrupt:
        # If `box` is None, area selection window pops up before generation.
        # Due to bug in cv2.selectROI, the window sometimes hangs ignoring
        # SIGINT.
        # TODO: Need to kill it manually so that this process can exit
        # gracefully.
        pass


if __name__ == '__main__':
    generate_training_data()
