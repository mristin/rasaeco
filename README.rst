RASAECO
=======

.. image:: https://travis-ci.com/mristin/rasaeco.svg?branch=master
    :target: https://travis-ci.com/mristin/rasaeco

RASAECO ("Requirements Analysis for Software in AECO Industry") is a tool
we developed within the `BIMprove Project <https://www.bimprove-h2020.eu/>`_ to
help us analyze the software requirements after the finished elicitation phase.

Since the tool is still work-in-progress, we do not document yet how to write
the scenarios. Please consult `sample_scenarios <sample_scenarios>`_ for examples.

Installation
------------
Please download and unzip the latest release from
`the GitHub release page <https://github.com/mristin/rasaeco/releases>`_.

Usage
-----
Start your native Windows command prompt.

(Please be careful not to start "Developer Command Prompt for VS 2019" or similar
as it includes a 32bit version of Python3 in its environment!)

Change to the directory where you unzipped the release.

Render the scenarios in-place:

.. code-block::

    pyrasaeco-render.exe once --scenarios_dir c:\some\path\to\scenarios

Open the scenario ontology with your browser from:
``c:\some\path\to\scenarios\ontology.html``.
