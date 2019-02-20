------------------
``lowatt_collect``
------------------

.. image:: https://travis-ci.com/lowatt/lowatt_collect.svg?branch=master

**Command line interface to collect distant data and do something about it**

Install and usage
-----------------

::

  $ pip install lowatt_collect

Once your sources file is written (see section below), start collect by running ::

  lowatt-collect collect sources.yml

Our run postcollect on all previously collected files::

  lowatt-collect postcollect sources.yml

or on specified files only::

  lowatt-collect postcollect sources.yml data/sources/*.csv

Type::

  lowatt-collect --help
  lowatt-collect <command> --help

for all available options.


Collect sources definition
--------------------------

This is driven by a 'sources' definition YAML_ file. Each source may either
define sub-sources or have a 'collect' value indicating the command to use to
collect data and/or a 'postcollect' value indicating the command or commands to
start when a new file is collected. Last but not least, a source with a
'poscollect' command may have a 'collectack' value indicating the command to use
to notify postcollect success / failure. This is useful for collect commands
relying on some index file that should be "commited" only if the postcollect
succeed.

A source may only have 'postcollect' defined without any 'collect' in case where
files are put in there by hand or any other way than the above 'collect'
command.

Last but not least, each collect is done within a temporary directory. Collected
files are moved from this directory to the sources hierarchy once fully
collected (e.g. downloaded) and all postcollect treatments occured (e.g. data is
imported in a database). If some error occurs for a file during postcollect,
it's moved in the 'errors' subdirectory of the source directory.

.. _YAML: http://yaml.org/

Below a sample source file:

.. code-block:: yaml

    root: /data/
    environment:
      CONFIG_DIR: /conf

    sources:

      meteofrance:
        collect: "python -m meteofrance -o {DIR}"
        postcollect: "python -m dataimport meteofrance"

      conso:

        bill:
          collect: "python -m conso dl-bill -I {ROOT}/index.json -o {DIR} {CONFIG_DIR}/conso.yml"
          postcollect:
          - "python -m dataimport conso bill"
          - "python -m billimport"
          collectack: "python -m conso dl-bill-ack -I {ROOT}/index.json"

        index:
          collect: "python -m conso dl-index -o {DIR} {CONFIG_DIR}/conso.yml"
          postcollect: "python -m dataimport conso index"

      be:
        collect:
        postcollect: "python -m dataimport be"


Sources hierarchy will be mirrored under the directory specified as `root` value. The
above example would be mapped to:

.. code-block:: text

  /data
    /be
      <files put there by hand and importable by des.suez.read_xls_stream>
    /meteofrance
      <files collected from meteofrance and importable by des.mf.read_csv_stream>
    /conso
      /bill
        <files collected from tsme and importable by des.suez.read_pdf_stream>
      /index
        <files collected from tsme and importable by des.suez.read_xls_stream>



Commands are not shell command, yet you may expand environment variables using
brackets "{ENV_VAR}". Since command are splitted to be given to `exec`,
environment variables are the way to go to insert argument values containing
spaces::

    environment:
      CONFIG_DIR: /conf/directory with spaces/

    sources
      meteofrance:
        collect: "python -m meteofrance -c {CONFIG_DIR}"

When run after `collect`, `postcollect` commands will be called for each
collected file, with its path as argument.

When run standalone, each `postcollect` command for a source will be called
once, either with all files specified as argument or with all files found in the
source directory.

Available environment variables are:

* those inherited from the process that launched the collect or postcollect

* those defined in the 'environment' section of the configuration file

* `SOURCE`: root source key from which the command is coming

* `COLLECTOR`: path from root to the collector joined by '.' - same as `SOURCE`
  if the collector is defined at the first level in the hierarchy

* `ROOT`: path to the root directory

* `DIR`: source directory - this may not be the actual directory under `ROOT`
  but a temporary directory, as collect happen within a temporary directory
  whose content is moved once collect and postcollect are done

* `LOG_LEVEL`: the log level name received as argument ('DEBUG', 'INFO',
  'WARNING' or 'ERROR')

'collectack' command has access to the following extra environment variables:

* `TMPDIR`: the temporary source directory that has been used to collect files
  before their processing, though they have been moved to their source directory
  when the command is called

* `ERROR_FILES`: collected files which have encountered an error during
  postcollect

* `SUCCESS_FILES`: collected files which have been successfully postcollected


Additional informations
-----------------------

This program is distributed under the terms of the GNU Public License v3 or later.

Comments and patches are welcome, see https://github.com/lowatt/lowatt_collect.
