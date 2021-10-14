This is a set of scripts and templates for exporting HS2/AI characters into Blender.

These scripts give you the exact rig used by the game, with realistic range of motion in knees and hips that is very hard to achieve with metarig. You get full armature + vertex weights + bone constraints + even shape keys (aka blend shapes) out of the box. In addition, you get hair, clothes, and accessories (though as far as how accurate they will be, YMMV.)

The downside is that you get a fully custom rig. No pretty metarig controls until someone (read: me) implements it. Also, there's no IK support yet.

STEP BY STEP INSTRUCTIONS

Install Grey's MeshExporter. (It comes as 'optional' with HS2 BetterRepack.)

Launch Studio Neo. Load the character. Hit F1, find Runtime Unity Editor, bind a key to open it.

Put the character in T-pose. Hit the key for Runtime Unity Editor. In the "Scene Unity Editor", find Common Space -> ChaF_001 -> BodyTop -> p_cf_anim -> cf_J_Root. (If it is a male character, it'll be ChaM_001.) Select cf_J_Root and hit 'dump'. Save the text file.

Use MeshExporter to export everything. Do ask for converted bump maps. Don't ask to pack png's into the fbx. 

Open prefab_materials_meshexporter.blend in Blender. 

Load meshexporter.py. Point the 'dump' variable at the text file you dumped from Runtime Unity Editor. Point 'fbx' and 'path' variables at the MeshExporter dump. If you know the numerical values of your character's hair and eye colors, put them into eye_color and hair_color variables. Run the script. 

Wait for it to complete (it may take a while.)

Go through the materials and adjust the settings as needed. You may want to set eye and hair colors and touch up gloss and bump levels on both body and head (they will be sewed into a single mesh, look for two different materials associated to the mesh.)

Demo: https://www.youtube.com/watch?v=RYYCRgpvDUo

Go to 'pose mode' on the armature. There should be a new panel on the right side of the 3D viewer. Click on it, it'll offer a few preset poses and the ability to morph the character between its actual shape and the default body shape for the gender.

TROUBLESHOOTING:

* Script does not seem to do anything, or it produces an untextured / incompletely textured object:

- Double check dump/fbx/path variables. 

* Script appears to hang Blender:

- Some delay is to be expected, because the script has to do some heavy duty number crunching. Enable the system console before running the script, and you'll see that it's working. Processing normally takes 15-30 s, but may take significantly longer in rare cases. 

* Script prints something about a matrix with no inverse, then takes a very long time to run and produces a messed-up mesh:

- May happen if the character has some dimensions set to -100 (perhaps you tried to delete the guy's nipples so you set his nipple size to -100). The character can't be imported, go back to the game and fix it.

* Script takes a very long time to run and produces a mesh with large defects (e.g. "exploded" hands or breasts):

- Known issue, no set recipe for now. Try a different character.

* Script imports a male character without errors, but his skin is completely messed up:

- To import male characters, you must turn off their genitals. If you don't, due to a bug in MeshExporter, the genitals texture will overwrite the main body texture.

* The character has bright green eyes with green pupils:

- Known issue. Manually edit the eye material to fix.

* There is a visible seam between the shoulder and the arm:

- Something went wrong with bump mapping. Edit the torso material and set both bump map levels to 0.

* There's a visible seam between the neck and the head:

- Either something went wrong with bump mapping (as above, set levels to 0 on the torso and the head); or the script failed to delete some extraneous bits of mesh inside the character's neck. Look inside the neck. If there's a ring of faces sticking out (or rather, in), delete it.

* The character has the "default" low-quality teeth mesh, even though it has good teeth in the game:

- This is probably a bug in Studio Neo (you may notice that the character has low-quality teeth there too.) Use MeshExporter to dump the character directly out of the game (you won't be able to do the whole process, since you can't put the character in T-pose, but you can at least get the fbx). Manually insert the correct teeth into the scene and parent them to the armature.

NOTES:

To pose the character, go to "pose mode" on the armature, select layers (primary FK bones are in the top row: left leg is layer 0, right leg is layer 1, etc), then select bones and rotate them with the mouse (click 'r' to go into rotation mode) or directly from the item transform window (top right corner of the 3D view panel).

A few facial features can be controlled this way too, others can't (e.g. can't open the character's mouth with bones at all), the preferred way is to use shape keys. "Body", "object mode", "object data properties" (green triangle in the properties panel), "shape keys" window. E.g., to open the character's mouth, set k09_open1 to 1.0. Most names are in Japanese, auto-translating them is on the todo list. "Warai" - laughing, "Kanasimi" - sad, "ikari" - angry, "fukure" - bulge(?), "damage"  - hurt, "fera" - blow, "sitadasi" - sticking the tongue out, "ahe" - cough(?), "tehepero" - sticking the tongue out at an angle. You also get 'k18_a', 'k19_i', etc, that you can use to simulate speech. E.g. "thank you" is
frame 0 - k18_a=0, k20_u=0
frame 10 - k18_a=1, k20_u=0
frame 20 - k18_a=0, k20_u=1
frame 30 - k18_a=0, k20_u=0

For more complex facial emotions, you need to use multiple shape keys. E.g., for a proper "hurt", you need e05_damage, g07_damage, and k06_damage.

Gaze direction is set with cf_J_look_L, cf_J_look_R.


KNOWN ISSUES:

* Produced characters have no pubic hair; males have no facial hair.
* Bone constraints have not been fully set up yet.
* It will have a shot at automatic texturing of clothing and hair, but the result is going to be very crude.
* It will correctly detect and try to reconstruct male characters, but may have major difficulties. As mentioned above, for now, to export males, you must turn off their genitals. Since "native" male characters' genitals have serious shortcomings (starting with being permanently erect, absurdly large even at the low end of the slider, and lacking foreskin), you're better off without them anyway. I'll be looking into automatically sewing on some properly resized and deflated equipment out of Hooh's scripted cocks mod as part of importing male chars.
* It does not import and texture all accessories; some accessories end up unpainted and unpositioned.
* Possibly many other bugs I haven't discovered yet.


