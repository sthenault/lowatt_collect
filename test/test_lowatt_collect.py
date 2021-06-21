# Copyright (c) 2018 by Sylvain Thénault sylvain@lowatt.fr
#
# This program is part of lowatt_collect
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

from contextlib import redirect_stderr, redirect_stdout
import doctest
from io import StringIO
from os import listdir as _listdir, makedirs
from os.path import abspath, basename, dirname, join
import sys
from tempfile import TemporaryDirectory
import unittest

from lowatt_collect import (
    build_env,
    collect, collect_commands,
    postcollect, postcollect_commands,
    run, source_defs,
)


THIS_DIR = abspath(dirname(__file__))
DATA_DIR = join(THIS_DIR, 'data')


def datafile(*filename):
    return join(DATA_DIR, *filename)


def listdir(directory):
    return sorted(_listdir(directory))


class BuildEnvTC(unittest.TestCase):

    def test(self):
        env = build_env({
            'root': 'hello',
            'environment': {
                'D1': '/d1',
                'D2': '{D1}/d2',
                'D3': 'relative/path',
            },
        }, "/opt/data/lowatt.yml")

        self.assertEqual(env['ROOT'], '/opt/data/hello')
        self.assertEqual(env['D1'], '/d1')
        self.assertEqual(env['D2'], '/d1/d2')
        self.assertEqual(env['D3'], '/opt/data/relative/path')


class CollectTC(unittest.TestCase):
    maxDiff = None

    def assertEOF(self, stream):
        self.assertEqual(stream.readline(), '')

    def test(self):
        with TemporaryDirectory() as tmpdir, \
             self.assertLogs('lowatt.collect', level='INFO') as cm:

            errors = collect(
                {
                    's1': {
                        'collect': '{HERE}/echofile.py {DIR}/s1.file hello',
                        'postcollect': 'crashmeforsure',
                        'collectack': '{HERE}/echofile.py {DIR}/ack {ERROR_FILES}',  # noqa
                    },
                    's2': {
                        'sub1': {
                            'collect': '{HERE}/echofile.py {DIR}/sub1.file {TEST} {SOURCE} {COLLECTOR}',  # noqa
                            'postcollect': '{HERE}/echofile.py {DIR}/sub1.file collected',  # noqa
                            'collectack': '{HERE}/echofile.py {DIR}/ack {SUCCESS_FILES}',  # noqa
                        },
                        'sub2': {
                            'collect': 'crashmeforsure',
                            'postcollect': 'wont ever happen',
                            'collectack': '{HERE}/echofile.py {DIR}/ack {ERROR_FILES} {SUCCESS_FILES}',  # noqa
                        },
                    },
                },
                env={'TEST': 'test', 'HERE': dirname(__file__)},
                root_directory=tmpdir,
            )

            self.assertEqual(
                sorted(msg.split(' No such file')[0] for msg in cm.output),
                [
                    'ERROR:lowatt.collect:Error running crashmeforsure: '
                    "[Errno 2]",
                    "ERROR:lowatt.collect:Error running crashmeforsure: "
                    "[Errno 2]",
                ],
            )

            self.assertEqual(len(errors), 2)

            self.assertEqual(
                listdir(tmpdir),
                ['s1', 's2'],
            )
            self.assertEqual(
                listdir(join(tmpdir, 's1')),
                ['.index.json', 'ack', 'errors'],
            )
            self.assertEqual(
                listdir(join(tmpdir, 's1', 'errors')),
                ['s1.file'],
            )
            self.assertEqual(
                listdir(join(tmpdir, 's2')),
                ['sub1', 'sub2'],
            )
            self.assertEqual(
                listdir(join(tmpdir, 's2', 'sub1')),
                ['.index.json', 'ack', 'sub1.file'],
            )
            # no errors directory since error occured during collect, so there
            # are no file to move there
            self.assertEqual(
                listdir(join(tmpdir, 's2', 'sub2')),
                ['.index.json', 'ack'],
            )

            with open(join(tmpdir, 's2', 'sub1', 'sub1.file')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    'test s2 s2.sub1',
                )
                nextline = stream.readline().strip()
                self.assertTrue(nextline.startswith('collected'))
                self.assertIn('sub1.file', nextline)
                self.assertEOF(stream)

            with open(join(tmpdir, 's2', 'sub1', 'ack')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    'sub1.file',
                )
                self.assertEOF(stream)

            with open(join(tmpdir, 's2', 'sub2', 'ack')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    '',
                )
                self.assertEOF(stream)

            with open(join(tmpdir, 's1', 'ack')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    's1.file',
                )
                self.assertEOF(stream)

    def test_shell_parser(self):
        with TemporaryDirectory() as tmpdir:
            collect(
                {
                    's1': {
                        'collect': '{HERE}/echofile.py {DIR}/s1.file "foo" \'bar\'',  # noqa
                        'postcollect': [],
                    },
                },
                env={'HERE': dirname(__file__)},
                postcollect_args=False,
                root_directory=tmpdir,
            )

            with open(join(tmpdir, 's1', 's1.file')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    'foo bar',
                )
                self.assertEOF(stream)

    def test_collect_no_postcollect_args(self):
        with TemporaryDirectory() as tmpdir:
            collect(
                {
                    's1': {
                        'collect': '{HERE}/echofile.py {DIR}/s1.file collect',
                        'postcollect': '{HERE}/echofile.py {DIR}/s1.file postcollect',  # noqa
                    },
                },
                env={'TEST': 'test', 'HERE': dirname(__file__)},
                postcollect_args=False,
                root_directory=tmpdir,
            )

            with open(join(tmpdir, 's1', 's1.file')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    'collect',
                )
                self.assertEqual(
                    stream.readline().strip(),
                    'postcollect',
                )
                self.assertEOF(stream)

    def test_postcollect_no_postcollect_args(self):
        with TemporaryDirectory() as tmpdir:
            makedirs(join(tmpdir, 's1'))
            open(join(tmpdir, 's1', 's1.file'), 'w').write('')
            postcollect(
                tmpdir,
                {
                    's1': {
                        'postcollect': '{HERE}/echofile.py {DIR}/s1.file postcollect',  # noqa
                    },
                },
                env={'TEST': 'test', 'HERE': dirname(__file__)},
                postcollect_args=False,
            )

            with open(join(tmpdir, 's1', 's1.file')) as stream:
                self.assertEqual(
                    stream.readline().strip(),
                    'postcollect',
                )
                self.assertEOF(stream)

    def test_bad_env_in_command(self):
        with TemporaryDirectory() as tmpdir, \
             self.assertLogs('lowatt.collect', level='INFO') as cm:
            errors = collect(
                {
                    's1': {
                        'collect': '{HERE}/echofile.py {DIRECTORY}/s1.file',
                        'postcollect': 'crashmeforsure',
                    },
                },
                env={'TEST': 'test', 'HERE': dirname(__file__)},
                root_directory=tmpdir,
            )

            self.assertEqual(len(errors), 1)
            self.assertEqual(
                cm.output,
                [
                    "ERROR:lowatt.collect:Command '{HERE}/echofile.py "
                    "{DIRECTORY}/s1.file' is using an unknown environment "
                    "variable, available are "
                    "COLLECTOR, DIR, HERE, SOURCE, TEST",
                ],
            )


def test_output_dir():
    with TemporaryDirectory() as tmpdir:
        collect(
            {
                's1': {
                    'collect': '{HERE}/echofile.py {DIR}/s1.file {OUTPUT_DIR}',
                    'postcollect': '{HERE}/echofile.py {DIR}/s1.file {OUTPUT_DIR}',  # noqa
                },
            },
            env={'TEST': 'test', 'HERE': dirname(__file__), "ROOT": "/data"},
            postcollect_args=False,
            root_directory=tmpdir,
        )

        with open(join(tmpdir, 's1', 's1.file')) as stream:
            assert stream.read() == "/data/s1\n/data/s1\n"


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
                'postcollect': ['echo s2.sub2 collected',
                                'echo s2.sub2 recollected'],
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
            commands[0].postcollect_cmds,
            'echo s2.sub1 collected',
        )
        self.assertEqual(
            commands[1].postcollect_cmds,
            [
                'echo s2.sub2 collected',
                'echo s2.sub2 recollected',
            ],
        )

    def test_no_postcollect(self):
        commands = list(collect_commands(self.sources, call_postcollect=False))
        commands = sorted(commands, key=lambda x: x.path)
        self.assertEqual(
            commands[0].postcollect_cmds,
            [],
        )
        self.assertEqual(
            commands[1].postcollect_cmds,
            [],
        )


class PostcollectCommandsTC(CollectCommandsTC):

    def test(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='INFO') as cm:
            commands = list(postcollect_commands(root_dir, self.sources))

        self.assertEqual(
            sorted(msg.replace(root_dir + '/', '') for msg in cm.output),
            [
                'ERROR:lowatt.collect:No postcollect command to '
                'handle s2/f2.csv',
                'ERROR:lowatt.collect:No source matching s1/unknown directory',
            ],
        )

        commands = sorted(commands, key=lambda x: x.path)
        self.assertEqual(len(commands), 3)
        self.assertEqual(
            repr(commands[0]),
            '<PostCollectFiles s1: echo manual source>',
        )
        self.assertEqual(
            [basename(file) for file in commands[0].files],
            ['f1.csv'],
        )
        self.assertEqual(
            repr(commands[1]),
            '<PostCollectFiles s2.sub1: echo s2.sub1 collected>',
        )
        self.assertEqual(
            repr(commands[2]),
            '<PostCollectFiles s2.sub2: echo s2.sub2 collected; '
            'echo s2.sub2 recollected>',
        )


class PostcollectTC(CollectCommandsTC):

    def test(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='INFO') as cm:
            errors = postcollect(root_dir, self.sources, {})

        self.assertEqual(
            sorted(msg.replace(root_dir + '/', '') for msg in cm.output),
            [
                'ERROR:lowatt.collect:No postcollect command to handle '
                's2/f2.csv',
                'ERROR:lowatt.collect:No source matching s1/unknown directory',
            ],
        )
        self.assertEqual(len(errors), 0)

    def test_specified_file(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='INFO') as cm:
            postcollect(
                root_dir, self.sources, {},
                [
                    datafile('s1', 'f1.csv'),
                    join(THIS_DIR, 'whatever'),
                    datafile('s2', 'f2.csv'),
                    datafile('s3', 'unexisting'),
                ],
            )

        self.assertEqual(
            sorted(msg.replace(THIS_DIR + '/', '') for msg in cm.output),
            [
                "ERROR:lowatt.collect:Can't find source for file "
                "data/s3/unexisting",
                "ERROR:lowatt.collect:File whatever isn't under "
                'root (data)',
                'ERROR:lowatt.collect:Source s2 for file data/s2/f2.csv has '
                'no postcollect command',
            ],
        )

    def test_specified_source(self):
        root_dir = DATA_DIR
        with self.assertLogs('lowatt.collect', level='DEBUG') as cm:
            postcollect(root_dir, self.sources, {}, ['s1'])

        self.assertEqual(
            sorted(msg.replace(THIS_DIR + '/', '') for msg in cm.output),
            [
                'DEBUG:lowatt.collect:post collecting 1 files for source s1',
            ],
        )


class SourceDefsTC(CollectCommandsTC):

    def test_key(self):
        sources = {
            's1': {
                'postcollect': 'echo hello',
            },
        }
        self.assertEqual(
            list(source_defs(sources)),
            [({'postcollect': 'echo hello'}, ['s1'])],
        )

        sources = {
            's1': {
                'collect': 'echo hello',
            },
        }
        self.assertEqual(
            list(source_defs(sources)),
            [({'collect': 'echo hello'}, ['s1'])],
        )

    def test_recurs(self):
        sources = {
            's1': {
                'sub1': {
                    'collect': 'echo s2.sub1',
                },
                'sub2': {
                    'postcollect': 'echo s2.sub2',
                },
            },
        }
        self.assertEqual(
            list(source_defs(sources)),
            [
                ({'collect': 'echo s2.sub1'},
                 ['s1', 'sub1']),
                ({'postcollect': 'echo s2.sub2'},
                 ['s1', 'sub2']),
            ],
        )

        sources = {
            's1': {
                'postcollect': 'echo s1',
                'sub1': {
                    'collect': 'echo s2.sub1',
                },
                'sub2': {
                    'postcollect': 'echo s2.sub2',
                },
            },
        }
        self.assertEqual(
            list(source_defs(sources)),
            [
                ({'postcollect': 'echo s1',
                  'sub1': {'collect': 'echo s2.sub1'},
                  'sub2': {'postcollect': 'echo s2.sub2'}},
                 ['s1']),
                ({'collect': 'echo s2.sub1'},
                 ['s1', 'sub1']),
                ({'postcollect': 'echo s2.sub2'},
                 ['s1', 'sub2']),
            ],
        )


class CLITC(unittest.TestCase):

    def test_no_command(self):
        sys.argv = ['lowatt-collect']

        stream = StringIO()
        with redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            run()

        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(
            stream.getvalue().startswith('usage:'),
            stream.getvalue().splitlines()[0] + '...',
        )

    def test_unexisting_sources_file(self):
        sys.argv = ['lowatt-collect', 'collect', 'unexisting_sources.yml']

        stream = StringIO()
        with redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            run()

        self.assertEqual(cm.exception.code, 1)

        output = stream.getvalue()
        self.assertTrue(
            output.startswith('An error occured while reading sources file:'),
            output.splitlines()[0] + '...',
        )

    def test_collect_specific_source_absolute(self):
        sys.argv = ['lowatt-collect', 'collect',
                    join(THIS_DIR, 'sources.yml'), join(DATA_DIR, 's2')]

        stream = StringIO()
        with redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            run()
        self.assertEqual(cm.exception.code, 0)

    def test_collect_specific_source_extra_args(self):
        sys.argv = ['lowatt-collect', 'collect',
                    join(THIS_DIR, 'sources.yml'), 's2', '--hop', 'extra']

        stream = StringIO()
        with redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            run()
        self.assertEqual(cm.exception.code, 0)
        # XXX test --hop extra actually reach the collect command

    def test_collect_error_unexisting_specific_source(self):
        sys.argv = ['lowatt-collect', 'collect',
                    join(THIS_DIR, 'sources.yml'), 's3']

        stream = StringIO()
        with redirect_stderr(stream), self.assertRaises(SystemExit) as cm:
            run()

        self.assertEqual(cm.exception.code, 2)
        self.assertIn('unexisting source s3', stream.getvalue())

    def test_collect_command_errors(self):
        sys.argv = ['lowatt-collect', 'collect',
                    join(THIS_DIR, 'sources.yml')]

        stream = StringIO()
        with redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            run()

        self.assertEqual(cm.exception.code, 2)

    def test_postcollect_errors(self):
        sys.argv = ['lowatt-collect', 'postcollect',
                    join(THIS_DIR, 'sources.yml')]

        stream = StringIO()
        with redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            run()

        self.assertEqual(cm.exception.code, 2)


def load_tests(loader, tests, ignore):
    tests.addTests(
        doctest.DocTestSuite('lowatt_collect', optionflags=doctest.ELLIPSIS),
    )
    return tests


if __name__ == '__main__':
    unittest.main()
