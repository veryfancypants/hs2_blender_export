import bpy
import os
import bmesh
import math
from mathutils import Matrix, Vector

def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


path="C:\\temp\\HS2\\Export\\20211004041049_Haruka_Sawamura_(o)\\"
fbx=path+"Haruka_Sawamura_(o).fbx"

suffix='abcd'

path += "Textures\\"

dump='C:\\Temp\\HS2\\UserData\\MaterialEditor\\haruka.txt'
dump=open(dump,'r').readlines()
dump=[x.strip() for x in dump]
if 'cf_J_Root' in dump[0]:
    dump[0]='cf_J_Root--UnityEngine.GameObject'
else:
    print('ERROR: Could not parse the dump file')




"""

TODO: changes needed to import male characters correctly:
   
* No body texture2 (where's the nipple?)
* Set head gloss map scale to 5, subtract constant to 0.850 instead of 0.650
* No head bumpmap2 or body bumpmap2
* Head bumpmap is same style as for girls (x in alpha, y in G), but body bumpmap is different (x in R, y in G)

"""

boy=False
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
    if obj in chara:
        chara[obj].materials[0].node_tree.nodes[node].image=tex
    else:
        bpy.data.meshes[obj].materials[0].node_tree.nodes[node].image=tex

sc = bpy.data.scenes[0]





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
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects[bn]
    box = bbox(bpy.data.meshes[bn].vertices)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='LOOSE')
    nails=[]
    boobies=[]
    other=[]
    junk=[]
    for x in bpy.data.meshes.keys():
        if not x.startswith(bn):
            continue
        b = bbox(bpy.data.meshes[x].vertices)
        #print(x, bpy.data.meshes[x].vertices[0].co, b, ( b[1][0]- b[0][0])/(box[1][0]-box[0][0]))
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
    print(nails)
    print(boobies)
    print(other)
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
    #bpy.ops.object.mode_set(mode='EDIT')
    print(other, bn)
    join_meshes(other, bn)

def load_textures():
    while len(chara['o_eyeshadow'].materials):
        chara['o_eyeshadow'].materials.pop()
    chara['o_eyeshadow'].materials.append(bpy.data.materials['Eyeshadow'])
    set_tex('o_eyeshadow', 'Image Texture', 'eyekage', 'MainTex')    

    eyelash_mat = bpy.data.materials['Eyelashes'].copy()
    eyelash_mat.name = 'Eyelashes_' + suffix
    while len(chara['o_eyelashes'].materials):
        chara['o_eyelashes'].materials.pop()
    chara['o_eyelashes'].materials.append(eyelash_mat)
    set_tex('o_eyelashes', 'Image Texture', 'eyelashes', 'MainTex', csp='Non-Color')    
    
    eye_mat = bpy.data.materials['Eyes'].copy()
    eye_mat.name = 'Eyes_' + suffix
    while len(chara['o_eyebase_R'].materials):
        chara['o_eyebase_R'].materials.pop()
    chara['o_eyebase_R'].materials.append(eye_mat)
    while len(chara['o_eyebase_L'].materials):
        chara['o_eyebase_L'].materials.pop()
    chara['o_eyebase_L'].materials.append(eye_mat)
    set_tex('o_eyebase_L', 'Image Texture', 'eye', 'MainTex', csp='Non-Color')    
    set_tex('o_eyebase_L', 'Image Texture.001', 'eye', 'Texture2', csp='Non-Color')    
    set_tex('o_eyebase_L', 'Image Texture.002', 'eye', 'Texture3', csp='Non-Color')    
    set_tex('o_eyebase_L', 'Image Texture.003', 'eye', 'Texture4')    

    head_mat = bpy.data.materials['Head'].copy()
    head_mat.name = 'Head_' + suffix
    while len(chara['o_head'].materials):
        chara['o_head'].materials.pop()
    chara['o_head'].materials.append(head_mat)
    set_tex('o_head', 'Image Texture', 'head', 'MainTex', alpha='NONE', csp='Non-Color')
    set_tex('o_head', 'Image Texture.002', 'head', 'DetailMainTex', csp='Non-Color')
    set_tex('o_head', 'Image Texture.003', 'head', 'DetailGlossMap', csp='Non-Color')
    set_tex('o_head', 'Image Texture.006', 'head', 'BumpMap2', csp='Non-Color')
    set_tex('o_head', 'Image Texture.007', 'head', 'BumpMap', csp='Non-Color')
    #head_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    #head_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0

    
    forehead_mat = bpy.data.materials['Eyebrows'].copy()
    forehead_mat.name = 'Eyebrows_' + suffix
    while len(chara['o_forehead'].materials):
        chara['o_forehead'].materials.pop()
    chara['o_forehead'].materials.append(forehead_mat)
    set_tex('o_forehead', 'Image Texture', 'head', 'Texture3')

    body_mat = bpy.data.materials['Torso'].copy()
    body_mat.name = 'Torso_' + suffix
    while len(chara[bn].materials):
        chara[bn].materials.pop()
    chara[bn].materials.append(body_mat)
    set_tex(bn, 'Image Texture', 'body', 'MainTex', alpha='NONE', csp='Non-Color')
    set_tex(bn, 'Image Texture.005', 'body', 'DetailGlossMap', csp='Non-Color')
    set_tex(bn, 'Image Texture.002', 'body', 'BumpMap_converted', csp='Non-Color')
    set_tex(bn, 'Image Texture.003', 'body', 'BumpMap2_converted', csp='Non-Color')
    body_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    body_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0

    while len(chara['nails'].materials):
        chara['nails'].materials.pop()
    chara['nails'].materials.append(bpy.data.materials['Nails'])
    
    booby_mat = bpy.data.materials['Boobies'].copy()
    booby_mat.name = 'Boobies_' + suffix
    while len(chara['l_booby'].materials):
        chara['l_booby'].materials.pop()
    chara['l_booby'].materials.append(booby_mat)
    while len(chara['r_booby'].materials):
        chara['r_booby'].materials.pop()
    chara['r_booby'].materials.append(booby_mat)
    set_tex('l_booby', 'Image Texture', 'body', 'Texture2')    
    bpy.data.objects['l_booby']['BoobyIndex']=1.0

    hair_mat = bpy.data.materials['test_hair'].copy()
    hair_mat.name = 'Hair_' + suffix
    for x in bpy.data.objects.keys():
        if 'hair' in x:
            o = bpy.data.meshes[x]
            while len(o.materials):
                o.materials.pop()
            o.materials.append(hair_mat)
            
    for x in bpy.data.objects.keys():
        if x.startswith('o_') and not x in chara:
            print(x)
            mesh = bpy.data.objects[x].data
            m = mesh.materials[0]
            n = m.name
            if '.' in n:
                n = n.split('.')[0]            
            while len(mesh.materials):
                mesh.materials.pop()
            mat = bpy.data.materials['Clothing'].copy()
            mesh.materials.append(mat)
            set_tex(mesh.name, 'Image Texture', n, 'MainTex', csp='Non-Color')
            set_tex(mesh.name, 'Image Texture.001', n, 'DetailGlossMap', csp='Non-Color')


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
    
    if False: # Not needed for meshexporter, the head is in the right place to begin with
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
    else:
        error = 0.01

    if False:        
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

def import_bodyparts():
    for bpy_data_iter in (bpy.data.objects, bpy.data.meshes):
        for id_data in bpy_data_iter:
            if  id_data.name!="Cube" and id_data.name!="Material Cube":
                bpy_data_iter.remove(id_data)
    bpy.ops.import_scene.fbx(filepath=fbx)
    for x in bodyparts:
        for y in bpy.data.meshes.keys(): #sc.objects.keys():
            if y.startswith(x):
                chara[x]=bpy.data.meshes[y]
    for bpy_data_iter in (bpy.data.objects, bpy.data.meshes):
        for id_data in bpy_data_iter:
            if id_data.name.startswith('k_') \
            or id_data.name.startswith('f_') \
            or id_data.name.startswith('cf_J') \
            or id_data.name.startswith('HS2_') \
            or id_data.name.startswith('N_') \
            or (bpy_data_iter==bpy.data.objects and id_data.type=='EMPTY'):                
                bpy_data_iter.remove(id_data)
    bpy.data.objects.remove(bpy.data.objects['o_namida'])
    if 'o_body_cf' in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects['o_body_cf']) # it's an Empty 
    bpy.data.objects['o_body_cf.001'].name='o_body_cf'
    #TODO: delete all the Empty objects and hierarchies    
    if not 'o_head' in bpy.data.meshes:
        heads=[x for x in bpy.data.meshes.keys() if x.startswith('o_head')]
        if len(heads)==1:
            bpy.data.meshes[heads[0]].name='o_head'
    arm = bpy.data.objects['Armature']
    body = arm.children[0]
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.scale_clear()                
    return True


bone_pos={}
bone_w2l={}
bone_parent={}
#bone_scale={}
root_pos=[0,0,0]

def mul4(x, y):
    return [sum([x[i][j]*y[j] for j in range(4)]) for i in range(4)]

def load_unity_dump():
    global root_pos
    global bone_pos
    name=''
    global bone_parent
    global bone_w2l
    for n in range(len(dump)):
        x=dump[n]
        if x.endswith('--UnityEngine.GameObject'):
           name=x.split('-')[0]
           #print(name)
        elif x.startswith('@parent<Transform>'):
            bone_parent[name]=x.split()[2]
        elif (x.startswith('@localToWorldMatrix<Matrix4x4>') \
            or x.startswith('@worldToLocalMatrix<Matrix4x4>')):
            if not name.startswith('cf_'):
                continue
            m=[
                x.split()[-4:],
                dump[n+1].split()[-4:],
                dump[n+2].split()[-4:],
                dump[n+3].split()[-4:] ]
            m=[[float(y) for y in z] for z in m]
            if x.startswith('@worldToLocalMatrix'):
                bone_w2l[name]=m
            else:
                if name=='cf_J_Root':
                    root_pos = [m[0][3],m[1][3],m[2][3]]
                    print('Root ', root_pos)
                m[0][3]-=root_pos[0]
                m[1][3]-=root_pos[1]
                m[2][3]-=root_pos[2]
                m[0][1]*=-1
                m[0][2]*=-1
                m[0][3]*=-1
                m[1][0]*=-1
                m[2][0]*=-1
                m[3][0]*=-1
                bone_pos[name]=m


def reshape_armature(): 
    bpy.ops.object.mode_set(mode='OBJECT')    
    arm = bpy.data.objects['Armature']
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    fix_bone_directions={
    'cf_J_Kosi02': (0,-1,0),
    'cf_J_Toes01_L': (0,0,1),
    'cf_J_Toes01_R': (0,0,1),

    'cf_J_Siri_L': (0,0,-1),
    'cf_J_Siri_R': (0,0,-1),
    'cf_J_Siri_s_L': (0,0,-1),
    'cf_J_Siri_s_R': (0,0,-1),
    
    'cf_J_ArmUp00_L': (1,0,0),
    'cf_J_ArmUp00_R': (-1,0,0),
    'cf_J_ArmLow01_L': (1,0,0),
    'cf_J_ArmLow01_R': (-1,0,0),
    }
    for x in bpy.context.object.data.edit_bones:
        if x.name in bone_pos:
            p = Matrix(bone_pos[x.name])
            local = arm.data.bones[x.name].matrix_local
            bone_length =  (p @ x.tail) - (p @ x.head)
            #local = arm.data.bones[x.name].matrix_local
            #bone_length = x.tail - x.head
            x.matrix=p
            x.head.x=p[0][3]
            x.head.y=p[1][3]
            x.head.z=p[2][3]            
            array=[False]*32
            array[31]=True
            side = (1 if x.name[-1]=='R' else 0)
            if x.name=='cf_N_height':
                array[15]=True
                array[31]=False
            if x.name[:-1] in ['cf_J_LegUp00_', 'cf_J_LegLow01_', 'cf_J_LegLowRoll_', 'cf_J_Foot01_', 'cf_J_Foot02_', 'cf_J_Toes01_', 'cf_J_SiriDam_', 'cf_J_Siri_']:
                array[0+side]=True # Leg FK
            if x.name[:-1] in ['cf_J_LegLow01_s_', 'cf_J_LegLow02_s_', 'cf_J_LegUp03_s_',           'cf_J_LegKnee_back_', 'cf_J_LegKnee_back_s_', 'cf_J_Siri_s_', 'cf_J_LegKnee_dam_', 
            'cf_J_LegKnee_low_s_', 'cf_J_LegUpDam_', 'cf_J_LegUpDam_s_']:
                array[16+side]=True # Leg soft
            if x.name[:-1] in ['cf_J_Shoulder_', 'cf_J_ArmUp00_', 'cf_J_ArmLow01_', 'cf_J_Hand_dam_']:
                array[2+side]=True # Arm FK
            if x.name[:-1] in ['cf_J_Shoulder02_s_', 'cf_J_ArmUp03_s_', 'cf_J_ArmLow01_s_', 'cf_J_Hand_Wrist_s_', 'cf_J_Hand_s_']:
                array[18+side]=True # Arm soft
            x.layers=array
                
            fix_dir=None
            if x.name in fix_bone_directions:
                fix_dir=fix_bone_directions[x.name]
            elif array[0] or array[1] or array[16] or array[17]:
                fix_dir=(0,-1,0)
            elif array[2] or array[18]:
                fix_dir=(1,0,0)
            elif array[3] or array[19]:
                fix_dir=(-1,0,0)
            if fix_dir!=None:
                bone_length = bone_length.length * Vector(fix_dir)
            x.tail=x.head+bone_length      
            # TODO: switch everyone to XYZ Euler or ZYX Euler

    bpy.ops.object.mode_set(mode='OBJECT')    
    bpy.ops.object.mode_set(mode='POSE')
    
    for n in ['cf_J_LegUp00_L', 'cf_J_LegLow01_L', 
            'cf_J_LegUp00_R', 'cf_J_LegLow01_R']:
        bone = arm.pose.bones[n]
        bone.rotation_mode='XYZ'
        
    for n in ['cf_J_LegKnee_dam_L', 'cf_J_LegKnee_dam_R', 
            'cf_J_LegKnee_back_L', 'cf_J_LegKnee_back_R',
            'cf_J_SiriDam_L', 'cf_J_SiriDam_R',
            'cf_J_LegUpDam_L', 'cf_J_LegUpDam_R',
            ]:
        bone = arm.pose.bones[n]
        bone.rotation_mode='XYZ'
        bpy.types.ArmatureBones.active = bone
        con = bone.constraints.new('COPY_ROTATION')
        con.mix_mode='ADD'
        con.target=arm
        print(n)
        if ('Siri' in n) or ('LegUp' in n):
            con.subtarget='cf_J_LegUp00_' + n[-1]
            con.use_x=True
            con.use_y=True
            con.use_z=True
            # TODO: work out the exact influence and rotation order factors used by the game;
            # the following is only a rough guess
            con.influence=0.5 if ('Siri' in n) else 0.75
        else:
            con.subtarget='cf_J_LegLow01_' + n[-1]
            con.use_x=True
            con.use_y=False
            con.use_z=False
            con.influence=1.0 if ('_back_' in n) else 0.5
        con.owner_space='LOCAL'
        con.target_space='LOCAL'

import_bodyparts()
rebuild_head()
rebuild_torso()
load_textures()

fixup_head()
fixup_torso()
stitch_head_to_torso()
load_unity_dump()
reshape_armature()            

# TODO: better texturing for all cloth and hair objects

bpy.ops.object.mode_set(mode='OBJECT')
light_data = bpy.data.lights.new('light', type='POINT')
light = bpy.data.objects.new('light', light_data)
bpy.context.collection.objects.link(light)
light.location = (5, -5, 10)
light.data.energy=2000.0

