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


class Worker(multiprocessing.Process):
    BREAK_FLAG = 'stop_consuming'

    def __init__(self, name, inq, train_uid=None, config=TrainConfig):
        """
        :param inq: inbound multiprocessing.Queue
        :param train_uid: If it's not None, csv data will be appended to
        existing data file.
        :param config: Config class. Anyone who wants to put custom config
        class should implement attributes in `TrainConfig`.

        """
        multiprocessing.Process.__init__(self, name=name)
        self._inq = inq
        self._data_path = get_config_value(config, 'DATA_PATH')
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
        # Init training data csv file. NOTE that this file is temporal and
        # will be removed later on.
        with open(os.path.join(
                self._data_path, self._train_uid + '_' + self.name + '.csv'),
                'w') as datafile:
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
        filename = self._img_path + self._train_uid + '_' + re.sub(
            '[-:.]', '_', datetime.datetime.now().isoformat('_')[:-4]) + \
            '.' + self._img_ext

        image = Image.fromarray(image_data, 'RGB')
        image.save(filename)

        data = [str(x) for x in sensor_data.values()]
        data.insert(0, filename)
        datafile.write(','.join(data) + '\n')


def generate_training_data(box=None, config=TrainConfig):
    """Generate training data.

    """
    streamer = stream_local_game_screen(box=box)
    q = multiprocessing.Queue()
    num_workers = multiprocessing.cpu_count()
    worker_name = str(0)
    first_worker = Worker(worker_name, q, config=config)
    workers = [first_worker]
    # We should share train_uid between multiple workers
    for i in range(num_workers - 1):
        worker_name = str(i + 1)
        workers.append(Worker(
            worker_name, q, train_uid=first_worker.train_uid))

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
        # Merge csv files generated from each worker into single file.
        data_path = get_config_value(config, 'DATA_PATH')
        csvs = [x for x in
            os.listdir(data_path)
            if x.startswith(first_worker.train_uid) and x.endswith('csv')
        ]

        # We assume that csv data will be small enough to fit into memory.
        rows = []
        for csv in csvs:
            with open(os.path.join(data_path, csv), 'r') as f:
                chunk = f.read()
                # Remove last data.
                # If worker process is interrupted while writing chunk to disk,
                # last row may or may not be broken. If it's broken, let's drop
                # it for data consistency. This can also happen in image data.
                # But we don't have to remove it because the image will never
                # be used if it's not in csv file.
                if chunk and chunk[-1] != '\n':
                    # Broken.
                    chunk = chunk[:chunk.rfind('\n')]
                else:
                    # Use :-1 to remove last newline
                    chunk = chunk[:-1]

                rows.extend(chunk.split('\n'))

        # remove blank content from rows
        rows = [x for x in rows if x is x.strip() != '']

        # Add seq id to rows
        rows = [str(idx) + ',' + x for idx, x in enumerate(rows)]

        # Remove temporal data files.
        for csv in csvs:
            os.remove(os.path.join(data_path, csv))

        # Make header row
        sensor_header = ','.join(controller_state.get_state().keys())
        header = 'id,' + 'img,' + sensor_header + '\n'

        # Write rows to final data file
        with open(os.path.join(
                data_path, first_worker.train_uid + '.csv'), 'w') as f:
            f.write(header)
            f.write('\n'.join(rows))

