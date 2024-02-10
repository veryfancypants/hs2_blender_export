import bpy
import os
import bmesh
import math
from mathutils import Matrix, Vector, Euler, Quaternion
import struct


from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import (
    Operator,
    Panel,
    PropertyGroup,
)


def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

eye_color=None
hair_color=None
use_config=False
wipe_scene=False

if not use_config:
    fbx='c:\\temp\\name.fbx'
    path='c:\\temp\\textures\\'
    dumpfilename='c:\\temp\\dump.txt'
else:
    cfg=open("C:\\temp\\hs2blender.cfg","r").readlines()
    waifus_path=cfg[0].strip()
    cfg=[x.strip().split(' ') for x in cfg[1:]]
    conf={}
    for x in cfg:
        if len(x)<2:
            continue
        y = x[1:]
        if len(y)==1:
            conf[x[0]]=(y[0],)
        else:
            colors=[float(z) for z in y[1:7]]
            conf[x[0]]=(y[0], colors[0:3], colors[3:6])

    name="Matthew2"
    path=waifus_path
    if path[-1]!='\\':
        path=path+'\\'
    cconf = conf[name]
    path+=cconf[0]+'\\'
    if len(cconf)>1:
        eye_color=cconf[1]
        hair_color=cconf[2]
    dumps=[x for x in os.listdir(path) if x.endswith('.txt') and not x.startswith('pose_')]
    if len(dumps)>0:
        dumpfilename=path+dumps[0]
    else:
        dumpfilename=None
        MessageBox('Failed to locate the dump')
    fbxs=[x for x in os.listdir(path) if x.endswith('.fbx')]
    if len(fbxs)>0:
        fbx=path+fbxs[0]
    else:
        fbx=None
        MessageBox('Failed to locate the FBX')
    path += "Textures\\"

suffix='abcd'

if hair_color!=None:
    if len(hair_color)==3:
        hair_color=(hair_color[0], hair_color[1], hair_color[2], 1.0)

if eye_color!=None:
    if len(eye_color)==3:
        eye_color=(eye_color[0], eye_color[1], eye_color[2], 1.0)

bodyparts=[
#bn,
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

def find_tex(x1, x2):
    f=os.listdir(path)
    for y in f:
        if (x1+'_' in y) and y.endswith("_"+x2+".png"):
            return path+y
    return None

def set_tex(obj, node, x, y, alpha=None, csp=None):
    #global chara
    tex=find_tex(x, y)
    if tex==None:
        print('ERROR: failed to find texture ', x, y)
        return False
    tex=bpy.data.images.load(tex)
    if tex==None:
        print('ERROR: failed to load texture ', x, y)
        return False
    if alpha!=None:
        tex.alpha_mode='NONE'
    if csp!=None:
        tex.colorspace_settings.name=csp
    obj.data.materials[0].node_tree.nodes[node].image=tex
    return True

sc = bpy.data.scenes[0]

def bbox(x):
     rv=[[x[0].co[0],x[0].co[1],x[0].co[2]],
         [x[0].co[0],x[0].co[1],x[0].co[2]]]
     for y in x:
         for n in range(3):
             rv[0][n]=min(rv[0][n], y.co[n])
             rv[1][n]=max(rv[1][n], y.co[n])
     return rv

def join_meshes(v, name):
    if len(v)==0:
        return
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for x in v:
        bpy.data.objects[x].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[v[0]] 
    bpy.ops.object.join()
    final=bpy.data.objects[v[0]]
    final.name=name
    return final

# the number of loose parts in the torso is variable depending on the uncensor
# we have to work out which parts are which by looking at their coordinates
def rebuild_torso(arm, body):
    #global chara
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    #body=bpy.data.objects[body.]
    bpy.context.view_layer.objects.active = body
    box = bbox(body.data.vertices)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.separate(type='LOOSE')
    nails=[]
    other=[]
    junk=[]
    bn=body.name
    if '.' in bn:
        bn=bn.split('.')
        bn=bn[0]
    #for x in bpy.data.meshes.keys():
    for ch in arm.children:
        if ch.type!='MESH':
            continue
        x=ch.name
        if not x.startswith(bn):
            continue
        b = bbox(bpy.data.objects[x].data.vertices)
        #print(x, bpy.data.meshes[x].vertices[0].co, b, ( b[1][0]- b[0][0])/(box[1][0]-box[0][0]))
        if b[1][0]<box[0][0]+0.2*(box[1][0]-box[0][0]) \
         or b[0][0]>box[0][0]+0.8*(box[1][0]-box[0][0]) \
         or b[1][1]<box[0][1]+0.2*(box[1][1]-box[0][1]):
            nails.append(x)
        elif b[0][1]>box[0][1]+0.96*(box[1][1]-box[0][1]):
            junk.append(x)
        else:
            other.append(x)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')        
    for x in junk:
        bpy.data.objects[x].select_set(True)
    bpy.ops.object.delete()
    if len(nails)!=20:
        print(len(nails))
        print("Warning: failed to find the right number of nails: reconstruct may fail")
    nails=join_meshes(nails, 'nails')
    if body['Boy']>0.0:
        if 'cm_o_dan00' in bpy.data.objects:
            other.append('cm_o_dan00')
        if 'cm_o_dan_f' in bpy.data.objects:
            other.append('cm_o_dan_f')            
    body=join_meshes(other, bn)
    body["nails"]=nails.name
    return body

def replace_mat(obj, mat, name):
    mat.name=name
    while len(obj.data.materials):
        obj.data.materials.pop()
    obj.data.materials.append(mat)
    return mat

def load_textures(arm, body):
    head = bpy.data.objects[body["o_head"]]
    tang = bpy.data.objects[body["o_tang"]]
    tooth = bpy.data.objects[body["o_tooth"]]
    eyeshadow = bpy.data.objects[body["o_eyeshadow"]]
    eyelashes = bpy.data.objects[body["o_eyelashes"]]
    eyebase_R = bpy.data.objects[body["o_eyebase_R"]]
    eyebase_L = bpy.data.objects[body["o_eyebase_L"]]
    nails = bpy.data.objects[body["nails"]]
    body_parts={body, head, tang, tooth, eyeshadow, eyelashes, eyebase_L, eyebase_R, nails}
    while len(eyeshadow.data.materials):
        eyeshadow.data.materials.pop()
    eyeshadow.data.materials.append(bpy.data.materials['Eyeshadow'])
    set_tex(eyeshadow, 'Image Texture', 'eyekage', 'MainTex')    

    eyelash_mat=replace_mat(eyelashes, bpy.data.materials['Eyelashes'].copy(),  'Eyelashes_' + suffix)
    set_tex(eyelashes, 'Image Texture', 'eyelashes', 'MainTex', csp='Non-Color')    
    if hair_color!=None:
        eyelash_mat.node_tree.nodes['RGB'].outputs[0].default_value = hair_color

    eye_mat = bpy.data.materials['Eyes'].copy()
    replace_mat(eyebase_L, eye_mat, 'Eyes_' + suffix)
    replace_mat(eyebase_R, eye_mat, 'Eyes_' + suffix)
    set_tex(eyebase_L, 'Image Texture', 'eye', 'MainTex', csp='Non-Color')    
    set_tex(eyebase_L, 'Image Texture.001', 'eye', 'Texture2', csp='Non-Color')    
    set_tex(eyebase_L, 'Image Texture.002', 'eye', 'Texture3', csp='Non-Color')    
    set_tex(eyebase_L, 'Image Texture.003', 'eye', 'Texture4', csp='Non-Color')    
    if eye_color!=None:
        eye_mat.node_tree.nodes['RGB'].outputs[0].default_value = eye_color

    head_mat=replace_mat(head, bpy.data.materials['Head'].copy(), 'Head_' + suffix)
    set_tex(head, 'Image Texture', 'head', 'MainTex', alpha='NONE')
    set_tex(head, 'Image Texture.002', 'head', 'DetailMainTex', csp='Non-Color')
    set_tex(head, 'Image Texture.003', 'head', 'DetailGlossMap', csp='Non-Color')
    set_tex(head, 'Image Texture.007', 'head', 'BumpMap_converted', csp='Non-Color')
    if body['Boy']>0.0:
        # No bump map 2
        head_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0
        head_mat.node_tree.nodes['Value.003'].outputs[0].default_value=1.0 # Scale for textured gloss
        head_mat.node_tree.nodes['Math.002'].inputs[1].default_value = 0.850 # Subtract constant for textured gloss
        head_mat.node_tree.nodes['Vector Math.003'].inputs[3].default_value = 5.0 # UV coordinate scale for textured gloss
    else:
        if not set_tex(head, 'Image Texture.006', 'head', 'BumpMap2_converted', csp='Non-Color'):
            head_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0
    #head_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    set_tex(head, 'Image Texture.001', 'head', 'Texture3', csp='Non-Color')
    if hair_color!=None:
        head_mat.node_tree.nodes['RGB'].outputs[0].default_value = hair_color

    replace_mat(tang, bpy.data.materials['Tongue'].copy(), 'Tongue_' + suffix)
    set_tex(tang, 'Image Texture', 'tang', 'MainTex')
    set_tex(tang, 'Image Texture.001', 'tang', 'BumpMap_converted', csp='Non-Color')
    set_tex(tang, 'Image Texture.002', 'tang', 'DetailGlossMap', csp='Non-Color')

    replace_mat(tooth, bpy.data.materials['Teeth'].copy(), 'Teeth_' + suffix)
    set_tex(tooth, 'Image Texture', 'tooth', 'MainTex')
    set_tex(tooth, 'Image Texture.001', 'tooth', 'BumpMap_converted', csp='Non-Color')

    replace_mat(body, bpy.data.materials['Torso'].copy(), 'Torso_' + suffix)
    set_tex(body, 'Image Texture', 'body', 'MainTex', alpha='NONE')
    set_tex(body, 'Image Texture.005', 'body', 'DetailGlossMap', csp='Non-Color')
    set_tex(body, 'Image Texture.002', 'body', 'BumpMap_converted', csp='Non-Color')
    set_tex(body, 'Image Texture.003', 'body', 'BumpMap2_converted', csp='Non-Color')
    #body_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    #body_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0
    set_tex(body, 'Image Texture.001', 'body', 'Texture2', csp='Non-Color')    

    replace_mat(nails, bpy.data.materials['Nails'].copy(), 'Nails_' + suffix)
    for ch in arm.children:
        x=ch.name
        obj = bpy.data.objects[x]
        mesh = obj.data
        if (bpy.data.objects[x].type!='MESH' 
                or ('Prefab ' in x) \
                or ('Material ' in x)):
            continue
        elif ('hair' in x) or (len(bpy.data.objects[x].data.materials)>0 \
                and 'hair' in bpy.data.objects[x].data.materials[0].name):
            print('Texturing', x, 'as hair')
            m = mesh.materials[0]
            n = m.name
            if '.' in n:
                n = n.split('.')[0]   
            mat=replace_mat(obj, bpy.data.materials['test_hair'].copy(), 'hair_' + suffix)                                 
            set_tex(obj, 'Image Texture', n, 'MainTex', csp='Non-Color')
            set_tex(obj, 'Image Texture.001', n, 'BumpMap_converted', csp='Non-Color')
            if hair_color!=None:
                mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = hair_color
        elif obj.type=='MESH' and not obj in body_parts:
            if len(mesh.materials)>1:
                print('Not trying to texture', x, ' - too many materials')
                continue
            print('Trying to texture', x, 'as clothing')
            m = mesh.materials[0]
            n = m.name
            if '.' in n:
                n = n.split('.')[0]            
            mat=replace_mat(obj, bpy.data.materials['Clothing'].copy(), 'clothing_' + suffix)                                 
            set_tex(obj, 'Image Texture', n, 'MainTex', csp='Non-Color')
            set_tex(obj, 'Image Texture.001', n, 'DetailGlossMap', csp='Non-Color')
            if not set_tex(obj, 'Image Texture.002', n, 'OcclusionMap', csp='Non-Color'):
                # Item does not support clothes damage
                mat.node_tree.nodes['Value'].outputs[0].default_value=-0.01

def fixup_head(body):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects[body["o_head"]]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles()

def fixup_torso(body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    join_meshes([body.name, body["nails"]], body.name)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles(use_unselected=True)

def stitch_head_to_torso(body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meshes=[body.name,body['o_head'],body['o_eyebase_L'],body['o_eyebase_R'],body['o_eyelashes'],body['o_eyeshadow']]
    join_meshes(meshes, body.name)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles(threshold=0.015, use_unselected=True)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_tools(mode='RESET')
    bpy.ops.mesh.select_all(action='DESELECT')
    
def import_bodyparts():
    if wipe_scene:
        for bpy_data_iter in (bpy.data.objects, bpy.data.meshes):
            for id_data in bpy_data_iter:
                if  id_data.name!="Cube" and id_data.name!="Material Cube" and not id_data.name.startswith('Prefab '):
                    bpy_data_iter.remove(id_data)
    try:
        bpy.ops.import_scene.fbx(filepath=fbx)
    except:
        return False, None, None
    if not 'Armature' in bpy.data.objects:
        return False, None, None
    arm = bpy.data.objects['Armature']
    
    boy = False
    bn=None
    for x in arm.children:
        if x.name.startswith('o_body_cm'):
            boy = True
            bn = x.name
            break
        elif x.name.startswith('o_body_cf'):
            bn = x.name
            break
    if bn==None:
        print('Could not find the body mesh in this fbx')
        return False, None, None
    body = bpy.data.objects[bn]
    body['Boy']=1.0 if boy else 0.0

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
    #if (not boy) and bn+'.001' in bpy.data.objects:
    #    bpy.data.objects[bn+'.001'].name=bn
    #if not 'o_head' in arm.children.keys(): #bpy.data.meshes:
    #    heads=[x for x in arm..keys() if x.startswith('o_head')]
    #    if len(heads)==1:
    #        bpy.data.meshes[heads[0]].name='o_head'
    for x in bodyparts:
        for y in arm.children: #bpy.data.meshes.keys(): #sc.objects.keys():
            if y.name==x or y.name.startswith(x+'.'):
                body[x]=y.name #bpy.data.meshes[y]
            
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.scale_clear()                
    #bpy.ops.object.rotation_clear()
    return True, arm, body


def load_unity_dump(dump):
    bone_pos={}
    bone_w2l={}
    bone_parent={}
    root_pos=[0,0,0]
    local_pos={}
    name=''
    f=open(dump,'r').readlines()
    f=[x.strip() for x in f]
    if 'cf_J_Root' in f[0]:
        f[0]='cf_J_Root--UnityEngine.GameObject'
    else:
        print(f[0])
        MessageBox('ERROR: Could not parse the dump file')
        return None, None

    for n in range(len(f)):
        x=f[n]
        if x.endswith('--UnityEngine.GameObject'):
           name=x.split('-')[0]
           #print(name)
        elif x.startswith('@parent<Transform>'):
            bone_parent[name]=x.split()[2]
        elif (x.startswith('@localToWorldMatrix<Matrix4x4>') \
            or x.startswith('@worldToLocalMatrix<Matrix4x4>')):
            if not name.startswith('cf_') \
                and not name.startswith('cm_') \
                and not name.startswith('p_c'):
                continue
            m=[
                x.split()[-4:],
                f[n+1].split()[-4:],
                f[n+2].split()[-4:],
                f[n+3].split()[-4:] ]
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
                if m[0][0]==0.0 and m[0][1]==0.0 and m[0][2]==0.0:
                    m[0][0]=0.0010
                if m[1][0]==0.0 and m[1][1]==0.0 and m[1][2]==0.0:
                    m[1][1]=0.0010
                if m[2][0]==0.0 and m[2][1]==0.0 and m[2][2]==0.0:
                    m[2][2]=0.0010
                bone_pos[name]=Matrix(m)
                if bone_parent[name] in bone_pos:
                    local_pos[name]=bone_pos[bone_parent[name]].inverted() @ bone_pos[name]
                else:
                    local_pos[name] = bone_pos[name]
    return bone_pos, local_pos

def matrix_world(armature_ob, bone_name):
    local = armature_ob.data.bones[bone_name].matrix_local
    basis = armature_ob.pose.bones[bone_name].matrix_basis
    parent = armature_ob.pose.bones[bone_name].parent
    if parent == None:
        return  local @ basis
    else:
        parent_local = armature_ob.data.bones[parent.name].matrix_local
        mw = matrix_world(armature_ob, parent.name)
        try:
            return  mw @ (parent_local.inverted() @ local) @ basis
        except:
            print('ERROR: non invertible matrix in matrix_world', bone_name, parent_local)
            return mw @ local @ basis

def absmat(x):
    return max([abs(x[y][z]) for y in range(4) for z in range(4)])

def snap(x):
    for y in range(2):
        for z in range(4 if y==1 else 3):
            if abs(x[y][z])<0.0003:
                x[y][z]=0.0
    if abs(x[1][0]-1)<0.0003:
        x[1][0]=1.0
    for z in range(3):
        if abs(x[2][z]-1)<0.0003:
            x[2][z]=1.0
    return x

def reset_pose_one_bone(x):        
    b = bpy.data.objects['Armature'].data.bones[x]
    if x in bone_pos:
        bpy.context.object.data.bones.active = b
        bpy.context.active_pose_bone.matrix_basis = Matrix()
    for x in b.children.keys():
        reset_pose_one_bone(x)


def dump_one_bone(x, a, of):
    arm = bpy.data.objects[a]
    b = arm.data.bones[x]
    #if x in bone_pos:
    if True:
        bpy.context.object.data.bones.active = b
        local = arm.data.edit_bones[x].matrix
        s = x+(' %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
            local[1][0], local[1][1], local[1][2], local[1][3],
            local[2][0], local[2][1], local[2][2], local[2][3],
            local[3][0], local[3][1], local[3][2], local[3][3]))
        of.write(s)        
    for x in b.children.keys():
        dump_one_bone(x, a, of)

def dump_one_bone_current(x, a, of):
    arm = bpy.data.objects[a]
    b = arm.data.bones[x]
    if x in bone_pos:
        bpy.context.object.data.bones.active = b
        local = arm.data.bones[x].matrix_local
        s = x+('local %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
            local[1][0], local[1][1], local[1][2], local[1][3],
            local[2][0], local[2][1], local[2][2], local[2][3],
            local[3][0], local[3][1], local[3][2], local[3][3]))
        of.write(s)        
        local = arm.pose.bones[x].matrix_basis
        s = x+('basis %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
            local[1][0], local[1][1], local[1][2], local[1][3],
            local[2][0], local[2][1], local[2][2], local[2][3],
            local[3][0], local[3][1], local[3][2], local[3][3]))
        of.write(s)        
        local = matrix_world(arm, x) 
        s = x+(' %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
            local[1][0], local[1][1], local[1][2], local[1][3],
            local[2][0], local[2][1], local[2][2], local[2][3],
            local[3][0], local[3][1], local[3][2], local[3][3]))
        of.write(s)        
    for x in b.children.keys():
        dump_one_bone_current(x, a, of)
        
#  This long table classifies all the various bones inside the armature, allowing us to distinguish between
# variables we change to customize the character (e.g. game 'shoulder width'), variables we change to pose the character,
# variables that the game sets according to some internal rules, and variables we should not touch.
# 
# 'f': Pure FK bone. Only rotations allowed. Shorthand for 'xxxfxxx'
# 'c': Constrained helper bone. Position constrained by internal rules, no direct manipulation. Shorthand for 'xxxcxxx'.
# '?': unclassified or ignored
# 7-letter codes: 3 letters for offset (x/y/z), 1 letter for rotation, 3 letters for scale.
# 
# 'x': locked at default value (1 for quat w and scale, 0 for other dof), no direct manipulation.
# 'c': constrained by other attributes, no direct manipulation, must reset to default when loading pose
# 's': soft, affects character's intrinsic shape
# 'f': FK, affects character's pose
# 'i': seeing small numbers here, assume they may be ignored; flag and report if seeing a large value
# 'u': potentially large numbers of unknown origin with nontrivial effect on mesh
# 
# Most 'u's may be "static constraints": small, constant for the same character, not settable directly from UI.
#
# some notable unexplained dynamic dof: 
# LegUp01_L/R rotation (along 1 axis)
# Mune00 rotation 
#
bone_classes={
'cf_N_height': 'xxxxsss', #overall body scale
'cf_J_Kosi01_s': 'xxxxsxs',
'cf_J_Kosi02_s': 'xxxxsxs',
'cf_J_Kokan': 'xxxxsss',

'cf_J_SiriDam_': 'c',
'cf_J_Siri_s_': 'sssssss', # I'm positive the game does not give me this much control (9 deg of freedom) over butt cheeks
'cf_J_Siriopen_s_': '?', # effect unclear - my meshes don't even have vgroups for it
'cf_J_Ana': 'sssssss',  # same as with cf_J_Siri_s_
'cf_J_LegUpDam_': 'xxxcxxx',
'cf_J_LegUpDam_s_': 'xxxxsxs',

'cf_J_LegUp00_': 'sssfsss', # game allows legup00 offset to travel along 1 axis only - offsets y and z are proportional to x
'cf_J_LegUp01_': 'xxxuxxx',
'cf_J_LegUp01_s_': 'uxuusxs', # no dynamic constraint
'cf_J_LegUp02_': 'xxxcxxx',
'cf_J_LegUp02_s_': 'xxxxsxs', 
'cf_J_LegUp03_s_': 'xxxxsxs', 

'cf_J_LegKnee_dam_': 'c',
'cf_J_LegKnee_low_s_': 'xxucsss', # no dynamic constraint
'cf_J_LegKnee_back_': 'xxxcxxx',  # r - dynamic constraint
'cf_J_LegKnee_back_s_': 'xxsxsss', # no dynamic constraint

'cf_J_LegLow01_s_': 'ixuisxs', # no dynamic constraint
'cf_J_LegLow02_s_': 'xxxxsxs', # no dynamic constraint
'cf_J_LegLow03_s_': 'uxuusxs', # no dynamic constraint

'cf_J_Foot01_': 'xxxfsss',
'cf_J_Foot02_': 'f',
'cf_J_Toes01_': 'f',
'cf_J_Toes_Hallux1_': 'sssfsss',
'cf_J_Toes_Long1_': 'sssfsss',
'cf_J_Toes_Middle1_': 'sssfsss',
'cf_J_Toes_Ring1_': 'sssfsss',
'cf_J_Toes_Pinky1_': 'sssfsss',

'cf_J_Spine01_s': 'uuuxsss', # not dynamic
'cf_J_Spine02_s': 'xxxxsxs', 
'cf_J_Spine03_s': 'xxxxsxs', # 

'cf_J_Shoulder_': 'f',
'cf_J_Shoulder02_s_': 'sxxxsss',# presumably, same x offset as on cf_J_ArmUp00
'cf_J_ArmUp00_': 'sxufsss', # not dynamic
'cf_J_ArmUp01_dam_': 'xxxcxxx', 
'cf_J_ArmUp02_dam_': 'xxxcxxx',
'cf_J_ArmUp01_s_': 'uuuuxss',  # no dynamic constraint
'cf_J_ArmUp02_s_': 'xixxxss',
'cf_J_ArmUp03_s_': 'xxxxxss',
'cf_J_ArmElbo_dam_01_': 'cxccxxx', # dynamic constraint on position and rotation
'cf_J_ArmElbo_low_s_': 'xxxxxss',
'cf_J_ArmElboura_dam_': 'xxxcxxx',
'cf_J_ArmElboura_s_': 'xxsxxxx',
'cf_J_ArmLow01_': 'f',
'cf_J_ArmLow01_s_': 'xxxxxss',
'cf_J_ArmLow02_s_': 'xxxxxss',
'cf_J_ArmLow02_dam_': 'xxxcxss',
'cf_J_Hand_Wrist_dam_': 'xxxcxxx',
'cf_J_Hand_': 'f',
'cf_J_Hand_s_': 'xxxxsss',
'cf_J_Hand_Wrist_s_': 'xxxxxss',
'cf_J_Hand_dam_': 'c',

'cf_J_Hand_Index01_': 'f',
'cf_J_Hand_Index02_': 'f',
'cf_J_Hand_Index03_': 'f',
'cf_J_Hand_Little01_': 'f',
'cf_J_Hand_Little02_': 'f',
'cf_J_Hand_Little03_': 'f',
'cf_J_Hand_Middle01_': 'f',
'cf_J_Hand_Middle02_': 'f',
'cf_J_Hand_Middle03_': 'f',
'cf_J_Hand_Ring01_': 'f',
'cf_J_Hand_Ring02_': 'f',
'cf_J_Hand_Ring03_': 'f',
'cf_J_Hand_Thumb01_': 'f',
'cf_J_Hand_Thumb02_': 'f',
'cf_J_Hand_Thumb03_': 'f',

'cf_J_Hips': 'ffffxxx',
'cf_J_Kosi01': 'f',
'cf_J_Kosi02': 'f',
'cf_J_LegLow01_': 'f',
'cf_J_Spine01': 'f',
'cf_J_Spine02': 'f',
'cf_J_Spine03': 'f',
'cf_J_Mune00': 'xccfxxx',
'cf_J_Neck': 'f',
'cf_J_Head': 'f',

'cf_J_Mune00_': 'iuuuxxx',
'cf_J_Mune00_t_':'sssssss',
'cf_J_Mune00_s_':'sssssss',
'cf_J_Mune00_d_':'sxssxxx',
'cf_J_Mune01_': 'xiiixxx',
'cf_J_Mune01_s_': 'xssssss',
'cf_J_Mune01_t_': 'sxssxxx',
'cf_J_Mune02_': 'xiiixxx',
'cf_J_Mune02_s_': 'xisssss',
'cf_J_Mune02_t_': 'xxssxxx',
'cf_J_Mune03_': 'xiixxxx',
'cf_J_Mune03_s_': 'xxsxsss',
'cf_J_Mune04_s_': 'xxsxsss',
'cf_J_Mune_Nip01_s_': 'xxsxsss',
'cf_J_Mune_Nip02_s_': 'xxixsss',

#todo: where's the head offset
'cf_J_FaceBase': 'xxxxsxs',
'cf_J_Head_s': 'xxxxsss', 
'cf_J_FaceLowBase': 'xxuxxxx',
'cf_J_FaceLow_s': 'xxxxsxx',
'cf_J_CheekLow_': 'sssxxxx',
'cf_J_CheekUp_': 'sssxxxx',
'cf_J_Chin_rs': 'xsissss',
'cf_J_ChinTip_s': 'xuuxsss',
'cf_J_ChinLow': 'xsxxxxx',
'cf_J_MouthBase_tr': 'xssxxxx',
'cf_J_MouthBase_s': 'xxxxssx',
'cf_J_Mouth_': 'xsxsxxx', # offset Y moves the mouth corner up/down, quat Z turns the mouth corner
'cf_J_MouthLow': 'xssxsxx', # position & width of the lower lip
'cf_J_Mouthup': 'xuxxxxx',
'cf_J_MouthCavity': 'xxixxxx',
'cf_J_EarLow_': 'xsxxsss',
'cf_J_EarUp_': 'sssisss',
'cf_J_EarBase_s_': 'xxxssss',
'cf_J_FaceUp_ty': 'xsxxxxx', # upper face height (moves eyes, ears and everything above them up/down)
'cf_J_FaceUp_tz': 'xxsxxxx', # upper face depth (moves eyes and eyebrows forward/back)
# the chain is t -> s -> r -> eyepos_rz -> look
'cf_J_Eye_t_': 'ssssxxx', # offset moves the eye; quat z rotates the eyelids around the forward-back axis
'cf_J_Eye_s_': 'xxxxssx', # scale x,y scales the eye
'cf_J_Eye_r_': 'xxxsxxx', # quat y rotates the eyelids around the vertical axis; quat z would rotate around the forward-back axis
'cf_J_EyePos_rz_': 'xxxuxxx', # observed nontrivial quat z - rotating the eyeball around the forward axis
'cf_J_look_': 'f',

'cf_J_Eye01_': 'xxxcxxx', # how does the game set rotation?
'cf_J_Eye02_': 'xxxcxxx', # how does the game set rotation?
'cf_J_Eye03_': 'iiicxxx', # how does the game set rotation?
'cf_J_Eye04_': 'xxxcxxx', # how does the game set rotation?
'cf_J_NoseBase_trs': 'xssxxxx',
'cf_J_NoseBase_s': 'xxxssss', # rotation: nose angle, X-axis only
'cf_J_Nose_t': 'xissxxx',  # offset z moves nose (minus bridge) forward/back; quat x turns nose up/down
'cf_J_Nose_tip': 'xssxsss', # moves and scales the nose tip
'cf_J_NoseWing_tx_': 'ssssxxx', # offset moves the nostril; rotation twists the nostril in odd ways
'cf_J_NoseBridge_t': 'xsssxxx', # nose bridge vertical position (y), height (z), & shape (r)
'cf_J_NoseBridge_s': 'xxxxsxx', # nose bridge width
'cf_J_Neck_s': 'xxxxsss', # how does the game set y-scale?

'cf_J_EarRing_': '?',
}

def bone_class(x, comp):
    c=None
    if x.startswith('cf_J_Vagina') or x.startswith('cf_J_Legsk'):
        return '?'
    elif x in bone_classes:
        c = bone_classes[x]
    elif x[:-1] in bone_classes:
        c = bone_classes[x[:-1]]
    if c=='?':
        return '?'
    if c=='f':
        c='xxxfxxx'
    if c=='c':
        c='xxxcxxx'
    if c!=None and len(c)!=1 and len(c)!=7:
        print('ERROR: illegal bone class ', c, x)
    if c==None:
        return c
    if comp=='offset':
        return c[:3]
    elif comp=='rotation':
        return c[3]
    elif comp=='scale':
        return c[4:]
    else:
        print('Invalid bone class component ', comp, 'requested')
        return None

def recompose(v):
        T = Matrix.Translation(v[0])
        R = v[1].to_matrix().to_4x4()
        S = Matrix.Diagonal(v[2].to_4d())            
        return T @ R @ S

# flags: 1 - FK, 2 - soft, 3 - everything
def load_pose(a, fn, flags=3):
    #global deformed_rig
    arm = bpy.data.objects[a]
    if arm["default_rig"]==None:
        print('Operation unsupported on a fallback-mode rig')
        return    
    default_rig=arm["default_rig"]
    deformed_rig=arm["deformed_rig"]
    bpy.ops.object.mode_set(mode='OBJECT')    
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    idx_map={'offset':0,'rotation':1,'scale':2}
    f=open(fn, "r").readlines()
    if 'UnityEngine' in f[0]:
        _, v=load_unity_dump(fn)
        for x in v:
            if x in default_rig \
            and x in arm.pose.bones \
            and arm.pose.bones[x].parent!=None \
            and arm.pose.bones[x].parent.name in default_rig:
                default_delta = Matrix(default_rig[arm.pose.bones[x].parent.name]).inverted() @ Matrix(default_rig[x])
                v[x] = default_delta.inverted() @ v[x]                
        f={}
        for x in v:
            y=v[x].decompose()
            f[(x,'offset')]=y[0]
            f[(x,'rotation')]=y[1]
            f[(x,'scale')]=y[2]
    else:
        f=[x.strip().split() for x in f]
        f={(x[0],x[1]): [float(y) for y in x[2:]] for x in f}

    null_pose=(Vector(), Quaternion(), Vector([1,1,1]))
    ch=('offset','rotation','scale')
    for x in arm.pose.bones.keys():
        pose = list(arm.pose.bones[x].matrix_basis.decompose())
        for y in range(3):
            if (x,ch[y]) in f:
                op = f[(x,ch[y])]
            else:
                op = null_pose[y]               
            c=bone_class(x, ch[y])
            for n in range(len(op)):
                if (c=='?') or (c==None) \
                    or ((flags&1) and c[n if y!=1 else 0] in ('f',)) \
                    or ((flags&2) and c[n if y!=1 else 0] in ('s','i','u')):
                        pose[y][n]=op[n]
        arm.pose.bones[x].matrix_basis=recompose(pose)
        if flags & 2:
            # todo: ideally, deformed_rig should exclude FK bones (but that's too much work) 
            deformed_rig[x]=arm.pose.bones[x].matrix_basis.copy()
                        
def dump_pose(a, of, x='cf_J_Root'):
    arm = bpy.data.objects[a]
    b = arm.data.bones[x]
    bpy.context.object.data.bones.active = b
    local = arm.pose.bones[x].matrix_basis
    local = snap(local.decompose())
    changes=[0,0,0, 0,0,0,0]
    for n in range(3):
        if local[0][n]!=0:
            changes[n]=1
        if abs(local[0][n])>=0.010:
            changes[n]=2
        if local[1][1+n]!=0:
            changes[3]|=1
        if abs(local[1][1+n])>=0.010:
            changes[3]|=2
        if local[2][n]!=1:
            changes[n+4]=1
        if abs(local[2][n]-1)>=0.010:
            changes[n+4]=2
    comp_name=('offset','rotation','scale')
    for comp in range(3):
        c = bone_class(x, comp_name[comp])
        if comp==0:
            def_trans=Vector() 
        elif comp==1:
            def_trans=Quaternion()
        else:
            def_trans=Vector([1,1,1])
        if comp==1:
            changes=changes[3:]
        if comp==2:
            changes=changes[1:]
        if c==None and local[comp]!=def_trans:
            print('Nontrivial ', comp_name[comp], ' in unclassified bone ', x)
        elif c!='?' and c!=None:
            for n in range(1 if comp==1 else 3):
                if (c[n]=='x' and changes[n]!=0) or (c=='i' and (changes[n] & 2)):
                    print('Violated', comp_name[comp], 'constraint', n, 'in bone ', x)
    if local[0]!=Vector():
        s=x+' offset %.4f %.4f %.4f\n' % (local[0][0], local[0][1], local[0][2])
        of.write(s)        
    if local[1]!=Quaternion():
        s=x+' rotation %.4f %.4f %.4f %.4f\n' % (local[1][0], local[1][1], local[1][2], local[1][3])
        of.write(s)        
    if local[2]!=Vector([1,1,1]):
        s=x+' scale %.4f %.4f %.4f\n' % (local[2][0], local[2][1], local[2][2])
        of.write(s)        
#        s = x+('basis %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
#            local[1][0], local[1][1], local[1][2], local[1][3],
#            local[2][0], local[2][1], local[2][2], local[2][3],
#            local[3][0], local[3][1], local[3][2], local[3][3]))
    for x in b.children.keys():
        dump_pose(a, of, x)

bone_transforms={}
def reshape_mesh_one_bone(x, arm, dic=None):        
    global bone_transforms
    b = arm.data.bones[x]
    if dic==None:
        dic=bone_pos
    if x in dic:
        bpy.context.object.data.bones.active = b
        local = arm.data.bones[x].matrix_local
        mw = matrix_world(arm, x)
        target = Matrix(dic[x])
        arm.pose.bones[x].matrix_basis = arm.pose.bones[x].matrix_basis @ mw.inverted() @ target
    for x in b.children.keys():
        reshape_mesh_one_bone(x, arm, dic)

def reset_pose_one_bone(x, ob):        
    b = ob.data.bones[x]
    if x in bone_pos:
        bpy.context.object.data.bones.active = b
        bpy.context.active_pose_bone.matrix_basis = Matrix()
    for x in b.children.keys():
        reset_pose_one_bone(x, ob)

def read_rigfile_from_textblock(x):
    txt=bpy.data.texts[x].lines
    f=[x.body.strip().split() for x in txt]
    f=[[x[0], [float(x[y]) for y in range(1, 17)]] for x in f]
    f={x[0]:Matrix([x[1][:4],x[1][4:8],x[1][8:12],x[1][12:16]]) for x in f}
    return f

def read_rigfile(x):
    default_rig=open(x)
    default_rig=default_rig.readlines()
    default_rig=[x.strip().split() for x in default_rig]
    default_rig=[[x[0], [float(x[y]) for y in range(1, 17)]] for x in default_rig]
    default_rig={x[0]:Matrix([x[1][:4],x[1][4:8],x[1][8:12],x[1][12:16]]) for x in default_rig}
    return default_rig

def write_rigfile(v, x):
    of=open(x, "w")
    for y in v:
        local=v[y]
        s = y+(' %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
            local[1][0], local[1][1], local[1][2], local[1][3],
            local[2][0], local[2][1], local[2][2], local[2][3],
            local[3][0], local[3][1], local[3][2], local[3][3]))
        of.write(s)        
    of.close()
        
def score_deform(b, depsgraph, undeformed):
    bpy.ops.object.mode_set(mode='EDIT')  
    bpy.ops.object.mode_set(mode='OBJECT')  
    bm = bmesh.new()
    bm.from_object( b, depsgraph )
    bm.verts.ensure_lookup_table()
    n = len(bm.verts)
    errors=[bm.verts[x].co - undeformed[x].co for x in range(n)]
    bm.free()
    return errors


def find_nearest(mesh, v, cands):
    a=cands[0]
    for x in cands:
        if (mesh.vertices[x].co-v).length<(mesh.vertices[a].co-v).length:
            a=x
    return a
    
# Given an object 'b' that is parented to an armature in a nontrivial pose, and a reference
# object with the same number of vertices, deforms the rest position of 'b' until it matches 'b2' in pose position.
def solve_for_deform(b, b2, shape_key=None, counter=None, scale=Vector([1,1,1])):
    npass=0
    nfail=0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.objects.active = b    
    print(b.name, shape_key)
    intl_step=1.0
    baseline=True
    if b.data.shape_keys!=None:
        basis=b.data.shape_keys.key_blocks['Basis'].data
        undeformed_basis=b2.data.shape_keys.key_blocks['Basis'].data
        if shape_key==None:
            np, fail=solve_for_deform(b, b2, 'Basis')
            npass = np
            nfail = fail
            c=0
            box1 = bbox(basis)
            box2 = bbox(undeformed_basis)
            dim1=[box1[1][0]-box1[0][0],box1[1][1]-box1[0][1],box1[1][2]-box1[0][2]]
            dim2=[box2[1][0]-box2[0][0],box2[1][1]-box2[0][1],box2[1][2]-box2[0][2]]
            scale=Vector([dim1[0]/dim2[0],dim1[1]/dim2[1],dim1[2]/dim2[2]])
            for x in b.data.shape_keys.key_blocks:
                if x.name=='Basis':
                    continue
                np, fail=solve_for_deform(b, b2, x.name, c, scale)
                npass+=np
                nfail+=fail
                c+=1
            for x in b.data.shape_keys.key_blocks:
                x.value=0.0
            return npass, nfail
        else:
            target=b.data.shape_keys.key_blocks[shape_key].data
            undeformed=b2.data.shape_keys.key_blocks[shape_key].data
            b.active_shape_key_index=b.data.shape_keys.key_blocks.find(shape_key)
            for x in b.data.shape_keys.key_blocks:
                x.value=0.0
            b.data.shape_keys.key_blocks[shape_key].value=1.0
            if shape_key!='Basis':
                baseline=False
                n=len(target)
                for x in range(n):
                    target[x].co=basis[x].co+(undeformed[x].co-undeformed_basis[x].co)*scale
    else:
        target=b.data.vertices
        undeformed=b2.data.vertices
    n = len(target)
    for attempt in range(2 if baseline else 1):
        errors = score_deform(b, depsgraph, undeformed)
        frozen=[(1 if x.length<0.0001 else 0) for x in errors]
        if attempt==1:
            # if we didn't get everything first time, try again but using solved vertexes as hints
            for x in range(len(errors)):
                if not frozen[x]:
                    nearest=None
                    for y in range(len(errors)):
                        if frozen[y] and (nearest==None or (undeformed[y].co-undeformed[x].co).length < (undeformed[nearest].co-undeformed[x].co).length):
                            nearest=y
                    target[x].co=target[nearest].co + (undeformed[x].co-undeformed[nearest].co)
            errors = score_deform(b, depsgraph, undeformed)
        dirs=errors[:]
        steps=[intl_step]*n
        age=[0]*n
        residual=sum([x.length for x in errors])
        print('Initial residual vertex error ', residual/n)
        last_max_residual_pos=-1
        last_max_residual=0.0
        solved=frozen[:]
        live=n-sum(frozen)
        for p in range(160 if baseline else 20):
            vsave = [target[x].co.copy() for x in range(n)]
            for x in range(n):
                if frozen[x]:
                    continue
                #if age[x]>=2:
            for x in range(n):
                if frozen[x]:
                    continue
                target[x].co=vsave[x]+dirs[x]*steps[x]*(-1 if (age[x]==0) else 1)
            errors2 = score_deform(b, depsgraph, undeformed)
            moved=0
            mean_step=0
            max_residual=0.0
            max_residual_pos=-1
            for x in range(n):
                if frozen[x]:
                    continue
                if errors2[x].length<errors[x].length:
                    delta=errors[x]-errors2[x]
                    delta/=delta.length
                    delta*=errors[x].length
                    cos_phi=delta.dot(errors[x])/(errors[x].length*delta.length)
                    beta=-0.5
                    if live<0.05*n:
                        beta = 0.25*((p%5)-2)
                    dirs[x]=errors2[x]+beta*delta*(1.0-cos_phi)
                    mean_step+=steps[x]
                    if steps[x]<1.3:
                        steps[x]*=1.25
                    errors[x]=errors2[x]
                    age[x]=0
                    moved+=1
                    if errors[x].length<0.0001:
                        frozen[x]=1
                        solved[x]=1
                        live-=1
                else:
                    age[x]+=1
                    if steps[x]>0.01:
                        target[x].co=vsave[x]
                        steps[x]/=2
                    else:
                        if age[x]<10:
                            target[x].co=vsave[x]
                            dirs[x]=Vector([dirs[x][1]*math.sin(p),dirs[x][2]*math.cos(p),dirs[x][0]])
                            steps[x]=intl_step
                        else:
                            # move anyway
                            age[x]=0
                            errors[x]=errors2[x]
                            #frozen[x]=1
                            #live-=1
                if errors[x].length>max_residual:
                    max_residual=errors[x].length
                    max_residual_pos=x
            last_residual = residual
            last_max_residual = max_residual
            last_max_residual_pos = max_residual_pos
            residual=sum([x.length for x in errors])
            print("Pass ", p, ": residual vertex error %.6f %.6f, %.6f moved, " % (residual/n, max_residual, float(moved)/n), 
                'mean step %.3f' % (mean_step/max(moved,1)), ', ', live, 'live')
            npass+=1
            if max_residual<0.0001 or live==0:
                break  
        print(sum(solved), "/", n, " vertices solved")
        if sum(solved) in (0, n):
            break
    return npass, n-sum(solved)

# todo: fallback mode for custom meshes


def prettify_armature(arm):
    #arm = bpy.data.objects['Armature']
    #arm = bpy.context.view_layer.objects.active
    bpy.ops.object.mode_set(mode='OBJECT')  
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')  
    """
    BONE LAYERS
    General principles:
    0-14: anything the user needs to pose the character
    15: anything that seems totally useless, and anything unclassified
    16-30: soft tissues (not used to pose, but may be used to customize the character)
    31: all bones
    
    There's no IK yet but a layer may need to be carved out for IK bones.
    
    Currently in use:    
    0: left leg FK
    1: right leg FK
    2: left arm FK
    3: right arm FK
    4: left hand FK
    5: right hand FK
    6: torso
    7: toes
    12: face
    13: breasts
    14: groin  
    16: left leg soft
    17: right leg soft
    18: left arm soft
    19: right arm soft
    22: torso soft
    28: face soft
    """
    for x in bpy.context.object.data.edit_bones:
        array=[False]*32
        array[15] = True
        side = (1 if x.name[-1]=='R' else 0)
        #if x.name in ['cf_J_Root', 'cf_N_height', 'cf_J_Hips', 'cf_J_Kosi03', 'cf_J_Kosi03_s']:
        #    array[15]=True
        #if x.name[:-1] in ['cf_J_ShoulderIK_', 'cf_J_Siriopen_s_']:
        #    array[15]=True
        if x.name[:-1] in ['cf_J_LegUp00_', 'cf_J_LegLow01_', 'cf_J_LegLowRoll_', 'cf_J_Foot01_', 'cf_J_Foot02_', 
            ]:
            array[0+side]=True # Leg FK
        if x.name[:-1] in ['cf_J_LegLow01_s_', 'cf_J_LegLow02_s_', 'cf_J_LegUp03_s_', 'cf_J_LegKnee_back_',
            'cf_J_LegKnee_back_s_', 'cf_J_Siri_s_', 'cf_J_LegKnee_dam_', 'cf_J_LegKnee_low_s_', 'cf_J_LegUpDam_',
            'cf_J_LegUpDam_s_', 'cf_J_LegUp01_', 'cf_J_LegUp01_s_', 'cf_J_LegUp02_', 'cf_J_LegUp02_s_', 
            'cf_J_LegUp03_', 'cf_J_LegUp03_s_', 'cf_J_LegLow03_', 'cf_J_LegLow03_s_',
            'cf_J_SiriDam_', 'cf_J_Siri_', 'cf_J_SiriDam01_']:
            array[16+side]=True # Leg soft
        if x.name[:-1] in ['cf_J_Shoulder_', 'cf_J_ArmUp00_', 'cf_J_ArmLow01_', 'cf_J_Hand_']:
            array[2+side]=True # Arm FK
        if x.name[:-1] in ['cf_J_Shoulder02_s_', 'cf_J_ArmUp01_s_', 'cf_J_ArmUp02_s_', 'cf_J_ArmElbo_low_s_', 
            'cf_J_ArmUp03_s_', 'cf_J_ArmLow01_s_', 'cf_J_Hand_Wrist_s_', 'cf_J_Hand_s_',
            'cf_J_ArmUp01_dam_', 'cf_J_ArmUp02_dam_', 'cf_J_ArmUp03_dam_', 'cf_J_ArmElboura_dam_', 'cf_J_ArmElboura_s_', 
            'cf_J_ArmElbo_dam_01_', 'cf_J_ArmLow02_dam_', 'cf_J_ArmLow02_s_', 'cf_J_Hand_Wrist_dam_', 'cf_J_Hand_dam_']:
            array[18+side]=True # Arm soft
        if x.name in ['cf_J_Kosi02', 'cf_J_Kosi01', 'cf_J_Spine01', 'cf_J_Spine02', 'cf_J_Spine03', 'cf_J_Neck', 'cf_J_Head', 'cf_J_FaceBase', 'cf_J_FaceRoot', 'cf_J_Head_s' ]:
            array[6]=True # Torso
        if x.name in ['cf_J_Kosi02_s', 'cf_J_Kosi01_s', 'cf_J_Spine01_s', 'cf_J_Spine02_s', 'cf_J_Spine03_s', 'cf_J_Neck_s']:
            array[22]=True # Torso soft
        if x.name[:-1] in [
            'cf_J_Hand_Thumb01_', 'cf_J_Hand_Index01_',  'cf_J_Hand_Middle01_',  'cf_J_Hand_Ring01_',  'cf_J_Hand_Little01_', 
            'cf_J_Hand_Thumb02_', 'cf_J_Hand_Index02_',  'cf_J_Hand_Middle02_',  'cf_J_Hand_Ring02_',  'cf_J_Hand_Little02_', 
            'cf_J_Hand_Thumb03_', 'cf_J_Hand_Index03_',  'cf_J_Hand_Middle03_',  'cf_J_Hand_Ring03_',  'cf_J_Hand_Little03_']:
            array[4+side]=True
        if x.name[:-1] in ['cf_J_Toes01_', 'cf_J_Toes_Long1_', 'cf_J_Toes_Hallux1_', 'cf_J_Toes_Middle1_', 'cf_J_Toes_Ring1_', 'cf_J_Toes_Pinky1_', 
                           'cf_J_Toes_Long2_', 'cf_J_Toes_Hallux2_', 'cf_J_Toes_Middle2_', 'cf_J_Toes_Ring2_', 'cf_J_Toes_Pinky2_']:
            array[7]=True
        if 'Mune' in x.name:
            array[29 if ('_s' in x.name) else 13]=True                
        if x.name in ['cf_J_Ana', 'cf_J_Kokan']:
            array[14]=True
        if ('Vagina' in x.name) or ('_dan' in x.name):
            array[14]=True
        if x.name in ['cf_J_Mouthup', 'cf_J_MouthLow', 'cf_J_MouthMove']:
            array[12]=True
        if x.name[:-1] in ['cf_J_Mouth_', 'cf_J_Mayu_', 'cf_J_look_']:
            array[12]=True
        if x.name in ['cf_J_ChinLow', 'cf_J_Chin_rs', 'cf_J_ChinTip_s', 'cf_J_NoseTip', 'cf_J_NoseBase_s', 'cf_J_MouthBase_tr', 
            'cf_J_MouthCavity', 'cf_J_FaceLow_s', 'cf_J_MouthBase_s', 'cf_J_FaceLowBase', 'cf_J_FaceRoot_s', 
            'cf_J_NoseBridge_t', 'cf_J_FaceUp_ty', 'cf_J_FaceUp_tz', 'cf_J_Nose_t', 'cf_J_Nose_tip', 'cf_J_NoseBase_trs',
            'cf_J_Nose_r', 'cf_J_NoseBridge_s', 
            ]:
            array[28]=True
        if x.name[:-1] in ['cf_J_CheekLow_', 'cf_J_NoseWing_tx_', 'cf_J_Eye01_s_', 'cf_J_Eye02_s_', 'cf_J_Eye03_s_', 'cf_J_Eye04_s_',
            'cf_J_pupil_s_', 'cf_J_Eye_t_', 'cf_J_MayuTip_s_', 'cf_J_MayuMid_s_', 'cf_J_Eye_s_', 
            'cf_J_EarUp_', 'cf_J_EarBase_s_', 'cf_J_EarLow_', 
            'cf_J_Eye01_', 'cf_J_Eye02_', 'cf_J_Eye03_', 'cf_J_Eye04_', 
            'cf_J_eye_rs_', 'cf_J_EyePos_rz_', 'cf_J_Eye_r_', 'cf_J_CheekUp_', 
            ]:
            array[28]=True
        array[15] = not(any(array[:15]) or any(array[16:]))
        array[31] = True
        x.layers=array
    
        # It would be nice to have all bones correctly oriented, but replacing either tail or roll replaces the matrix we just uploaded, 
        # and redefines the axes. Which, in turn, messes with bone constraints. Let's just leave everything pointing up.

    #if not loaded:
    #    cs.serialize()

    bpy.ops.object.mode_set(mode='POSE')
    
    for n in ['cf_J_LegUp00', 'cf_J_LegLow01', 'cf_J_LegLowRoll',     
            'cf_J_look', 'cf_J_ArmLow01', 'cf_J_Hand'
            ]:
            arm.pose.bones[n+'_L'].rotation_mode='YZX'
            arm.pose.bones[n+'_R'].rotation_mode='YZX'

    # these all need to be redone
    limit_rotation_constraints=[
    # leave some freedom to twist (ideally, we'd just turn the hip, but the rig has its limits)
    ('cf_J_LegLow01', -170, 0, -45, 45, 0, 0), 
    ('cf_J_LegLowRoll', 0, 0, -60, 60, 0, 0),
    ('cf_J_ArmUp00', -100, 100, -90, 90, -100, 100),
    ('cf_J_ArmLow01', 0, 170, -30, 30, -90, 90),
    ('cf_J_Hand', -45, 45, -90, 90, -100, 100),
    ('cf_J_look', -30, 30, -30, 30, 0, 0),
    ]
    for c in limit_rotation_constraints:
        for s in ('L', 'R'):
            if not c[0]+'_'+s in arm.pose.bones:
                continue
            continue
            bone = arm.pose.bones[c[0]+'_'+s]
            bone.rotation_mode='XYZ'
            bpy.types.ArmatureBones.active = bone
            con = bone.constraints.new('LIMIT_ROTATION')
            con.min_x=c[1]*3.14159/180.
            con.max_x=c[2]*3.14159/180.
            con.min_y=c[3]*3.14159/180.
            con.max_y=c[4]*3.14159/180.
            con.min_z=c[5]*3.14159/180.
            con.max_z=c[6]*3.14159/180.
            con.use_limit_x=True
            con.use_limit_y=True
            con.use_limit_z=True
            con.owner_space='LOCAL'

    # TODO: these may not be 100% exact; there may be others
    constraints=[
        ('cf_J_LegUp00_', 'cf_J_SiriDam_', 'x', 0.5),
        ('cf_J_LegUp00_', 'cf_J_SiriDam_', 'yz', 0.2),
        ('cf_J_LegUp00_', 'cf_J_LegUpDam_', 'xz', 0.74),
        ('cf_J_LegLow01_', 'cf_J_LegKnee_dam_', 'x', 0.5),
        ('cf_J_LegLow01_', 'cf_J_LegKnee_back_', 'x', 1.0),
        # check this one in game - in default orientation, x rotation is not really valid for this bone
        ('cf_J_ArmUp00_', 'cf_J_ArmUp01_dam_', 'x', -0.66),  
        ('cf_J_ArmUp00_', 'cf_J_ArmUp02_dam_', 'x', -0.33),
        ('cf_J_ArmLow01_', 'cf_J_ArmElboura_dam_', 'yz', 0.578),
        ('cf_J_ArmLow01_', 'cf_J_ArmElbo_dam_01_', 'x', 0.6),
        ('cf_J_Hand_', 'cf_J_ArmLow02_dam_', 'y', 0.5),
        #('cf_J_Hand_', 'cf_J_Hand_Wrist_dam_', 'y', 1.0), double check this one
        ('cf_J_Hand_','cf_J_Hand_dam_', 'y', 0.65),
    ]
    for c in constraints:
        for s in ('L','R'):
            if not c[1]+s in arm.pose.bones:
                continue
            #continue
            bone = arm.pose.bones[c[1]+s]
            bone.rotation_mode='XYZ'
            bpy.types.ArmatureBones.active = bone
            con = bone.constraints.new('COPY_ROTATION')
            con.mix_mode='ADD'
            con.target=arm
            con.owner_space='LOCAL'
            con.target_space='LOCAL'
            con.euler_order='YZX' #not sure if this is universal
            con.subtarget=c[0]+s
            con.use_x=('x' in c[2])
            con.use_y=('y' in c[2])
            con.use_z=('z' in c[2])
            con.influence=abs(c[3])            
            con.invert_x=con.use_x and c[3]<0
            con.invert_y=con.use_y and c[3]<0
            con.invert_z=con.use_z and c[3]<0
        
    arm.data.display_type = 'STICK'
    arm.data.layers=[True,True,True,True] + [False]*28
    arm.show_in_front = True
    

def reshape_armature_fallback(): 
    #arm = bpy.data.objects['Armature']
    arm = bpy.context.view_layer.objects.active
    body = bpy.data.objects['body']
    arm["default_rig"]=None
    
    bone_pos, _ = load_unity_dump(dumpfilename)
    if bone_pos==None:
        print("Failed to load the unity dump, aborting")
        return
    #print(bone_pos)
    bpy.ops.object.mode_set(mode='OBJECT')    
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    def apply_offsets_bone(x, bone_pos):
        if x.name in bone_pos:
            x.matrix=bone_pos[x.name]
        for y in x.children:
            apply_offsets_bone(y, bone_pos)
    apply_offsets_bone(arm.data.edit_bones['cf_J_Root'], bone_pos)
    prettify_armature(arm)

def to_int(v):
    return (int(v.co[0]*100000.), int(v.co[1]*100000.), int(v.co[2]*100000.))

def from_int(v):
    return Vector([v[0]/100000., v[1]/100000., v[2]/100000.])

def try_load_solution_cache(b):
    try:
        f=open(path+"solution.cache","rb")
    except:
        return False
    buf = f.read()
    f.close()
    buf=struct.unpack('%si' % (len(buf)//4), buf)
    map={}
    for x in range(len(buf)//6):
        v1=(buf[x*6],buf[x*6+1],buf[x*6+2])
        v2=from_int(buf[x*6+3:x*6+6])
        map[v1]=v2

    solved=0
    unsolved=0
    for x in b:
        if x.data.shape_keys!=None:
            for k in x.data.shape_keys.key_blocks.keys():                
                source=bpy.data.objects[x["ref"]].data.shape_keys.key_blocks[k].data
                target=x.data.shape_keys.key_blocks[k].data
                for y in range(len(source)):
                    v=to_int(source[y])
                    if v in map:
                        target[y].co=map[v]
                        solved+=1
                    else:
                        unsolved+=1
        else:
            source = bpy.data.objects[x["ref"]].data.vertices
            target = x.data.vertices
            for y in range(len(source)):
                v=to_int(source[y])
                if v in map:
                    target[y].co=map[v]
                    solved+=1
                else:
                    unsolved+=1
    print("Loaded ", solved, "of", solved+unsolved, "vertex coordinates from cache")
    return unsolved==0

def save_solution_cache_one_obj(v, of):
    for x in v:
        s='%.6f %.6f %.6f\n' % (x.co[0], x.co[1], x.co[2])
        of.write(s)

def save_solution_cache(b):
    of=open(path+"solution.cache","wb")
    map={}
    for x in b:
        #n=b.name.split('.')[0]
        if x.data.shape_keys!=None:
            for k in x.data.shape_keys.key_blocks.keys():
                source=bpy.data.objects[x["ref"]].data.shape_keys.key_blocks[k].data
                target=x.data.shape_keys.key_blocks[k].data
                for y in range(len(source)):
                    v1=to_int(source[y])
                    v2=to_int(target[y])
                    map[v1]=v2
        else:
            source = bpy.data.objects[x["ref"]].data.vertices
            target = x.data.vertices
            for y in range(len(source)):
                v1=to_int(source[y])
                v2=to_int(target[y])
                map[v1]=v2
            #of.write(x.name+'\t'+str(len(x.data.vertices))+'\n')
            #save_solution_cache_one_obj(x.data.vertices, of)
    vf=[]
    for x in map:
        vf.extend([x[0],x[1],x[2],map[x][0],map[x][1],map[x][2]])
    buf = struct.pack('%si' % len(vf), *vf)
    of.write(buf)
    of.close()


def reshape_armature(arm, body): 
    #global deformed_rig
    #    arm = bpy.data.objects['Armature']
    boy = body['Boy']>0.0        
    bpy.ops.object.mode_set(mode='OBJECT')    
    #bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    
    # custom head mesh
    if not 'cf_J_CheekLow_L' in arm.data.edit_bones:
        print("Custom head mesh suspected, taking the fallback route");
        return reshape_armature_fallback()

    default_rig = read_rigfile_from_textblock('Rig_Male' if boy else 'Rig_Female')
    default_rig_head = read_rigfile_from_textblock('Rig_Male_Head' if boy else ('Rig_Female_Head1' if 'cf_J_pupil_s_R' in arm.data.edit_bones else 'Rig_Female_Head0'))
    for x in default_rig_head:
        m=default_rig_head[x]
        m[1][3]+=15.935
        m[2][3]+=-0.23
        default_rig[x]=m
        
    for x in arm.data.edit_bones:
        if not x.name in default_rig:
            #print(x.name, x.matrix)
            default_rig[x.name] = x.matrix
    #bpy.ops.object.mode_set(mode='EDIT')    

    # By default, cf_J_Hips is connected to cf_N_Height, but neither Spine01 nor Kosi01 are connected to cf_J_Hips 
    # (and therefore they use the same local transform matrix).
    arm.data.edit_bones['cf_J_Hips'].use_connect=False
    hips_position = (arm.data.edit_bones['cf_J_Spine01'].matrix.decompose()[0] + arm.data.edit_bones['cf_J_Kosi01'].matrix.decompose()[0])*0.5
    def apply_offsets_bone(x):
        o = Vector()
        y = x
        if x.name in default_rig:
            x.matrix=default_rig[x.name]
        for y in x.children:
            apply_offsets_bone(y)
                        
    apply_offsets_bone(arm.data.edit_bones['cf_J_Root'])

    # Set the rest position of 'arm' to "custom body" state
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')    

    body_parts=arm.children 

    # duplicate each item 
    bpy.ops.object.mode_set(mode='OBJECT')  
    for x in body_parts:
        bpy.ops.object.select_all(action='DESELECT')    
        x.select_set(True)
        bpy.context.view_layer.objects.active = x
        bpy.ops.object.duplicate()
        dup = bpy.context.object
        x["ref"] = dup.name

        # unparent duplicate from the rig
        bpy.ops.object.select_all(action='DESELECT')
        dup.select_set(True)
        bpy.context.view_layer.objects.active = dup
        bpy.ops.object.parent_clear(type='CLEAR')  


    bone_pos, _ = load_unity_dump(dumpfilename)
    if bone_pos==None:
        print("Failed to load the unity dump, aborting")
        return

     # Stretch 'arm' back to 'custom body' 
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')    
    reshape_mesh_one_bone('cf_J_Root', arm, bone_pos)
    deformed_rig={}
    for x in arm.pose.bones:
        deformed_rig[x.name]=x.matrix_basis.copy()

    arm["default_rig"]=default_rig
    arm["deformed_rig"]=deformed_rig
    #of=open("c:\\temp\\pose_" + name + ".txt","w")
    #dump_pose('cf_J_Root', 'Armature', of)
    #of.close()

    bpy.ops.object.mode_set(mode='OBJECT')  
    npass=0
    fail_vert=0

    if not try_load_solution_cache(body_parts):
        # Solve for undeformed mesh shape
        for b in body_parts:
            b2 = bpy.data.objects[b["ref"]]
            x, y = solve_for_deform(b, b2)
            npass += x
            fail_vert += y
        print("Done in ", npass, " passes, ", fail_vert, "failed vertices")
        save_solution_cache(body_parts)
    bpy.ops.object.select_all(action='DESELECT')
    for x in body_parts:
        bpy.data.objects[x["ref"]].select_set(True)
    bpy.ops.object.delete(use_global=False)
    prettify_armature(arm)


def vgroup(obj, name):
    id=obj.vertex_groups[name].index
    return [x for x in range(len(obj.data.vertices)) if id in [g.group for g in obj.data.vertices[x].groups]]

def vgroup2(obj, name1, name2):
    id1=obj.vertex_groups[name1].index
    id2=obj.vertex_groups[name2].index
    v=[x for x in range(len(obj.data.vertices)) if id1 in [g.group for g in obj.data.vertices[x].groups]]
    return [x for x in v if id2 in [g.group for g in obj.data.vertices[x].groups]]

def weighted_center(name):
    id=bpy.context.active_object.vertex_groups[name].index
    mesh=bpy.context.active_object.data
    vs=vgroup(bpy.context.active_object, name)
    s=Vector()
    wt=0.0
    for x in vs:
        for y in mesh.vertices[x].groups:
            if y.group==id:
                s+=mesh.vertices[x].co*y.weight
                wt+=y.weight
    return s*(1.0/wt)

def fix_mouth(obj):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = obj
    mesh=obj.data
    if not 'cf_J_CheekLow_L' in bpy.context.active_object.vertex_groups: # custom head
        return 

    cheek=vgroup(obj, 'cf_J_CheekLow_L')
    mcands=vgroup2(obj, 'cf_J_MouthLow', 'cf_J_Mouthup')
    if len(mcands)==0:
        print("Can't do mouth blendshape on this character")
        return
    mcorn=weighted_center('cf_J_Mouth_L')

    mcorn_nearest=find_nearest(mesh, mcorn, mcands)
    cheek_nearest=find_nearest(mesh, mcorn, cheek)
    mcorn = (mesh.vertices[mcorn_nearest].co + mesh.vertices[cheek_nearest].co)*0.5
    mcorn_nearest = find_nearest(mesh, mcorn, mcands)
    mcorn = mesh.vertices[mcorn_nearest].co
    #mesh.vertices[mcorn_nearest].co[2]+=1
    mcent=mcorn.copy()
    mcent[0]=0
    ccent=weighted_center('cf_J_CheekLow_L')
    ccorn=mcorn + (ccent-mcorn)*2.0
    ccorn_nearest=mesh.vertices[0].co
    for x in mesh.vertices:
        if (x.co-ccorn).length<(ccorn_nearest-ccorn).length:
            ccorn_nearest=x.co
    ccorn=ccorn_nearest
    print(ccorn)
    ccent=(ccorn+mcorn)*0.5
    vmc=ccent-mcorn
    yneg_cutoff=-(mcent-mcorn).dot(vmc)/(vmc.length*vmc.length)

    sk = obj.shape_key_add(name='better_smile')
    sk.interpolation='KEY_LINEAR'
    
    for side in range(2):
        if side==1:
            mcorn[0]*=-1
            ccorn[0]*=-1
        ccent=(mcorn+ccorn)*0.5
        vmc=ccent-mcorn
        vmm=mcorn-mcent
        normal=Vector([vmc[2], 0, -vmc[0]])
        normal2=vmc.cross(normal)
        normal2/=normal2.length
        if normal[2]<0:
            normal*=-1.0
        mod=[x for x in range(len(mesh.vertices)) if (mesh.vertices[x].co-ccent).length<1.5*vmc.length or (mesh.vertices[x].co-mcorn).length<1.5*vmm.length]
        deform=0.2

        for x in mod:
            v = obj.data.vertices[x] #bm.verts[x]
            y=(v.co-mcorn).dot(vmc)/(vmc.length*vmc.length)
            if y<0:
                y/=yneg_cutoff
            z=(v.co-mcorn).dot(normal2)/vmc.length
            #z*=(1.0 if y<0 else max(1.0, 2.0-y))
            #z*=2
            if abs(z)>=1.0:
                z=0.0
            else:
                z=0.5*(1.0+math.cos(math.pi*z))
            #  we pull the vertex toward the ear, maximal effect at lip corner and smoothly decaying 
            #  until we hit 0 at lip center or cheek center.
            #  for positive y (cheek), we also displace the vertex away from the face,
            # trying to create a 'bulge' right next to the lip corner.
            #   Can be improved with a better mathematical model (removing all the ad hoc constants)
            # but seems to work okay as is.
            sk.data[x].co+=vmc*max(0.0, 1.0-abs(y))*deform*z
            if y>0:
                tslope = 3.0
                if y<0.0 or y>2.0:
                    tfun=0.0
                else:
                    tfun = tslope*y*(0.25*y*y-y+1.0)
                sk.data[x].co+=normal*tfun*deform*z


class hs2rig_props(PropertyGroup):
    finger_curl_scale: FloatProperty(
        name="Finger curl", min=0, max=100,
        default=10, precision=1,
        description="Finger curl"
    )
    custom_geo: FloatProperty(
        name="Body customization", min=0, max=2,
        default=1, precision=2,
        description="Morphs between default body shape and character specific body shape"
    )
    file_path: StringProperty(
        name="File path", 
        default='c:\\temp\\pose.txt', 
        description="File path"
    )
    def execute(self, context):
        return {'FINISHED'}
    


class hs2rig_posing_base(Operator):
    def finger_curl(self, x):
        return [('cf_J_Hand_'+a+'0'+str(b)+'_L', 0, 0, -x, -1   ) for a in ('Index','Middle','Ring','Little') for b in range(1,4)]
    poses={
    'sit':[('cf_J_LegUp00_L', -90, 0, 0), 
        ('cf_J_LegLow01_L', 90, 0, 0), 
        ('cf_J_ArmUp00_L', 0, 0, -75, -1),
        ('cf_J_ArmLow01_L', 10, 0, 0),
        ],
    'kneel':[('cf_J_LegUp00_L', -30, 0, 45, -1), 
        ('cf_J_LegLow01_L', 120, 0, 0), 
        ('cf_J_ArmUp00_L', 0, 0, -75, -1),
        ('cf_J_ArmLow01_L', 10, 0, 0),
        ('cf_J_Foot01_L', 20, 0, 0),
        ('cf_J_Foot02_L', 40, 0, 0),
        ],
    'T':[],
    'A':[('cf_J_LegUp00_L', 0, 0, 20, -1), 
        ('cf_J_ArmUp00_L', 0, 0, -60, -1),
        ],
    }

    def set_pose(self, context, pose):
        #print("Executing! Finger curl is ", context.scene.hs2rig_data.finger_curl_scale)
        #arm = bpy.data.objects['Armature']
        arm = context.active_object
        v=hs2rig_posing_base.poses[pose]+self.finger_curl(0.0 if pose=='T' else context.scene.hs2rig_data.finger_curl_scale)
        #print(v)
        # todo: clear all bones
        deformed_rig = arm["deformed_rig"]
        for x in arm.pose.bones:
            if x.name in deformed_rig:
                x.matrix_basis=deformed_rig[x.name])
        for x in v:
            arm.pose.bones[x[0]].rotation_mode='YZX'
            arm.pose.bones[x[0]].rotation_euler=Euler((x[1]*math.pi/180., x[2]*math.pi/180., x[3]*math.pi/180.), 'YZX')
            mult = -1.0 if len(x)>4 else 1.0
            arm.pose.bones[x[0][:-1]+'R'].rotation_mode='YZX'
            arm.pose.bones[x[0][:-1]+'R'].rotation_euler=Euler((x[1]*math.pi/180., mult*x[2]*math.pi/180., mult*x[3]*math.pi/180.), 'YZX')
        return {'FINISHED'}

class hs2rig_OT_load_fk(Operator):
    bl_idname = "object.load_pose_fk"
    bl_label = "Load pose"
    bl_description = "Loads the character pose from the file"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        load_pose(context.active_object.name, context.scene.hs2rig_data.file_path, 1)
        return {'FINISHED'}

class hs2rig_OT_load_shape(Operator):
    bl_idname = "object.load_pose_soft"
    bl_label = "Load shape"
    bl_description = "Loads the character shape from the file"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        load_pose(context.active_object.name, context.scene.hs2rig_data.file_path, 2)
        return {'FINISHED'}

class hs2rig_OT_load_all(Operator):
    bl_idname = "object.load_pose_all"
    bl_label = "Load all"
    bl_description = "Loads the character pose and shape from the file"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        load_pose(context.active_object.name, context.scene.hs2rig_data.file_path, 3)
        return {'FINISHED'}

class hs2rig_OT_save_all(Operator):
    bl_idname = "object.save_pose_all"
    bl_label = "Save all"
    bl_description = "Saves the character pose and shape to the file"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        of=open(context.scene.hs2rig_data.file_path,"w")
        dump_pose(context.active_object.name, of)
        of.close()
        return {'FINISHED'}

class hs2rig_OT_posing(hs2rig_posing_base):
    bl_idname = "object.set_pose"
    bl_label = "Sit"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'sit')

class hs2rig_OT_posing2(hs2rig_posing_base):
    bl_idname = "object.set_pose2"
    bl_label = "Kneel"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'kneel')

class hs2rig_OT_posing3(hs2rig_posing_base):
    bl_idname = "object.set_pose3"
    bl_label = "T-pose"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'T')
        
class hs2rig_OT_posing4(hs2rig_posing_base):
    bl_idname = "object.set_pose4"
    bl_label = "A-pose"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'A')

class hs2rig_OT_clothing(Operator):
    bl_idname = "object.toggle_clothing"
    bl_label = "Toggle clothing"
    bl_description = "Set selected scale"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        for x in context.active_object.children:
            if x.type=='ARMATURE' or x.type=='LIGHT':
                continue
            if 'Prefab ' in x.name:
                continue
            if 'hair' in x.name:
                continue
            if x.name.startswith('o_tang'):
                continue
            if x.name.startswith('o_tooth'):
                continue
            if x.name.startswith('o_body'):
                continue
            x.hide_viewport = not x.hide_viewport
        return {'FINISHED'}


class hs2rig_OT_scale(Operator):
    bl_idname = "object.apply_scale"
    bl_label = "Apply body shape"
    bl_description = "Set selected scale"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm = context.active_object #bpy.data.objects['Armature']
        z=context.scene.hs2rig_data.custom_geo
        deformed_rig=arm["deformed_rig"]
        #z=self.custom_geo
        #cs=char_shape()
        #loaded=cs.deserialize()

        def scale_one_bone(x):
            max_deform = Matrix(deformed_rig[x.name]).decompose()
            offset, rotation, scale = max_deform        
            bc = bone_class(x.name, 'offset')
            if bc!='?' and bc!=None:
                for c in range(3):                    
                    if bc[c] in ('s','i','u'):
                        offset[c] = offset[c]*z
            if bone_class(x.name, 'rotation') in ('s','i','u'):
                rotation = Quaternion([1,0,0,0])*(1.-z) + rotation*z
            bc=bone_class(x.name, 'scale')
            if bc!='?' and bc!=None:
                for c in range(3):
                    if bc[c] in ('s','i','u'):
                        scale[c]=math.pow(scale[c], z)
            
            T = Matrix.Translation(offset)
            R = rotation.to_matrix().to_4x4()
            S = Matrix.Diagonal(scale.to_4d())            
            x.matrix_basis=T @ R @ S
            for c in x.children:
                scale_one_bone(c)
        scale_one_bone(arm.pose.bones['cf_J_Root'])
        return {'FINISHED'}
    
class hs2rig_PT_ui(Panel):
    bl_idname = "hs2rig_main"
    bl_label = "HS2 rig"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Rig"
    bl_context = "posemode"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        arm = context.active_object #bpy.data.objects['Armature']

        if context.active_object is not None:
            if context.active_object.type == 'ARMATURE' and arm.get("default_rig")!=None:
                row = layout.row(align=True)
                row.operator("object.set_pose")
                row.operator("object.set_pose2")
                row.operator("object.set_pose3")
                row.operator("object.set_pose4")
                row = layout.row(align=True)
                row.operator("object.apply_scale")
                row.operator("object.toggle_clothing")
                row = layout.row(align=True)
                row.prop(context.scene.hs2rig_data, "finger_curl_scale")
                #row = layout.row(align=True)
                row.prop(context.scene.hs2rig_data, "custom_geo", slider=True)
                #row.prop(hs2rig_scale.custom_geo, "custom_geo", slider=True)
                row = layout.row(align=True)
                row.prop(context.scene.hs2rig_data, "file_path")
                row = layout.row(align=True)
                row.operator("object.load_pose_fk")
                row.operator("object.load_pose_soft")
                row.operator("object.load_pose_all")
                row.operator("object.save_pose_all")
                #row.operator("object.load_unity")
            else:
                buf = "No valid object selected"
                layout.label(text=buf, icon='MESH_DATA')

addon_classes=[
hs2rig_OT_posing, 
hs2rig_OT_posing2, 
hs2rig_OT_posing3, 
hs2rig_OT_posing4, 
hs2rig_OT_clothing,
hs2rig_OT_scale,

hs2rig_OT_load_fk,
hs2rig_OT_load_shape,
hs2rig_OT_load_all,
hs2rig_OT_save_all,
hs2rig_PT_ui, 
hs2rig_props
]

for x in addon_classes: 
    bpy.utils.register_class(x)    
bpy.types.Scene.hs2rig_data = PointerProperty(type=hs2rig_props)

success, arm, body = import_bodyparts()
if success:
    body=rebuild_torso(arm, body)
    load_textures(arm, body)
    fixup_head(body)
    fixup_torso(body)
    stitch_head_to_torso(body)
    arm.name=name
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    reshape_armature(arm, body)
    fix_mouth(body)
    if wipe_scene:
        bpy.ops.object.mode_set(mode='OBJECT')
        light_data = bpy.data.lights.new('light', type='POINT')
        light = bpy.data.objects.new('light', light_data)
        bpy.context.collection.objects.link(light)
        light.location = (5, -5, 10)
        light.data.energy=2000.0
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
