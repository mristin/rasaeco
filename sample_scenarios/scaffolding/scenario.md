<rasaeco-meta>
{
    "identifier": "scaffolding",
    "title": "Scaffolding",
    "relations": [
        { "target": "z_dummy_scenario", "nature": "is instance of" }
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

## Summary

A wrong planification of scaffolding. Wrong height prevents the proper fixing of
the reception platform. Workers not authorized to make any changes.

## Models

### plan/main

This is the main model of the site plan covering the whole site.
It is updated on demand, as the plan changes.

### observed/main

This is the main model representing the digital twin of the building.
It is updated daily.

### staff

This is the model capturing the information about the site personnel.
It is updated in real time.

## Definitions

### scaffolds

```bim
scaffoldLabel = IfcLabel("Scaffold")

scaffolds = 
    SELECT e
    FROM
        e is IfcBuildingElementType modeled in plan/main
    WHERE 
        e.ElementType == scaffoldLabel
```

### receptionPlatforms

```bim
receptionPlatformLabel = IfcLabel("ReceptionPlatform")

receptionPlatforms = 
    SELECT e
    FROM
        e is IfcBuildingElementType modeled in observed/main
    WHERE
        e.ElementType == receptionPlatformLabel
```

### misplacedScaffolds

The scaffolds with incorrectly planned height:

```bim
misplacedScaffolds = 
    SELECT s
    FROM
        rp in receptionPlatforms
        s in scaffolds
    WHERE
        abs(s.NominalHeight - rp.NominalHeight) < 1 meter 
```

### workers

```bin
workerLabel = IfcLabel("Worker")

workers = 
    SELECT a
    FROM
        a is IfcActor in staff
    WHERE
        a.Category == workerLabel
```


## Scenario

### As-planned

The <ref name="scaffolds" /> are expected to be tracked in 
the model <modelref name="plan/main" />. The plan should include the position 
and the height of the scaffolds.  

### As-observed

The possible placements for the reception platform should be computed based on
the <modelref name="observed/main" />.

### Divergence

<phase name="planning">
    During the planning phase, the <ref name="scaffolds" /> are wrongly planed.
</phase>
<phase name="construction">
    The <ref name="receptionPlatforms" /> can not be appropriately fixed 
    on <level name="site">the site</level>.
</phase>

### Analytics

The <ref name="misplacedScaffolds" /> should be reported on the web platform.

### Scheduling

All the tasks affected by the <ref name="misplacedScaffolds" /> should be set 
to blocking.

Formally:

```bim
tt = SELECT t 
    FROM
        s in misplacedScaffolds
        t in IfcTask modeled in plan/main
    WHERE
        Affected(t, s)

blockedLabel = IfcLabel("blocked")

UPDATE
    t.Status = blockedLabel
FROM
    t in tt
```

### Safety

No <ref name="workers">worker</ref> is allowed to make changes to 
the <ref name="misplacedScaffolds" />:

```bim
FROM
    w in workers
    s in misplacedScaffolds
MUST
    not CanModify(w, s)
```

<level name="site">We consider only the scaffolding on a single construction 
site.</level>
