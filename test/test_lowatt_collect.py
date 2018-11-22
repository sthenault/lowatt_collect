# Copyright (c) 2018 by Sylvain Thénault sylvain@lowatt.fr
#
# This program is part of lowatt_collect
#
# lowatt_collect is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Foobar is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Foobar.  If not, see <https://www.gnu.org/licenses/>.

from contextlib import contextmanager
import doctest
from io import StringIO
from os import listdir as _listdir
from os.path import abspath, basename, dirname, join
import sys
from tempfile import TemporaryDirectory
import unittest

from lowatt_collect import (
    collect, collect_commands,
    postcollect, postcollect_commands,
    run,
)


THIS_DIR = abspath(dirname(__file__))
DATA_DIR = join(THIS_DIR, 'data')


def datafile(*filename):
    return join(DATA_DIR, *filename)


def listdir(directory):
    return sorted(_listdir(directory))


@contextmanager
def redirect(output):
    setattr(sys, output, StringIO())
    yield getattr(sys, output)
    setattr(sys, output, getattr(sys, '__{}__'.format(output)))


class CollectTC(unittest.TestCase):
    maxDiff = None

    def test(self):
        with TemporaryDirectory() as tmpdir:
            with self.assertLogs('lowatt.collect', level='INFO') as cm:

                errors = collect(
                    {
                        's1': {
                            'collect': 'echo hello > $DIR/s1.file',
                            'postcollect': 'crashmeforsure',
                        },
                        's2': {
                            'sub1': {
                                'collect': 'echo $TEST $SOURCE $COLLECTOR > $DIR/sub1.file',  # noqa
                                'postcollect': 'echo `basename $FILE` collected >> $FILE',  # noqa
                            },
                            'sub2': {
                                'collect': 'crashmeforsure',
                                'postcollect': 'wont ever happen',
                            },
                        },
                    },
                    env={'TEST': 'test'},
                    root_directory=tmpdir)

            self.assertEqual(
                sorted([msg.rstrip('.') for msg in cm.output]),
                ['ERROR:lowatt.collect:error running crashmeforsure '
                 'on s1.file: '
                 "Command 'crashmeforsure' returned non-zero exit status 127",
                 "ERROR:lowatt.collect:error running crashmeforsure: "
                 "Command 'crashmeforsure' returned non-zero exit status 127"])
            self.assertEqual(len(errors), 2)

            self.assertEqual(listdir(tmpdir),
                             ['s1', 's2'])
            self.assertEqual(listdir(join(tmpdir, 's1')),
                             ['errors'])
            self.assertEqual(listdir(join(tmpdir, 's1', 'errors')),
                             ['s1.file'])
            self.assertEqual(listdir(join(tmpdir, 's2')),
                             ['sub1', 'sub2'])
            self.assertEqual(listdir(join(tmpdir, 's2', 'sub1')),
                             ['sub1.file'])
            # no errors directory since error occured during collect, so there
            # are no file to move there
            self.assertEqual(listdir(join(tmpdir, 's2', 'sub2')),
                             [])

            with open(join(tmpdir, 's2', 'sub1', 'sub1.file')) as stream:
                self.assertEqual(
                    stream.read().strip(),
                    'test s2 s2.sub1\nsub1.file collected',
                )


class CollectCommandsTC(unittest.TestCase):
    maxDiff = None

    sources = {
        's1': {
            'postcollect': 'echo manual source',
        },
        's2': {
            'sub1': {
                'collect': 'echo s2.sub1',
                'postcollect': 'echo s2.sub1 collected',
            },
            'sub2': {
                'collect': 'echo s2.sub2',
                'postcollect': 'echo s2.sub2 collected',
            },
        },
    }

    def test(self):
        commands = list(collect_commands(self.sources))

        commands = sorted(commands, key=lambda x: x.path)
        # postcollect only sources are not collected
        self.assertEqual(len(commands), 2)

        self.assertEqual(
            repr(commands[0]),
            '<CollectSource s2.sub1: echo s2.sub1>',
        )
        self.assertEqual(
            commands[0].postcollect_cmd,
            'echo s2.sub1 collected',
        )


class PostcollectCommandsTC(CollectCommandsTC):

    def test(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='INFO') as cm:
            commands = list(postcollect_commands(root_dir, self.sources))

        self.assertEqual(
            sorted([msg.replace(root_dir + '/', '') for msg in cm.output]),
            [
                'ERROR:lowatt.collect:No postcollect command to '
                'handle s2/f2.csv',
                'ERROR:lowatt.collect:No source matching s1/unknown directory',
            ])

        commands = sorted(commands, key=lambda x: x.path)
        self.assertEqual(len(commands), 3)
        self.assertEqual(repr(commands[0]),
                         '<PostCollectFile s1: echo manual source>')
        self.assertEqual(basename(commands[0].fpath), 'f1.csv')
        self.assertEqual(repr(commands[1]),
                         '<PostCollectFile s2.sub1: echo s2.sub1 collected>')
        self.assertEqual(repr(commands[2]),
                         '<PostCollectFile s2.sub2: echo s2.sub2 collected>')


class PostcollectTC(CollectCommandsTC):

    def test(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='INFO') as cm:
            errors = postcollect(root_dir, self.sources, {})

        self.assertEqual(
            sorted([msg.replace(root_dir + '/', '') for msg in cm.output]),
            [
                'ERROR:lowatt.collect:No postcollect command to handle '
                's2/f2.csv',
                'ERROR:lowatt.collect:No source matching s1/unknown directory',
            ])
        self.assertEqual(len(errors), 0)

    def test_specified_file(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='INFO') as cm:
            postcollect(root_dir, self.sources, {},
                        [
                            datafile('s1', 'f1.csv'),
                            join(THIS_DIR, 'whatever'),
                            datafile('s2', 'f2.csv'),
                            datafile('s3', 'unexisting'),
                        ])

        self.assertEqual(
            sorted([msg.replace(THIS_DIR + '/', '') for msg in cm.output]),
            [
                "ERROR:lowatt.collect:Can't find source for file "
                "data/s3/unexisting",
                "ERROR:lowatt.collect:File whatever isn't under "
                'root (data)',
                'ERROR:lowatt.collect:Source for file data/s2/f2.csv has '
                'no postcollect command',
            ])


class CLITC(unittest.TestCase):

    def test_no_command(self):
        sys.argv = ['lowatt-collect']

        with redirect('stdout') as stream:
            with self.assertRaises(SystemExit) as cm:
                run()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(stream.getvalue().startswith('usage:'),
                        stream.getvalue().splitlines()[0] + '...')

    def test_unexisting_sources_file(self):
        sys.argv = ['lowatt-collect', 'collect', 'unexisting_sources.yml']

        with redirect('stdout') as stream:
            with self.assertRaises(SystemExit) as cm:
                run()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(
            stream.getvalue().startswith('An error occured while reading sources file:'),
            stream.getvalue().splitlines()[0] + '...')

    def test_collect_errors(self):
        sys.argv = ['lowatt-collect', 'collect', join(THIS_DIR, 'sources.yml')]

        with redirect('stdout') as stream:
            with self.assertRaises(SystemExit) as cm:
                run()

        self.assertEqual(cm.exception.code, 2)

    def test_postcollect_errors(self):
        sys.argv = ['lowatt-collect', 'postcollect', join(THIS_DIR, 'sources.yml')]

        with redirect('stdout') as stream:
            with self.assertRaises(SystemExit) as cm:
                run()

        self.assertEqual(cm.exception.code, 2)


def load_tests(loader, tests, ignore):
    tests.addTests(
        doctest.DocTestSuite('lowatt_collect', optionflags=doctest.ELLIPSIS)
    )
    return tests


if __name__ == '__main__':
    unittest.main()
