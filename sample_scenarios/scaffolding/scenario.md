<rasaeco-meta>
{
    "title": "Scaffolding",
    "contact": "Marko Ristin <rist@zhaw.ch>, Somebody Else <somebody@else.ch>",
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

<model name="plan/main">

This is the main model of the site plan covering the whole site.
It is updated on demand, as the plan changes.

</model>

<model name="observed/main">

This is the main model representing the digital twin of the building.
It is updated daily.

</model>

<model name="staff">

This is the model capturing the information about the site personnel.
It is updated in real time.

</model>

## Definitions

<def name="scaffold">

```bim
scaffold 
    is IfcBuildingElementType modeled in plan/main
    with .ElementType == "Scaffold"
```

</def>

<def name="reception_platform">

```bim
reception_platform 
    is IfcBuildingElementType modeled in observed/main
    with .ElementType == "ReceptionPlatform"
```

</def>

<def name="misplaced_scaffold">

The scaffold with incorrectly planned height:

```bim
misplaced_scaffold 
    is a scaffold
    associated with the reception_platform rp
    where 
        abs(misplaced_scaffold.NominalHeight - rp.NominalHeight) < 1 meter 
```

</def>

<def name="worker">

```bin
worker
    is IfcActor modeled in staff
    with .Category == "Worker"
```

</def>


## Scenario

### As-planned

The <ref name="scaffold" />s are expected to be tracked in 
the model <modelref name="plan/main" />. The plan should include the position 
and the height of the scaffolds.  

### As-observed

The possible placements for the reception platform should be computed based on
the <modelref name="observed/main" />.

### Divergence

<phase name="planning">
    During the planning phase, the <ref name="scaffold" />s are wrongly planed.
</phase>
<phase name="construction">
    The <ref name="reception_platform" />s can not be appropriately fixed 
    on <level name="site">the site</level>.
</phase>

### Analytics

The <ref name="misplaced_scaffold" />s should be reported on the web platform.

### Scheduling

All the tasks affected by the <ref name="misplaced_scaffold" />s should be set 
to blocking.

Formally:

```bim
tt = 
    SELECT t 
    FROM
        s is a misplaced_scaffold
        t is an IfcTask modeled in plan/main
    WHERE
        Affected(t, s)

UPDATE
    t.Status = "blocked"
FROM
    t in tt
```

### Safety

No <ref name="worker" /> is allowed to make changes to 
the <ref name="misplaced_scaffold" />s:

```bim
FROM
    w is a worker
    s is a misplaced_scaffold
MUST
    not CanModify(w, s)
```

<level name="site">We consider only the scaffolding on a single construction 
site.</level>
