import bpy
import os
import bmesh
import math
from mathutils import Matrix, Vector
#bones=bpy.data.armatures['Armature'].data.bones
#for x in bones.keys():

dump='C:\\Temp\\HS2\\UserData\\MaterialEditor\\dump3.txt'
dump=open(dump,'r').readlines()
dump=[x.strip() for x in dump]

bone_pos={}
bone_w2l={}
bone_parent={}
#bone_scale={}
name=''
root_pos=[0,0,0]

def mul4(x, y):
    return [sum([x[i][j]*y[j] for j in range(4)]) for i in range(4)]

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
            m[0][3]-=root_pos[0]
            m[1][3]-=root_pos[1]
            m[2][3]-=root_pos[2]
            m[0][1]*=-1
            m[0][2]*=-1
            m[0][3]*=-1
            m[1][0]*=-1
            m[2][0]*=-1
            m[3][0]*=-1
            #root=mul4(m, [0,0,0,1])#[m[0][3],m[1][3],m[2][3],m[3][3]]
            #print(name)
            bone_pos[name]=m
            """
            root = mul4(pm, root)
            root[0]/=root[3]
            root[1]/=root[3]
            root[2]/=root[3]
                bone_pos[name]=(root[0],root[1],root[2])
            sc=[0,0,0]
            for i in range(3):
                y=[0,0,0,1]
                y[i]=1
                y=mul4(m, y)
                y = mul4(pm, y)
                y[0]/=y[3]
                y[1]/=y[3]
                y[2]/=y[3]
                sc[i]=y[i]-root[i]
                #print(root)
            bone_scale[name]=sc
            #print(name,root)
            """
#        else:
#                print('No known parent for ', name)
        
arm = bpy.data.objects['Armature']
body = arm.children[0]
scene_bones=arm.data.bones.keys()        
    
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.rotation_clear()
bpy.ops.object.scale_clear()

def matrix_world(armature_ob, bone_name):
    local = armature_ob.data.bones[bone_name].matrix_local
    basis = armature_ob.pose.bones[bone_name].matrix_basis
    parent = armature_ob.pose.bones[bone_name].parent
    if parent == None:
        return  local @ basis
    else:
        parent_local = armature_ob.data.bones[parent.name].matrix_local
        mw = matrix_world(armature_ob, parent.name)
        return  mw @ (parent_local.inverted() @ local) @ basis

def reshape_mesh_one_bone(x):        
    b = bpy.data.objects['Armature'].data.bones[x]
    if x in bone_pos:
        bpy.context.object.data.bones.active = b
        mw = matrix_world(arm, x)
        target = Matrix(bone_pos[x])
        #print(x, bpy.context.active_pose_bone.matrix_basis)
        bpy.context.active_pose_bone.matrix_basis = bpy.context.active_pose_bone.matrix_basis @ mw.inverted() @ target
    for x in b.children.keys():
        reshape_mesh_one_bone(x)

def reset_pose_one_bone(x):        
    b = bpy.data.objects['Armature'].data.bones[x]
    if x in bone_pos:
        bpy.context.object.data.bones.active = b
        bpy.context.active_pose_bone.matrix_basis = Matrix()
    for x in b.children.keys():
        reset_pose_one_bone(x)


def reshape_mesh():
    bpy.ops.object.mode_set(mode='POSE')
    reshape_mesh_one_bone('cf_J_Root')    
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_apply(modifier='Armature')
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    reset_pose_one_bone('cf_J_Root')    

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE')
    
reshape_mesh()    
    
def reshape_armature(): 
    bpy.ops.object.mode_set(mode='EDIT')
    #bpy.ops.armature.select_all(action='SELECT')
    #bones = bpy.context.selected_bones
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
        #print(x.name)
        if x.name in bone_pos:
            p = Matrix(bone_pos[x.name])
            local = arm.data.bones[x.name].matrix_local
            bone_length =  (p @ x.tail) - (p @ x.head)
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

    bpy.ops.object.mode_set(mode='POSE')
        
    for n in ['cf_J_LegKnee_dam_L', 'cf_J_LegKnee_dam_R', 
            'cf_J_LegKnee_back_L', 'cf_J_LegKnee_back_R',
            'cf_J_SiriDam_L', 'cf_J_SiriDam_R',
            'cf_J_LegUpDam_L', 'cf_J_LegUpDam_R',
            ]:
        bone = arm.pose.bones[n]
        bpy.types.ArmatureBones.active = bone
        con = bone.constraints.new('COPY_ROTATION')
        con.mix_mode='ADD'
        con.target=arm
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
            
reshape_armature()            
