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

.. _YAML: http://yaml.org/

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


Additional informations
-----------------------

This program is distributed under the terms of the GNU Public License v3 or later.

Comments and patches are welcome, see https://github.com/lowatt/lowatt_collect.
