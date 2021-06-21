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
"""
``lowatt_collect``
------------------

**Command line interface and misc tools to collect distant data and do something
about it**

See the README file for documentation on usage and configuration.

.. autofunction:: collect
.. autofunction:: postcollect
.. autofunction:: collect_commands
.. autofunction:: postcollect_commands
.. autofunction:: files_postcollect_commands
.. autofunction:: source_defs
.. autofunction:: build_env
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from concurrent import futures
import logging
import os
from os.path import abspath, dirname, isdir, join, relpath
import shlex
from shutil import move
import subprocess
import sys
from tempfile import TemporaryDirectory


LOGGER = logging.getLogger('lowatt.collect')


def collect(
        sources, root_directory, env,
        max_workers=4, collect_options=None,
        call_postcollect=True, postcollect_args=True,
):
    """Start collection of data from 'sources' dictionary, using 'env' environment
    variables. Fully collected files are put in the corresponding source
    directory under `root_directory`, or in a 'errors' subdirectory if some
    error occured during postcollect.

    One may specify the maximum number of parallel collects using `max_workers`,
    or a list of options that should be added to the collect command found in
    sources definition.
    """
    root_directory = abspath(root_directory)
    collect_cmds = collect_commands(
        sources, collect_options,
        call_postcollect=call_postcollect,
        postcollect_args=postcollect_args,
    )
    return _execute(max_workers, collect_cmds, root_directory, env)


def collect_commands(
        sources, collect_options=None,
        call_postcollect=True, postcollect_args=True,
        _path=None,
):
    """Generator of "CollectSource" instances given `sources` configuration as a
    dictionary.

    `collect_options` is an optional list of options to append to the collect
    command string.
    """
    for source_def, _path in source_defs(sources):
        collect_cmd_string = source_def.get('collect')
        if collect_cmd_string:
            if collect_options:
                collect_cmd_string += ' ' + ' '.join(collect_options)
            if call_postcollect:
                postcollect_cmds = source_def['postcollect']
            else:
                postcollect_cmds = []

            yield CollectSource(
                collect_cmd_string, postcollect_cmds,
                source_def.get('collectack'), _path[:],
                postcollect_args=postcollect_args,
            )


def postcollect(
    root_directory, sources, env, files=None, max_workers=4,
    postcollect_args=True,
):
    """Run postcollect on previously collected files.

    If files is specified, only import given files provided some matching source
    is found, else attempt to run postcollect on every files within
    `root_directory`.

    One may specify the maximum number of parallel collects using `max_workers`.
    """
    root_directory = abspath(root_directory)
    if files:
        commands = files_postcollect_commands(files, sources, root_directory)
    else:
        commands = postcollect_commands(
            root_directory,
            sources,
            postcollect_args=postcollect_args,
        )

    return _execute(max_workers, commands, env)


def postcollect_commands(
    directory, sources, _path=None, postcollect_args=True,
):
    """Generator of "PostCollectFiles" instances for each matching file within
    `directory` considering `sources` definition.
    """
    if _path is None:
        _path = []

    files = []
    for fname in os.listdir(directory):
        fpath = join(directory, fname)

        if isdir(fpath):
            if fname not in sources:
                if fname != 'errors':
                    LOGGER.error('No source matching %s directory', fpath)
            else:
                _path.append(fname)
                yield from postcollect_commands(
                    fpath,
                    sources[fname],
                    _path,
                    postcollect_args=postcollect_args,
                )
                _path.pop()

        elif 'postcollect' not in sources:
            LOGGER.error('No postcollect command to handle %s', fpath)

        else:
            files.append(fpath)

    if files:
        yield PostCollectFiles(
            directory, files if postcollect_args else [],
            sources['postcollect'], _path[:],
        )


def files_postcollect_commands(files, sources, root_directory):
    """Generator of "PostCollectFiles" instances for given `files`, provided a
    matching source is found in `sources` definition.

    Source is located by looking at file's subdirectory within `root_directory`.
    """
    files_by_source = defaultdict(list)
    sources_cache = {}

    def source_for_path(path):
        key = '.'.join(path)
        try:
            return key, sources_cache[key]
        except KeyError:

            file_source = sources
            for part in path:
                file_source = file_source[part]

            sources_cache[key] = file_source
            return key, file_source

    def source_for_file(fpath):
        path = relpath(dirname(fpath), root_directory).split(os.sep)
        return source_for_path([part for part in path if part])

    for fpath in files:
        path = fpath.split('.')
        try:
            key, file_source = source_for_path(path)
        except KeyError:

            fpath = abspath(fpath)
            if not fpath.startswith(root_directory):
                LOGGER.error("File %s isn't under root (%s)",
                             fpath, root_directory)
                continue

            try:
                key, file_source = source_for_file(fpath)
                files = [fpath]
            except KeyError:
                LOGGER.error("Can't find source for file %s", fpath)
                continue

        else:
            files = [join(root_directory, *path, fname)
                     for fname in os.listdir(join(root_directory, *path))]
            files = [filepath for filepath in files if not isdir(filepath)]

        if file_source.get('postcollect'):
            files_by_source[key] += files
        else:
            LOGGER.error(
                "Source %s for file %s has no postcollect command", key, fpath)

    for source_key, files in files_by_source.items():
        LOGGER.debug('post collecting %s files for source %s',
                     len(files), source_key)
        directory = join(root_directory, *source_key.split('.'))
        yield PostCollectFiles(
            directory, files, sources_cache[source_key]['postcollect'],
            source_key.split('.'),
        )


SOURCE_KEYS = {'collect', 'postcollect'}


def source_defs(sources, _path=None):
    """Return a generator on `({source definition}, [source path])` from `sources`
    structure as defined in the configuration file.
    """
    if _path is None:
        _path = []

    for source_key, source_def in sources.items():

        _path.append(source_key)

        if SOURCE_KEYS & set(source_def):
            yield source_def, _path[:]

        if isinstance(source_def, dict):
            yield from source_defs(source_def, _path)

        _path.pop()


def build_env(config, source_file=None, log_level=None):
    """Initialize and return process environment from os environment and custom
    environment defined in `config['environ]` if any.
    """
    env = os.environ.copy()

    env['ROOT'] = config['root']
    if source_file is not None:
        env['ROOT'] = join(dirname(source_file), env['ROOT'])

    if log_level is not None:
        env['LOG_LEVEL'] = log_level

    file_environ = config.get('environment', {})
    # rely on python 3.6 ordered dict to ensure proper ordering
    for key, value in file_environ.items():
        file_environ[key] = value.format(**file_environ)
        if source_file is not None:
            file_environ[key] = join(dirname(source_file), file_environ[key])
    env.update(file_environ)

    return env


class Command(ABC):

    def __init__(self, cmds, path):
        if isinstance(cmds, str):
            cmds = [cmds]
        self.cmds = cmds
        self.path = path

    def __repr__(self):
        return '<{} {}: {}>'.format(
            self.__class__.__name__, '.'.join(self.path),
            '; '.join(self.cmds))

    def init_env(self, env, directory):
        env = env.copy()
        env['SOURCE'] = self.path[0]
        env['COLLECTOR'] = '.'.join(self.path)
        env['DIR'] = directory
        try:
            env['OUTPUT_DIR'] = join(env["ROOT"], *self.path)
        except KeyError:
            pass
        return env

    def execute(self, directory, env, *files):
        env = self.init_env(env, directory)

        errors = []
        for base_cmd in self.cmds:
            errors += _call(env, base_cmd, files)

        return errors

    @abstractmethod
    def run(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


class CollectSource(Command):

    def __init__(
            self, collect_cmd, postcollect_cmds, ack_cmd, path,
            postcollect_args=True,
    ):
        super().__init__(collect_cmd, path)
        self.postcollect_cmds = postcollect_cmds
        self.ack_cmd = ack_cmd
        self.postcollect_args = postcollect_args

    def run(self, root_directory, env):
        destdir = join(root_directory, *self.path)
        os.makedirs(destdir, exist_ok=True)

        error_files = []
        success_files = []

        with TemporaryDirectory() as tmpdir:
            errors = self.execute(tmpdir, env)
            # run post collect for each file separatly to properly handle move
            # in the source directory or its errors directory
            for fname in os.listdir(tmpdir):
                if fname.startswith('.'):
                    continue  # skip hidden files

                fpath = join(tmpdir, fname)
                files = [fpath] if self.postcollect_args else []
                cmd = PostCollectFiles(
                    tmpdir, files, self.postcollect_cmds, self.path,
                )
                excs = cmd.run(env)
                if excs:
                    errors += excs

                    os.makedirs(join(destdir, 'errors'), exist_ok=True)
                    move(fpath, join(destdir, 'errors', fname))
                    error_files.append(fname)
                else:
                    move(fpath, join(destdir, fname))
                    success_files.append(fname)

            if self.ack_cmd:
                env = self.init_env(env, destdir)
                env['TMPDIR'] = tmpdir
                env['SUCCESS_FILES'] = ';'.join(success_files)
                env['ERROR_FILES'] = ';'.join(error_files)
                _call(env, self.ack_cmd)

        return errors


class PostCollectFiles(Command):
    def __init__(self, directory, files, postcollect_cmds, path):
        super().__init__(postcollect_cmds, path)
        self.directory = directory
        self.files = files

    def run(self, env):
        return self.execute(self.directory, env, *self.files)


def _call(env, base_cmd, files=()):
    errors = []

    try:
        cmd = [arg.format(**env) for arg in shlex.split(base_cmd)]

    except KeyError as exc:
        LOGGER.error(
            'Command %r is using an unknown environment variable, available '
            'are %s', base_cmd, ', '.join(sorted(env)),
        )
        errors.append(exc)

    else:
        cmd += files
        try:
            subprocess.check_call(cmd, env=env)
        except (IOError, subprocess.CalledProcessError) as exc:
            LOGGER.error('Error running %s: %s', base_cmd, exc)
            errors.append(exc)
        except BaseException as exc:  # pragma: no cover
            LOGGER.exception('Error running %s: %s', base_cmd, exc)
            errors.append(exc)

    return errors


def _execute(max_workers, commands, *args):
    errors = []
    with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_cmds = {executor.submit(command.run, *args): command
                       for command in commands}

        try:
            for future in futures.as_completed(future_cmds):
                command = future_cmds[future]
                try:
                    errors += future.result()
                except Exception as exc:  # pragma: nocover
                    LOGGER.exception(
                        '%r generated an exception: %s', command, exc)
        except KeyboardInterrupt:  # pragma: nocover
            executor._threads.clear()
            futures.thread._threads_queues.clear()
            raise

    return errors


def _cli_parser():
    import argparse

    parser = argparse.ArgumentParser(prog='lowatt-collect',
                                     description='Collect data from sources.')
    parser._positionals.title = ('available commands (type "<command> '
                                 '--help" for help about a command)')

    parser.add_argument(
        '-W', '--max-workers', type=int, default=4,
        help='Number of parallel [post]collect jobs.')
    parser.add_argument(
        '-L', '--log-level', default=os.environ.get('LOG_LEVEL', 'INFO'),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set log level, default to INFO.')

    subparsers = parser.add_subparsers(
        dest='command')
    cparser = subparsers.add_parser(
        'collect',
        help='Collect sources and run postcollect on each downloaded file, '
        'as specified in the sources configuration file.',
    )
    pcparser = subparsers.add_parser(
        'postcollect',
        help='Run postcollect on previously collected files.',
    )

    for subparser in [cparser, pcparser]:
        subparser.add_argument(
            'source_file', nargs=1,
            help='YAML sources definition file.')

    cparser.add_argument(
        'sources', nargs='*',
        help='Sources that should be collected. If not specified, '
        'all sources specified in the configuration file will be considered.')
    cparser.add_argument(
        'extra', nargs=argparse.REMAINDER, metavar='collect command options',
        help='Any extra options, plus their following positional arguments, '
        'will be given to collect commands.')
    group = cparser.add_mutually_exclusive_group()
    group.add_argument(
        '--no-postcollect', action='store_false', default=True,
        dest='call_postcollect',
        help='Do not run postcollect commands after collect.')
    for subparser in (group, pcparser):
        subparser.add_argument(
            '--no-postcollect-args', action='store_false', default=True,
            dest='postcollect_args',
            help='Do not give collected files to postcollect commands.')

    pcparser.add_argument(
        'files', nargs='*',
        help='Files on which postcollect should be executed. If not specified, '
        'the whole hierarchy under "root" directory (specified in the '
        'configuration file) will be considered. Else specified files must be '
        'under the root directory.')

    return parser


def run():
    try:
        _run()
    except KeyboardInterrupt:  # pragma: nocover
        sys.exit(1)


def _run():
    import yaml

    parser = _cli_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    LOGGER.setLevel(args.log_level)
    LOGGER.propagate = False
    LOGGER.addHandler(logging.StreamHandler(stream=sys.stdout))

    try:
        with open(args.source_file[0]) as stream:
            config = yaml.load(stream, yaml.FullLoader)
    except Exception as exc:
        LOGGER.error('An error occured while reading sources file:\n  %s', exc)
        sys.exit(1)

    env = build_env(config, args.source_file[0], args.log_level)
    root = env['ROOT']

    if args.command == 'collect':
        if args.sources:
            sources = {}
            for source in args.sources:
                if source.startswith(root):
                    source = os.path.relpath(source, root)
                basedict = config['sources']
                for key in source.split(os.path.sep):
                    try:
                        basedict = basedict[key]
                    except KeyError:
                        parser.error('unexisting source {}'.format(source))

                sources[source] = basedict
        else:
            sources = config['sources']
        errors = collect(
            sources, root, env,
            collect_options=args.extra,
            call_postcollect=args.call_postcollect,
            postcollect_args=args.postcollect_args,
            max_workers=args.max_workers,
        )

    elif args.command == 'postcollect':
        errors = postcollect(
            root, config['sources'], env, files=args.files,
            postcollect_args=args.postcollect_args,
            max_workers=args.max_workers,
        )

    sys.exit(2 if errors else 0)


if __name__ == '__main__':  # pragma: nocover
    run()
