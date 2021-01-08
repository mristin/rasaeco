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

Render once
~~~~~~~~~~~
Render the scenarios in-place once:

.. code-block::

    pyrasaeco-render.exe once --scenarios_dir c:\some\path\to\scenarios

(Change ``c:\some\path\to\scenarios`` to fit your system.)

Open the scenario ontology with your browser from:
``c:\some\path\to\scenarios\ontology.html``.

(Don't forget to change ``c:\some\path\to\scenarios`` again to fit 
your system.)

Render continuously
~~~~~~~~~~~~~~~~~~~
Monitor the scenario files and re-render on changes:

.. code-block::

    pyrasaeco-render.exe continuously --scenarios_dir c:\some\path\to\scenarios

(Change ``c:\some\path\to\scenarios`` to fit your system.)

Open the scenario ontology with your browser from:
``c:\some\path\to\scenarios\ontology.html``.

(Don't forget to change ``c:\some\path\to\scenarios`` again to fit 
your system.)


Render continuously + automatic refresh
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`pyrasaeco-render` can also start a demo server for you so that you do not have
to manually re-load in the browser. You have to specify the port and the server
will be automatically started:

.. code-block::

    pyrasaeco-render.exe continuously
        --scenarios_dir c:\some\path\to\scenarios
        --port 8000

(Change ``c:\some\path\to\scenarios`` to fit your system.)

The ontology will be available on: ``http://localhost:8000``.

Help
~~~~
.. code-block::

    pyrasaeco-render.exe -h
    pyrasaeco-render.exe once -h
    pyrasaeco-render.exe continuously -h

Cheatsheet
----------

Directory Structure
~~~~~~~~~~~~~~~~~~~
Write documents in the following directory structure:

.. code-block::

    ontology/
        some-scenario/
            scenario.md
        some-group/
            another-scenario/
                scenario.md
            yet-another-scenario/
                scenario.md
    ...

The identifier of a scenarios is given by the POSIX path of the scenario directory relative to
the ontology directory.

For example, ``some-scenario`` and ``some-group/another-scenario``.

Header
~~~~~~
Write a ``<rasaeco-meta>`` header at the beginning of a scenario.

Here is an example:

.. code-block::

    <rasaeco-meta>
    {
        "title": "Some Scenario",
        "contact": "Marko Ristin <rist@zhaw.ch>, Somebody Else <somebody@else.ch>",
        "relations": [
            { "target": "some-group/another_scenario", "nature": "is instance of" }
            { "target": "some-group/yet_another_scenario", "nature": "refines" }
        ],
        "volumetric": [
            {
                "aspect_from": "as-planned", "aspect_to": "safety",
                "phase_from": "construction", "phase_to": "construction",
                "level_from": "site", "level_to": "site"
            }
        ]
    }
    </rasaeco-meta>

+-------------------+--------------------+---------------+
| Aspects           | Phases             | Levels        |
+-------------------+--------------------+---------------+
| * ``as-planned``  | * ``planning``     | * ``device``  |
| * ``as-observed`` | * ``construction`` | * ``machine`` |
| * ``divergence``  | * ``operation``    | * ``unit``    |
| * ``scheduling``  | * ``renovation``   | * ``site``    |
| * ``cost``        | * ``demolition``   | * ``company`` |
| * ``safety``      |                    | * ``network`` |
| * ``analytics``   |                    |               |
+-------------------+--------------------+---------------+

Tags in the Scenario
~~~~~~~~~~~~~~~~~~~~
Tag text in markdown with XML tags.

**Models**.
Models are defined as ``<model name="...">...</model>``.

**Definitions**.
Definitions are defined ``<def name="...">...</def>``.

If you want to write (pseudo)code in the definition, use ``````` (three backticks):

.. code-block::

    <def name="reception_platforms">

    ```bim
    reception_platform_label = IfcLabel("ReceptionPlatform")

    reception_platforms =
        SELECT e
        FROM
            e is IfcBuildingElementType modeled in observed/main
        WHERE
            e.ElementType == reception_platform_label
    ```

    </def>


**Model references** are written using ``<modelref>`` tag:

.. code-block::

    The possible placements for the reception platform should be computed based on
    the <modelref name="observed/main" />.

It is also possible to reference models from another scenario by writing the scenario identifier,
followed by ``#`` and the model name:

.. code-block::

    This is a dummy reference to the model <modelref name="scaffolding#plan/main" />.


**Definition references** are written using ``<ref>`` tag:

.. code-block::

    The <ref name="receptionPlatforms" /> can not be appropriately fixed.

It is also possible to reference models from another scenario by writing the scenario identifier,
followed by ``#`` and the definition name:

.. code-block::

    This is a dummy reference to the definition <ref name="scaffolding#scaffolds" />.


**Marking phase and level**. Use ``<phase>`` and ``<level>`` to mark the phase in
the building life cycle and hierarchy level of detail, respectively.

.. code-block::

    <phase name="planning">During the planning phase, the <ref name="scaffolds" />
    are wrongly planed.</phase>

    <phase name="construction">The <ref name="receptionPlatforms" /> can not be appropriately fixed
    on <level name="site">the site</level>.</phase>

Further Examples
~~~~~~~~~~~~~~~~
Please see
`Sample scenarios <https://github.com/mristin/rasaeco/tree/main/sample_scenarios>`_
for further examples.

Known Issues
------------
Markdown can be sometimes unintuitive when mixed with the mark-up (XML) tags. You have to be careful
when inserting new lines as they are going to be automatically converted by
`marko library <https://pypi.org/project/marko/>`_ to ``<p>``.

This can result in invalid HTML. For example, make sure you do not write:

.. code-block::

    <model name="something">first line

    second line</model>

as this results in invalid HTML:

.. code-block::

    <p><model name="something">first line</p>
    <p>second line</model></p>

Note the inverted ``</p>`` and ``</model>``. This should be correctly written as:

.. code-block::

    <model name="something">

    first line

    second line

    </model>

(Note the empty lines after the opening tag and before the closing tag, respectively.)
