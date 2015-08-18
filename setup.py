#!/usr/bin/env python

import os
from setuptools import setup, find_packages
import re

with open(os.path.join(os.path.dirname(__file__), "VERSION")) as ff:
    VERSION = ff.read().strip()

with open(os.path.join(os.path.dirname(__file__), "requirements.txt")) as ff:
    requirements = [x for x in ff if x and re.match('^\s*\w.*', x)]

setup(name='docker_riemann',
      version=VERSION,
      description='Docker to riemann event router',
      author='Antonio Valente',
      author_email='antonio.valente@statpro.com',

      packages=find_packages(exclude=["*.tests"]),

      install_requires=requirements,

      entry_points={
          'console_scripts': [
              "docker-riemann=docker_riemann:main"
          ]
      }
)
