## UI 

### Settings

* ''Refactor armature'': recompute the armature so that all shape adjustments become parts of the rig (typically, as scales or offsets on non-deform bones). This makes hair and clothing (mostly) interchangeable between characters.

On by default; a number of other features assume that refactoring is done, and will either break or be disabled if the setting is unchecked.

* ''Replace teeth'': replace the teeth mesh from the dump with a prefabricated version. 

* ''Extend (safe)'': add enhancements (bones, shape keys, weight repaints) which improve control over shape, but are not expected to change character appearance at their default settings. On by default.

* ''Extend (full)'': add enhancements which _are_ expected to change character appearance. Create a few new facial bones that the user may need to tweak manually; create and turn on several shape keys.  Off by default.

* ''Add an injector'': add a prefabricated injector to the mesh. A choice between 'On', 'Off', and 'Auto'. 'Auto' (default) enables the feature only if the character is male and does not have one already. 
** If this feature is requested for a male character without an existing injector, the newly imported mesh will (hopefully) be attached seamlessly (the corresponding part of the original mesh will be excised and new mesh will be stitched in its place.) Otherwise, the new mesh will be joined to the original mesh and the process will stop there.
** The prefabricated injector will be color-matched to the torso.
** If a prefab injector is added, controls for its dimensions and readiness state will appear in the UI panel.

* ''Add an exhaust'': add a prefabricated exhaust to the mesh. As with the injector, the importer will attempt seamless attachment; if it is successful, it will replace part of the original mesh, otherwise, it will merely join it to the existing mesh. A new 'Exhaust' control will be added to the UI panel: a slider from 0 (closed) to 10 (open to anatomically improbable levels) with the default of 1. 

### Operations

All preset operations work with the JSON file, which is located in C:\Users\<user name>\AppData\Roaming\Blender Foundation\Blender\<version>\scripts\addons\hs2_blender_export-main\assets\hs2blender.json (Windows) or in /home/<user name>/.config/blender/<version>/scripts/addons/hs2_blender_export-main/assets/hs2blender.json (Linux).

* ''Reload presets'':  reload the preset .json, discarding any unsaved additions/deletions and any unsaved character changes (including names, colors, material attributes, shapes).
* ''Save presets'': save the preset .json with all edits
 A backup will be created in the same location.
* ''Delete presets'': delete the currently selected preset. The result 

## Rig features

### New shape keys

All these assume a standard head; on a custom head, they may be missing or broken.

Emotion control:

* ''better_smile'': a smile shape key, an alternative to the standard 'k02_warai2'. Pull lip corners toward ears, bulge cheeks, and crease nasolabial folds. 

Shape control:

* ''Nostril pinch'': sharper defined nose
* ''Eye shape'': an attempt to make eyelid edges sharper and more realistic
* ''Eyelid crease'': creases along upper eyelids
* ''Upper lip trough'': pushes the skin between the upper lip and the nose back (toward the skull), creating an U-shaped trough
* ''Lip arch'': pushes centers of both lips upwards and slightly back
* ''Temple depress'': creates depressions on both sides of the skull just above and behind the eyes
* ''Forehead flatten'': pushes sides of the forehead forward 
* ''Jaw soften'' / ''Jaw soften more'': rounds the edge of the lower jaw

### Bone classifications

The rig contains several hundred bones. Internally, each bone is assigned a seven-character 'bone class' (see the long table in armature.py) which describes roles played by its offset, rotation, and scale. This is needed in order to determine which parameters are part of the pose, which are part of the shape, and which should not be touched. A few general principles apply:
* Most bones with '_s' in their names are 'soft' (part of the shape). 
* For symmetric soft bones, only bones on one side ("_L") should be manipulated directly; corresponding bones on the other side have copy location / rotation / scale constraints.
* A few bones have both a shape role and a pose role. E.g, in cf_J_LegUp00_L, rotation is part of the pose (hip joint), and offset and scale are parts of the shape. 
* Bones with '_dam' in their names generally have something to do with joint correctives (see below). 
* Many parameters are either locked or constrained.

### New bones

When "Extend (safe)" is checked, the importer creates the following bones:

* cf_J_ChinFront_s: child of cf_J_Chin_rs
* cf_J_FaceUpFront_ty: child of cf_J_FaceUp_ty
* cf_J_FaceRoot_r_s: child of cf_J_FaceRoot_s
* cf_J_CheekMid_L: child of cf_J_CheekUp_L
* cf_J_CheekMid_R: child of cf_J_CheekMid_R
* cf_J_NeckFront_s: child of cf_J_Neck_s
* cf_J_NeckUp_s: child of cf_J_Neck_s
* cf_J_Spine01_r_s: child of cf_J_Spine01_s
* cf_J_Spine02_r_s: child of cf_J_Spine02_s
* cf_J_Spine03_r_s: child of cf_J_Spine03_s

In all these cases, the vertex group of the parent bone is split along a certain direction (e.g., when cf_J_Spine01_s is split, vertexes in front of the body stay in cf_J_Spine01_s, vertexes in the back are reassigned to cf_J_Spine01_r_s, and vertexes in between are in both vgroups). The effect is that, as long as the new bone is left in its default state, the combined effect of deforms is identical to what it would be without splitting.

* cf_J_LowerJaw, child of cf_J_MouthCavity.

Vertexes in the lower jaw of the tooth mesh are placed in the cf_J_LowerJaw vertex group. 

It also creates:

* cf_J_Nose_t_s: child of cf_J_Nose_t
* cf_J_FaceLow_s_s: child of cf_J_FaceLow_s
* cf_J_MouthBase_s_s: child of cf_J_MouthBase_s

and renames corresponding vertex groups on the mesh. This is done because cf_J_FaceLow_s, etc. have dual roles: they are simultaneously parent bones and deform bones. E.g. rescaling cf_J_FaceLow_s directly moves vertexes in its vertex group, but it also scales and moves all bones parented to cf_J_FaceLow_s (cf_J_CheekUp_L, cf_J_ChinLow, etc. etc.) The change separates these two roles. As above, as long as cf_J_FaceLow_s_s is in its default state, the rig behaves as if nothing was changed.

Finally, it creates 

* cf_J_LegUp01_dam_<L,R>
* cf_J_LegUp02_dam_<L,R>
* cf_J_LegLow01_dam_<L,R>
* cf_J_LegLow02_dam_<L,R>

and the same bones on the other side. Each of these is inserted in the chain between the corresponding soft bone (e.g. cf_J_LegUp01_s_L for cf_J_LegUp01_dam_L) and its parent. These are used as joint correctives.

When "Extend (full)" is checked, and if the mesh does not have a custom head, it creates:

* cf_J_Nasolabial_s: child of cf_J_FaceBase
* cf_J_NoseCheek_s: child of cf_J_NoseBase_s
* cf_J_Nostril_L, cf_J_Nostril_R, cf_J_Nose_Septum: children of cf_J_Nose_t

When 'Add an exhaust' is checked, it creates:
* cf_J_ExhaustValve, cf_J_ExhaustClench, cf_J_Exhaust: children of cf_J_Ana

### Joint correctives

Joint correctives are used to improve / correct behavior of joints when simple armature deform is insufficient for the job. 

There are ~15 correctives per side in-game (6 for the hip joint, 2 for the knee, 2 for the shoulder, 2 for the elbow, and 3 for the wrist). In this project, they are reproduced as copy constraints or drivers from primary joint FK bones (e.g. cf_J_LegUp00_L - left hip) to specialized "helper" bones. 

With "Extend (safe)" checked, the importer adds a few others, to improve behavior of thighs, calves and elbows at large bend angles.
