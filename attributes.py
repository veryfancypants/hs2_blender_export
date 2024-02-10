import bpy
import math
from mathutils import Euler, Vector, Matrix
from .armature import apply_daisy_protocol

def hs2object():
    arm = bpy.context.active_object
    if arm is None:
        return None
    if arm.type=='MESH':
        arm = arm.parent
    if arm.type!='ARMATURE':
        return None
    return arm


#
#
#   MALE PROPERTIES
#
#

def get_eagerness(self):
    h = hs2object()
    try:
        return h['eagerness']
    except:
        return 25.0

def get_length(self):
    h = hs2object()
    try:
        return h['length']
    except:
        return 75.0

def get_girth(self):
    h = hs2object()
    try:
        return h['girth']
    except:
        return 75.0

def get_volume(self):
    h = hs2object()
    try:
        return h['volume']
    except:
        return 75.0

def set_equipment(h, x, length, width, volume):
    if h is None:
        return
    if not 'balls' in h.pose.bones:
        return
    retract=max(0, 1-2*volume)
    #bs=0.5+0.5*volume
    h.pose.bones['dick_base'].scale=Vector([1,1,1])
    h.pose.bones['dick_base'].location=Vector([0,-0.01*retract,0])
    h.pose.bones['stick_01'].location=Vector([0,-0.05*retract,0])
    bs=0.25+0.75*volume
    h.pose.bones['balls'].scale=(bs,bs,bs)
    h.pose.bones['balls'].location=(0, 0.10*(volume-1), 0)
    h.pose.bones['balls'].rotation_euler=Euler((15*(volume-1)*math.pi/180., 0, 0))
    width=0.5 + (width-0.25)*1.5
    h.pose.bones['stick_01'].rotation_euler=Euler((50.*(0.8-x)*math.pi/180., 0, 0), 'XYZ')
    h.pose.bones['stick_01'].scale=((0.8+0.2*x)*width, (0.4*length+0.6*x), (0.8+0.2*x)*width)
    h.pose.bones['stick_02'].rotation_euler=Euler((20.*(1.-x)*math.pi/180., 0, 0), 'XYZ')
    h.pose.bones['stick_02'].scale=((0.7+0.3*x)*width, (0.3*length+0.7*x), (0.7+0.3*x)*width)
    h.pose.bones['stick_03'].rotation_euler=Euler((15.*(1.-x)*math.pi/180., 0, 0), 'XYZ')
    h.pose.bones['stick_03'].scale=((0.7+0.3*x)*width, (0.3*length+0.7*x), (0.7+0.3*x)*width)
    h.pose.bones['stick_04'].rotation_euler=Euler((10.*(1.-x)*math.pi/180., 0, 0), 'XYZ')
    h.pose.bones['stick_04'].scale=((0.7+0.3*x)*width, (0.3*length+0.7*x), (0.7+0.3*x)*width)
    h.pose.bones['tip_base'].scale=((0.6+0.4*x)*width, (0.7*length+0.3*x), (0.6+0.4*x)*width)
    h.pose.bones['fskin_left'].scale=(1, 1+0.6*(1-x), 1)
    h.pose.bones['fskin_right'].scale=(1, 1+0.6*(1-x), 1)
    h.pose.bones['fskin_top'].scale=(1, 1+1.4*(1-x), 1)
    h.pose.bones['fskin_bottom'].scale=(1, 1+0.6*(1-x), 1)
    h.pose.bones['sheath'].location=(0, 0.10*(1-x), 0)
    h.pose.bones['sheath'].scale=(x*0.5+0.5, 1, x*0.5+0.5)

    sheath = h["sheath_object"]
    # contracts the outer edge of the sheath if eagerness is low
    sheath.data.shape_keys.key_blocks["Key 1"].value = max(0., min(1., (0.75-x)*2.))
    
def set_eagerness(self, x):
    h = hs2object()
    if h is None:
        return
    h['eagerness']=x
    e = get_eagerness(h)*0.01
    l = get_length(h)*0.01
    g = get_girth(h)*0.01
    v = get_volume(h)*0.01
    set_equipment(h, e, l, g, v)

def set_length(self, x):
    h = hs2object()
    if h is None:
        return
    h['length']=x
    e = get_eagerness(h)*0.01
    l = get_length(h)*0.01
    g = get_girth(h)*0.01
    v = get_volume(h)*0.01
    set_equipment(h, e, l, g, v)

def set_girth(self, x):
    h = hs2object()
    if h is None:
        return
    h['girth']=x
    e = get_eagerness(h)*0.01
    l = get_length(h)*0.01
    g = get_girth(h)*0.01
    v = get_volume(h)*0.01
    set_equipment(h, e, l, g, v)

def set_volume(self, x):
    h = hs2object()
    if h is None:
        return
    h['volume']=x
    e = get_eagerness(h)*0.01
    l = get_length(h)*0.01
    g = get_girth(h)*0.01
    v = get_volume(h)*0.01
    set_equipment(h, e, l, g, v)

def get_wet(self):
    h = hs2object()
    if h is None:
        return
    x = h.get('wet')
    return True if (x is None) else x

def set_wet(self,x):
    h = hs2object()
    if h is None:
        return
    h['wet']=x
    for y in h.children:
        if y.type=='MESH':
            for m in y.data.materials:
                if 'Injector' in m.name:
                    m.node_tree.nodes['Wetness'].outputs[0].default_value=1.0 if x else 0.0
    
def get_sheath(self):
    h = hs2object()
    if h is None:
        return
    x = h.get('sheath')
    return True if (x is None) else x
    
def set_sheath(self,x):
    h = hs2object()
    if h is None:
        return
    h['sheath']=x
    h["sheath_object"].hide_viewport=not x
    h["sheath_object"].hide_render=not x

#
#
#   UNISEX PROPERTIES
#
#

def set_exhaust(self, x):
    h = hs2object()
    if h is None:
        return
    h['exhaust'] = x
    if not 'cf_J_ExhaustClench' in h.pose.bones:
        return
    if x<=1:
        h.pose.bones['cf_J_ExhaustClench'].scale=Vector([-2+3*x,1,-2+3*x])
        h.pose.bones['cf_J_Ana'].scale = Vector([1,1,1])
        h.pose.bones['cf_J_ExhaustValve'].scale=Vector([1,1,1])
    else:
        h.pose.bones['cf_J_Ana'].scale = Vector([max(x/1.5,1),1,max(x/3,1)])
        h.pose.bones['cf_J_ExhaustClench'].scale=Vector([max(x/3,1),1,max(x/3,1)])
        h.pose.bones['cf_J_ExhaustValve'].scale=Vector([max(x/3,1),1,max(x/3,1)])
    h.pose.bones['cf_J_ExhaustClench'].location=Vector([0.008*(max(x/3,1)-1), 0, 0])
    h.pose.bones['cf_J_ExhaustValve'].location=Vector([0.008*(max(x/3,1)-1), 0, 0])

def get_exhaust(self):
    h = hs2object()
    if h is None:
        return
    try:
        return h['exhaust']
    except:
        return 1.0

def get_geo_dp(idx):
    h = hs2object()
    if h is None:
        return 0.0
    try:
        return h["daisy_protocol" if idx else "custom_geo"]
    except:
        return 0.0 if idx else 1.0

def get_custom_geo(self):
    return get_geo_dp(0)

def get_daisy_protocol(self):
    return get_geo_dp(1)

def set_geo_dp(idx, y):
    h = hs2object()
    if h is None:
        return
    #print("set_daisy_protocol", x)
    cg = h.get("custom_geo", 1.0)
    dp = h.get("daisy_protocol", 0.0)
    if idx==0:
        cg=y
    else:
        dp=y
    apply_daisy_protocol(h, max(0,cg-dp*0.5), dp)
    h["custom_geo"]=cg
    h["daisy_protocol"]=dp

def set_custom_geo(self, x):
    set_geo_dp(0, x)

def set_daisy_protocol(self, x):
    set_geo_dp(1, x)

def set_ik(self, x):
    h = hs2object()
    if h is None:
        return
    h['ik'] = x

    ik_affected_bones = ['cf_J_ArmUp00_', 'cf_J_ArmLow01_', 'cf_J_Hand_', 'cf_J_LegLow01_', 'cf_J_LegUp01_', 'cf_J_Foot01_',
        'cf_J_Head', 'cf_J_Neck', 'cf_J_Spine03', 'cf_J_Spine02', 'cf_J_Spine01']
    ik_affected_bones = [x for x in ik_affected_bones if x[-1]!='_'] + \
        [x+'L' for x in ik_affected_bones if x[-1]=='_'] + \
        [x+'R' for x in ik_affected_bones if x[-1]=='_']
    ik_controlled_bones = [
        'cf_J_Hand_L',
        'cf_J_Hand_R',
        'cf_J_Foot01_L',
        'cf_J_Foot01_R',
        'cf_J_Neck']
    """
    # does not work and not clear how to fix
    if not x:
        for b in ik_affected_bones:
            m = h.pose.bones[b].parent.matrix.inverted() @ h.pose.bones[b].matrix
            #m0 = Matrix(h["deformed_rig"][h.pose.bones[b].parent.name]).inverted() @ Matrix(h["deformed_rig"][b])
            m0 = h.data.bones[b].parent.matrix.inverted() @ h.data.bones[b].matrix
            print(b)
            #print(m.decompose()[1])
            print(m0.decompose()[1].to_euler(h.pose.bones[b].rotation_mode))
            print(m.decompose()[1].to_euler(h.pose.bones[b].rotation_mode))
            #print((m0.inverted() @ m).decompose()[1].to_euler(h.pose.bones[b].rotation_mode))

            #edit_delta = m0.decompose()[1].to_euler(h.pose.bones[b].rotation_mode)
            delta = (m0.inverted() @ m).decompose()[1].to_euler(h.pose.bones[b].rotation_mode)
            h.pose.bones[b].rotation_euler=m.decompose()[1].to_euler(h.pose.bones[b].rotation_mode)
    """
    for b in ik_controlled_bones:
        if b in h.pose.bones:
            for c in h.pose.bones[b].constraints:
                if c.type=='IK':
                    c.enabled=x
    if x:
        for b in ik_affected_bones:
            h.pose.bones[b].rotation_euler=Euler([0,0,0])


def get_ik(self):
    h = hs2object()
    if h is None:
        return
    try:
        return h['ik']
    except:
        return True

