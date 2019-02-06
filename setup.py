#!/usr/bin/env python3
#
# Copyright (c) 2018 by Sylvain Thénault sylvain@lowatt.fr
#
# This program is part of lowatt_collect.
#
# lowatt_collect is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# lowatt_collect is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with lowatt_collect.  If not, see <https://www.gnu.org/licenses/>.

from setuptools import setup

setup(
    name='lowatt_collect',
    version='1.0',
    url='https://github.com/lowatt/lowatt_collect',

    license='GPL3',
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "License :: OSI Approved :: GNU General Public License v3 or later "
        "(GPLv3+)",
        "Operating System :: OS Independent",
        "Topic :: System :: Archiving :: Mirroring",
    ],
    description='collect arbitrary data',
    long_description='Command line interface to collect distant data and do '
    'something about it',
    author='Sylvain Thénault',
    author_email='info@lowatt.fr',

    py_modules=['lowatt_collect'],
    install_requires=[
        'pyyaml',
    ],
    entry_points={
        'console_scripts': [
            'lowatt-collect=lowatt_collect:run',
        ],
    },
)
