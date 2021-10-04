import bpy
import os
import bmesh
import math

def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

path="C:\\temp\\HS2\\UserData\\MaterialEditor\\"
suffix='abcd'


"""

TODO: changes needed to import male characters correctly:
   
* No body texture2 (where's the nipple?)
* Set head gloss map scale to 5, subtract constant to 0.850 instead of 0.650
* No head bumpmap2 or body bumpmap2
* Head bumpmap is same style as for girls (x in alpha, y in G), but body bumpmap is different (x in R, y in G)

"""

boy=True
bn='o_body_cm' if boy else 'o_body_cf'

bodyparts=[bn,
'o_eyebase_L',
'o_eyebase_R',
'o_eyelashes',
'o_eyeshadow',
'o_head',
'o_tang',
'o_tooth',
]

if path[-1]!='\\':
    path+='\\'

chara={x:None for x in bodyparts}
chara['o_forehead']=None


def find_tex(x1, x2):
    f=os.listdir(path)
    for y in f:
        if (x1 in y) and y.endswith("_"+x2+".png"):
            return path+y
    return None

def set_tex(obj, node, x, y, alpha=None, csp=None):
    global chara
    tex=find_tex(x, y)
    if tex==None:
        print('ERROR: failed to find texture ', x, y)
        return
    tex=bpy.data.images.load(tex)
    if tex==None:
        print('ERROR: failed to load texture ', x, y)
        return
    if alpha!=None:
        tex.alpha_mode='NONE'
    if csp!=None:
        tex.colorspace_settings.name=csp
    chara[obj].materials[0].node_tree.nodes[node].image=tex

sc = bpy.data.scenes[0]

for bpy_data_iter in (bpy.data.objects, bpy.data.meshes):
    for id_data in bpy_data_iter:
        if  id_data.name!="Cube" and id_data.name!="Material Cube":
            bpy_data_iter.remove(id_data)

def import_bodyparts():
    f=os.listdir(path)
    for x in bodyparts:
        if not x+'.obj' in f:
            ShowMessageBox('ERROR: could not find the mesh ' + x+'.obj')
            return False
        bpy.ops.import_scene.obj(filepath=path+x+".obj")
    for x in bodyparts:
        for y in bpy.data.meshes.keys(): #sc.objects.keys():
            if y.startswith(x):
                chara[x]=bpy.data.meshes[y]
    return True



def bbox(x):
    rv=[[x[0].co[0],x[0].co[1],x[0].co[2]],
        [x[0].co[0],x[0].co[1],x[0].co[2]]]
    for y in x:
        for n in range(3):
            rv[0][n]=min(rv[0][n], y.co[n])
            rv[1][n]=max(rv[1][n], y.co[n])
    return rv

# The head always (or at least typically) has three parts: skull, forehead, mouth cavity.
# Their order is not guaranteed. We make a duplicate of the forehead to apply eyebrow textures,
# then merge one of the copies into the skull.
def rebuild_head():
    global chara
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects['o_head']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='LOOSE')
    y0=bbox(bpy.data.meshes['o_head'].vertices)[0][1]
    y1=bbox(bpy.data.meshes['o_head.001'].vertices)[0][1]
    y2=bbox(bpy.data.meshes['o_head.002'].vertices)[0][1]
    if y0<y1 and y0<y2:
        if y1>y2:
            head='o_head'
            forehead='o_head.001'
            mouth='o_head.002'
        else:
            head='o_head'
            forehead='o_head.002'
            mouth='o_head.001'
    elif y0>y1 and y0>y2:
        if y1>y2:
            forehead='o_head'
            mouth='o_head.001'
            head='o_head.002'
        else:
            forehead='o_head'
            mouth='o_head.002'
            head='o_head.001'
    else:
        if y1>y2:
            mouth='o_head'
            forehead='o_head.001'
            head='o_head.002'
        else:
            mouth='o_head'
            forehead='o_head.002'
            head='o_head.001'
    bpy.data.objects[forehead].select_set(True)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.duplicate()
    bpy.data.objects[head].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[head]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.join()
    bpy.data.objects[mouth].name='o_mouth'
    bpy.data.objects[forehead].name='o_forehead'
    bpy.data.objects[head].name='o_head'
    bpy.data.meshes[mouth].name='o_mouth'
    bpy.data.meshes[forehead].name='o_forehead'
    bpy.data.meshes[head].name='o_head'
    chara['o_forehead']=bpy.data.meshes['o_forehead']
    chara['o_head']=bpy.data.meshes['o_head']


def join_meshes(v, name):
    if len(v)==0:
        return
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for x in v:
        bpy.data.objects[x].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[v[0]] 
    bpy.ops.object.join()
    bpy.data.objects[v[0]].name=name

# the number of loose parts in the torso is variable depending on the uncensor
# we have to work out which parts are which by looking at their coordinates
def rebuild_torso():    
    global chara
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects[bn]
    box = bbox(bpy.data.meshes[bn].vertices)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='LOOSE')
    nails=[]
    boobies=[]
    other=[]
    junk=[]
    print(box)
    for x in bpy.data.meshes.keys():
        if not x.startswith(bn):
            continue
        b = bbox(bpy.data.meshes[x].vertices)
        if b[1][0]<box[0][0]+0.2*(box[1][0]-box[0][0]) \
         or b[0][0]>box[0][0]+0.8*(box[1][0]-box[0][0]) \
         or b[1][1]<box[0][1]+0.2*(box[1][1]-box[0][1]):
            nails.append(x)
        elif b[0][1]>box[0][1]+0.66*(box[1][1]-box[0][1]) \
            and b[1][1]<box[0][1]+0.95*(box[1][1]-box[0][1]) \
            and b[0][0]>box[0][0]+0.25*(box[1][0]-box[0][0]) \
            and b[1][0]<box[0][0]+0.75*(box[1][0]-box[0][0]):
                boobies.append(x)
        elif b[0][1]>box[0][1]+0.90*(box[1][1]-box[0][1]):
            junk.append(x)
        else:
            other.append(x)
    #print(nails)
    #print(boobies)
    #print(other)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')        
    for x in junk:
        bpy.data.objects[x].select_set(True)
    bpy.ops.object.delete()

    if len(nails)!=20 or len(boobies)!=2:
        print(len(nails), len(boobies))
        print("ERROR: failed to find the right number of nails or boobies: reconstruct may fail")
        print(nails)
    join_meshes(nails, 'nails')
    chara['nails']=bpy.data.meshes[nails[0]]
    if len(boobies)==2:
        if bbox(bpy.data.meshes[boobies[0]].vertices)[0][0]>bbox(bpy.data.meshes[boobies[1]].vertices)[0][0]:
            boobies=[boobies[1],boobies[0]]
        bpy.data.objects[boobies[0]].name='r_booby'
        bpy.data.objects[boobies[1]].name='l_booby'
        bpy.ops.object.select_all(action='DESELECT')        
        bpy.data.objects['l_booby'].select_set(True)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.duplicate()
        bpy.ops.object.select_all(action='DESELECT')        
        bpy.data.objects['r_booby'].select_set(True)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.duplicate()
        other.append('l_booby.001')
        other.append('r_booby.001')
        chara['r_booby']=bpy.data.meshes[boobies[0]]
        chara['l_booby']=bpy.data.meshes[boobies[1]]
    join_meshes(other, bn)

def load_textures():
    chara['o_eyeshadow'].materials.pop()
    chara['o_eyeshadow'].materials.append(bpy.data.materials['Eyeshadow'])
    set_tex('o_eyeshadow', 'Image Texture', 'eyekage', 'MainTex')    

    eyelash_mat = bpy.data.materials['Eyelashes'].copy()
    eyelash_mat.name = 'Eyelashes_' + suffix
    chara['o_eyelashes'].materials.pop()
    chara['o_eyelashes'].materials.append(eyelash_mat)
    set_tex('o_eyelashes', 'Image Texture', 'eyelashes', 'MainTex')    
    
    eye_mat = bpy.data.materials['Eyes'].copy()
    eye_mat.name = 'Eyes_' + suffix
    chara['o_eyebase_R'].materials.pop()
    chara['o_eyebase_R'].materials.append(eye_mat)
    chara['o_eyebase_L'].materials.pop()
    chara['o_eyebase_L'].materials.append(eye_mat)
    set_tex('o_eyebase_L', 'Image Texture', 'eye', 'MainTex')    
    set_tex('o_eyebase_L', 'Image Texture.001', 'eye', 'Texture2')    
    set_tex('o_eyebase_L', 'Image Texture.002', 'eye', 'Texture3')    
    set_tex('o_eyebase_L', 'Image Texture.003', 'eye', 'Texture4')    

    head_mat = bpy.data.materials['Head'].copy()
    head_mat.name = 'Head_' + suffix
    chara['o_head'].materials.pop()
    chara['o_head'].materials.append(head_mat)
    set_tex('o_head', 'Image Texture', 'head', 'MainTex', alpha='NONE')
    set_tex('o_head', 'Image Texture.002', 'head', 'DetailMainTex', csp='Non-Color')
    set_tex('o_head', 'Image Texture.003', 'head', 'DetailGlossMap', csp='Non-Color')
    set_tex('o_head', 'Image Texture.006', 'head', 'BumpMap2', csp='Non-Color')
    set_tex('o_head', 'Image Texture.007', 'head', 'BumpMap', csp='Non-Color')
    forehead_mat = bpy.data.materials['Eyebrows'].copy()
    forehead_mat.name = 'Eyebrows_' + suffix
    chara['o_forehead'].materials.pop()
    chara['o_forehead'].materials.append(forehead_mat)
    set_tex('o_forehead', 'Image Texture', 'head', 'Texture3')

    body_mat = bpy.data.materials['Torso'].copy()
    body_mat.name = 'Torso_' + suffix
    chara[bn].materials.pop()
    chara[bn].materials.append(body_mat)
    set_tex(bn, 'Image Texture', 'body', 'MainTex', alpha='NONE')
    set_tex(bn, 'Image Texture.005', 'body', 'DetailGlossMap', csp='Non-Color')
    set_tex(bn, 'Image Texture.002', 'body', 'BumpMap', csp='Non-Color')
    set_tex(bn, 'Image Texture.003', 'body', 'BumpMap2', csp='Non-Color')

    chara['nails'].materials.pop()
    chara['nails'].materials.append(bpy.data.materials['Nails'])
    
    booby_mat = bpy.data.materials['Boobies'].copy()
    booby_mat.name = 'Boobies_' + suffix
    chara['l_booby'].materials.pop()
    chara['l_booby'].materials.append(booby_mat)
    chara['r_booby'].materials.pop()
    chara['r_booby'].materials.append(booby_mat)
    set_tex('l_booby', 'Image Texture', 'body', 'Texture2')    
    bpy.data.objects['l_booby']['BoobyIndex']=1.0

def fixup_head():
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects['o_head']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles()

def fixup_torso():
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    join_meshes([bn,'nails'], bn)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects[bn]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles(use_unselected=True)

def stitch_head_to_torso():
    tv=bpy.data.meshes[bn].vertices
    hv=bpy.data.meshes['o_head'].vertices
    ttv=tv[0].co[:]
    bhv=hv[0].co[:]
    ttv2=tv[0].co[:]
    bhv2=hv[0].co[:]
    # Find front and rear stitch points. (This approach could fail if the character has
    # a particularly long and sharply angled jaw, so that the chin is below the stitch surface...)
    for x in tv:
        if abs(x.co[0])>0.01:
            continue
        if x.co[1]-2*x.co[2] > ttv[1]-2*ttv[2]:
            ttv=x.co
        if x.co[1]+x.co[2] > ttv2[1]+ttv2[2]:
            ttv2=x.co
    tan_neck = (ttv[1]-ttv2[1])/(ttv[2]-ttv2[2])

    for x in hv:
        if abs(x.co[0])>0.01:
            continue
        if x.co[1]-tan_neck*1.1*x.co[2] < bhv[1]-tan_neck*1.1*bhv[2]:
            bhv=x.co
        if x.co[1]-tan_neck*0.9*x.co[2] < bhv2[1]-tan_neck*0.9*bhv2[2]:
            bhv2=x.co
    delta1 = [-ttv[2]+bhv[2], ttv[1]-bhv[1]]
    delta2 = [-ttv2[2]+bhv2[2], ttv2[1]-bhv2[1]]
    med = [(delta1[0]+delta2[0])/2., (delta1[1]+delta2[1])/2.]
    #print(ttv, ttv2, bhv, bhv2)
    rm = [med[0]-delta1[0], med[1]-delta1[1]]
    error = math.sqrt(rm[0]*rm[0]+rm[1]*rm[1])
    if error>0.01:
        print('ERROR: excessive head/torso alignment error (%f)' % error)        
        ShowMessageBox('ERROR: excessive head/torso alignment error (%f)' % error)
        return        
    
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')        
    bpy.data.objects['o_head'].select_set(True)
    bpy.data.objects['o_mouth'].select_set(True)
    if boy:
        bpy.data.objects['o_tang'].select_set(True)
    bpy.data.objects['o_tooth'].select_set(True)
    bpy.data.objects['o_eyebase_L'].select_set(True)
    bpy.data.objects['o_eyebase_R'].select_set(True)
    bpy.data.objects['o_eyelashes'].select_set(True)
    bpy.data.objects['o_eyeshadow'].select_set(True)
    bpy.data.objects['o_forehead'].select_set(True)
    bpy.ops.transform.translate(value=[0.0, med[0], med[1]])
    
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    join_meshes([bn,'o_head'], 'body')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects['body']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles(threshold=max(error*1.5, 0.001), use_unselected=True)
    bpy.ops.mesh.select_more()
    bpy.ops.mesh.normals_tools(mode='RESET')
    #selected_verts = [v for v in bpy.data.meshes[bn].vertices if v.select]    

if import_bodyparts():
    rebuild_head()
    rebuild_torso()
    load_textures()

    fixup_head()
    fixup_torso()
    stitch_head_to_torso()

    bpy.ops.object.mode_set(mode='OBJECT')
    light_data = bpy.data.lights.new('light', type='POINT')
    light = bpy.data.objects.new('light', light_data)
    bpy.context.collection.objects.link(light)
    light.location = (10, -10, 10)
    light.data.energy=2000.0
