This is a set of scripts and templates for exporting HS2/AI characters into Blender.

These scripts give you the exact rig used by the game, with realistic range of motion in knees and hips that is very hard to achieve with metarig. You get full armature + vertex weights + bone constraints + even shape keys (aka blend shapes) out of the box. In addition, you get hair, clothes, and accessories (though as far as how accurate they will be, YMMV.)

The downside is that you get a fully custom rig. No pretty metarig controls until someone (read: me) implements it. Also, there's no IK support yet.

STEP BY STEP INSTRUCTIONS

Install Grey's MeshExporter. (It comes as 'optional' with HS2 BetterRepack.)

Launch Studio Neo. Load the character. Hit F1, find Runtime Unity Editor, bind a key to open it.

Use MeshExporter to export everything. Do ask for converted bump maps. Don't ask to pack png's into the fbx. 

Put the character in T-pose. Hit the key for Runtime Unity Editor. In the "Scene Unity Editor", find the node called "Common Space", select it and hit 'dump'. Save it in the same folder where MeshExporter put the fbx (it is typically called something like "<HS2 root dir>\Export\20221213104852_Kazumi"), make sure to give it the '.txt' extension.

Open prefab_materials_meshexporter.blend in Blender. You will see a new panel called "HS2 rig" on the right side of the 3D viewer. Put the export folder in "Char directory". Hit "import model".

Wait for it to complete (it may take a while.)

If the process is successful, several new controls will appear, including hair color and eye color settings and a few posing crontrols. 

Switch to object mode, go through the materials and adjust the settings as needed. You may want to touch up gloss and bump levels on both body and head (they will be sewed into a single mesh, look for two different materials associated to the mesh), and fix any incorrectly/poorly textured clothes.

TROUBLESHOOTING:

* Script does not seem to do anything, or it produces an untextured / incompletely textured object:

Double check that the "Char directory" is correct and it contains everything it should. If a major failure occurs, the script will report the error in the "HS2 rig" panel.

* Script appears to hang Blender if 'Refactor armature' is checked:

Some delay is to be expected, because the script has to do some heavy duty number crunching. Enable the system console before running the script, and you'll see that it's working. Processing normally takes 1-2 min, but may take significantly longer in rare cases. 

* Script prints something about a matrix with no inverse, then takes a very long time to run and produces a messed-up mesh:

May happen if the character has some dimensions set to -100 (perhaps you tried to delete the guy's nipples so you set his nipple size to -100). The character can't be imported, go back to the game and fix it.

* Script takes a very long time to run and produces a mesh with large defects (e.g. "exploded" hands or breasts):

Known issue, no set recipe for now. Either turn off 'Refactor armature', or try a different character.

* Script imports a character without reporting errors, but the armature is acting weird, and, when in T-pose, arm bones aren't aligned vertically with the character's arms:

May be have a few different causes. One possibility is that the Unity dump is wrong (it is for the wrong character, or you've exported the wrong node). It also occurs when importing a character wearing high heels. Remove the shoes and retry. (Most shoes are okay, though. As a general rule, if the character moves up/down when you toggle 'shoes' in Studio Neo, we're going to have trouble.)

* Script imports a male character without reporting errors, but his skin is completely messed up:

To import male characters, you must turn off their genitals. If you don't, due to a bug in MeshExporter, the genitals texture will overwrite the main body texture.

* The character has bright green eyes with green pupils:

Known issue. Manually edit the eye material to fix. Start by trying to disconnect the "Eye Texture 4" node.

* There is a visible seam (skin color discontinuity) between the shoulder and the arm:

Something went wrong with bump mapping. Disable by editing the torso material and setting both bump map levels to 0. 

* There's a visible seam between the neck and the head:

Either something went wrong with bump mapping (as above, set levels to 0 on the torso and the head); or the script failed to delete some extraneous bits of mesh inside the character's neck. Look inside the neck. If there's a ring of faces sticking out (or rather, in), delete it.

* The character has the "default" low-quality teeth mesh, even though it has good teeth in the game:

This is probably a bug in Studio Neo (you may notice that the character has low-quality teeth there too.) Use MeshExporter to dump the character directly out of the game (you won't be able to do the whole process, since you can't put the character in T-pose, but you can at least get the fbx). Manually insert the correct teeth into the scene and parent them to the armature.

* The character has torn clothing:

Edit the material for the item you want to fix and set 'Clothes damage' to 0 or -0.1.

NOTES:

To pose the character, go to "pose mode" on the armature, select layers (primary FK bones are in the top row: left leg is layer 0, right leg is layer 1, etc), then select bones and rotate them with the mouse (click 'r' to go into rotation mode) or directly from the item transform window (top right corner of the 3D view panel).

A few facial features can be controlled this way too. The script will try to tweak weight paints around the lips to make it possible to open the mouth by rotating 'cf_J_Chin_rs' (this can't be done with stock mesh.) The preferred way to control the face is to use shape keys. "Body", "object mode", "object data properties" (green triangle in the properties panel), "shape keys" window. E.g., to open the character's mouth, set k09_open1 to 1.0. Most names are in Japanese, auto-translating them is on the todo list. "Warai" - laughing, "Kanasimi" - sad, "ikari" - angry, "fukure" - bulge(?), "damage"  - hurt, "fera" - blow, "sitadasi" - sticking the tongue out, "ahe" - cough(?), "tehepero" - sticking the tongue out at an angle. You also get 'k18_a', 'k19_i', etc, that you can use to simulate speech.

For more complex facial emotions, you need to use multiple shape keys. E.g., for a proper "hurt", you need e05_damage (eyes), g07_damage (eyebrows), and k06_damage (mouth).

The script autogenerates a somewhat more realistic 'better_smile' shape key, give it a try.

Gaze direction is set with cf_J_look_L, cf_J_look_R.

Handling multiple characters will be more convenient with a config file. Just create a text file along these lines
```
C:\temp\waifus\Export\
Emily 20211006234404_Emily 0.424 0.562 0.633 0.313 0.198 0.120
Angel 20211015005854_angel 0.330 0.330 0.330 0.733 0.838 0.512
Takeda 20211015164736_Takeda_Miu 0.000 0.600 0.000 0.150 0.100 0.050
```
This assumes that you have, e.g., in C:\temp\waifus\Export\20211006234404_Emily, a .fbx (from MeshExporter), a .txt (Unity dump), and a Textures\ subfolder with textures. The 6 numbers are the eye color and the hair color (in this case, 0.424 0.562 0.633 means light blue eyes and 0.313 0.198 0.120 is straw colored hair.) 

KNOWN ISSUES:

* Produced characters have no pubic hair; males have no facial hair.
* Bone constraints have not been fully set up yet.
* It will have a shot at automatic texturing of clothing and hair, but the result is going to be very crude.
* It does not import and texture all accessories; some accessories end up unpainted and unpositioned.
* Possibly many other bugs I haven't discovered yet.


