#!/usr/bin/env python3

from setuptools import setup

setup(name='lowatt_collect',
      version='1.0',
      license=license,
      url='',
      description='',
      long_description='',
      author='Sylvain Thénault',
      author_email='contact@lowatt.fr',
      py_modules=['lowatt_collect'],
      include_package_data=True,
      #  package_data=package_data,
      install_requires=[
          'pyyaml',
      ],
      entry_points={
          'console_scripts': [
              'lowatt-collect=lowat_collect:run',
          ],
      },
      extras_require={
      })
