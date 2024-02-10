import bpy
import os
import bmesh
import math
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy as np
import time

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
    StringProperty,
    FloatVectorProperty
)

from . import add_extras, armature
from .armature import ImportException

bodyparts=[
'o_eyebase_L',
'o_eyebase_R',
'o_eyelashes',
'o_eyeshadow',
'o_head',
'o_tang',
'o_tooth',
]

#if path[-1]!='\\':
#    path+='\\'
path=""

hash_to_file_map={}

def find_tex(x1, x2):
    f=os.listdir(path)
    for y in f:
        if (x1+'_' in y) and y.endswith("_"+x2+".png"):
            md5=hashlib.md5(open(path+y,'rb').read()).hexdigest()
            if md5 in hash_to_file_map:
                return hash_to_file_map[md5]
            return path+y
    return None

def set_tex(obj, node, x, y, alpha=None, csp=None):
    #global chara
    tex=find_tex(x, y)
    #print("set_tex", obj, node, x, y, tex)
    if tex==None:
        #print('Warning: failed to find texture ', x, y)
        return None
    for t in bpy.data.images:
        if t.filepath == tex:
            #print("Reusing", t.filepath)
            if isinstance(obj, bpy.types.Material):
                obj.node_tree.nodes[node].image=t
            else:
                obj.data.materials[0].node_tree.nodes[node].image=t
            return t
    tex=bpy.data.images.load(tex, check_existing=True)
    if tex==None:
        print('Warning: failed to load texture ', x, y)
        return None
    if alpha!=None:
        tex.alpha_mode='NONE'
    if csp!=None:
        tex.colorspace_settings.name=csp
    if isinstance(obj, bpy.types.Material):
        obj.node_tree.nodes[node].image=tex
    else:
        obj.data.materials[0].node_tree.nodes[node].image=tex
    return tex

#sc = bpy.data.scenes[0]

def bbox(x):
     rv=[[x[0].co[0],x[0].co[1],x[0].co[2]],
         [x[0].co[0],x[0].co[1],x[0].co[2]]]
     for y in x:
         for n in range(3):
             rv[0][n]=min(rv[0][n], y.co[n])
             rv[1][n]=max(rv[1][n], y.co[n])
     return rv

def join_meshes(v, name=None):
    if len(v)==0:
        return
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for x in v:
        bpy.data.objects[x].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects[v[0]] 
    bpy.ops.object.join()
    final=bpy.data.objects[v[0]]
    if name is not None:
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
        # Not uncommon to have >20 because some nails come in several pieces
        print(len(nails), "nail pieces")
        #print("Warning: failed to find the right number of nails: reconstruct may fail")
    nails=join_meshes(nails, 'nails')
    #bpy.ops.object.select_all(action='QWERTY')
    if body['Boy']>0.0:
        if 'cm_o_dan00' in bpy.data.objects:
            other.append('cm_o_dan00')
        if 'cm_o_dan_f' in bpy.data.objects:
            other.append('cm_o_dan_f')            
    body=join_meshes(other, bn)
    body["nails"]=nails.name
    return body

def replace_mat(obj, mat, name = None):
    if name is not None:
        mat.name=name
    while len(obj.data.materials):
        obj.data.materials.pop()
    obj.data.materials.append(mat)
    return mat


def disconnect_link(mat, node):
    v = [x for x in mat.node_tree.links if x.from_node.name==node]
    for x in v:
        mat.node_tree.links.remove(x)

# Sometimes BumpMap.png and BumpMap_converted.png are reversed.
# we expect BumpMap_converted.png to be a normal map (B=255, variance in R&G),
# and BumpMap.png to be a bump map (R=B=255, variance in G.)
# But I have at least one test case where _converted is a bump map.
# This is a rough test to detect the condition and to switch the correct image.
def test_inverted_bump_map(tex):
    w = tex.size[0]
    h = tex.size[1]
    v=tex.pixels[:]
    for x in range(w//4, w*3//4, max(1,w//32)):
        for y in range(h//4, h*3//4, max(1,h//32)):
            index = ( y* w + x ) * 4
            pixel = [
                v[index], # RED
                v[index + 1], # GREEN
                v[index + 2], # BLUE
            ]
            #print("BumpMap center pixel", pixel)
            if not (pixel[0]>0.999 and pixel[2]>0.999):
                return False
    return True

def estimate_bump_gamma(tex):
    # Fast copy of pixel data from bpy.data to numpy array.
    # (Naively doing 'np.array(tex.pixels)' can take as long as 15 s for an 8k texture)
    v = np.zeros((tex.size[0]*tex.size[1], 4), 'f')
    tex.pixels.foreach_get(v.ravel())
    if tex.size[0]>=1024 or tex.size[1]>=1024:
        v = v.reshape([tex.size[0], tex.size[1], 4])
        v = v[::max(1,tex.size[0]//512), ::max(1,tex.size[1]//512), :]
        v = v.reshape([-1, 4])
    averages = np.median(v, axis=0)
    #print("Bump texture", tex.filepath, tex.size[0], tex.size[1], "%.5f %.5f" % (averages[0], averages[1]))

    bump_gamma_r = 1.0
    bump_gamma_g = 1.6
    if averages[0]==1.0 or averages[1]==1.0:
        print("ERROR: this is not a normal map!")
        return 0.0, 0.0

    if (averages[0]>0.47 and averages[0]<0.53) and \
        ((averages[1]>0.63 and averages[1]<0.67) or (averages[1]>0.47 and averages[1]<0.53)):
            bump_gamma_r = 1.0
            bump_gamma_g = 1.0 if (averages[1]>0.47 and averages[1]<0.53) else 1.6
    else:
        bump_gamma_r = -1. / math.log(averages[0], 2)
        bump_gamma_g = -1. / math.log(averages[1], 2)
        # averages[0] ^ bump_gamma_r = 0.5
    return bump_gamma_r, bump_gamma_g

def set_bump(obj, node, x, y):
    if isinstance(obj, bpy.types.Material):
        mat = obj
    else:
        mat = obj.data.materials[0]

    tex = set_tex(obj, node, x, 'BumpMap'+y+'_converted', csp='Non-Color')
    fix_bump_gamma = False
    disable = False
    if (tex is None) or test_inverted_bump_map(tex):
        if tex is not None:
            print("Bump texture", tex.filepath, tex.size[0], tex.size[1])
            print("Mislabeled BumpMap textures detected: fixing...")
        tex = set_tex(obj, node, x, 'BumpMap'+y, csp='Non-Color')


    gamma_r = 'Bump gamma ' + y + 'R'
    gamma_g = 'Bump gamma ' + y + 'G'
    scale = 'Bump scale' + (' ' if len(y)>0 else '') + y

    if tex is None:
        for n in mat.node_tree.nodes:
            if (scale in n.inputs):
                n.inputs[scale].default_value = 0.0
        return False

    bump_gamma_r, bump_gamma_g = estimate_bump_gamma(tex)
    if bump_gamma_r==0.0:
        for n in mat.node_tree.nodes:
            if (scale in n.inputs):
                n.inputs[scale].default_value = 0.0
        return False

    #print("Setting bump gamma %.3f %.3f" % (bump_gamma_r, bump_gamma_g))
    for n in mat.node_tree.nodes:
        if (gamma_r in n.inputs):
            n.inputs[gamma_r].default_value = bump_gamma_r
        if (gamma_g in n.inputs):
            n.inputs[gamma_g].default_value = bump_gamma_g
    return (tex is not None)

def load_textures(arm, body, hair_color, eye_color, suffix):
    hair_mats=[]
    head = bpy.data.objects[body["o_head"]]
    tang = bpy.data.objects[body["o_tang"]]
    tooth = bpy.data.objects[body["o_tooth"]]
    eyeshadow = bpy.data.objects[body["o_eyeshadow"]]
    eyelashes = bpy.data.objects[body["o_eyelashes"]]
    eyebase_R = bpy.data.objects[body["o_eyebase_R"]]
    eyebase_L = bpy.data.objects[body["o_eyebase_L"]]
    nails = bpy.data.objects[body["nails"]]
    body_parts={body, head, tang, tooth, eyeshadow, eyelashes, eyebase_L, eyebase_R, nails}
    print("Body parts:", body_parts)

    with bpy.data.libraries.load(os.path.dirname(__file__)+"/assets/prefab_materials_meshexporter.blend") as (data_from, data_to):
        #print(data_from.materials)
        data_to.materials = data_from.materials
        data_to.meshes = data_from.meshes

    eyeshadow_mat=replace_mat(eyeshadow, bpy.data.materials['Eyeshadow'].copy(),  'Eyeshadow_' + suffix)
    set_tex(eyeshadow, 'Image Texture', 'eyekage', 'MainTex')    

    """
    while len(eyeshadow.data.materials):
        eyeshadow.data.materials.pop()
    eyeshadow.data.materials.append(bpy.data.materials['Eyeshadow'])
    set_tex(eyeshadow, 'Image Texture', 'eyekage', 'MainTex')    
    """

    eyelash_mat=replace_mat(eyelashes, bpy.data.materials['Eyelashes'].copy(),  'Eyelashes_' + suffix)
    set_tex(eyelashes, 'Image Texture', 'eyelashes', 'MainTex', csp='Non-Color')    
    hair_mats.append(eyelash_mat)
    #if hair_color!=None:
    eyelash_mat.node_tree.nodes['RGB'].outputs[0].default_value = hair_color

    eye_mat = bpy.data.materials['Eyes'].copy()
    replace_mat(eyebase_L, eye_mat, 'Eyes_' + suffix)
    replace_mat(eyebase_R, eye_mat, 'Eyes_' + suffix)
    set_tex(eyebase_L, 'Image Texture', 'eye', 'MainTex', csp='Non-Color')    
    set_tex(eyebase_L, 'Image Texture.001', 'eye', 'Texture2', csp='Non-Color')    
    set_tex(eyebase_L, 'Image Texture.002', 'eye', 'Texture3', csp='Non-Color')    
    set_tex(eyebase_L, 'Image Texture.003', 'eye', 'Texture4', csp='Non-Color')    
    #if eye_color!=None:
    eye_mat.node_tree.nodes['RGB'].outputs[0].default_value = eye_color

    head_mat=replace_mat(head, bpy.data.materials['Head'].copy(), 'Head_' + suffix)
    set_tex(head, 'Image Texture', 'skin_head', 'MainTex', alpha='NONE')
    set_tex(head, 'Image Texture.002', 'skin_head', 'DetailMainTex', csp='Non-Color')
    set_tex(head, 'Image Texture.003', 'skin_head', 'DetailGlossMap', csp='Non-Color')
    set_bump(head, 'Image Texture.007', 'skin_head', '')

    if set_tex(head, 'Image Texture.004', 'skin_head', 'SubsurfaceAlbedo', csp='Non-Color') is None:
        disconnect_link(head_mat, 'Image Texture.004')
    else:
        head_mat.node_tree.nodes['Group'].inputs['Subsurface/MainTex mix'].default_value=0.2
    if body['Boy']>0.0:
        # No bump map 2
        head_mat.node_tree.nodes['Group'].inputs['Bump scale 2'].default_value=0.0
        head_mat.node_tree.nodes['Group'].inputs['Textured skin gloss'].default_value=1.0
        head_mat.node_tree.nodes['Group'].inputs['Textured skin gloss delta'].default_value = 0.850
        head_mat.node_tree.nodes['Vector Math.003'].inputs[3].default_value = 5.0 # UV coordinate scale for textured gloss
    else:
        set_bump(head, 'Image Texture.006', 'skin_head', '2')
    #head_mat.node_tree.nodes['Value'].outputs[0].default_value=0.0
    set_tex(head, 'Image Texture.001', 'skin_head', 'Texture3', csp='Non-Color')
    hair_mats.append(head_mat)
    #if hair_color!=None:
    head_mat.node_tree.nodes['RGB'].outputs[0].default_value = hair_color

    replace_mat(tang, bpy.data.materials['Tongue'].copy(), 'Tongue_' + suffix)
    set_tex(tang, 'Image Texture', 'tang', 'MainTex')
    set_bump(tang, 'Image Texture.001', 'tang', '')
    set_tex(tang, 'Image Texture.002', 'tang', 'DetailGlossMap', csp='Non-Color')


    replace_mat(tooth, bpy.data.materials['Teeth'].copy(), 'Teeth_' + suffix)
    set_tex(tooth, 'Image Texture', 'tooth', 'MainTex')
    set_bump(tooth, 'Image Texture.001', 'tooth', '')

    torso_mat = replace_mat(body, bpy.data.materials['Torso'].copy(), 'Torso_' + suffix)
    set_tex(body, 'MainTex', 'skin_body', 'MainTex', alpha='NONE')
    set_tex(body, 'DetailGlossMap', 'skin_body', 'DetailGlossMap', csp='Non-Color')
    set_bump(body, 'BumpMap', 'skin_body', '')
    set_bump(body, 'BumpMap2', 'skin_body', '2')

    set_tex(body, 'Texture2', 'skin_body', 'Texture2', csp='Non-Color')    
    if set_tex(body, 'Subsurface', 'skin_body', 'SubsurfaceAlbedo', csp='Non-Color') is None:
        disconnect_link(torso_mat, 'Subsurface')
    else:
        torso_mat.node_tree.nodes['Group.004'].inputs['Subsurface/MainTex mix'].default_value=0.2
    body["torso_mat"] = torso_mat.name

    replace_mat(nails, bpy.data.materials['Nails'].copy(), 'Nails_' + suffix)
    hair=[]
    for ch in arm.children:
        x=ch.name
        obj = bpy.data.objects[x]
        mesh = obj.data

        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_tools(mode='RESET')
        bpy.ops.object.mode_set(mode='OBJECT')

        if (bpy.data.objects[x].type!='MESH' 
                or ('Prefab ' in x) \
                or ('Material ' in x)):
            continue
        elif ('hair' in x) or (len(bpy.data.objects[x].data.materials)>0 \
                and 'hair' in bpy.data.objects[x].data.materials[0].name) \
                or any(['hair' in y.name for y in bpy.data.objects[x].vertex_groups]):
            print('Texturing', x, 'as hair')
            obj.cycles.use_adaptive_subdivision = True
            obj.cycles.dicing_rate=2.0
            mod=obj.modifiers.new("subsurf", "SUBSURF")
            mod.levels=2
            try:
                mesh.use_auto_smooth=False
            except:
                pass
            m = mesh.materials[0]
            n = m.name
            if '.' in n:
                n = n.split('.')[0]   
            mat=replace_mat(obj, bpy.data.materials['test_hair'].copy(), 'hair_' + suffix)
            if set_tex(obj, 'Image Texture', n, 'MainTex', csp='Non-Color') is None:
                disconnect_link(mat, 'Alpha')
            set_bump(obj, 'Image Texture.001', n, '')
            #if hair_color!=None:
            mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = hair_color
            hair_mats.append(mat)
            hair.append(obj)
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
            if set_tex(obj, 'Main Texture', n, 'MainTex') is None:
                disconnect_link(mat, 'Alpha')
                disconnect_link(mat, 'Combined Color')
            if set_tex(obj, 'Metallic', n, 'MetallicGlossMap', csp='Non-Color') is None:
                disconnect_link(mat, "Material Properties")
            set_bump(obj, 'Bump', n, '')
            ok = set_tex(obj, 'Specular2', n, 'DetailGlossMap2', csp='Non-Color') is not None
            ok = ok and (set_tex(obj, 'DetailMask', n, 'DetailMask', csp='Non-Color') is not None)
            ok = ok and (set_tex(obj, 'Specular', n, 'DetailGlossMap', csp='Non-Color') is not None)
            if not ok:
                disconnect_link(mat, "Combine Detail")                
            if set_tex(obj, 'Occlusion', n, 'OcclusionMap', csp='Non-Color') is not None:
                disconnect_link(mat, 'Damage')
                # Item does not support clothes damage
                mat.node_tree.nodes['Value'].outputs[0].default_value=-0.01
        arm['hair_mats']=hair_mats
    if len(hair)>1:
        join_meshes([x.name for x in hair])

def fixup_head(body):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bpy.data.objects[body["o_head"]]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type="VERT")
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles()

def fixup_torso(body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    join_meshes([body.name, body["nails"]], body.name)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type="VERT")
    bpy.ops.mesh.select_non_manifold()
    bpy.ops.mesh.remove_doubles(use_unselected=True)

def stitch_head_to_torso(body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    meshes=[body.name,body['o_head']]
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
    
    bpy.ops.object.mode_set(mode='OBJECT')
    sh = bpy.data.objects[body['o_eyeshadow']]
    sh.vertex_groups.clear()
    sh.vertex_groups.new(name='cf_J_eye_rs_L')
    sh.vertex_groups.new(name='cf_J_eye_rs_R')
    for v in range(len(sh.data.vertices)):
        side = 1 if sh.data.vertices[v].co[0]<0 else 0
        sh.vertex_groups[side].add([v], 1.0, 'ADD')
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.mark_sharp(clear=True)

    bpy.ops.mesh.select_all(action='DESELECT')
    meshes=[body.name,body['o_eyebase_L'],body['o_eyebase_R'],body['o_eyelashes'],body['o_eyeshadow']]
    bpy.ops.object.mode_set(mode='OBJECT')
    body = join_meshes(meshes, body.name)

    #bpy.ops.mesh.select_all(action='SELECT')

    body.cycles.use_adaptive_subdivision = True
    body.cycles.dicing_rate=2.0
    mod=body.modifiers.new("subsurf", "SUBSURF")
    mod.levels=2
    mod.show_viewport=False
    try:
        body.data.use_auto_smooth=False
    except:
        pass

    
def import_bodyparts(fbx, wipe_scene):
    if wipe_scene:
        for bpy_data_iter in (bpy.data.objects, bpy.data.meshes):
            for id_data in bpy_data_iter:
                #if  id_data.name!="Cube" and id_data.name!="Material Cube" and not id_data.name.startswith('Prefab '):
                bpy_data_iter.remove(id_data)

    obj_list = bpy.data.objects.keys()
    arm_list = [x for x in obj_list if bpy.data.objects[x].type=='ARMATURE']
    bpy.ops.import_scene.fbx(filepath=fbx)
    new_obj_list = bpy.data.objects.keys()
    new_arm_list = [x for x in new_obj_list if bpy.data.objects[x].type=='ARMATURE']
    new_arms=[x for x in new_arm_list if (x not in arm_list)]
    #print(arm_list)
    #print(new_arm_list)
    #print(new_arms)
    if len(new_arms)==0:
        raise ImportException("No armatures found in the FBX")
    arm = bpy.data.objects[new_arms[0]]
    while arm.parent is not None:
        arm = arm.parent
    #print("Root armature", arm)
    new_objects=[bpy.data.objects[x] for x in new_obj_list if (x not in obj_list)]        

    #if not 'Armature' in bpy.data.objects:
    #    return False, None, None
    #arm = bpy.data.objects['Armature']

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.scale_clear()
    
    trash_objects=[]
    for id_data in new_objects:
        if id_data.name.startswith('k_') \
        or id_data.name.startswith('f_') \
        or id_data.name.startswith('cf_J') \
        or id_data.name.startswith('HS2_') \
        or id_data.name.startswith('N_') \
        or id_data.type=='EMPTY':
            trash_objects.append(id_data.name)
    unparent=[x for x in bpy.data.objects if x.parent in trash_objects]
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
        raise ImportException('Could not find the body mesh in this fbx')
    body = bpy.data.objects[bn]
    body['Boy']=1.0 if boy else 0.0
    bone_map={
    'N_Wrist_L': 'cf_J_Hand_L',
    'N_Wrist_R': 'cf_J_Hand_R',
    'N_Ring_L': 'cf_J_Hand_Ring02_L',
    'N_Ring_R': 'cf_J_Hand_Ring02_R',
    'N_Waist': 'cf_J_Kosi01',
    'N_Earring_L': 'cf_J_EarLow_L',
    'N_Earring_R': 'cf_J_EarLow_R',
    'N_Megane': ('cf_J_NoseBridge_t', 'cf_J_Custom_Nosebridge_S'),
    'N_Chest_f': 'cf_J_Neck',
    'N_Head_top': 'cf_J_FaceUp_tz',
    'N_chest': 'cf_J_Spine03',
    'N_Chest': 'cf_J_Neck',
    'N_Head': 'cf_J_Head',
    }
    
    for tn in trash_objects:
        id_data = bpy.data.objects[tn]
        v=[y.name for y in id_data.children]
        for n in v:
            y = bpy.data.objects[n]
            if y.type!='MESH':
                continue
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = arm
            y.select_set(True)
            if len(y.modifiers)>0 and y.modifiers[0].type=='ARMATURE':
                print("Reparenting", y.name, " -> ", arm, "as armature")
                bpy.ops.object.parent_set(type='ARMATURE', keep_transform=True)
            else:
                bone=None
                c = id_data.parent
                bpy.ops.object.select_all(action='DESELECT')
                bpy.context.view_layer.objects.active = id_data.parent
                print("Trying to parent", y.name)
                while c is not None:
                    print(" Parent", c.name)
                    if c.name in bone_map:
                        bone = bone_map[c.name]
                        break
                    if (not c.name.startswith('N_')) and c.name in arm.data.bones.keys():
                        bone = c.name
                        break
                    c = c.parent
                if bone is not None:
                    if isinstance(bone,tuple):
                        for x in bone:
                            #print(x, arm.data.edit_bones, x in arm.data.bones.keys())
                            if x in arm.data.bones.keys():
                                bone = x
                                break
                        else:
                            bone = None
                    if bone is None:
                        print("Can't find any bones for", y.name)
                    elif (bone in arm.data.bones.keys()):
                        print("Reparenting", y.name, " -> ", arm, "as bone", bone)
                        bpy.context.view_layer.objects.active = arm
                        bpy.ops.object.mode_set(mode='EDIT')
                        arm.data.edit_bones.active = arm.data.edit_bones[bone]
                        bpy.ops.object.mode_set(mode='OBJECT')
                        y.select_set(True)
                        bpy.ops.object.parent_set(type='BONE', keep_transform=True)
                    else:
                        print("Can't parent", y.name, bone)
                else:
                    print("Could not identify the parent bone for", y.name)
                    c = id_data.parent
                    while c is not None:
                        print(c.name)
                        c = c.parent
                #y.parent = id_data.parent                    
            #y.matrix_parent_inverse = id_data.parent.matrix_world.inverted()
        #print('Deleting', tn)
    #bpy.abcd()
    for tn in trash_objects:
        id_data = bpy.data.objects[tn]
        bpy.data.objects.remove(id_data)
    bpy.data.objects.remove(bpy.data.objects['o_namida'])
    for x in bodyparts:
        for y in arm.children: #bpy.data.meshes.keys(): #sc.objects.keys():
            if y.name==x or y.name.startswith(x+'.'):
                body[x]=y.name #bpy.data.meshes[y]
           
    for y in arm.children:
        if y.type=='MESH':
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = y
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.mark_sharp(clear=True)
            bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.scale=Vector([0.12, 0.12, 0.12])
    #bpy.ops.object.scale_clear()
    return True, arm, body


def load_customization(arm, custfn):
    try:
        f=open(custfn, "r").readlines()
    except:
        print("Failed to open", custfn)
        return
    print("Customization script found")
    for x in f:
        y = x.split()
        bone = y[0]
        if bone in arm.pose.bones:
            insns = y[1]
            y = y[2:]
            if insns.startswith('l'):
                arm.pose.bones[bone].location = Vector([float(y[0])*0.01, float(y[1])*0.01, float(y[2])*0.01])
                y=y[3:]
                insns=insns[1:]
            if insns.startswith('r'):
                arm.pose.bones[bone].rotation_euler = Euler([float(y[0])*math.pi/180., float(y[1])*math.pi/180., float(y[2])*math.pi/180.])
                y=y[3:]
                insns=insns[1:]
            if insns.startswith('s'):
                arm.pose.bones[bone].scale = Vector([float(y[0]), float(y[1]), float(y[2])])
                y=y[3:]
                insns=insns[1:]
            arm["deformed_rig"][bone]=arm.pose.bones[bone].matrix_basis.copy()


def fix_neck_loop(body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    bmd = bmesh.new()
    bmd.from_mesh(body.data)
    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    v=set()
    for x in bmd.edges:
        if x.is_boundary:
            if len(x.verts[0].link_faces)<=3:
                v.add(x.verts[0].index)
            if len(x.verts[1].link_faces)<=3:
                v.add(x.verts[1].index)

    vg = body.vertex_groups['cf_J_Head_s'].index
    #body.data.vertices.select_set('select',boundary)
    boundary = [(x in v) and (add_extras.get_weight(body, x, vg)>0.99) for x in range(len(body.data.vertices))]
    #print(len(v), "boundary verts")
    #print(sum(boundary), "/", len(body.data.vertices), "selected")
    if len(boundary)>0:
        print("Attempting to delete the loop inside neck")
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        body.data.vertices.foreach_set('select',boundary)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.delete(type='VERT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_tools(mode='RESET')
        bpy.ops.object.mode_set(mode='OBJECT')

last_import_status='...'


def import_body(input, refactor, do_tweak_mouth, do_tweak_cheeks, add_injector,
        add_exhaust,
        replace_teeth, wipe, c_eye, c_hair, name,
        ):
    #global path, fbx, suffix, dumpfilename, last_import_status, customization
    global path, last_import_status
    print('import_body', input)
    hair_color=c_hair
    eye_color=c_eye
    path=input
    if len(path)>0 and path[-1]!='/':
        path=path+'/'
    dumps=[x for x in os.listdir(path) if x.endswith('.txt') and not x.startswith('pose_')]
    if len(dumps)>0:
        dumpfilename=path+dumps[0]
    else:
        dumpfilename=None
        last_import_status='Failed to locate the Unity dump'
        print('Failed to locate the Unity dump')
        return None

    fbxs=[x for x in os.listdir(path) if x.endswith('.fbx')]
    if len(fbxs)>0:
        fbx=path+fbxs[0]
        #if not use_config:
        name=fbxs[0][:-4]
    else:
        fbx=None
        last_import_status='Failed to locate the FBX'
        print('Failed to locate the FBX')
        return None

    custfile = path+'/customization'
    custfile2 = path+'/customization2'
    path += "Textures/"

    suffix=name

    if hair_color!=None:
        if len(hair_color)==3:
            hair_color=(hair_color[0], hair_color[1], hair_color[2], 1.0)

    if eye_color!=None:
        if len(eye_color)==3:
            eye_color=(eye_color[0], eye_color[1], eye_color[2], 1.0)
        
    try:
        t1=time.time()
        success, arm, body = import_bodyparts(fbx, wipe)
        t2=time.time()
        print("FBX imported in %.3f s" % (t2-t1))
        if success:
            t1=time.time()
            body=rebuild_torso(arm, body)
            load_textures(arm, body, hair_color, eye_color, suffix)
            fixup_head(body)
            fixup_torso(body)
            stitch_head_to_torso(body)
            fix_neck_loop(body)
            t2=time.time()
            print("Basic restructure done in %.3f s" % (t2-t1))

            body.add_rest_position_attribute = True

            arm.name=name
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.context.view_layer.objects.active = body
            bpy.context.object.modifiers["Armature"].show_in_editmode = True
            bpy.context.object.modifiers["Armature"].show_on_cage = True
            bpy.context.view_layer.objects.active = arm
            if do_tweak_cheeks:
                add_extras.repaint_cheeks(arm, body)

            t1=time.time()
            refactor = armature.reshape_armature(path, arm, body, not refactor, dumpfilename)
            t2=time.time()
            print("Armature refactor done in %.3f s" % (t2-t1))
            #return
            armature.add_ik(arm)

            load_customization(arm, custfile)
            print(body.data.vertices[9908].normal)
            body.active_shape_key_index = 0
            #print(body.data.vertices[9908].normal)
            body.data.update()
            #print(body.data.vertices[9908].normal)
            #return

            if replace_teeth:
                tooth = bpy.data.objects[body["o_tooth"]]
                tooth.data=bpy.data.meshes["Prefab Tooth v2"]
                tooth.data.shape_keys.key_blocks["20"].value=1.
                tooth.data.shape_keys.key_blocks["Smaller"].value=1.
                tooth.location=Vector([0, 15.92, -0.08])
                #tooth.data*=3.

            if do_tweak_mouth and refactor:
                t1=time.time()
                add_extras.tweak_mouth(arm, body)
                t2=time.time()
                print("Mouth tweak done in %.3f s" % (t2-t1))

            t1=time.time()

            if add_injector is None:
                add_injector = (body['Boy'] > 0.0)
            if add_injector:
                if refactor:
                    print("Trying to attach the injector")
                    add_extras.attach_injector(arm, body)
                else:
                    print("Can't attach the injector (fallback armature)")
            if add_exhaust and refactor:
                add_extras.attach_exhaust(arm, body)
            if do_tweak_mouth:
                load_customization(arm, custfile2)

            add_extras.add_mouth_blendshape(body)
            add_extras.tweak_nose(body)
            add_extras.paint_scalp(body)
            t2=time.time()
            print("Tweaks done in %.3f s" % (t2-t1))

            #return
            if wipe:
                #t1=time.time()
                bpy.ops.object.mode_set(mode='OBJECT')
                light_data = bpy.data.lights.new('light', type='POINT')
                light = bpy.data.objects.new('light', light_data)
                bpy.context.collection.objects.link(light)
                light.location = (0.2, -2, 1.5)
                light.data.energy=100.0
                #t2=time.time()
                #print("Scene wiped in %.3f s" % (t2-t1))
            bpy.context.view_layer.objects.active = arm
            bpy.ops.object.mode_set(mode='OBJECT')

            bpy.types.Object.body = body.name
            #arm.hair_color = FloatVectorProperty(name="Hair color", default=hair_color[:3], subtype='COLOR', min=0.0, max=1.0, get=get_hair_color, set=set_hair_color)
            #arm.eye_color = FloatVectorProperty(name="Eye color", default=eye_color[:3], subtype='COLOR', min=0.0, max=1.0, get=get_eye_color, set=set_eye_color)
            #if body['Boy']>0.0 and refactor:
            #    create_male_properties(arm)
            arm["hair_color"] = hair_color[:3]
            arm["eye_color"] = eye_color[:3]

            arm["daisy_protocol"] = 0.0
            arm["custom_geo"] = 1.0
            arm['ik'] = True

            body["pore_depth"] = 1.0
            body["pore_intensity"] = 1.0
            body["pore_density"] = 1.0

            bpy.context.view_layer.objects.active = body
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.context.view_layer.objects.active = arm
            bpy.ops.object.mode_set(mode='POSE')

            last_import_status=name+' imported successfully'
        else:
            last_import_status='Failed to locate the FBX'
            print('Failed to import body')
    except ImportException as e:
        print(e.text)
        last_import_status=e.text
    except:
        last_import_status='Import failed, see system console for details'
        raise
    return arm