from controllerstate import ControllerState
import threading
import sys
from subprocess import PIPE, Popen

if __name__ == '__main__':
    c = ControllerState()
    c.start()

    def print_output():
        threading.Timer(10.0, print_output).start()
        print(c.get_state())

    print_output()

    # ON_POSIX = 'posix' in sys.builtin_module_names
    # p = Popen(['python', '-u', 'g27.py'], bufsize=0, stdout=PIPE,
    #                close_fds=ON_POSIX)
    # for line in iter(p.stdout.readline, ''):
    #     print("line: %s" % line)
    # p.stdout.close()