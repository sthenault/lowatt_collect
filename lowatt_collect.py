"""
``lowatt_collect``
------------------

**Command line interface and misc tools to collect distant data and do something
about it**

This is driven by a 'sources' definition YAML_ file. Each source may either
define sub-sources or have a 'collect' value indicating the shell command to use
to collect data and/or a 'postcollect' value indicating the shell command to
start when a new file is collected.

One source may only have 'postcollect' defined without any 'collect' in case
where files are put in there by hand.

Last but not least, each collect is done within a temporary directory. Collected
files are moved from this directory to the sources hierarchy once fully
collected (e.g. downloaded) and all postcollect treatments occured (e.g. data is
imported in a database). If some error occurs during postcollect, it's moved in
the 'errors' subdirectory of the source directory.

Below a sample source file:

.. code-block:: yaml

    root: /data/
    environment:
      CONFIG_DIR: /conf

    sources:

      meteofrance:
        collect: "python -m des.mf -o $DIR"
        postcollect: "python -m des.dataimport des.mf.read_csv_stream $FILE"

      tsme:

        bill:
          collect: "python -m des.suez dl-bill -I $ROOT/index_tsme.json -o $DIR $CONFIG_DIR//tsme.yml"
          postcollect: "python -m des.dataimport des.suez.read_pdf_stream $FILE"

        index:
          collect: "python -m des.suez dl-index -o $DIR $CONFIG_DIR//tsme.yml"
          postcollect: "python -m des.dataimport des.suez.read_xls_stream $FILE"

      des-conseil:
        collect:
        postcollect: "python -m des.dataimport des.scripts.read_xls_stream $FILE"


Sources hierarchy will be mirrored under the directory specified as 'root' value. The
above example would be mapped to:

.. code-block:: text

  /data
    /des-conseil
      <files put there by hand and importable by des.suez.read_xls_stream>
    /meteofrance
      <files collected from meteofrance and importable by des.mf.read_csv_stream>
    /tsme
      /bill
        <files collected from tsme and importable by des.suez.read_pdf_stream>
      /index
        <files collected from tsme and importable by des.suez.read_xls_stream>


Each 'collect' and 'postcollect' shell command may use environment
variables. Environment variables available are:

* those inherited from the process that launched the collect

* those defined in the 'environment' section of the configuration file

* 'SOURCE': root source key from which the command is coming

* 'COLLECTOR': path from root to the collector joined by '.' - same as 'SOURCE'
  if the collector is defined at the first level in the hierarchy

* 'ROOT': path to the root directory

* 'FILE': path to the file to treat (**postcollect only**)

* 'DIR': source directory - this may not be the actual directory under 'ROOT'
  but a temporary directory, as collect happen within a temporary directory
  whose content is moved once collect and postcollect are done

* 'LOG_LEVEL' = the log level name received as argument ('DEBUG', 'INFO',
  'WARNING' or 'ERROR')

.. autofunction:: collect
.. autofunction:: postcollect
.. autofunction:: collect_commands
.. autofunction:: postcollect_commands
.. autofunction:: files_postcollect_commands
.. autofunction:: source_defs
"""  # noqa

from abc import ABC, abstractmethod
from concurrent import futures
import logging
import os
from os.path import abspath, basename, dirname, isdir, join
from shutil import move
import subprocess
import sys
from tempfile import TemporaryDirectory


LOGGER = logging.getLogger('lowatt.collect')


def collect(sources, root_directory, env, max_workers=4):
    """Start collection of data from 'sources' dictionary, using 'env' environment
    variables. Fully collected files are put in the corresponding source
    directory under `root_directory`, or in a 'errors' subdirectory if some
    error occured during postcollect.

    One may specify the maximum number of parallel collects using `max_workers`.
    """
    return _execute(max_workers, collect_commands(sources), root_directory, env)


def collect_commands(sources, _path=None):
    """Generator of "CollectSource" instances given `sources` configuration as a
    dictionary.
    """
    for source_def, _path in source_defs(sources):
        collect = source_def.get('collect')
        if collect:
            yield CollectSource(collect, source_def['postcollect'],
                                _path[:])


def postcollect(root_directory, sources, env, files=None, max_workers=4):
    """Run postcollect on previously collected files.

    If files is specified, only import given files provided some matching source
    is found, else attempt to run postcollect on every files within
    `root_directory`.

    One may specify the maximum number of parallel collects using `max_workers`.
    """
    if files:
        commands = files_postcollect_commands(files, sources, root_directory)
    else:
        commands = postcollect_commands(root_directory, sources)

    return _execute(max_workers, commands, env)


def postcollect_commands(directory, sources, _path=None):
    """Generator of "PostCollectFile" instances for each matching file within
    `directory` considering `sources` definition.
    """
    if _path is None:
        _path = []

    for fname in os.listdir(directory):
        fpath = join(directory, fname)

        if isdir(fpath):
            if fname not in sources:
                if fname != 'errors':
                    LOGGER.error('No source matching %s directory', fpath)
            else:
                _path.append(fname)
                yield from postcollect_commands(fpath, sources[fname], _path)
                _path.pop()

        elif 'postcollect' not in sources:
            LOGGER.error('No postcollect command to handle %s', fpath)

        else:
            yield PostCollectFile(fpath, sources['postcollect'], _path[:])


def files_postcollect_commands(files, sources, root_directory):
    """Generator of "PostCollectFile" instances for given `files`, provided a
    matching source is found in `sources` definition.

    Source is located by looking at file's subdirectory within `root_directory`.
    """
    for fpath in files:
        fpath = abspath(fpath)
        if not fpath.startswith(root_directory):
            LOGGER.error("File %s isn't under root (%s)", fpath, root_directory)
            continue

        path = dirname(fpath).split(root_directory)[1].split(os.sep)
        path = [part for part in path if part]
        file_source = sources
        for part in path:
            try:
                file_source = file_source[part]
            except KeyError:
                LOGGER.error("Can't find source for file %s", fpath)
                break
        else:
            if file_source.get('postcollect'):
                yield PostCollectFile(fpath, file_source['postcollect'], path)
            else:
                LOGGER.error(
                    "Source for file %s has no postcollect command", fpath)


def source_defs(sources, _path=None):
    """Return a generator on `({source definition}, [source path])` from `sources`
    structure as defined in the configuration file.
    """
    if _path is None:
        _path = []

    for source_key, source_def in sources.items():
        _path.append(source_key)

        if 'postcollect' in source_def:
            yield source_def, _path[:]
        else:
            yield from source_defs(source_def, _path)

        _path.pop()


class Command(ABC):

    def __init__(self, cmd, path):
        self.cmd = cmd
        self.path = path

    def __repr__(self):
        return '<{} {}: {}>'.format(
            self.__class__.__name__, '.'.join(self.path), self.cmd)

    def init_env(self, env):
        env = env.copy()
        env['SOURCE'] = self.path[0]
        env['COLLECTOR'] = '.'.join(self.path)
        return env

    @abstractmethod
    def run(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


class CollectSource(Command):

    def __init__(self, collect_cmd, postcollect_cmd, path):
        super().__init__(collect_cmd, path)
        self.postcollect_cmd = postcollect_cmd

    def run(self, root_directory, env):
        destdir = join(root_directory, *self.path)
        os.makedirs(destdir, exist_ok=True)

        errors = []

        with TemporaryDirectory() as tmpdir:
            env = self.init_env(env)
            env['DIR'] = tmpdir

            try:
                subprocess.check_call(self.cmd, env=env, shell=True)
            except subprocess.CalledProcessError as exc:
                LOGGER.error('error running %s: %s', self.cmd, exc)
                errors.append(exc)

            else:
                for fname in os.listdir(tmpdir):
                    fpath = join(tmpdir, fname)

                    cmd = PostCollectFile(fpath, self.postcollect_cmd,
                                          self.path)
                    excs = cmd.run(env)
                    if excs:
                        errors += excs

                        os.makedirs(join(destdir, 'errors'), exist_ok=True)
                        move(fpath, join(destdir, 'errors', fname))

                    else:
                        move(fpath, join(destdir, fname))

        return errors


class PostCollectFile(Command):
    def __init__(self, fpath, postcollect_cmd, path):
        super().__init__(postcollect_cmd, path)
        self.fpath = fpath

    def run(self, env):
        env = self.init_env(env)
        env['DIR'] = dirname(self.fpath)
        env['FILE'] = self.fpath
        try:
            subprocess.check_call(self.cmd, env=env, shell=True)
        except subprocess.CalledProcessError as exc:
            LOGGER.error('error running %s on %s: %s',
                         self.cmd, basename(env['FILE']), exc)
            return [exc]
        except BaseException as exc:  # pragma: no cover
            LOGGER.exception('error while importing %s: %s',
                             env['FILE'], exc)
            return [exc]

        return []


def _execute(max_workers, commands, *args):
    errors = []
    with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_cmds = {executor.submit(command.run, *args): command
                       for command in commands}

        for future in futures.as_completed(future_cmds):
            command = future_cmds[future]
            try:
                errors += future.result()
            except Exception as exc:
                LOGGER.exception('%r generated an exception: %s', command, exc)

    return errors


def _cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
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
        help='Collect sources and run postcollect on each downloaded file.\n\n'
        'Sources and destination are specified through the configuration file '
        ' specified using the DES_CONFIG_FILE environment variable.\n\n'
    )
    pcparser = subparsers.add_parser(
        'postcollect',
        help='Run postcollect on previously collected files.\n\n'
        'Sources are specified through the configuration file specified '
        'using the DES_CONFIG_FILE environment variable.\n\n'
    )

    for subparser in [cparser, pcparser]:
        subparser.add_argument(
            'source_file', nargs=1,
            help='YAML sources definition file.')

    pcparser.add_argument(
        'files', nargs='*',
        help='Files on which postcollect should be executed. If not specified, '
        'the whole hierarchy under "root" directory (specified in the '
        'configuration file) will be considered. Else specified files must be '
        'under the root directory.')

    return parser


def run():
    import yaml

    parser = _cli_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    LOGGER.setLevel(args.log_level)
    LOGGER.propagate = False
    LOGGER.addHandler(logging.StreamHandler(stream=sys.stdout))

    with open(args.source_file) as stream:
            config = yaml.load(stream)

    env = os.environ.copy()
    env['ROOT'] = config['root']
    env['LOG_LEVEL'] = args.log_level
    env.update(config.get('environment', {}))

    if args.command == 'collect':
        errors = collect(config['sources'], config['root'], env,
                         max_workers=args.max_workers)
    elif args.command == 'postcollect':
        errors = postcollect(config['root'], config['sources'], env,
                             files=args.files, max_workers=args.max_workers)

    sys.exit(2 if errors else 0)


if __name__ == '__main__':
    run()
