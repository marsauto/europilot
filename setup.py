import os
from setuptools import setup


install_requires = [
    'mss==3.0.1',
    'numpy>=1.12.1',
    'Pillow>=4.2.1',
    'pynput>=1.3.5'
]

about = {}
cur_path = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(
        cur_path, 'europilot', '__version__.py'), 'r') as f:
    exec(f.read(), {'__builtins__' : None}, about)

setup(
    name=about['__title__'],
    version=about['__version__'],
    description=about['__description__'],
    packages=['europilot', 'scripts'],
    install_requires=install_requires
)
