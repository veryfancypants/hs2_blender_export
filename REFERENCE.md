==== UI ====

=== Settings ===

* ''Refactor armature'': recompute the armature so that all shape adjustments become parts of the rig (typically, as scales or offsets on non-deform bones). This makes hair and clothing (mostly) interchangeable between characters.

At present, refactoring is likely to fail if the character has a custom head.

On by default; a number of other features assume that refactoring is done, and will either break or be disabled if the setting is unchecked.

* ''Replace teeth'': replace the teeth mesh from the dump with a prefabricated version. 

* ''Extend (safe)'': add enhancements (bones, shape keys, weight repaints) which improve control over shape, but are not expected to change character appearance at their default settings. On by default.

* ''Extend (full)'': add enhancements which _are_ expected to change character appearance. Create a few new bones (cf_J_NoseCheek, cf_J_Nasolabial, cf_J_Nose_Septum, cf_J_Nostril_L) that the user may need to tweak manually; create and turn on several shape keys.  Off by default.

* ''Add an injector'': add a prefabricated injector to the mesh. A choice between 'On', 'Off', and 'Auto'. 'Auto' (default) enables the feature only if the character is male and does not have one already. 
** If this feature is requested for a male character without an existing injector, the newly imported mesh will (hopefully) be attached seamlessly (the corresponding part of the original mesh will be excised and new mesh will be stitched in its place.) Otherwise, the new mesh will be joined to the original mesh and the process will stop there.
** The prefabricated injector will be color-matched to the torso.
** If a prefab injector is added, controls for its dimensions and readiness state will appear in the UI panel.

* ''Add an exhaust'': add a prefabricated exhaust to the mesh. As with the injector, the importer will attempt seamless attachment; if it is successful, it will replace part of the original mesh, otherwise, it will merely join it to the existing mesh. A new 'Exhaust' control will be added to the UI panel: a slider from 0 (closed) to 10 (open to anatomically improbable levels) with the default of 1. 

=== Operations ===

All preset operations work with the JSON file, which is located in C:\Users\<user name>\AppData\Roaming\Blender Foundation\Blender\<version>\scripts\addons\hs2_blender_export-main\assets\hs2blender.json (Windows) or in /home/<user name>/.config/blender/<version>/scripts/addons/hs2_blender_export-main/assets/hs2blender.json (Linux).

* ''Reload presets'':  reload the preset .json, discarding any unsaved additions/deletions and any unsaved character changes (including names, colors, material attributes, shapes).
* ''Save presets'': save the preset .json with all edits
 A backup will be created in the same location.
* ''Delete presets'': delete the currently selected preset. The result 

==== New shape keys ====

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
* ''Jaw soften'' / ''Jaw soften more'': 


=== New bones ===


=== Joint correctives ===

