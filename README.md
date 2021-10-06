This is a set of scripts and templates for exporting HS2/AI characters into Blender.

At present, there are two possible routes, with different pros and cons.

1. Manual rigging route (legacy)

Launch Studio Neo. Load the character you wish to export. Hit F1, find Material Editor, set a checkbox that says "export baked meshes" (or some such). Put the character in T-pose (it may be advisable to bend the knees and elbows slightly, but make sure to keep the character exactly symmetrical - use "Copy Left Arm", etc. in HS2PE.) 

Open Material Editor. Export all textures and all .obj files you see. Make sure to put all textures and objects for one character in the same folder and not to mix them with other characters.

Open prefab_materials.blend. In the scripting tab, open apply_textures.py, edit the path on line 11 to point at the place where objects were saved.

Optionally, edit the 'suffix' variable on line 12. It will be appended to names of materials the script creates for this character.

Run the script. It will create a complete textured and patched-up mesh for the body, plus separate meshes for eyes, eyebrows, etc.

Go through the materials and tweak the settings. In particular, adjust eye/eyebrow/eyelash/nipple colors (all these are set to default values), bump map and gloss settings on both torso and head, and nail colors.

Scale the character down to human size (scale factor 0.12 or so) and then move on to rigging the character any way you want (e.g. with metarig).

2. Automatic rigging route (WORK IN PROGRESS)

The advantage of this route is that you get the exact rig used by the game. The game rig gives you realistic range of motion in knees and hips that is very hard to achieve with metarig. You get full armature + vertex weights + bone constraints + even shape keys (aka blend shapes) out of the box.

It would also, in principle, be possible to export poses and animations from the game.

In addition, you get hair, clothes, and accessories (though as far as how accurate they will be, YMMV.)

The downside is that you get a fully custom rig. No pretty metarig controls until someone (read: me) implements it. So far, there are no controls and no IK support.

Install Grey's MeshExporter. (It comes as 'optional' with HS2 BetterRepack.)

Launch Studio Neo. Load the character. Hit F1, find Runtime Unity Editor, bind a key to open it.

Put the character in T-pose (unlike route 1, don't bend any limbs.) Hit the key for Runtime Unity Editor. In the "Scene Unity Editor", find Common Space -> ChaF_001 -> BodyTop -> p_cf_anim -> cf_J_Root. (If it is a male character, it'll be ChaM_001.) Select cf_J_Root and hit 'dump'. Save the text file.

Use MeshExporter to export everything. Do ask for converted bump maps. Don't ask to pack png's into the fbx. 

Open prefab_materials_meshexporter.blend in Blender. 

Load meshexporter.py. Point the 'dump' variable at the text file you dumped from Runtime Unity Editor. Point 'fbx' and 'path' variables at the MeshExporter dump. If you know the numerical values of your character's hair and eye colors, put them into eye_color and hair_color variables. Run the script. 

It will clean up the scene, set up the materials, prettify the rig, sort the bones into several layers for ease of use, and add several bone constraints that you need for proper knee and hip function.

Tweak the texture settings as in route 1.

Demo: https://www.youtube.com/watch?v=RYYCRgpvDUo

NOTES:

To pose the character, go to "pose mode" on the armature, select layers (primary FK bones are in the top row: left leg is layer 0, right leg is layer 1, etc), then select bones and rotate them with the mouse (click 'r' to go into rotation mode) or directly from the item transform window (top right corner of the 3D view panel).

A few facial features can be controlled this way too, others can't (e.g. can't open the character's mouth with bones at all), the preferred way is to use shape keys. "Body", "object mode", "object data properties" (green triangle in the properties panel), "shape keys" window. E.g., to open the character's mouth, set k09_open1 to 1.0. Most names are in Japanese, auto-translating them is on the todo list. "Warai" - laughing, "Kanasimi" - sad, "ikari" - angry, "fukure" - bulge(?), "damage"  - hurt, "fera" - blow (mouth shape 13), "sitadasi" - sticking the tongue out, "ahe" - cough(?), "tehepero" - sticking the tongue out at an angle. You also get 'k18_a', 'k19_i', etc, that you can use to simulate speech. E.g. "thank you" is
frame 0 - k18_a=0, k20_u=0
frame 10 - k18_a=1, k20_u=0
frame 20 - k18_a=0, k20_u=1
frame 30 - k18_a=0, k20_u=0

For more complex facial emotions, you need to use multiple shape keys on multiple objects. E.g., for a proper "hurt", you need:
e05_damage, g07_damage, k06_damage on 'body'
e05_damage on 'o_eyelashes'
g07_damage on 'o_forehead'

Alternately, you could join all secondary meshes to the body and then only set the shape keys on the body (though you may still need to set some of them multiple times.)

Gaze direction is set with cf_J_look_L, cf_J_look_R.

If you experience eyebrows or nipples partially/completely disappearing from view, nudge them forward (toward the front of the body) slightly. They start off right on top of the body mesh, but may need to be offset slightly to avoid visibility issues. (But you don't want to move them _too_ far, or your character's nipples will be visibly hanging in midair, detached from the breast.)



KNOWN ISSUES:

Manual rigging route:

* Male characters aren't textured correctly.
* Tongue and teeth are inserted into the scene but not textured or properly placed.
* Produced characters have no pubic hair.
* No support of characters with custom meshes; in particular, will fail to assemble correctly if it finds the head mesh in more (or fewer) than 3 discrete pieces (head, mouth cavity, forehead).

Automatic rigging route:

* Upper body bone constraints have not been fully set up yet.
* It will have a shot at automatic texturing of clothing and hair, but the result is going to be very crude.
* All of the issues of the manual route.
* It will correctly detect and try to reconstruct male characters, but may have major difficulties. For now, to export males, you must turn off their genitals (if you don't, due to a bug in MeshExporter, the genitals texture will overwrite the main body texture).
Since "native" male characters' genitals have serious shortcomings (starting with being permanently erect, absurdly large even at the low end of the slider, and lacking foreskin), you're better off without them anyway. I'll be looking into automatically sewing on some properly resized and deflated equipment out of Hooh's scripted dicks mod as part of importing male chars.
* Possibly many other bugs I haven't discovered yet.


