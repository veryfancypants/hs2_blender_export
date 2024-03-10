import bpy
import os
from os import path
import bmesh
import math
import time
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy
from .solve_for_deform import try_load_solution_cache, solve_for_deform, save_solution_cache
from . import add_extras, importer

def recompose(v):
        T = Matrix.Translation(v[0])
        R = v[1].to_matrix().to_4x4()
        S = Matrix.Diagonal(v[2].to_4d())            
        return T @ R @ S


"""

# Currently known unclassifieds:

cf_J_LegKnee_low_s_L offset z 
cf_J_LegKnee_back_s_L offset z

cf_J_LegLow03_s_L offset x,z, rotation z
    offset_x = t
    offset_z = 1.25 t
    rot_x = rot_z = -1.75 t rad

regression: t = 0.0006-0.0659*(leglow03_scale_z-1)

cf_J_LegUp01_L 3

cf_J_LegUp01_s_L offset x,z, rotation z
    offset_x = t
    offset_z = 0.115 t
    rot_z = -0.215 t rad

cf_J_Spine01_s offset z
cf_J_ArmUp00_L offset z
cf_J_ArmUp01_s_L
    nontrivial offset and z-rotation; appear linked to Shoulder02_s offset, though the exact formula is nontrivial
    (possibly piecewise linear?)

"""


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
#        NOTE: we are reconstructing everything from dump values with only 5 significant digits; 
#        it is common for 'x' values to be reconstructed as slightly nonzero. These are purely rounding errors.
# 'c': constrained by other attributes, no direct manipulation, must reset to default when loading pose
# 's': soft, affects character's intrinsic shape
# 'S': (presumed) internal soft: affects intrinsic shape, but not settable directly from UI. 
# 'f': FK, affects character's pose
# 'i': seeing small numbers here, assume they may be ignored; flag and report if seeing a large value
#         some are side-effects of small but nonzero rolls on many bones
# 'u': potentially large numbers of unknown origin with nontrivial effect on mesh
# 
# Most 'u's are probably 'S'
#
# Actual characters will often have additional bones to control hair, genitals, and accessories.
#
# Several of categories here were flipped from x to s to allow better customization.
#
bone_classes={
'cf_N_height': 'fffxscc', #overall body scale; must be uniform
'cf_J_Kosi01_s': 'xxxxsxs', #pelvis width/thickness
'cf_J_Kosi02_s': 'xxxxsxs',
'cf_J_Kokan': 'xxsssss', # "Genital area scale"; added offset & rotation for dp

'cf_J_SiriDam_': 'c',

'cf_J_Siri_s_': 'sssssss', # "Ass position" (offset z), "Ass scale" (scale x/y/z), "Butt size" modifies all offsets and scales
# 'Butt size 200 is offset 0.6000 0.2500 -0.6259, scale 2.4621 2.1000 2.8724

'cf_J_Siriopen_s_': '?', # effect unclear - my meshes don't even have vgroups for it
'cf_J_Ana': 'sssssss',  # scale is "Anus scale" 
'cf_J_LegUpDam_s_': 'xixxsxs', # 'Outer Upper Thigh Scale X/Z'

'cf_J_LegUp00_': 'sssfscc', # game allows legup00 offset to travel along 1 axis only - offsets y and z are proportional to x
'cf_J_LegUp01_': 'xxxSxxx',

# The correction moves soft tissue to the axis and slightly back and bends it 
'cf_J_LegUp01_s_': 'SxSSsxs', # 'Upper Thigh Scale X/Z'; no dynamic constraint
'cf_J_LegUp02_': 'xxxcxxx', # what's the constraint (if any)?

'cf_J_LegUp02_s_': 'xxxisxs', #'Center Thigh Scale X/Z'
'cf_J_LegUp03_s_': 'xxxxsxs', #'Lower Thigh Scale X/Z'

'cf_J_LegKnee_low_s_': 'xxScsss', # 'Kneecap Scale'; no dynamic constraint
'cf_J_LegKnee_back_s_': 'xxSxsss', # 'Kneecap Back Scale'; no dynamic constraint

'cf_J_LegLow01_s_': 'ixuisxs', # 'Upper Calve Scale'; no dynamic constraint
'cf_J_LegLow02_s_': 'xxxxsxs', # 'Center Calve Scale'; no dynamic constraint

'cf_J_LegLow03_s_': 'SxSSsxs', # 'Lower Calve Scale'; no dynamic constraint

'cf_J_Foot01_': 'xxxfsss', # 'Foot Scale 1'; need separate scales for left-right and forward-back
'cf_J_Foot02_': 'xssfsss', # 'Foot Scale 2'; allowing offset to fit ankle medial/lateral hits
'cf_J_Toes01_': 'xcsfsss', #  position is 'Foot Toes Offset' (axis 0.0, -0.15, 1.1); scale is 'Foot Toes Scale'

'cf_J_Toes_Hallux1_': 'sssfsss',
'cf_J_Toes_Long1_': 'sssfsss',
'cf_J_Toes_Middle1_': 'sssfsss',
'cf_J_Toes_Ring1_': 'sssfsss',
'cf_J_Toes_Pinky1_': 'sssfsss',

'cf_J_LegUpDam_': 'c',
'cf_J_LegKnee_back_': 'c',  # r - dynamic constraint
'cf_J_LegKnee_dam_': 'c',

# these are normally scale xz only, but could have scale y if the player messes with 'Torso Scale' sliders
'cf_J_Spine01_s': 'usSssss', # offset y is 'Waist Height'; scales are 'Waist Width', 'Waist Thickness', 'Lower Torso Scale'
'cf_J_Spine02_s': 'xxxssss', # 'Chest Width', 'Chest Thickness', 'Middle Torso Scale'
'cf_J_Spine03_s': 'xxxssss', # "Shoulder Width', 'Shoulder Thickness'
'cf_J_Spine01_r_s': 'xssssss',
'cf_J_Spine02_r_s': 'xssssss',
'cf_J_Spine03_r_s': 'xssssss',

'cf_J_Shoulder_': 'f',

# Shoulder Shape' is bone length
'cf_J_Shoulder02_s_': 'sxxxsss',# x offset is "Shoulder Shape", scale is 'Shoulder Scale'

# Fixed constraint: off_z = 0.0261*off_x
'cf_J_ArmUp00_': 'sxcfscc', # x offset is "Arm offset", scale is 'Arm overall scale', the rest not dynamic

# pretty sure all these have bugs in the game: they want Scale Y/Z for each

# off_z is purely the effect of roll of ArmUp00
'cf_J_ArmUp01_s_': 'SSSSsss', # x,z are 'Upper Arm Deltoid Scale X/Z', the rest not dynamic

'cf_J_ArmUp02_s_': 'sssxsss', # x,z are 'Upper Arm Triceps Scale X/Z'
'cf_J_ArmUp03_s_': 'sssxsss', # x,z are 'Upper Arm Lower Scale X/Z'
'cf_J_ArmElbo_low_s_': 'xxxxsss', # x,z are 'Elbow Cap Scale X/Z'
'cf_J_ArmElboura_s_': 'xxuxsxs', # 'Elbow Scale'
'cf_J_ArmLow01_': 'xxxfscc', # it seems necessary to allow x-scale to proper fit 3d scans
'cf_J_ArmLow01_s_': 'sssxsss', # 'Forearm Upper Scale X/Z'
'cf_J_ArmLow02_s_': 'sssxsss', # 'Forearm Lower Scale X/Z'
'cf_J_Hand_': 'f',
'cf_J_Hand_s_': 'xxxxsss', # 'Hand Scale'; need at least separate x and z (different as much as 1.25 and 1.65) to fit the boy
'cf_J_Hand_Wrist_s_': 'xxxxsss', # Wrist Scale X/Z'

'cf_J_ArmUp01_dam_': 'c', 
'cf_J_ArmUp02_dam_': 'c',
'cf_J_ArmUp03_dam_': '?',
'cf_J_ArmElbo_dam_01_': 'cxccxxx', # dynamic constraint on position and rotation
'cf_J_ArmElboura_dam_': 'c',
'cf_J_ArmLow02_dam_': 'xxxcxss', 
'cf_J_Hand_Wrist_dam_': 'xxxcxxx',
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

'cf_J_Hips': 'xxxfxxx',
'cf_J_Kosi01': 'xxxfsxs',  # Optional scale x,z "Pelvis and legs scale X, Z"
'cf_J_Kosi02': 'xxxfsxs',  # Optional scale x,z "Hips and legs scale X, Z"
'cf_J_LegLow01_': 'f',
'cf_J_Spine01': 'f',
'cf_J_Spine02': 'f',
'cf_J_Spine03': 'f',
'cf_J_Mune00': 'xccfxxx',
'cf_J_Neck': 'f',
'cf_J_Head': 'f',

#Mune00 is Scale 1, Mune01 is Scale 2, Mune02 is Scale 3, Mune03 is Tip Scale, Mune04 is Areola Scale
'cf_J_Mune00_': 'iiiuxxx',
'cf_J_Mune00_t_':'sssssss',
'cf_J_Mune00_s_':'sssssss', # scale is 'Breast Scale 1'
'cf_J_Mune00_d_':'sxssxxx',
'cf_J_Mune01_': 'iiiixxx',
'cf_J_Mune01_s_': 'xssssss', # scale is 'Breast Scale 2'
'cf_J_Mune01_t_': 'sxssxxx',
'cf_J_Mune02_': 'xiiixxx',
'cf_J_Mune02_s_': 'xisssss',  # scale is 'Breast Scale 3'
'cf_J_Mune02_t_': 'xxssxxx',
'cf_J_Mune03_': 'xiixxxx', 
'cf_J_Mune03_s_': 'xxsxsss', # scale is 'Tip Scale'
'cf_J_Mune04_s_': 'xxsxsss', # scale is 'Areola Scale', bone length is 'Areola Protrusion'
'cf_J_Mune_Nip01_s_': 'ixsxsss', # scale is 'Nipple Scale'
'cf_J_Mune_Nip02_s_': 'xxixsss', # scale is 'Nipple Tip Scale'

'cf_J_Neck_s': 'xxxxsss', # how does the game set y-scale?
'cf_J_NeckUp_s': 'xssssss',
'cf_J_NeckFront_s': 'xssssss',

'p_cf_head_bone': 'xxxxxxx', 
'cf_J_FaceRoot': 'xxxxxxx',
'cf_J_FaceRoot_s': 'xssssss', # not in game
'cf_J_FaceBase': 'xscxsss', # offset is 'Head Position' (axis 0.00 0.20 0.06); scale is 'Head Scale'
'cf_J_Head_s': 'xssxsss',   # natively scale-only ('Head + Neck Scale'), allowing offset improves head positioning
'cf_J_FaceLowBase': 'xxSxxxx', 
'cf_J_FaceLow_s': 'xxxxsss',  # 'Lower Head Cheek Scale' gives uniform xyz scaling
'cf_J_FaceLow_s_s': 'xssssss',  # Created from cf_J_FaceLow_s to separate WG and bone parent functions
'cf_J_FaceUp_ty': 'xssxsss', # upper face height (moves eyes, ears and everything above them up/down);
 # scale is 'Upper Head Scale'; offset 2 dp
'cf_J_FaceUp_tz': 'xxsxsss', # upper face depth (moves eyes and eyebrows forward/back); scale is 'Upper Front Head Scale'
'cf_J_FaceUpFront_ty': 'xssssss',
'cf_J_FaceRoot_r_s': 'xssssss',

'cf_J_CheekLow_': 'sssssss',
'cf_J_CheekUp_': 'sssssss',
'cf_J_CheekMid_': 'sssssss',

'cf_J_Chin_rs': 'xssssss', # despite the name, controls the entire lower jaw; limited rotation
'cf_J_ChinTip_s': 'xssssss',
'cf_J_ChinLow': 'xsxxsss',
'cf_J_ChinFront_s': 'xssssss',
'cf_J_ChinFront2_s': 'xssssss',

'cf_J_MouthBase_tr': 'xssxsss', # 'mouth height', 'mouth depth'
'cf_J_MouthBase_s': 'xssssss',
'cf_J_Mouth_': 'fffffff', # offset Y moves the mouth corner up/down, quat Z turns the mouth corner
'cf_J_MouthLow': 'xssxsss', # position & width of the lower lip
'cf_J_MouthMove': '?',
'cf_J_Mouthup': 'xSxxsss',
'cf_J_MouthCavity': 'xxSxxxx',

'cf_J_EarLow_': 'xsxxsss',
'cf_J_EarUp_': 'sssisss',
'cf_J_EarBase_s_': 'xxsssss', # must allow offset z to move ears forward/back

# the chain is t -> s -> r -> eyepos_rz -> look
'cf_J_Eye_t_': 'ssssxxx', # offset moves the eye + the eyelid; quat z rotates the eyelids around the forward-back axis
'cf_J_Eye_s_': 'SSSxsss', # scale x,y scales the eye
'cf_J_Eye_r_': 'xxxsxxx', # quat y rotates the eyelids around the vertical axis; quat z would rotate around the forward-back axis
'cf_J_EyePos_rz_': 'xxxsxxx', # observed nontrivial quat z - rotating the eyeball around the forward axis
'cf_J_look_': 'f',

'cf_J_Eye01_': 'xxxSxxx', # how does the game set rotation?
'cf_J_Eye02_': 'xxxSxxx', 
'cf_J_Eye03_': 'iiiSxxx', 
'cf_J_Eye04_': 'xxxSxxx', 
'cf_J_Eye01_s_': 'sssssss', # may not be exposed in game
'cf_J_Eye02_s_': 'sssssss',
'cf_J_Eye03_s_': 'sssssss',
'cf_J_Eye04_s_': 'sssssss',

'cf_J_NoseBase_trs': 'xssxxxx', # Game uses _trs for offset and _s for rotation & scale. 
# Offset on _trs moves the entire nose, offset on _s excludes the bridge.
'cf_J_NoseBase_s': 'xxxssss', # rotation: nose angle, X-axis only
'cf_J_Nose_r': 'xxxsxxx',
'cf_J_Nose_t': 'xssssss',  # offset z moves nose (minus bridge) forward/back; quat x turns nose up/down
'cf_J_Nose_t_s': 'xssssss',
'cf_J_Nose_tip': 'xssssss', # moves and scales the nose tip
'cf_J_NoseWing_tx_': 'sssssss', # offset moves the nostril; rotation twists the nostril in odd ways
'cf_J_NoseBridge_t': 'xssssss', # nose bridge vertical position (y), height (z), & shape (r)
'cf_J_NoseBridge_s': 'xssssss', # nose bridge width
'cf_J_NoseCheek_s': 'xssssss',
'cf_J_Nostril_': 'sssssss',
'cf_J_Nose_Septum': 'xssssss',
'cf_J_Nasolabial_s': 'xssssss',

'cf_J_Forehead': 'xxxxsss',
'cf_J_UpperJaw': 'sssssss',
'cf_J_LowerJaw': 'sssxsss',

'balls': 'fffffff',
'stick_01': 'fffffff',
'stick_02': 'fffffff',
'stick_03': 'fffffff',
'stick_04': 'fffffff',
'tip_base': 'fffffff',
'fskin_bottom': 'fffffff',
'fskin_top': 'fffffff',
'fskin_left': 'fffffff',
'fskin_right': 'fffffff',
'sheath': 'fffffff',
}

def bone_class(x, comp=None):
    c=None
    if x.startswith('cf_J_Vagina') or x.startswith('cf_J_Legsk'):
        return '???????'
    elif x in bone_classes:
        c = bone_classes[x]
    elif x[:-1] in bone_classes:
        c = bone_classes[x[:-1]]
    else:
        c='?'
    if c=='?':
        c='???????'
    if c=='f':
        c='xxxfxxx'
    if c=='c':
        c='xxxcxxx'
    if c!=None and len(c)!=1 and len(c)!=7:
        print('ERROR: illegal bone class ', c, x)
    if c==None:
        return c
    if comp==None:
        return c
    c=c.lower()
    if comp=='offset':
        return c[:3]
    elif comp=='rotation':
        return c[3]
    elif comp=='scale':
        return c[4:]
    else:
        print('Invalid bone class component ', comp, 'requested')
        return None


rot_mode='YZX'

def copy_location(arm, c, comps='xyz'):
    if not c+'R' in arm.pose.bones:
        return
    bone = arm.pose.bones[c+'R']
    bpy.types.ArmatureBones.active = bone
    bone.lock_location[0]=True
    bone.lock_location[1]=True
    bone.lock_location[2]=True
    con = bone.constraints.new('COPY_LOCATION')
    con.target=arm
    con.owner_space='LOCAL'
    con.target_space='LOCAL'
    con.subtarget=c+'L'
    con.use_x='x' in comps
    con.use_y='y' in comps
    con.use_z='z' in comps
    con.invert_x=True

def copy_rotation(arm, c, target=None, flags='xyz', invert='yz', strength=1.0, order=None):
    if not c in arm.pose.bones:
        return
    bone = arm.pose.bones[c]
    bpy.types.ArmatureBones.active = bone
    con = bone.constraints.new('COPY_ROTATION')
    con.target=arm
    con.owner_space='LOCAL'
    con.target_space='LOCAL'
    con.subtarget=target if (target is not None) else c[:-1]+'L'
    con.euler_order=order or rot_mode
    con.use_x=('x' in flags)
    con.use_y=('y' in flags)
    con.use_z=('z' in flags)
    con.invert_x=('x' in invert) ^ (strength<0.0)
    con.invert_y=('y' in invert) ^ (strength<0.0)
    con.invert_z=('z' in invert) ^ (strength<0.0)
    con.influence=abs(strength)
    bone.lock_rotation[0]=True
    bone.lock_rotation[1]=True
    bone.lock_rotation[2]=True
    if order:
        bone.rotation_mode = order
        arm.pose.bones[con.subtarget].rotation_mode = order

def copy_scale(arm, c, comps='xyz'):
    if not c+'R' in arm.pose.bones:
        return
    bone = arm.pose.bones[c+'R']
    bpy.types.ArmatureBones.active = bone
    con = bone.constraints.new('COPY_SCALE')
    con.target=arm
    con.owner_space='LOCAL'
    con.target_space='LOCAL'
    con.subtarget=c+'L'
    con.use_x='x' in comps
    con.use_y='y' in comps
    con.use_z='z' in comps
    bone.lock_scale[0]=True
    bone.lock_scale[1]=True
    bone.lock_scale[2]=True

def delete_driver(arm, target_bone, target_prop, target_component):
    arm.pose.bones[target_bone].driver_remove(target_prop, target_component)

def drive(arm, target_bone, target_prop, target_component,
        driver_bone, driver_prop, formula, order='AUTO'):
    d=arm.pose.bones[target_bone].driver_remove(target_prop, target_component)
    d=arm.pose.bones[target_bone].driver_add(target_prop, target_component)
    var=d.driver.variables.new()
    var.type='TRANSFORMS'
    var.targets[0].id = arm
    var.targets[0].bone_target = driver_bone
    var.targets[0].transform_type = driver_prop
    var.targets[0].transform_space = 'LOCAL_SPACE'
    var.targets[0].rotation_mode = order
    d.driver.expression = formula

def drive2(arm, target_bone, target_prop, target_component,
        driver_bone1, driver_prop1, 
        driver_bone2, driver_prop2, 
        formula, order='AUTO'):
    arm.pose.bones[target_bone].driver_remove(target_prop, target_component)
    d=arm.pose.bones[target_bone].driver_add(target_prop, target_component)
    var=d.driver.variables.new()
    var.type='TRANSFORMS'
    var.targets[0].id = arm
    var.targets[0].bone_target = driver_bone1
    var.targets[0].transform_type = driver_prop1
    var.targets[0].transform_space = 'LOCAL_SPACE'
    var.targets[0].rotation_mode = order
    var2=d.driver.variables.new()
    var2.type='TRANSFORMS'
    var2.targets[0].id = arm
    var2.targets[0].bone_target = driver_bone2
    var2.targets[0].transform_type = driver_prop2
    var2.targets[0].transform_space = 'LOCAL_SPACE'
    var.targets[0].rotation_mode = order
    d.driver.expression = formula


def prettify_armature(arm, body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    #return
    #arm = bpy.data.objects['Armature']
    #arm = bpy.context.view_layer.objects.active


    """
    BONE LAYERS
    General ordering:
    * anything the user needs to pose the character
    * anything that seems totally useless, and anything unclassified
    * soft tissues (not used to pose, but may be used to customize the character)
    * IK
    last entry: all bones
    
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
    layer_names=[
    

    'Left leg',
    'Right leg',
    'Left arm',
    'Right arm',
    'Left hand',
    'Right hand',
    'Spine',
    'Feet',
    'Chin',
    'Mouth',
    'Nose',
    'Cheeks',
    'Brows',
    'Ears',
    'Eyes',
    'Misc',
    'Leg - soft', # 16
    'Arm - soft', # 17
    'Spine - soft', # 18
    'Constrained - soft', # 19
    'Eyes - soft', # 20
    '...',
    '...',
    '...',
    '...',
    '...',
    'Correctives',
    'Head internal',
    'Breasts',
    'Genitals',
    'IK',
    'Everything'
    ]
    #for ln in range(1,33):
    #    if 'Layer '+str(ln) in arm.data.collections:
    #        arm.data.collections['Layer '+str(ln)].name = layer_names[ln-1]
    for ln in layer_names:
        if ln!='...':
            arm.data.collections.new(ln)

    #for nl in range(1,33):
    #    arm.data.collections.new('Layer '+str(nl))

    for x in bpy.context.object.data.edit_bones:
        array=[False]*32
        array[15] = True
        side = (1 if x.name[-1]=='R' else 0)
        #if x.name in ['cf_J_Root', 'cf_N_height', 'cf_J_Hips', 'cf_J_Kosi03', 'cf_J_Kosi03_s']:
        #    array[15]=True
        #if x.name[:-1] in ['cf_J_ShoulderIK_', 'cf_J_Siriopen_s_']:
        #    array[15]=True
        if x.name[:-1] in ['cf_J_LegUp00_', 'cf_J_LegLow01_', 'cf_J_LegLowRoll_', 'cf_J_Foot01_', 'cf_J_Foot02_', 
            'cf_J_LegUp00_Twist_']:
            array[0+side]=True # Leg FK
        if x.name[:-1] in ['cf_J_LegLow01_s_', 'cf_J_LegLow02_s_',  'cf_J_LegLow03_s_',
            'cf_J_LegKnee_back_s_', 'cf_J_LegKnee_low_s_', 
            'cf_J_LegUp01_s_', 'cf_J_LegUp02_s_',  'cf_J_LegUp03_s_',
            'cf_J_Siri_s_', 'cf_J_LegUpDam_s_', ]:
            array[19 if side else 16]=True # Leg soft
        if x.name[:-1] in ['cf_J_LegUpDam_', 'cf_J_LegKnee_dam_', 'cf_J_LegKnee_back_',  'cf_J_SiriDam01_', 'cf_J_SiriDam_',
            'cf_J_Siri_', 'cf_J_LegUp01_', 'cf_J_LegUp02_', 'cf_J_LegUp03_', 'cf_J_LegLow03_', 
            ]:
            array[26]=True
        if x.name[:-1] in ['cf_J_Shoulder_', 'cf_J_ArmUp00_', 'cf_J_ArmLow01_', 'cf_J_Hand_', 'cf_J_ArmUp00_Twist_']:
            array[2+side]=True # Arm FK
        if x.name[:-1] in ['cf_J_Shoulder02_s_', 'cf_J_ArmUp01_s_', 'cf_J_ArmUp02_s_', 'cf_J_ArmElbo_low_s_', 
            'cf_J_ArmUp03_s_', 'cf_J_ArmLow01_s_', 'cf_J_Hand_Wrist_s_', 'cf_J_Hand_s_',
            'cf_J_ArmElboura_s_',  'cf_J_ArmLow02_s_']:
            array[19 if side else 17]=True # Arm soft
        if x.name[:-1] in ['cf_J_ArmUp01_dam_', 'cf_J_ArmUp02_dam_', 'cf_J_ArmUp03_dam_', 'cf_J_ArmElboura_dam_', 
            'cf_J_ArmElbo_dam_01_', 'cf_J_ArmLow02_dam_','cf_J_Hand_Wrist_dam_', 'cf_J_Hand_dam_']:
                array[26] = True
        if x.name in ['cf_J_Hips', 'cf_J_Kosi02', 'cf_J_Kosi01', 'cf_J_Spine01', 'cf_J_Spine02', 'cf_J_Spine03', 'cf_J_Neck', 'cf_J_Head', 'cf_N_height']:
            array[6]=True # Torso
        if x.name in ['cf_J_Kosi02_s', 'cf_J_Kosi01_s', 'cf_J_Spine01_s', 'cf_J_Spine02_s', 'cf_J_Spine03_s', 'cf_J_Neck_s',
            'cf_J_FaceBase', 'cf_J_Head_s', 
            'cf_J_Spine01_r_s', 'cf_J_Spine02_r_s', 'cf_J_Spine03_r_s']:
            array[18]=True # Torso soft
        if x.name[:-1] in [
            'cf_J_Hand_Thumb01_', 'cf_J_Hand_Index01_',  'cf_J_Hand_Middle01_',  'cf_J_Hand_Ring01_',  'cf_J_Hand_Little01_', 
            'cf_J_Hand_Thumb02_', 'cf_J_Hand_Index02_',  'cf_J_Hand_Middle02_',  'cf_J_Hand_Ring02_',  'cf_J_Hand_Little02_', 
            'cf_J_Hand_Thumb03_', 'cf_J_Hand_Index03_',  'cf_J_Hand_Middle03_',  'cf_J_Hand_Ring03_',  'cf_J_Hand_Little03_']:
            array[4+side]=True
        if x.name[:-1] in ['cf_J_Toes01_', 'cf_J_Toes_Long1_', 'cf_J_Toes_Hallux1_', 'cf_J_Toes_Middle1_', 'cf_J_Toes_Ring1_', 'cf_J_Toes_Pinky1_', 
                           'cf_J_Toes_Long2_', 'cf_J_Toes_Hallux2_', 'cf_J_Toes_Middle2_', 'cf_J_Toes_Ring2_', 'cf_J_Toes_Pinky2_']:
            array[7]=True
        if 'Mune' in x.name:
            array[28]=True
        if x.name in ['cf_J_Ana', 'cf_J_Kokan']:
            array[29]=True
        if ('Vagina' in x.name) or ('_dan' in x.name):
            array[29]=True
        if x.name in ['cf_J_ChinLow', 'cf_J_Chin_rs', 'cf_J_ChinTip_s']:
            array[8]=True
        if x.name in ['cf_J_Mouthup', 'cf_J_MouthLow', 'cf_J_MouthBase_tr', 'cf_J_MouthBase_s', 'cf_J_MouthCavity']:
            array[9]=True
        if x.name[:-1] in ['cf_J_Mouth_']:
            array[9]=True
        if x.name in ['cf_J_Nose_t', 'cf_J_Nose_tip', 'cf_J_NoseBase_trs',
            'cf_J_Nose_r', 'cf_J_NoseBridge_s', 'cf_J_NoseBridge_t', 'cf_J_NoseTip', 'cf_J_NoseBase_s']:
            array[10]=True
        if x.name[:-1] in ['cf_J_NoseWing_tx_']:
            array[19 if side else 10]=True
        if x.name[:-1] in ['cf_J_CheekLow_', 'cf_J_CheekUp_', 'cf_J_CheekMid_']:
            array[19 if side else 11]=True
        if x.name[:-1] in ['cf_J_MayuTip_s_', 'cf_J_MayuMid_s_', 'cf_J_Mayu_']:
            array[12]=True
        if x.name[:-1] in ['cf_J_EarUp_', 'cf_J_EarBase_s_', 'cf_J_EarLow_']:
            array[19 if side else 13]=True
        if x.name in ['cf_J_Eye_t_R', 'cf_J_Eye01_s_R', 'cf_J_Eye02_s_R', 'cf_J_Eye03_s_R', 'cf_J_Eye04_s_R', 'cf_J_Eye_s_R',
            'cf_J_Eye_t_R']:
            array[19] = True
        elif x.name[:-1] in ['cf_J_Eye01_s_', 'cf_J_Eye02_s_', 'cf_J_Eye03_s_', 'cf_J_Eye04_s_', 'cf_J_Eye_s_', 'cf_J_Eye_t_']:
            array[20] = True
        # Can control gaze direction with eye_rs
        elif x.name[:-1] in [
            'cf_J_Eye01_', 'cf_J_Eye02_', 'cf_J_Eye03_', 'cf_J_Eye04_', 
            'cf_J_eye_rs_', 'cf_J_Eye_r_', 
            ]:
            array[14]=True
        #if x.name[:-1] in ['cf_J_look_']:
        #    array[24]=True
        if x.name in ['cf_J_FaceLow_s', 'cf_J_FaceRoot_s', 'cf_J_FaceUp_ty', 'cf_J_FaceUp_tz', 'cf_J_FaceLowBase'] \
            or x.name[:-1] in ['cf_J_pupil_s_', 'cf_J_EyePos_rz_']:
            array[27]=True
        #array[15] = not(any(array[:15]) or any(array[16:]))
        array[31] = True
        for k in range(32):
            if array[k]:
                arm.data.collections[layer_names[k]].assign(x)
    
        # It would be nice to have all bones correctly oriented, but replacing either tail or roll replaces the matrix we just uploaded, 
        # and redefines the axes. Which, in turn, messes with bone constraints. Let's just leave everything pointing up.   

    # These bones are sometimes turned; elbow corrections don't work correctly unless they are reoriented
    for x in ['cf_J_ArmUp02_dam_', 'cf_J_ArmElboura_dam_']:
        for c in ('L','R'):
            if x+c in bpy.context.object.data.edit_bones:
                b = bpy.context.object.data.edit_bones[x+c]
                b.tail = b.head + Vector([0.0, 0.1, 0.0])

    bpy.ops.object.mode_set(mode='POSE')
    
    for b in arm.pose.bones:
        if b.rotation_mode == 'QUATERNION':
            b.rotation_mode = rot_mode

    limit_rotation_constraints=[
    #('cf_J_ArmLow01_L', 0, 0, -170, 0, 0, 0),
    #('cf_J_ArmLow01_R', 0, 0, 0, 170, 0, 0),
    ('cf_J_LegLow01_L', -5, 165, 0, 0, 0, 0),
    ('cf_J_LegLow01_R', -5, 165, 0, 0, 0, 0),
    ('cf_J_LegLowRoll_L', 0, 0, -60, 60, 0, 0),
    ('cf_J_LegLowRoll_R', 0, 0, -60, 60, 0, 0),

    ('cf_J_Shoulder_L', -30, 30, -10, 10, -10, 55),
    ('cf_J_Shoulder_R', -30, 30, -10, 10, -55, 10),
    ('cf_J_ArmLow01_L', -45, 45, -170, 0, 0, 0),
    ('cf_J_ArmLow01_R', -45, 45, 0, 170, 0, 0),
    ('cf_J_Hand_L', -60, 60, -30, 30, -90, 90),
    ('cf_J_Hand_R', -60, 60, -30, 30, -90, 90),
    ]
    limit_rotation_constraints+=[
    ('cf_J_LegUp00_L', -145, 30, -120, 120, -15, 45),
    ('cf_J_LegUp00_R', -145, 30, -120, 120, -45, 15),
    ('cf_J_ArmUp00_L', -135, 135, -120, 25, -105, 20),
    ('cf_J_ArmUp00_R', -135, 135, -25, 120, -20, 105),
    ]

    for c in limit_rotation_constraints:
            if not c[0]in arm.pose.bones:
                continue
            #continue
            bone = arm.pose.bones[c[0]]
            #bone.rotation_mode='XZY' if ('ArmUp00' in c[0]) else rot_mode
            bone.rotation_mode=rot_mode
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
            if c[1]==0 and c[2]==0:
                bone.lock_rotation[0]=True
                bone.lock_ik_x=True
            if c[3]==0 and c[4]==0:
                bone.lock_rotation[1]=True
                bone.lock_ik_y=True
            if c[5]==0 and c[6]==0:
                bone.lock_rotation[2]=True
                bone.lock_ik_z=True

    for c in bone_classes:
        if (c[-1]=='_' and '_s_' in c) or c in (
            'cf_J_NoseWing_tx_', 'cf_J_Eye_t_',
            'cf_J_EarLow_', 'cf_J_EarUp_',
            'cf_J_CheekLow_', 'cf_J_CheekUp_', 'cf_J_CheekMid_', 
            'cf_J_ArmUp00_', 'cf_J_ArmLow01_', 'cf_J_Hand_',
            'cf_J_Mune00_', 'cf_J_Mune00_t_', 'cf_J_Mune00_d_',
            'cf_J_Mune01_', 'cf_J_Mune02_', 'cf_J_Mune01_t_', 'cf_J_Mune02_t_',
            'cf_J_LegUp00_', 'cf_J_LegLow01_', 
            'cf_J_Foot01_', 'cf_J_Foot02_', 
            ):
            if c=='cf_J_LegUp01_s_':
                copy_scale(arm, c, comps='xy')
            elif c=='cf_J_LegUp02_s_':
                copy_scale(arm, c, comps='y')
                copy_location(arm, c, comps='xy')
            elif c=='cf_J_LegLow01_s_':
                copy_scale(arm, c, comps='xyz')
                copy_location(arm, c, comps='xy')
            elif c=='cf_J_LegLow02_s_':
                copy_scale(arm, c, comps='xyz')
                copy_location(arm, c, comps='xy')
            else:
                copy_scale(arm, c)
                copy_location(arm, c)
            if (c[-1]=='_' and '_s_' in c) or (c in ['cf_J_NoseWing_tx_', 'cf_J_Eye_t_',  'cf_J_EarLow_', 'cf_J_EarUp_',
                'cf_J_CheekLow_', 'cf_J_CheekUp_', 'cf_J_CheekMid_']):
                copy_rotation(arm, c+'R')

        s = bone_class(c, 'offset')
        def lock_location(bones, b, n):
            if b in bones:
                #if abs(bones[b].location[n])>0.001:
                #   print("Warning: locking", b, "in non-null location")
                bones[b].lock_location[n]=True
        for n in range(3):
            if len(s)==3 and (s[n]=='x' or s[n]=='c'):
                lock_location(arm.pose.bones, c, n)
                lock_location(arm.pose.bones, c+'L', n)
                lock_location(arm.pose.bones, c+'R', n)
        s = bone_class(c, 'scale')
        for n in range(3):
            if len(s)==3 and (s[n]=='x' or s[n]=='c'):
                if c in arm.pose.bones:
                    arm.pose.bones[c].lock_scale[n]=True
                elif c+'L' in arm.pose.bones:
                    arm.pose.bones[c+'L'].lock_scale[n]=True
                    arm.pose.bones[c+'R'].lock_scale[n]=True
        s = bone_class(c, 'rotation')
        for n in range(3):
            if s=='x' or s=='c':
                if c in arm.pose.bones:
                    arm.pose.bones[c].lock_rotation[n]=True
                elif c+'L' in arm.pose.bones:
                    arm.pose.bones[c+'L'].lock_rotation[n]=True
                    arm.pose.bones[c+'R'].lock_rotation[n]=True

    # These may not be 100% exact. A few others exist and are implemented as drivers.
    constraints=[
        # turning the leg pulls the buttock after it
        ('cf_J_LegUp00_', 'cf_J_SiriDam_', 'x', 0.5, 'YZX'),
        ('cf_J_LegUp00_', 'cf_J_SiriDam_', 'z', 0.25, 'YZX'),

        # raising leg forward/sideways pulls the front upper thigh 
        ('cf_J_LegUp00_', 'cf_J_LegUpDam_', 'xz', 0.737, 'YZX'),

        ('cf_J_LegLow01_', 'cf_J_LegKnee_dam_', 'x', 0.5, 'YZX'),
        ('cf_J_LegLow01_', 'cf_J_LegKnee_back_', 'xyz', 1.0, 'YZX'),

        # when twisting the hand, wrist and lower part of lower arm follows
        ('cf_J_Hand_', 'cf_J_ArmLow02_dam_', 'x', 0.5, 'XYZ'),
        ('cf_J_Hand_', 'cf_J_Hand_Wrist_dam_', 'x', 1.0, 'XYZ'), 

        # when bending the hand up/down or sideways, wrist partially follows
        ('cf_J_Hand_','cf_J_Hand_dam_', 'yz', 0.7, 'XYZ'),

        # when bending the elbow, correct the inside of the elbow 
        ('cf_J_ArmLow01_', 'cf_J_ArmElboura_dam_', 'yz', 0.577, 'XYZ'),
        # and the outside 
        ('cf_J_ArmLow01_', 'cf_J_ArmElbo_dam_01_', 'y', 0.60, 'XYZ'),
    ]

    for c in constraints:
        for s in ('L','R'):
            #print("Trying to apply constraint", c[1]+s)
            copy_rotation(arm, c[1]+s, target=c[0]+s, flags=c[2], invert='', strength=c[3], order=c[4])
    
    arm.data.display_type = 'STICK'
    for c in arm.data.collections:
        c.is_visible = False
    for c in ['Left leg', 'Right leg', 'Left arm', 'Right arm', 'Spine', 'IK']:
        arm.data.collections[c].is_visible = True
    arm.show_in_front = True

def delete_drivers(arm):
    for s,sgn in (('L','-'),('R','')):
        delete_driver(arm, 'cf_J_ArmUp01_dam_' + s, 'rotation_euler', 0)
        delete_driver(arm, 'cf_J_ArmUp02_dam_' + s, 'rotation_euler', 0)
        delete_driver(arm, 'cf_J_SiriDam_' + s, 'rotation_euler', 1)
        delete_driver(arm, 'cf_J_LegUp01_' + s, 'rotation_euler', 1)
        delete_driver(arm, 'cf_J_LegUp02_' + s, 'rotation_euler', 1)
        delete_driver(arm, 'cf_J_ArmElboura_dam_'+s, 'location', 2)
        delete_driver(arm, 'cf_J_ArmElboura_dam_'+s, 'scale', 1,)
        delete_driver(arm, 'cf_J_ArmElbo_dam_01_'+s, 'location', 2)
        delete_driver(arm, 'cf_J_SiriDam_'+s, 'location', 1)
        delete_driver(arm, 'cf_J_SiriDam_'+s, 'location', 2)
        delete_driver(arm, 'cf_J_LegUp01_s_'+s, 'location', 1)
        delete_driver(arm, 'cf_J_LegUp01_s_'+s, 'location', 2)
        delete_driver(arm, 'cf_J_LegUp01_s_'+s, 'scale', 2)
        delete_driver(arm, 'cf_J_LegUp01_s_'+s, 'location', 0)
        delete_driver(arm, 'cf_J_LegUp02_s_'+s, 'scale', 0)
        delete_driver(arm, 'cf_J_LegUp02_s_'+s, 'scale', 2)
        delete_driver(arm, 'cf_J_LegLow01_s_'+s, 'location', 2)
        delete_driver(arm, 'cf_J_LegLow02_s_'+s, 'location', 2)
        delete_driver(arm, 'cf_J_LegUp02_s_'+s, 'location', 2)

def set_drivers(arm):
    save_scale = str(arm.pose.bones['cf_J_LegUp01_s_L'].scale[2])
    save_scale_2x = str(arm.pose.bones['cf_J_LegUp02_s_L'].scale[0])
    save_scale_2z = str(arm.pose.bones['cf_J_LegUp02_s_L'].scale[2])

    save_legup01_x = str(-arm.pose.bones['cf_J_LegUp01_s_L'].location[0])
    save_scale_legup01_x = str(arm.pose.bones['cf_J_LegUp01_s_L'].scale[0])

    for s,sgn in (('L','-'),('R','')):
        # when twisting ArmUp00 (twist = along its length), gradient the effect from shoulder to elbow
        drive(arm, 'cf_J_ArmUp01_dam_' + s, 'rotation_euler', 0, 'cf_J_ArmUp00_'+s, 'ROT_X', '-0.75*var', order='SWING_TWIST_X') # changed from game -0.66
        drive(arm, 'cf_J_ArmUp02_dam_' + s, 'rotation_euler', 0, 'cf_J_ArmUp00_'+s, 'ROT_X', '-0.33*var', order='SWING_TWIST_X')

        # when twisting LegUp00, likewise gradient the effect from hip to knee, and propagate some twist up the buttock
        drive(arm, 'cf_J_SiriDam_' + s, 'rotation_euler', 1, 'cf_J_LegUp00_'+s, 'ROT_Y', '0.2*var', order='SWING_TWIST_Y')
        drive(arm, 'cf_J_LegUp01_' + s, 'rotation_euler', 1, 'cf_J_LegUp00_'+s, 'ROT_Y', '-0.85*var', order='SWING_TWIST_Y')
        drive(arm, 'cf_J_LegUp02_' + s, 'rotation_euler', 1, 'cf_J_LegUp00_'+s, 'ROT_Y', '-0.5*var', order='SWING_TWIST_Y')
        arm.pose.bones['cf_J_ArmUp00_'+s].rotation_mode='XYZ'

        drive(arm, 'cf_J_ArmElboura_dam_'+s, 'location', 2, 'cf_J_ArmLow01_'+s, 'ROT_Y', "-clamp("+sgn+"var-2,0,1)*0.5")
        drive(arm, 'cf_J_ArmElboura_dam_'+s, 'scale', 1, 'cf_J_ArmLow01_'+s, 'ROT_Y', "1+clamp("+sgn+"var-2,0,1)")
        drive(arm, 'cf_J_ArmElbo_dam_01_'+s, 'location', 2, 'cf_J_ArmLow01_'+s, 'ROT_Y', "clamp("+sgn+"var-2,0,1)*0.3")

        # Corrective that kicks in when leg is lifted to the point of touching belly with front upper thigh. Stronger when leg is also bent toward center.
        corrective="max(-var-("+sgn+"var_001)-1.5,0)"
        kwargs={'driver_bone1':'cf_J_LegUp00_'+s, 'driver_prop1':'ROT_X', 'driver_bone2':'cf_J_LegUp00_'+s, 'driver_prop2':'ROT_Z', 'order':'SWING_TWIST_Y'}
        drive2(arm, 'cf_J_SiriDam_'+s, 'location', 1, formula=corrective+"*-0.9", **kwargs)
        drive2(arm, 'cf_J_SiriDam_'+s, 'location', 2, formula=corrective+"*0.9", **kwargs)

        # optimal values vary a bit from char to char
        drive2(arm, 'cf_J_LegUp01_s_'+s, 'location', 1, formula=corrective+"*0.6", **kwargs)
        drive2(arm, 'cf_J_LegUp01_s_'+s, 'location', 2, formula=corrective+"*-0.9", **kwargs) 
        drive2(arm, 'cf_J_LegUp01_s_'+s, 'scale', 2, formula=save_scale+"+"+corrective+"*-0.3", **kwargs)

        # Corrective that kicks in when the leg is simultaneously lifted and bent toward center, especially when it's lifted more than 45 degrees.
        # Push the upper thigh slightly out to minimize clipping the belly and the pubic bone
        drive2(arm, 'cf_J_LegUp01_s_'+s, 'location', 0, formula=sgn+"1*"+save_legup01_x+"+clamp(-var,0,1)*max("+sgn+"var_001,0)*1.0", **kwargs)

        # Corrective that kicks in when knee is bent past ~110 degrees.
        # "Squish" the lower thigh (scale_x up, scale_z down) when the calf is pressed against the lower thigh.
        # Additionally, widen the entire thigh when we're sharply twisting the thigh bone (see Yoga pose for impact:
        # without this corrective, lower thigh looks weird there)
        corrective="clamp(abs(var_001)-1.0,0,0.5)+max(var-2.5,0)"
        kwargs={"driver_bone1":"cf_J_LegLow01_"+s, "driver_prop1":"ROT_X", "driver_bone2": "cf_J_LegUp00_"+s, "driver_prop2": "ROT_Y", "order": "SWING_TWIST_Y"}
        drive2(arm, 'cf_J_LegUp02_s_'+s, 'scale', 0, formula=save_scale_2x+"+"+corrective+"*1.5", **kwargs)
        drive2(arm, 'cf_J_LegUp02_s_'+s, 'scale', 2, formula=save_scale_2z+"+"+corrective+"*-1.5", **kwargs)

        corrective="max(var-2.5,0)"
        kwargs={"driver_bone":"cf_J_LegLow01_"+s, "driver_prop":"ROT_X"}

        # In response, lower thigh pushes the flesh of the calf.
        pos = str(arm.pose.bones["cf_J_LegLow01_s_L"].location[2])
        drive(arm, 'cf_J_LegLow01_s_'+s, 'location', 2, formula=pos+"+"+corrective+"*0.9", **kwargs)
        pos = str(arm.pose.bones["cf_J_LegLow02_s_L"].location[2])
        drive(arm, 'cf_J_LegLow02_s_'+s, 'location', 2, formula=pos+"+"+corrective+"*0.5", **kwargs)

        # Lower part of the thigh responds to two different correctives. It can be pushed forward by a sharply bent knee, and backward by a sharply bent thigh.
        # TODO: this does not work correctly when the thigh is sharply twisted (see: Yoga), because it pushes in the wrong direction.
        drive2(arm, 'cf_J_LegUp02_s_'+s, 'location', 2, 'cf_J_LegUp00_'+s, 'ROT_X', "cf_J_LegLow01_"+s, "ROT_X", "max(-var-1.5,0)*-0.6+max(var_001-2.25,0)*1.0", order='SWING_TWIST_Y')

def add_ik(arm):
    bpy.ops.object.mode_set(mode='OBJECT')  
    bpy.context.view_layer.objects.active = arm
    
    bpy.ops.object.mode_set(mode='EDIT')

    # IK always attempts to pull the tail of some bone to the IK target. (Checking/unchecking 'Use Tail'
    # only switches it between the tail of bone with the constraint, or the tail of its parent.)
    # It is a problem with this rig as it is originally set up, because e.g. the tail of cf_J_ArmLow01_L
    # is, by default, the air above the elbow.

    arm.data.edit_bones['cf_J_Head'].tail = arm.data.edit_bones['cf_J_Head'].head + Vector([0, 0.5, 0])

    arm.data.edit_bones['cf_J_Hand_L'].length = 0.2
    arm.data.edit_bones['cf_J_Hand_R'].length = 0.2
    arm.data.edit_bones['cf_J_Neck'].length = 0.8


    arm.data.edit_bones['cf_J_LegLowRoll_R'].tail = arm.data.edit_bones['cf_J_Foot01_R'].head
    arm.data.edit_bones['cf_J_Foot01_R'].tail = arm.data.edit_bones['cf_J_Foot01_R'].head + Vector([0, -0.5, 0])
    arm.data.edit_bones['cf_J_Foot02_R'].tail = arm.data.edit_bones['cf_J_Foot02_R'].head + Vector([0, 0, 0.5])

    arm.data.edit_bones['cf_J_LegLowRoll_L'].tail = arm.data.edit_bones['cf_J_Foot01_L'].head
    arm.data.edit_bones['cf_J_Foot01_L'].tail = arm.data.edit_bones['cf_J_Foot01_L'].head + Vector([0, -0.5, 0])
    arm.data.edit_bones['cf_J_Foot02_L'].tail = arm.data.edit_bones['cf_J_Foot02_L'].head + Vector([0, 0, 0.5])

    for pairs in [
        ('cf_J_Hand_L', 'cf_J_Hand_IK_L', 'cf_J_Hand_P_L', 3, True),
        ('cf_J_Hand_R', 'cf_J_Hand_IK_R', 'cf_J_Hand_P_R', 3, True),
        ('cf_J_Foot01_L', 'cf_J_Foot_IK_L', 'cf_J_Foot_P_L', 4, True),
        ('cf_J_Foot01_R', 'cf_J_Foot_IK_R', 'cf_J_Foot_P_R', 4, True),
        ('cf_J_Neck', 'cf_J_Head_IK', None, 3, True),
        ]:
        bpy.ops.object.mode_set(mode='EDIT')
        bone = arm.data.edit_bones.new(pairs[1])
        bone.head = arm.data.edit_bones[pairs[0]].head
        if pairs[0]=='cf_J_Neck':
            bone.head = arm.data.edit_bones['cf_J_Head'].head
        if 'Foot' in pairs[0]:
            bone.head += Vector([0, -0.5, 0])
            bone.tail = bone.head+Vector([0, -0.5, 0])
        else:
            bone.tail = bone.head+Vector([0, 0.5, 0])
        bone.parent = arm.data.edit_bones['cf_N_height']
        arm.data.collections['IK'].assign(bone)
        bone.color.palette = 'THEME05'

        if pairs[2] is not None:
            bone = arm.data.edit_bones.new(pairs[2])
            bone.head = arm.data.edit_bones[pairs[0]].head
            if pairs[0]=='cf_J_Neck':
                bone.head = arm.data.edit_bones['cf_J_Head'].head

            if 'Hand' in pairs[0]:
                bone.head = Vector([0,12,0]) + Vector([1, 0, 0])*(1 if pairs[0][-1]=='L' else -1)
            else:
                bone.head += Vector([0,5,0]) +Vector([5, 0, 0])*(1 if pairs[0][-1]=='L' else -1)

            bone.tail = bone.head+Vector([0, 0, 0.5])
            bone.parent = arm.data.edit_bones['cf_N_height']
            arm.data.collections['IK'].assign(bone)
            bone.color.palette = 'THEME05'

        bpy.ops.object.mode_set(mode='POSE')
        pb=arm.pose.bones[pairs[1]]
        pb.color.palette = 'THEME05'
        pb.rotation_mode = 'YZX'
        pb=arm.pose.bones[pairs[0]]
        #pb.color.palette = 'THEME05'
        con = pb.constraints.new('IK')
        con.target=arm
        con.subtarget=pairs[1]
        con.chain_count=pairs[3]

        con.use_tail = pairs[4]
        con.use_stretch = False
        if pairs[2] is not None:
            con.pole_target = arm
            con.pole_subtarget = pairs[2]
            con.use_rotation =  True
            #if 'Hand' in pairs[0]:
            #    con.pole_angle = (-3.1415926/2.) * (1 if pairs[0][-1]=='L' else -1)
            #else:
            con.pole_angle = 3.1415926 if pairs[0][-1]=='R' else 0.
            arm.pose.bones[pairs[2]].color.palette = 'THEME05'
        #con.owner_space='LOCAL'
        #con.target_space='LOCAL'
        #con.subtarget=c+'L'
        #pb.lock_ik_x=True
        #pb.lock_ik_y=True
        #pb.lock_ik_z=True
    for c in 'L','R':
        arm.pose.bones['cf_J_ArmLow01_'+c].lock_ik_z=True
        arm.pose.bones['cf_J_LegLow01_'+c].lock_ik_y=True
        arm.pose.bones['cf_J_LegLow01_'+c].lock_ik_z=True
        arm.pose.bones['cf_J_LegLowRoll_'+c].lock_ik_x=True
        arm.pose.bones['cf_J_LegLowRoll_'+c].lock_ik_z=True

    arm.pose.bones['cf_J_LegLow01_L'].use_ik_limit_x=True
    arm.pose.bones['cf_J_LegLow01_L'].ik_min_x=0
    arm.pose.bones['cf_J_LegLow01_R'].use_ik_limit_x=True
    arm.pose.bones['cf_J_LegLow01_R'].ik_min_x=0

    arm.pose.bones['cf_J_ArmLow01_L'].use_ik_limit_y=True
    arm.pose.bones['cf_J_ArmLow01_L'].ik_max_y=0
    arm.pose.bones['cf_J_ArmLow01_R'].use_ik_limit_y=True
    arm.pose.bones['cf_J_ArmLow01_R'].ik_min_y=0

    bpy.ops.object.mode_set(mode='OBJECT') 


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

def assert_bone_class_compliance(x, decomp, scale):
    if 'Vagina' in x:
        return
    if 'hair' in x:
        return
    if 'Legsk' in x:
        return
    bc = bone_class(x)
    if bc is not None:
        for k in range(7):
            large=False
            if k<3:
                val = (abs(decomp[0][k]) > 1e-4)
                large = (abs(decomp[0][k]) > 0.01)
            elif k==3:
                #val = (decomp[1] != Quaternion([1,0,0,0]))
                ampl = abs(decomp[1][1])+abs(decomp[1][2])+abs(decomp[1][3])
                val = (ampl > 1e-4)
                large = (ampl > 0.01)
            else:
                val = (abs(decomp[2][k-4]-1)>1e-4)
                large = (abs(decomp[2][k-4]-1)>0.01)
            if (val and (bc[k] in 'ux')) or (large and bc[k]=='i'):
                print("Setting unclassified bone component:", x, k, "class", bc[k], "value", decomp)

bone_transforms={}
def reshape_armature_one_bone(x, arm, dic=None):
    global bone_transforms
    b = arm.data.bones[x]
    if dic==None:
        dic=bone_pos
    if x in dic:
        bpy.context.object.data.bones.active = b
        local = arm.data.bones[x].matrix_local
        mw = matrix_world(arm, x)
        target = Matrix(dic[x])
        decomp = snap((arm.pose.bones[x].matrix_basis @ mw.inverted() @ target).decompose())
        #print(decomp)
        arm.pose.bones[x].matrix_basis = recompose(decomp)
        if not x.endswith('_R'):
            assert_bone_class_compliance(x, decomp, arm.pose.bones[x].matrix[0][0])

    for x in b.children.keys():
        reshape_armature_one_bone(x, arm, dic)


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

def load_unity_dump(dump):
    bone_pos={}
    bone_w2l={}
    bone_parent={}
    root_pos=[0,0,0]
    local_pos={}
    name=''
    f=open(dump,'r').readlines()
    hash = hashlib.md5(''.join(f).encode('utf-8')).digest()
    f=[x.strip() for x in f]
    if 'cf_J_Root' in f[0]:
        f[0]='cf_J_Root--UnityEngine.GameObject'
    elif 'CommonSpace' in f[0]:
        f[0]='CommonSpace--UnityEngine.GameObject'
    else:
        print(f[0])
        #raise ImportException('ERROR: Could not parse the dump file')

    for n in range(len(f)):
        x=f[n]
        if x.endswith('--UnityEngine.GameObject'):
           name=x.split('-')[0]
           #print(name)
        elif x.startswith('@parent<Transform>'):
            parent=None
            if len(x.split())>2:
                parent=x.split()[2]
            bone_parent[name]=parent
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
    return bone_pos, local_pos, hash

def reshape_armature(path, arm, body, fallback, dumpfilename): 
    boy = body['Boy']>0.0
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    
    # custom head mesh
    if fallback or (not 'cf_J_CheekLow_L' in arm.data.edit_bones):
        print("Custom head mesh suspected, taking the fallback route");
        reshape_armature_fallback(arm, body, dumpfilename)
        return False

    with bpy.data.libraries.load(os.path.dirname(__file__)+"/assets/prefab_materials_meshexporter.blend") as (data_from, data_to):
        data_to.texts = data_from.texts

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
    arm["default_rig"] = default_rig
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

    #for b in arm.data.edit_bones:
    #    if abs(b.roll)<0.05:
    #        b.roll=0.0
    #    else:
    #        print("Nontrivial roll:", b.name, b.roll)
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


    bone_pos, _, md5sum = load_unity_dump(dumpfilename)
    if bone_pos==None:
        raise importer.ImportException("Failed to load the unity dump, aborting")

     # Stretch 'arm' back to 'custom body' 
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    reshape_armature_one_bone('cf_J_Root', arm, bone_pos)
    deformed_rig={}
    for x in arm.pose.bones:
        deformed_rig[x.name]=x.matrix_basis.copy()

    arm["default_rig"]=default_rig
    arm["deformed_rig"]=deformed_rig

    bpy.ops.object.mode_set(mode='OBJECT')  
    npass=0
    fail_vert=0
    t1 = time.time()
    loaded, map = try_load_solution_cache(path, body_parts, md5sum)
    if not loaded:
        # Solve for undeformed mesh shape
        #t1 = time.time()
        with bpy.data.libraries.load(os.path.dirname(__file__)+"/assets/prefab_materials_meshexporter.blend") as (data_from, data_to):
            data_to.meshes = data_from.meshes
        for b in body_parts:
            b2 = bpy.data.objects[b["ref"]]
            x, y = solve_for_deform(b, b2, map=map)
            npass += x
            fail_vert += y
            print(" => ", npass, fail_vert)
        #t2 = time.time()
        print("Done in ", npass, " passes, ", fail_vert, "failed vertices")
        #print("Lead time", lead_time, "Total time", total_time)
        save_solution_cache(path, body_parts, md5sum)
    t2 = time.time()
    print("Rest position calculated in %.3f s" % (t2-t1)) 
    bpy.ops.object.select_all(action='DESELECT')
    for x in body_parts:
        bpy.data.objects[x["ref"]].select_set(True)
    bpy.ops.object.delete(use_global=False)
    prettify_armature(arm, body)
    return True

def reshape_armature_fallback(arm, body, dumpfilename): 
    #arm = bpy.data.objects['Armature']
    #arm = bpy.context.view_layer.objects.active
    #body = bpy.data.objects['body']
    arm["default_rig"]=None
    
    bone_pos, _, _ = load_unity_dump(dumpfilename)
    if bone_pos==None:
        raise importer.ImportException("Failed to load the unity dump, aborting")
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
    prettify_armature(arm, body)


def load_pose_file(arm, fn):
    f=None
    try:
        f=open(fn, "r").readlines()
    except:
        pass
    if f is None:
        try:
            f=open(os.path.dirname(__file__)+"/"+fn, "r").readlines()
        except:
            print("No such file:", path.dirname(__file__)+"/"+fn)
            return {}
    if 'UnityEngine' in f[0]:
        _, v, _ =load_unity_dump(fn)
        default_rig = arm["default_rig"]
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
        f = [x for x in f if len(x)>10 and x[0]!="#"]
        f=[x.strip().split() for x in f]
        f={(x[0],x[1]): [float(y) for y in x[2:]] for x in f if (len(x)==5 or (len(x)==6 and x[1]=='rotation'))}
    return f

# flags: 1 - FK, 2 - soft, 3 - everything; bit 2 - no sanity check
def load_pose(a, fn, flags=3):
    print("load_pose", a, fn, flags)
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
    f=load_pose_file(arm, fn)
    print("%d pose entries read\n" % len(f))
    #print(f)
    null_pose=(Vector(), Quaternion(), Vector([1,1,1]))
    ch=('offset','rotation','scale')
    for x in arm.pose.bones.keys():
        #print(x)
        pose = list(arm.pose.bones[x].matrix_basis.decompose())
        for y in range(3):
            known=False
            if (x,ch[y]) in f:
                #print(f[(x,ch[y])])
                known=True
                op = f[(x,ch[y])]
            else:
                #print(x, ch[y], "not in file")
                op = null_pose[y]               
            c=bone_class(x, ch[y])
            for n in range(len(op)):
                if (flags&4) or (c=='?') or (c==None) \
                    or ((flags&1) and c[n if y!=1 else 0] in ('f',)) \
                    or ((flags&2) and c[n if y!=1 else 0] in ('s','i','u')):
                        #if known:
                        #    print(x,y,n,op[n])
                        pose[y][n]=op[n]
        arm.pose.bones[x].matrix_basis=recompose(pose)
        if flags & 2:
            # todo: ideally, deformed_rig should exclude FK bones (but that's too much work) 
            deformed_rig[x]=arm.pose.bones[x].matrix_basis.copy()
            
def snap(x):
    for y in range(2):
        for z in range(4 if y==1 else 3):
            if abs(x[y][z])<0.0001:
                x[y][z]=0.0
    if abs(x[1][0]-1)<0.0001:
        x[1][0]=1.0
    for z in range(3):
        if abs(x[2][z]-1)<0.0001:
            x[2][z]=1.0
    return x


def rescale_one_bone(x, default_rig, deformed_rig, z, rig_delta={}, delta_z=0.0):
    if not x.name in deformed_rig:
        return
    offset, rotation, scale = Matrix(deformed_rig[x.name]).decompose()
    #print(x.name, "Deformed rig: ", offset, rotation, scale)
    #print(x.name, "matrix_basis: ", x.matrix_basis.decompose())
    #print(x.name, "matrix: ", x.matrix.decompose())
    _, fk_rotation, _ = x.matrix_basis.decompose()
    #max_deform = Matrix(deformed_rig[x.name]).decompose()
    #offset, rotation, scale = deformed_delta.decompose()
    bc = bone_class(x.name, 'offset')
    if bc!='?' and bc!=None:
        for c in range(3):
            if abs(offset[c])>0.0001 and not (bc[c] in ('s','i','u', 'c')):
                print("Nontrivial offset in bone", x.name, c)
            if (bc[c] in ('s','i','u','c')):
                offset[c] = offset[c]*z

    if (x.name, "offset") in rig_delta:
        offset += Vector(rig_delta[(x.name, "offset")])*delta_z

    #if Vector(offset).length > 0.001:
    #    print(x.name, offset)
    bc = bone_class(x.name, 'rotation')
    if x=='cf_J_Chin_rs' and 'cf_J_LowerJaw' in deformed_rig:
        bc = 'f'
    if bc in ('s','i','u'):
        #print(x.name, "rotation", z, rotation)
        rotation = Quaternion([1,0,0,0])*(1.-z) + rotation*z
        if (x.name, "rotation") in rig_delta:
            rotation += (Quaternion(rig_delta[(x.name, "rotation")])-Quaternion([1,0,0,0]))*delta_z
    else:
        if delta_z>0 and ((x.name, "rotation") in rig_delta) and rig_delta[(x.name, "rotation")]!=Quaternion([1,0,0,0]):
            print("Ignoring rig_delta rotation", x.name, rig_delta[(x.name, "rotation")])
        rotation = fk_rotation
    bc=bone_class(x.name, 'scale')
    if bc!='?' and bc!=None:
        for c in range(3):
            if abs(scale[c]-1)>0.001 and not (bc[c] in ('s','i','u','c')):
                print("Nontrivial scale in bone", x.name, c)
            if (bc[c] in ('s','i','u','c')):
                scale[c]=math.pow(scale[c], z)
                if (x.name,"scale") in rig_delta:
                    #print(x.name, "scale", c, ":", math.pow(scale[c], z), "+", rig_delta[(x.name,"scale")][c]-1., "*", delta_z, "=>", scale[c] + (rig_delta[(x.name,"scale")][c]-1.)*delta_z)
                    scale[c] += (rig_delta[(x.name,"scale")][c]-1.)*delta_z
                    if scale[c]<0.01:
                        scale[c] = 0.01
            else:
                if delta_z>0 and ((x.name,"scale") in rig_delta) and rig_delta[(x.name,"scale")][c]!=1.0:
                    print("Ignoring rig delta scale", x.name, c, rig_delta[(x.name,"scale")][c])
                    #print(x.name, c, 'scale', scale[c], '^', z)
    #if (scale-Vector([1,1,1])).length>0.001:
    #    print(x.name, scale)
    T = Matrix.Translation(offset)
    R = rotation.to_matrix().to_4x4()
    S = Matrix.Diagonal(scale.to_4d())
    x.matrix_basis=(T @ R @ S)

    for c in x.children:
        rescale_one_bone(c, default_rig, deformed_rig, z, rig_delta=rig_delta, delta_z=delta_z)


def dump_pose(a, of, x='cf_J_Root', flags=3):
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
    assert_bone_class_compliance(x, local, arm.pose.bones[x].matrix[0][0])
    comp_name=('offset','rotation','scale')
    if not (x.endswith("_R") and (flags==2)):
        for comp in range(3):
            c = bone_class(x, comp_name[comp])
        if (flags & 2) and local[0]!=Vector():
            s=x+' offset %.4f %.4f %.4f\n' % (local[0][0], local[0][1], local[0][2])
            of.write(s)        
        if local[1]!=Quaternion():
            bc = bone_class(x, 'rotation')
            if bc in ['c','x']:
                print("Not saving", x, "rotation")
            else:
                fk = (bc == 'f')
                if ((flags & 1) and fk) or ((flags & 2) and not fk):
                    s=x+' rotation %.4f %.4f %.4f %.4f\n' % (local[1][0], local[1][1], local[1][2], local[1][3])
                    of.write(s)
        if (flags & 2) and local[2]!=Vector([1,1,1]):
            s=x+' scale %.4f %.4f %.4f\n' % (local[2][0], local[2][1], local[2][2])
            of.write(s)        
    #        s = x+('basis %f %f %f %f  %f %f %f %f  %f %f %f %f  %f %f %f %f\n' % (local[0][0], local[0][1], local[0][2], local[0][3],
    #            local[1][0], local[1][1], local[1][2], local[1][3],
    #            local[2][0], local[2][1], local[2][2], local[2][3],
    #            local[3][0], local[3][1], local[3][2], local[3][3]))
    for x in b.children.keys():
        dump_pose(a, of, x, flags)


def set_fk_pose(arm, v):
    deformed_rig = arm["deformed_rig"]
    for x in arm.pose.bones:
        if x.name in deformed_rig and bone_class(x.name, 'rotation')=='f':
            default_rig = Matrix(deformed_rig[x.name]).decompose()
            current_rig = x.matrix_basis.decompose()
            current_rig = (current_rig[0], default_rig[1], current_rig[2])
            x.matrix_basis = recompose(current_rig) #deformed_rig[x.name]
    for x in v:
        #arm.pose.bones[x[0]].rotation_mode=rot_mode
        arm.pose.bones[x[0]].rotation_euler=Euler((x[1]*math.pi/180., x[2]*math.pi/180., x[3]*math.pi/180.), rot_mode)
        if x[0][-1]=='L':
            asym = False
            for y in v:
                if y[0]==x[0][:-1]+'R':
                    asym=True
                    break
            if asym:
                continue
            mult = -1.0 if len(x)>4 else 1.0
            #arm.pose.bones[x[0][:-1]+'R'].rotation_mode=rot_mode
            arm.pose.bones[x[0][:-1]+'R'].rotation_euler=Euler((x[1]*math.pi/180., mult*x[2]*math.pi/180., mult*x[3]*math.pi/180.), rot_mode)
