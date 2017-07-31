"""
http://upgrayd.blogspot.de/2011/03/logitech-dual-action-usb-gamepad.html

G27
===
example::

    A0 B7 A3 04 5C 7D 02 02
     0  1  2  3  4  5  6  7


    0, 1, 2, 3: sequence, little endian
    4, 5: value, little endian
    6: group
    7: axis

NOTE! From here on, I talk big endian -- also in hex!

Wheel values::

            left               dead           right
            <-------------------XX---------------->
    dec     32769      65535     0      1     32767
    hex     80 01      ff ff  00 00 00 01     7F FF


Pedal values::

- no pressure: 7F FF
- halfway: 00 00
- full: 80 01


Button values::

- on: 01 00
- off: 00 00


Gear values::

- on: 01 00
- off: 00 00


Arrow Pad values::

- left/up: 01 80 (32769)
- right/down: ff 7f (32767)
- off : 00 00


For wheel values, the output range is normalized to [-32767, 32767].
For pedal values, the output range is normalized to [0, 65535].
For Arrow Pad values, the output range is normalized to [-1, 1].


"""
import os
import sys
import time
import random
from binascii import hexlify

BUTTON_NAME = """
0200=wheel-axis
0201=clutch
0203=brake
0202=gas
0105=paddle-left
0104=paddle-right
0107=wheel-button-left-1
0114=wheel-button-left-2
0115=wheel-button-left-3
0106=wheel-button-right-1
0112=wheel-button-right-2
0113=wheel-button-right-3
0101=shifter-button-left
0102=shifter-button-right
0103=shifter-button-up
0100=shifter-button-down
0204=dpad-left/right
0205=dpad-up/down
010b=shifter-button-1
0108=shifter-button-2
0109=shifter-button-3
010a=shifter-button-4
010c=gear-1
010d=gear-2
010e=gear-3
010f=gear-4
0110=gear-5
0111=gear-6
0116=gear-R
"""


class Bytewurst(object):

    def __init__(self, bs):
        self.raw = bs
        self.ints = map(ord, bs)

    def __repr__(self):
        return ' '.join(map(hexlify, self.raw))

    @property
    def int(self):
        """
        For "01 0A" ints would be [1, 10], so::
            >>> bs = '\x01\x0A'
            >>> bw = Bytewurst(bs)
            >>> bw.int == (1 * 1) + (10 * 256)
        """

        def powergenerator(start=0):
            """Generate powers of 256"""
            i = start
            while True:
                yield 256 ** i
                i += 1

        return sum(a * b for a, b in zip(self.ints, powergenerator()))

    @property
    def hexLE(self):
        return hexlify(self.raw)

    @property
    def bits(self):
        return ' '.join([format(x, '08b') for x in self.ints])


class Button(Bytewurst):
    def __init__(self, bs):
        super(Button, self).__init__(bs)
        button_namedict = dict(line.split('=') for line in
                               BUTTON_NAME.strip().split('\n'))
        self.name = button_namedict.get(self.hexLE, 'UNKNOWN:%s' % self.hexLE)


class Value(Bytewurst):
    def __repr__(self):
        if self.int == 0:
            return ' off'
        elif self.int == 1:
            return ' on'
        else:
            return ' %d' % self.int

    def int_normalized(self, name):
        """ Normalizes value to an adequate range

        For wheel values, the output range is normalized to [-32767, 32767].
        For pedal values, the output range is normalized to [0, 65535].
        For Arrow Pad values, the output range is normalized to [-1, 1].
        """
        v = super(Value, self).int
        if name == 'wheel-axis':
            if v >= 32769:
                v = v - 65536
        elif name == 'clutch' or name == 'brake' or name == 'gas':
            if v >= 32769:
                v = -v + 98304
            else:
                v = -v + 32767
        elif name == 'dpad-left/right' or name == 'dpad-up/down':
            if v == 32769:
                v = -1
            elif v == 32767:
                v = 1

        return v


class Message(object):
    def __init__(self, bs):
        self.bs = bs
        self.raw_seq = bs[0:4]
        self.raw_value = bs[4:6]
        self.raw_id = bs[6:8]
        self.ints = map(ord, bs)
        self.sequence = Bytewurst(bs[0:4])
        self.value = Value(bs[4:6])
        self.button = Button(bs[6:8])

    def __repr__(self):
        values = (self.button.name,
                  self.value.int_normalized(self.button.name))
        return ' '.join(map(str, values))


class LinuxVirtualJoystick(object):
    """
    A Virtual joystick driver is implemented by attaching userspace device
    drivers in the kernel by outputting events into udev.

    Relevant information about the virtual driver was derived with evtest.

    A LinuxVirtualJoystick object must be initialized before ETS is started
    for the game to recognize the virtual driver.

    Note that you may have to adjust the control settings inside ETS to
    map the events with the necessary values. Check the project page for more
    details.
    """
    def __init__(self, name='Virtual G27 Racing Wheel', bustype=0x0003,
                 vendor=0x046d, product=0xc29b, version=0x0111, events=None):
        if events is None:
            events = (
                # EV_KEY
                uinput.BTN_TRIGGER,
                uinput.BTN_THUMB,
                uinput.BTN_THUMB2,
                uinput.BTN_TOP,
                uinput.BTN_TOP2,
                uinput.BTN_PINKIE,
                uinput.BTN_BASE,
                uinput.BTN_BASE2,
                uinput.BTN_BASE3,
                uinput.BTN_BASE4,
                uinput.BTN_BASE5,
                uinput.BTN_BASE6,
                (0x01, 0x12c),  # (event code 300)
                (0x01, 0x12d),  # (event code 301)
                (0x01, 0x12e),  # (event code 302)
                uinput.BTN_DEAD,
                uinput.BTN_TRIGGER_HAPPY1,
                uinput.BTN_TRIGGER_HAPPY2,
                uinput.BTN_TRIGGER_HAPPY3,
                uinput.BTN_TRIGGER_HAPPY4,
                uinput.BTN_TRIGGER_HAPPY5,
                uinput.BTN_TRIGGER_HAPPY6,
                uinput.BTN_TRIGGER_HAPPY7,

                # EV_ABS
                uinput.ABS_X + (-32767, 32767, 0, 0),   # steering wheel
                uinput.ABS_Y + (0, 65535, 0, 0),   # clutch
                uinput.ABS_Z + (0, 65535, 0, 0),   # acceleration
                uinput.ABS_RZ + (0, 65535, 0, 0),  # break
                uinput.ABS_HAT0X + (-1, 1, 0, 0),
                uinput.ABS_HAT0Y + (-1, 1, 0, 0),
            )

        self.device = uinput.Device(events,
                                    name=name,
                                    bustype=bustype,
                                    vendor=vendor,
                                    product=product,
                                    version=version)

    def emit(self, angle, clutch=None, accel=None, brk=None):
        # emit as one atomic event, by using syn=True at the last emit call
        # for more information check the source code at
        # https://github.com/tuomasjjrasanen/python-uinput/blob/master/src/__init__.py#L191

        if clutch:
            self.device.emit(uinput.ABS_Y, clutch, syn=False)
        if accel:
            self.device.emit(uinput.ABS_Z, accel, syn=False)
        if brk:
            self.device.emit(uinput.ABS_RZ, brk, syn=False)

        self.device.emit(uinput.ABS_X, angle, syn=True)

    def __del__(self):
        self.device.destroy()


# Handle platform dependent joystick impl
if sys.platform.startswith('linux'):
    import uinput
    VirtualJoystick = LinuxVirtualJoystick
elif sys.platform == 'darwin':
    pass


if __name__ == '__main__':
    def _dump_messages(input_):
        with open(input_, 'rb') as device:
            while True:
                bs = device.read(8)
                message = Message(bs)
                print(message)

    def _dump_dummy_messages():
        # Need to simulate straight wheel axis to test realtime fps adjustment.
        straight = False
        straight_start_time = None
        straight_duration = 5
        while True:
            if not straight and random.randint(0, 99) == 0:
                # Straight wheel axis for 5 secs.
                straight = True
                straight_start_time = time.time()

            if straight and \
                    time.time() - straight_start_time > straight_duration:
                # End of straight wheel axis
                straight = False
                straight_start_time = None

            # Axis value 0 will be regarded as straight wheel regardless of
            # `train.FpsAdjuster._max_straight_wheel_axis`.
            wheel_axis = random.randint(-32767, 32767) if not straight else 0

            print('wheel-axis ' + str(wheel_axis))

    # TODO: Get device path as argument
    device = '/dev/input/js0'
    if os.path.exists(device):
        _dump_messages(device)
    else:
        # When joystick doesn't exist. Let's dump dummy messages.
        # TODO: Warn this to stdout so that we can be aware of mock g27.
        _dump_dummy_messages()
