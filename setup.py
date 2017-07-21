import os
from setuptools import setup


install_requires = [
    'opencv_python>=3.2.0.7',
    'Keras>=2.0.4',
    'matplotlib>=1.3.1',
    'mss==3.0.1',
    'numpy>=1.12.1',
    'pandas>=0.19.0',
    'scipy>=0.17.1',
    'Theano>=0.8.2',
    'ipython>=5.0.0,<5.4.1',
    'Pillow>=4.2.1',
    'bcolz>=1.1.2',
    'scikit_learn>=0.19b2'
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
    packages=['europilot'],
    install_requires=install_requires
)
