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

2. Automatic rigging route

The advantage of this route is that you get the exact rig used by the game. The game rig gives you realistic range of motion in knees and hips that is very hard to achieve with metarig. You get full armature + vertex weights + bone constraints out of the box.

It would also, in principle, be possible to export poses and animations from the game.

The downside is that you get a fully custom rig. No pretty metarig controls until someone (read: me) implements it. So far I don't even have the head, and there's no IK support.

Launch Studio Neo. Load the character. Hit F1, find Runtime Unity Editor, bind a key to open it.

Put the character in T-pose (unlike route 1, don't bend any limbs.) Hit the key for Runtime Unity Editor. In the "Scene Unity Editor", find Common Space -> ChaF_001 -> BodyTop -> p_cf_anim -> cf_J_Root. (If it is a male character, it'll be ChaM_001.) Select cf_J_Root and hit 'dump'. Save the text file.

Export the objects and the textures as in route 1, but skip the body .obj.

Locate the unbaked mesh for the character. The best process for this step is TBD. For now I've included the standard "sexless" mesh from the game (default_rig_body.fbx) and the uncensored BP Sac.Innie1 mesh. Others can be pulled out of their zipmods with SB3U, instructions can be found elsewhere. (Differences are normally limited to nipples and the groin area.)

Import the FBX into Blender. 

Load convert_armature.py, point the 'dump' variable at the text file you dumped from Runtime Unity Editor, run the script. It will scale the mesh to the exact dimensions of the character, prettify the rig, sort the bones into several layers for ease of use, and add several bone constraints that you need for proper knee and hip function.

Proceed with texturing (the script from step 1 will work for this too in future, but it needs to be adapted first.)


KNOWN ISSUES:

Manual rigging route:

* Male characters aren't textured correctly (need to create separate materials for them)
* Tongue and teeth are inserted into the scene but not textured or properly placed
* Produced characters have no pubic hair

Automatic rigging route:

* Work in progress, many missing features




