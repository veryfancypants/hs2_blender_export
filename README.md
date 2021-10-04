This is a set of scripts and templates for exporting HS2/AI characters into Blender.

At present, there are two possible routes, with different pros and cons.

1. Manual rigging route

Launch Studio Neo. Load the character you wish to export. Hit F1, find Material Editor, set a checkbox that says "export baked meshes" (or some such). Put the character in T-pose (it may be advisable to bend the knees and elbows slightly, but make sure to keep the character exactly symmetrical - use "Copy Left Arm", etc. in HS2PE.) 

Open Material Editor. Export all textures and all .obj files you see. Make sure to put all textures and objects for one character in the same folder and not to mix them with other characters.

Open prefab_materials.blend. In the scripting tab, open apply_textures.py, edit the path on line 11 to point at the place where objects were saved.

Optionally, edit the 'suffix' variable on line 12. It will be appended to names of materials the script creates for this character.

Run the script. It will create a complete textured and patched-up mesh for the body, plus separate meshes for eyes, eyebrows, etc.

Go through the materials and tweak the settings. In particular, adjust eye/eyebrow/eyelash/nipple colors (all these are set to default values), bump map and gloss settings on both torso and head, and nail colors.

Scale the character down to human size (scale factor 0.12 or so) and then move on to rigging the character any way you want (e.g. with metarig).

2. Automatic rigging route (WORK IN PROGRESS)

The advantage of this route is that you get the exact rig used by the game. The game rig gives you realistic range of motion in knees and hips that is very hard to achieve with metarig. You get full armature + vertex weights + bone constraints out of the box.

It would also, in principle, be possible to export poses and animations from the game.

In addition, you get hair, clothes, and accessories (though as far as how accurate they will be, YMMV.)

The downside is that you get a fully custom rig. No pretty metarig controls until someone (read: me) implements it. So there are no controls, no IK support, and only the lower body has been reviewed.

Install Grey's MeshExporter. (It comes as 'optional' with HS2 BetterRepack.)

Launch Studio Neo. Load the character. Hit F1, find Runtime Unity Editor, bind a key to open it.

Put the character in T-pose (unlike route 1, don't bend any limbs.) Hit the key for Runtime Unity Editor. In the "Scene Unity Editor", find Common Space -> ChaF_001 -> BodyTop -> p_cf_anim -> cf_J_Root. (If it is a male character, it'll be ChaM_001.) Select cf_J_Root and hit 'dump'. Save the text file.

Use MeshExporter to export everything. Do ask for converted bump maps. Don't ask to pack png's into the fbx. 

Open prefab_materials_meshexporter.blend in Blender. 

Load meshexporter.py. Point the 'dump' variable at the text file you dumped from Runtime Unity Editor. Point 'fbx' and 'path' variables at the MeshExporter dump. Run the script. 

It will clean up the scene, set up the materials, prettify the rig, sort the bones into several layers for ease of use, and add several bone constraints that you need for proper knee and hip function.

Tweak the texture settings as in route 1.


KNOWN ISSUES:

Manual rigging route:

* Male characters aren't textured correctly (need to create separate materials for them)
* Tongue and teeth are inserted into the scene but not textured or properly placed
* Produced characters have no pubic hair
* No support of characters with custom meshes 

Automatic rigging route:

* Work in progress, many missing features
* Bump mapping is disabled because MeshExplorer messes with gamma in bump maps, making them unusable without some postprocessing, and I need to sort out the kind of postprocessing needed
* No support of male characters 
* All of the issues of the manual route


