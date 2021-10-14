import bpy
import os
import bmesh
import math
from mathutils import Matrix, Vector, Euler



from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
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

if not use_config:
    fbx='c:\\temp\\name.fbx'
    path='c:\\temp\\textures\\'
    dump='c:\\temp\\dump.txt'
else:
    cfg=open("C:\\temp\\hs2blender.cfg","r").readlines()
    waifus_path=cfg[0].strip()
    cfg=[x.strip().split(' ') for x in cfg[1:]]
    conf={}
    for x in cfg:
        if len(x)<2:
            continue
        y = x[1:]
        print(x[0], y)
        if len(y)==1:
            conf[x[0]]=(y[0],)
        else:
            colors=[float(z) for z in y[1:7]]
            conf[x[0]]=(y[0], colors[0:3], colors[3:6])

    name=""
    path=waifus_path
    if path[-1]!='\\':
        path=path+'\\'
    cconf = conf[name]
    path+=cconf[0]+'\\'
    if len(cconf)>1:
        eye_color=cconf[1]
        hair_color=cconf[2]
    dumps=[x for x in os.listdir(path) if x.endswith('.txt')]
    if len(dumps)>0:
        dump=path+dumps[0]
    else:
        dump=None
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

chara={x:None for x in bodyparts}
chara['o_forehead']=None

def find_tex(x1, x2):
    f=os.listdir(path)
    for y in f:
        if (x1+'_' in y) and y.endswith("_"+x2+".png"):
            return path+y
    return None

def set_tex(obj, node, x, y, alpha=None, csp=None):
    global chara
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
    if obj in chara:
        chara[obj].materials[0].node_tree.nodes[node].image=tex
    else:
        bpy.data.meshes[obj].materials[0].node_tree.nodes[node].image=tex
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
        elif b[0][1]>box[0][1]+0.90*(box[1][1]-box[0][1]):
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
    join_meshes(nails, 'nails')
    chara['nails']=bpy.data.meshes[nails[0]]
    if boy:
        if 'cm_o_dan00' in bpy.data.objects:
            other.append('cm_o_dan00')
        if 'cm_o_dan_f' in bpy.data.objects:
            other.append('cm_o_dan_f')            
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
    if hair_color!=None:
        eyelash_mat.node_tree.nodes['RGB'].outputs[0].default_value = hair_color

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
    set_tex('o_eyebase_L', 'Image Texture.003', 'eye', 'Texture4', csp='Non-Color')    
    if eye_color!=None:
        eye_mat.node_tree.nodes['RGB'].outputs[0].default_value = eye_color

    head_mat = bpy.data.materials['Head'].copy()
    head_mat.name = 'Head_' + suffix
    while len(chara['o_head'].materials):
        chara['o_head'].materials.pop()
    print(chara['o_head'])
    chara['o_head'].materials.append(head_mat)
    #return
    set_tex('o_head', 'Image Texture', 'head', 'MainTex', alpha='NONE')
    set_tex('o_head', 'Image Texture.002', 'head', 'DetailMainTex', csp='Non-Color')
    set_tex('o_head', 'Image Texture.003', 'head', 'DetailGlossMap', csp='Non-Color')
    set_tex('o_head', 'Image Texture.007', 'head', 'BumpMap_converted', csp='Non-Color')
    if boy:
        # No bump map 2
        head_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0
        head_mat.node_tree.nodes['Value.003'].outputs[0].default_value=1.0 # Scale for textured gloss
        head_mat.node_tree.nodes['Math.002'].inputs[1].default_value = 0.850 # Subtract constant for textured gloss
        head_mat.node_tree.nodes['Vector Math.003'].inputs[3].default_value = 5.0 # UV coordinate scale for textured gloss
    else:
        if not set_tex('o_head', 'Image Texture.006', 'head', 'BumpMap2_converted', csp='Non-Color'):
            head_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0
    #head_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    set_tex('o_head', 'Image Texture.001', 'head', 'Texture3', csp='Non-Color')
    if hair_color!=None:
        head_mat.node_tree.nodes['RGB'].outputs[0].default_value = hair_color
    tongue_mat = bpy.data.materials['Tongue'].copy()
    tongue_mat.name = 'Tongue_' + suffix
    while len(chara['o_tang'].materials):
        chara['o_tang'].materials.pop()
    chara['o_tang'].materials.append(tongue_mat)
    set_tex('o_tang', 'Image Texture', 'tang', 'MainTex')
    set_tex('o_tang', 'Image Texture.001', 'tang', 'BumpMap_converted', csp='Non-Color')
    set_tex('o_tang', 'Image Texture.002', 'tang', 'DetailGlossMap', csp='Non-Color')

    teeth_mat = bpy.data.materials['Teeth'].copy()
    teeth_mat.name = 'Teeth_' + suffix
    while len(chara['o_tooth'].materials):
        chara['o_tooth'].materials.pop()
    chara['o_tooth'].materials.append(teeth_mat)
    set_tex('o_tooth', 'Image Texture', 'tooth', 'MainTex')
    set_tex('o_tooth', 'Image Texture.001', 'tooth', 'BumpMap_converted', csp='Non-Color')

    body_mat = bpy.data.materials['Torso'].copy()
    body_mat.name = 'Torso_' + suffix
    while len(chara[bn].materials):
        chara[bn].materials.pop()
    chara[bn].materials.append(body_mat)
    set_tex(bn, 'Image Texture', 'body', 'MainTex', alpha='NONE')
    set_tex(bn, 'Image Texture.005', 'body', 'DetailGlossMap', csp='Non-Color')
    set_tex(bn, 'Image Texture.002', 'body', 'BumpMap_converted', csp='Non-Color')
    set_tex(bn, 'Image Texture.003', 'body', 'BumpMap2_converted', csp='Non-Color')
    #body_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    #body_mat.node_tree.nodes['Value.001'].outputs[0].default_value=0.0
    if boy:
        bpy.data.objects[bn]['Boy']=1.0
    set_tex(bn, 'Image Texture.001', 'body', 'Texture2', csp='Non-Color')    

    while len(chara['nails'].materials):
        chara['nails'].materials.pop()
    chara['nails'].materials.append(bpy.data.materials['Nails'])
    
    for x in bpy.data.objects.keys():
        if 'hair' in x or (bpy.data.objects[x].type=='MESH' \
                and not ('Prefab ' in x) \
                and not ('Material ' in x) \
                and len(bpy.data.objects[x].data.materials)>0 \
                and 'hair' in bpy.data.objects[x].data.materials[0].name):
            print('Texturing', x, 'as hair')
            mesh = bpy.data.objects[x].data
            m = mesh.materials[0]
            n = m.name
            if '.' in n:
                n = n.split('.')[0]            
            while len(mesh.materials):
                mesh.materials.pop()
            mat = bpy.data.materials['test_hair'].copy()
            mesh.materials.append(mat)
            set_tex(mesh.name, 'Image Texture', n, 'MainTex', csp='Non-Color')
            set_tex(mesh.name, 'Image Texture.001', n, 'BumpMap_converted', csp='Non-Color')
            if hair_color!=None:
                mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = hair_color
            
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
            if not set_tex(mesh.name, 'Image Texture.002', n, 'OcclusionMap', csp='Non-Color'):
                # Item does not support clothes damage
                mat.node_tree.nodes['Value'].outputs[0].default_value=-0.01

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
    error = 0.01
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meshes=[bn,'o_head','o_eyebase_L','o_eyebase_R','o_eyelashes','o_eyeshadow']
    join_meshes(meshes, 'body')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects['body']
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles(threshold=0.015, use_unselected=True)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_tools(mode='RESET')
    bpy.ops.mesh.select_all(action='DESELECT')
    
def import_bodyparts():
    global chara
    global bn
    global boy
    for bpy_data_iter in (bpy.data.objects, bpy.data.meshes):
        for id_data in bpy_data_iter:
            if  id_data.name!="Cube" and id_data.name!="Material Cube" and not id_data.name.startswith('Prefab '):
                bpy_data_iter.remove(id_data)
    bpy.ops.import_scene.fbx(filepath=fbx)
    boy = ('o_body_cm' in bpy.data.objects)
    bn='o_body_cm' if boy else 'o_body_cf'
    bodyparts.append(bn)
    chara[bn]=None

    for x in bodyparts:
        for y in bpy.data.meshes.keys(): #sc.objects.keys():
            if y==x or y.startswith(x+'.'):
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
    if (not boy) and bn+'.001' in bpy.data.objects:
        bpy.data.objects[bn+'.001'].name=bn
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
    #bpy.ops.object.rotation_clear()
    return True

class char_shape:
    offset_bones=[
    ('cf_J_ArmUp00_L', 'x'),
    ('cf_J_CheekLow_L', 'xyz'),
    ('cf_J_CheekUp_L', 'xyz'),
    ('cf_J_Chin_rs', 'yz'),
    ('cf_J_ChinLow', 'y'),
    ('cf_J_EarLow_L', 'xyz'),
    ('cf_J_EarUp_L', 'xyz'),
    ('cf_J_Eye_t_L', 'xyz'),
    ('cf_J_FaceLowBase', 'z'),
    ('cf_J_FaceUp_ty', 'y'),
    ('cf_J_FaceUp_tz', 'z'),
    ('cf_J_Mouth_L', 'y'),
    ('cf_J_MouthBase_tr', 'yz'),
    ('cf_J_MouthLow', 'yz'),
    ('cf_J_Mouthup', 'y'),
    ('cf_J_Nose_r', 'y'),
    ('cf_J_Nose_t', 'yz'),
    ('cf_J_Nose_tip', 'yz'),
    ('cf_J_NoseBase_trs', 'yz'),
    ('cf_J_NoseBridge_t', 'yz'),
    ('cf_J_NoseWing_tx_L', 'xyz'),
    ('cf_J_MouthCavity', 'z'), # moves mouth+teeth+tongue forward-back
    ('cf_J_LegUp00_L', 'xyz'), #  1 axis: 0.71906 -0.40854  -0.0817
    ('cf_J_Mune00_L', 'xyz'), #
    ('cf_J_Mune00_s_L', 'xyz'), #
    ('cf_J_Mune00_t_L', 'xyz'), #
    ('cf_J_Mune00_d_L', 'xz'), #  (possibly 1-d)
    ('cf_J_Mune01_s_L', 'yz'), #
    ('cf_J_Mune02_L', 'xyz'), #
    ('cf_J_Mune02_s_L', 'yz'), #
    ('cf_J_Mune_Nip01_L', 'y'), # (?) (very small)
    ('cf_J_Mune_Nip01_s_L', 'z'), #
    ('cf_J_Mune_Nip02_L', 'y'), #
    ('cf_J_Mune_Nip02_s_L', 'z'), #
    ('cf_J_Mune03_L', 'xyz'), # (small)
    ('cf_J_Mune03_s_L', 'z'), #
    ('cf_J_Mune04_s_L', 'yz'), # (small)

    #Variable offset soft bones:
    ('cf_J_ArmUp01_s_L',  'xy'), #   upper muscle pos along the arm, vertical
    ('cf_J_ArmUp02_s_L',  'y'), #    biceps pos along the arm
    ('cf_J_ChinTip_s',  'yz'), #
    ('cf_J_LegKnee_back_s_L',  'z'), #
    ('cf_J_LegKnee_low_s_L',  'z'), #
    ('cf_J_LegLow03_s_L',  'xz'), # adjusts ankle just above the foot joint; x left-right, z forward-back
    ('cf_J_LegUp01_s_L',  'xz'), # adjusts upper thigh just below the hip joint; x left-right, z forward-back
    ('cf_J_Shoulder02_s_L',  'x'), #', #   shoulder shape
    ('cf_J_Siri_s_L',  'xyz'), #
    ('cf_J_Spine01_s',  'yz'), #
    ]
    scale_bones={
    'cf_N_height':  'xyz', #  - overall dimensions of the torso (roughly groin to neck)
    'cf_J_ArmUp00_L':  'xyz', # - overall arm scale 
    'cf_J_LegUp00_L':  'xyz', # - overall leg scale
    'cf_J_Foot01_L':  'xyz', # - overall foot scale
    'cf_J_Hand_s_L':  'xyz', # - overall hand scale
    'cf_J_Kosi01_s': 'xz',
    'cf_J_Kosi02_s': 'xz',
    'cf_J_LegKnee_low_s_L': 'xyz',
    'cf_J_LegLow01_s_L': 'xz',
    'cf_J_LegLow03_s_L': 'xz',
    'cf_J_LegLow02_s_L': 'xz',
    'cf_J_LegU': 'xz',
    'cf_J_LegUp01_s_L': 'xz',
    'cf_J_LegUp02_s_L': 'xz',
    'cf_J_LegUp03_s_L': 'xz',
    'cf_J_LegKnee_back_s_L': 'xz',
    'cf_J_Siri_s_L': 'xyz',
    'cf_J_LegUpDam_s_L': 'xz',
    'cf_J_Spine01_s': 'xz',
    'cf_J_Spine02_s': 'xz',
    'cf_J_Mune00_t_L': 'xyz',
    'cf_J_Neck_s': 'xz',
    'cf_J_Spine03_s': 'xz',

    'cf_J_Mune00_s_L': 'xyz',
    'cf_J_Mune01_s_L': 'xyz',
    'cf_J_Mune02_s_L': 'xyz',
    'cf_J_Mune03_s_L': 'xyz',
    'cf_J_Mune04_s_L': 'xyz',
    'cf_J_Mune_Nip01_s_L': 'xyz',
    'cf_J_Head_s': 'xyz',
    'cf_J_ChinTip_s': 'xyz',
    'cf_J_EarBase_s_L': 'xyz',
    'cf_J_EarUp_L': 'xyz',
    'cf_J_EarLow_L': 'xyz',
    'cf_J_NoseBase_s': 'xyz',
    'cf_J_Nose_tip': 'xyz',

    'cf_J_FaceBase': 'xz',
    'cf_J_FaceLow_s': 'x',
    'cf_J_Chin_rs': 'x',
    'cf_J_MouthLow': 'x',
    'cf_J_MouthBase_s': 'xy',
    'cf_J_Eye_s_L': 'xy',
    'cf_J_NoseBridge_s': 'x',

    'cf_J_ArmElbo_low_s_L': 'yz',
    'cf_J_ArmLow01_s_L': 'yz',
    'cf_J_ArmLow02_s_L': 'yz',
    'cf_J_Hand_Wrist_s_L': 'yz',
    'cf_J_ArmUp01_s_L': 'yz',
    'cf_J_ArmUp02_s_L': 'yz',
    'cf_J_ArmUp03_s_L': 'yz',
    'cf_J_Shoulder02_s_L': 'xyz',
    'cf_J_Ana': 'xyz',
    'cf_J_ArmElboura_s_L': 'z',
    'cf_J_Mune_Nip02_s_L': 'xyz'
    }
    def __init__(self):
        self.scales={}
        self.default_offsets={}
        self.offsets={}
        return
    def set_scale(self, name, v):
        if name.endswith('R'):
            return
        if not name in char_shape.scale_bones:
            print(name, v[0], v[1], v[2]) #'Bone ', name, 'is not expected')
            return
        for c in range(3):
            if abs(v[c]-1)>0.005 and not chr(ord('x')+c) in char_shape.scale_bones[name]:
                print('Unexpected large scale ', c, ' in ', name, v[0], v[1], v[2])
        self.scales[name]=v

    def serialize(self):
        of=open("c:\\temp\\scales_"+name+".txt", "w")
        for x in self.scales:
            s=x+(' %.4f %.4f %.4f\n' % (self.scales[x][0], self.scales[x][1], self.scales[x][2]))
            of.write(s)
        of.close()
    def deserialize(self):
        try:
            of=open("c:\\temp\\scales_"+name+".txt", "r")
            if of==None:
                return False
            for x in of.readlines():
                y=x.strip().split()
                self.scales[y[0]]=[float(y[1]),float(y[2]),float(y[3])]
            of.close()
            of=open("c:\\temp\\shape_default.txt","r")
            for x in of.readlines():
                y=x.strip().split()
                self.default_offsets[y[0]]=[float(y[1]),float(y[2]),float(y[3])]
            of=open("c:\\temp\\shape_"+name+".txt","r")
            for x in of.readlines():
                y=x.strip().split()
                self.offsets[y[0]]=[float(y[1]),float(y[2]),float(y[3])]
            return True
        except:
            return False

bone_pos={}
bone_w2l={}
bone_parent={}
root_pos=[0,0,0]

def load_unity_dump():
    global root_pos
    global bone_pos
    name=''
    global bone_parent
    global bone_w2l
    global dump
    dump=open(dump,'r').readlines()
    dump=[x.strip() for x in dump]
    if 'cf_J_Root' in dump[0]:
        dump[0]='cf_J_Root--UnityEngine.GameObject'
    else:
        print(dump[0])
        MessageBox('ERROR: Could not parse the dump file')
        return False

    for n in range(len(dump)):
        x=dump[n]
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
                if m[0][0]==0.0 and m[0][1]==0.0 and m[0][2]==0.0:
                    m[0][0]=0.0010
                if m[1][0]==0.0 and m[1][1]==0.0 and m[1][2]==0.0:
                    m[1][1]=0.0010
                if m[2][0]==0.0 and m[2][1]==0.0 and m[2][2]==0.0:
                    m[2][2]=0.0010
                bone_pos[name]=Matrix(m)

    
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
        bpy.context.active_pose_bone.matrix_basis = bpy.context.active_pose_bone.matrix_basis @ mw.inverted() @ target
        bone_transforms[x]=bpy.context.active_pose_bone.matrix_basis @ mw.inverted() @ target
        local=bone_transforms[x]
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
    errors = score_deform(b, depsgraph, undeformed)
    dirs=errors[:]
    steps=[intl_step]*n
    age=[0]*n
    residual=sum([x.length for x in errors])
    print('Initial residual vertex error ', residual/n)
    last_max_residual_pos=-1
    frozen=[(1 if x.length<0.0001 else 0) for x in errors]
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
                dirs[x]=errors2[x]-0.5*delta*(1.0-cos_phi)
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
                target[x].co=vsave[x]
                age[x]+=1
                if steps[x]>0.01:
                    steps[x]/=2
                else:
                    dirs[x]=Vector([dirs[x][1]*math.sin(p),dirs[x][2]*math.cos(p),dirs[x][0]])
                    steps[x]=intl_step
                    if age[x]>=5:
                        frozen[x]=1
                        live-=1
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
    return npass, n-sum(solved)

deformed_rig={}

def reshape_armature(): 
    global deformed_rig
    arm = bpy.data.objects['Armature']
    body = bpy.data.objects['body']
    bpy.ops.object.mode_set(mode='OBJECT')    
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    
    default_rig = read_rigfile_from_textblock('Rig_Male' if boy else 'Rig_Female')
    default_rig_head=read_rigfile_from_textblock('Rig_Male_Head' if boy else ('Rig_Female_Head1' if 'p_cf_head_01' in arm.data.edit_bones else 'Rig_Female_Head0'))
    for x in default_rig_head:
        m=default_rig_head[x]
        m[1][3]+=15.935
        m[2][3]+=-0.23
        default_rig[x]=m
        
    bpy.ops.object.mode_set(mode='EDIT')    
    char_offsets={}
    for x in arm.data.edit_bones:
        if x.name in bone_pos and x.parent and x.parent.name in bone_pos \
            and (x.name in default_rig) and (x.parent.name in default_rig):
            cur_offset=x.matrix.decompose()[0]-x.parent.matrix.decompose()[0]
            ref_offset=default_rig[x.name].decompose()[0]-default_rig[x.parent.name].decompose()[0]
            delta_offset=cur_offset-ref_offset
            if len(delta_offset)>0.005:
                print(x.name, delta_offset)
            char_offsets[x.name]=delta_offset        

    def apply_offsets_bone(x):
        o = Vector()
        y = x
        if x.name in default_rig:
            x.matrix=default_rig[x.name]
        """
        while y!=None:
            if y.name in char_offsets:
                o += char_offsets[y.name]
            y=y.parent
        x.matrix[0][3]-=o[0]
        x.matrix[1][3]-=o[1]
        x.matrix[2][3]-=o[2]
        """
        for y in x.children:
            apply_offsets_bone(y)
                        
    apply_offsets_bone(arm.data.edit_bones['cf_J_Root'])

    cs=char_shape()
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

    loaded=cs.deserialize()
    print('Load attempt: ', loaded)

    # Set the rest position of 'arm' to "custom body" state
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')    

    body_parts=arm.children 

    # duplicate body
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

    """
    # Set the rest position of 'arm' to "default body" state
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')    
    reset_pose_one_bone('cf_J_Root', arm)
    bpy.ops.object.mode_set(mode='EDIT')    
    for x in bpy.context.object.data.edit_bones:
        if x.name=='cf_J_FaceBase':
            print(x.name in bone_pos, x.name in default_rig)
        if x.name in bone_pos and x.name in default_rig:
            x.matrix=default_rig[x.name]
    """
     # Stretch 'arm' back to 'custom body' 
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')    
    reshape_mesh_one_bone('cf_J_Root', arm)
    for x in arm.pose.bones:
        deformed_rig[x.name]=x.matrix_basis.copy()
    
    bpy.ops.object.mode_set(mode='OBJECT')  
    npass=0
    fail_vert=0

    # Solve for undeformed mesh shape
    for b in body_parts:
        b2 = bpy.data.objects[b["ref"]]
        x, y = solve_for_deform(b, b2)
        npass += x
        fail_vert += y

    print("Done in ", npass, " passes, ", fail_vert, "failed vertices")
    bpy.ops.object.select_all(action='DESELECT')
    for x in body_parts:
        bpy.data.objects[x["ref"]].select_set(True)
    bpy.ops.object.delete(use_global=False)

    bpy.ops.object.mode_set(mode='OBJECT')  
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')  
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

    if not loaded:
        cs.serialize()

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

class hs2rig_props(PropertyGroup):
    finger_curl_scale: FloatProperty(
        name="Finger curl", min=0, max=100,
        default=10, precision=1,
        description="Finger curl"
    )
    custom_geo: FloatProperty(
        name="Body customization", min=0, max=2,
        default=1, precision=2,
        description="Custom geometry"
    )
    def execute(self, context):
        print('hs2rig_props ', custom_geo, finger_curl_scale)
        return {'FINISHED'}
    


class hs2rig_posing_base(Operator):
    def finger_curl(self, x):
        return [('cf_J_Hand_'+a+'0'+str(b)+'_L', 0, 0, -x, -1   ) for a in ('Index','Middle','Ring','Little') for b in range(1,4)]
    poses={
    'sit':[('cf_J_LegUp00_L', -90, 0, 0), 
        ('cf_J_LegLow01_L', 90, 0, 0), 
        ('cf_J_ArmUp00_L', 0, 0, -75, -1),
        ('cf_J_ArmLow01_L', 10, 0, 0),
        ('cf_J_Foot01_L', 0, 0, 0),
        ('cf_J_Foot02_L', 0, 0, 0),
        ],
    'kneel':[('cf_J_LegUp00_L', -30, 0, 45, -1), 
        ('cf_J_LegLow01_L', 120, 0, 0), 
        ('cf_J_ArmUp00_L', 0, 0, -75, -1),
        ('cf_J_ArmLow01_L', 10, 0, 0),
        ('cf_J_Foot01_L', 20, 0, 0),
        ('cf_J_Foot02_L', 40, 0, 0),
        ],
    'T':[('cf_J_LegUp00_L', 0, 0, 0), 
        ('cf_J_LegLow01_L', 0, 0, 0), 
        ('cf_J_ArmUp00_L', 0, 0, 0, -1),
        ('cf_J_ArmLow01_L', 00, 0, 0),
        ('cf_J_Foot01_L', 0, 0, 0),
        ('cf_J_Foot02_L', 0, 0, 0),
        ],
    'A':[('cf_J_LegUp00_L', 0, 0, 20, -1), 
        ('cf_J_LegLow01_L', 0, 0, 0), 
        ('cf_J_ArmUp00_L', 0, 0, -60, -1),
        ('cf_J_ArmLow01_L', 00, 0, 0),
        ('cf_J_Foot01_L', 0, 0, 0),
        ('cf_J_Foot02_L', 0, 0, 0),
        ],
    }

    def set_pose(self, context, pose):
        #print("Executing! Finger curl is ", context.scene.hs2rig_data.finger_curl_scale)
        arm = bpy.data.objects['Armature']
        v=hs2rig_posing_base.poses[pose]+self.finger_curl(0.0 if pose=='T' else context.scene.hs2rig_data.finger_curl_scale)
        print(v)
        for x in v:
            arm.pose.bones[x[0]].rotation_mode='YZX'
            arm.pose.bones[x[0]].rotation_euler=Euler((x[1]*math.pi/180., x[2]*math.pi/180., x[3]*math.pi/180.), 'YZX')
            mult = -1.0 if len(x)>4 else 1.0
            arm.pose.bones[x[0][:-1]+'R'].rotation_mode='YZX'
            arm.pose.bones[x[0][:-1]+'R'].rotation_euler=Euler((x[1]*math.pi/180., mult*x[2]*math.pi/180., mult*x[3]*math.pi/180.), 'YZX')
        return {'FINISHED'}


class hs2rig_posing(hs2rig_posing_base):
    bl_idname = "object.set_pose"
    bl_label = "Sit"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'sit')

class hs2rig_posing2(hs2rig_posing_base):
    bl_idname = "object.set_pose2"
    bl_label = "Kneel"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'kneel')

class hs2rig_posing3(hs2rig_posing_base):
    bl_idname = "object.set_pose3"
    bl_label = "T-pose"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'T')
        
class hs2rig_posing4(hs2rig_posing_base):
    bl_idname = "object.set_pose4"
    bl_label = "A-pose"
    bl_description = "Set selected pose"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return self.set_pose(context, 'A')

class hs2rig_clothing(Operator):
    bl_idname = "object.toggle_clothing"
    bl_label = "Toggle clothing"
    bl_description = "Set selected scale"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        for x in bpy.data.objects:
            if x.type=='ARMATURE' or x.type=='LIGHT':
                continue
            if 'Prefab ' in x.name:
                continue
            if 'hair' in x.name:
                continue
            if x.name in ['o_tang', 'o_tooth', 'body', 'Material Cube']:
                continue
            x.hide_viewport = not x.hide_viewport
        return {'FINISHED'}


class hs2rig_scale(Operator):
    bl_idname = "object.apply_scale"
    bl_label = "Apply body shape"
    bl_description = "Set selected scale"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm = bpy.data.objects['Armature']
        z=context.scene.hs2rig_data.custom_geo
        #z=self.custom_geo
        cs=char_shape()
        loaded=cs.deserialize()

        def scale_one_bone(x):
            max_deform = deformed_rig[x.name].decompose()
            offset = max_deform[0]*z
            scale=Vector([math.pow(max_deform[2][i], z) for i in range(3)])
            T = Matrix.Translation(offset)
            R = max_deform[1].to_matrix().to_4x4()
            S = Matrix.Diagonal(scale.to_4d())            
            x.matrix_basis=T @ R @ S
            for c in x.children:
                scale_one_bone(c)
        scale_one_bone(arm.pose.bones['cf_J_Root'])
        return {'FINISHED'}
    
class hs2rig_ui(Panel):
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
        arm = bpy.data.objects['Armature']

        if context.active_object is not None:
            if context.active_object.type == 'ARMATURE':
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
            else:
                buf = "No valid object selected"
                layout.label(text=buf, icon='MESH_DATA')

addon_classes=[
hs2rig_posing, 
hs2rig_posing2, 
hs2rig_posing3, 
hs2rig_posing4, 
hs2rig_clothing,
hs2rig_scale,
hs2rig_ui, 
hs2rig_props
]

for x in addon_classes: 
    bpy.utils.register_class(x)    
bpy.types.Scene.hs2rig_data = PointerProperty(type=hs2rig_props)

if import_bodyparts():
    rebuild_torso()
    load_textures()
    fixup_head()
    fixup_torso()
    stitch_head_to_torso()
    load_unity_dump()
    reshape_armature()
    bpy.ops.object.mode_set(mode='OBJECT')
    light_data = bpy.data.lights.new('light', type='POINT')
    light = bpy.data.objects.new('light', light_data)
    bpy.context.collection.objects.link(light)
    light.location = (5, -5, 10)
    light.data.energy=2000.0
