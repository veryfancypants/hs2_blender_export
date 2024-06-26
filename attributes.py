import bpy
import math
from mathutils import Euler, Vector, Matrix, Color

# Will return an object so long as the active object is an armature.
# It's up to the caller to validate accesses (it may not be a HS2 armature,
# and could have none of the expected attributes)
def hs2object():
    arm = bpy.context.active_object
    if arm is None:
        return None
    if arm.type=='MESH':
        arm = arm.parent
    if arm is None:
        return None
    if arm.type!='ARMATURE':
        return None
    return arm


defaults={
    "Hair color": (0.8,0.8,0.5),
    "Eye color": (0.0,0.0,0.8),
    'Eagerness': 25.0,
    'Length': 75.0,
    'Girth': 75.0,
    'Volume': 75.0,
    'Wet': False,
    'Sheath': True,
    'Neuter': False,
    'Exhaust': 1.0,
    "IK": True,
    "Skin tone": Color([-1,-1,-1]),
    "Name": "Kitten",
    "Fat": 0.0,
}
print(defaults) 

def get_default_attr(name):
    return defaults[name]

def get_attr(name):
    if not (name in defaults):
        return None
    h = hs2object()
    if h is None:
        return defaults[name]
    try:
        return h[name]
    except:
        if name=="Skin tone":
            try:
                return h["body"].mean_skin_tone
            except:
                pass
        return defaults[name]

def set_equipment(h):
    if h is None:
        return
    if not 'balls' in h.pose.bones:
        return
    x = get_attr("Eagerness")*0.01
    length = get_attr("Length")*0.01
    width = get_attr("Girth")*0.01
    volume = get_attr("Volume")*0.01

    retract=max(0, 1-2*volume)
    #bs=0.5+0.5*volume
    h.pose.bones['dick_base'].scale=Vector([1,1,1])
    h.pose.bones['dick_base'].location=Vector([0,-0.01*retract,0])
    h.pose.bones['stick_01'].location=Vector([0,-0.05*retract,0])
    bs=0.25+0.75*volume
    h.pose.bones['balls'].scale=((bs+1)/2,bs,(bs+1)/2)
    h.pose.bones['balls'].location=(0, 0.10*(volume-1), 0)
    h.pose.bones['balls'].rotation_euler=Euler((15*(volume-1)*math.pi/180., 0, 0))
    width=0.5 + (width-0.25)*1.5
    h.pose.bones['stick_01'].rotation_euler=Euler((50.*(0.8-x)*math.pi/180., 0, 0), 'XYZ')
    h.pose.bones['stick_01'].scale=((0.8+0.2*x)*width, (0.4*length+0.6*x), (0.8+0.2*x)*width)
    h.pose.bones['stick_02'].rotation_euler=Euler((20.*(1.-x)*math.pi/180., 0, 0), 'XYZ')
    s2 = (0.7+0.3*x)*width
    l2 = 0.5*length+0.5*x
    h.pose.bones['stick_02'].scale=(s2, l2, s2)
    h.pose.bones['stick_03'].rotation_euler=Euler((15.*(1.-x)*math.pi/180., 0, 0), 'XYZ')
    l3 = 0.5*length+0.5*x
    s3 = (0.7+0.3*x)*width*min(0.9+length,1.0)
    h.pose.bones['stick_03'].scale=(s3, l3, s3)
    h.pose.bones['stick_04'].rotation_euler=Euler((10.*(1.-x)*math.pi/180., 0, 0), 'XYZ')
    l4 = 0.5*length+0.5*x
    s4 = (0.7+0.3*x)*width*min(0.8+length,1.0)
    h.pose.bones['stick_04'].scale=(s4, l4, s4)

    l5 = 0.7*length+0.3*x
    s5 = (0.6+0.4*x)*width*min(0.6+length,1.0)
    h.pose.bones['tip_base'].scale=(s5, l5, s5)

    l6 = 1.0
    s6 = min(0.9+length,1.0)
    h.pose.bones['tip'].scale=(s6, l6, s6)

    h.pose.bones['fskin_left'].scale=(1, 1+0.6*(1-x), 1)
    h.pose.bones['fskin_right'].scale=(1, 1+0.6*(1-x), 1)
    h.pose.bones['fskin_top'].scale=(1, 1+1.4*(1-x), 1)
    h.pose.bones['fskin_bottom'].scale=(1, 1+0.6*(1-x), 1)
    h.pose.bones['sheath'].location=(0, 0.10*(1-x), 0)
    s6 = 1.0
    h.pose.bones['sheath'].scale=(s6, 1, s6)

    sheath = h["sheath_object"]
    # contracts the outer edge of the sheath if eagerness is low
    sheath.data.shape_keys.key_blocks["Key 1"].value = max(0., min(1., (0.75-x)*2.))
    

def set_fat(arm, x):
    torso_bones = [
('cf_J_LegUp01_s_L',  0.100,   0.0,   0.093),
('cf_J_LegUp02_s_L',  0.111,   0.0,   0.161),
('cf_J_LegUp03_s_L',  0.070,   0.0,   0.063),
('cf_J_LegLow01_s_L',  0.091,   0.0,   0.091),
('cf_J_LegLow02_s_L',  0.151,   0.0,   0.117),
('cf_J_LegLow03_s_L',  0.0,   0.0,   0.066),
('cf_J_LegKnee_low_s_L',  0.0,   0.0,   0.0),
('cf_J_Siri_s_L',  0.010,   0.0,   0.010,),
('cf_J_Kosi01_f_s',  0.015,   0.0,   0.0),
('cf_J_Kosi02_s',  0.027,   0.0,   0.028),
('cf_J_Kosi01_s',  0.024,  .0 ,  0.000,),
('cf_J_Spine01_s',  0.074,   0.0,   0.048),
('cf_J_Spine02_s',  0.030,   0.0,   0.012),
('cf_J_Spine03_s',  0.003,   0.0,   0.019),
('cf_J_ArmUp01_s_L',  0.0,   0.081,   0.082),
('cf_J_ArmUp02_s_L',  0.0,   0.136,   0.137),
('cf_J_ArmUp03_s_L',  0.0,   0.013,   0.028),
('cf_J_ArmLow01_s_L',  0.0,   0.060,   0.040),
('cf_J_ArmLow02_s_L',  0.0,   0.100,   0.100),
('cf_J_Hand_Wrist_s_L',  0.0, -0.020, -0.023),
('cf_J_Neck_s', 0.100, 0.0, 0.100),
('cf_J_FaceRoot_s', 0.100, 0.0, 0.100),
('cf_J_FaceRoot_r_s', 0.100, 0.0, 0.100, "inv"),
('cf_J_ChinLow', 0.0, 0.100, 0.0),
    ]
    if not "deformed_rig" in arm:
        return
    for b in torso_bones:
        if not b[0] in arm["deformed_rig"]:
            continue
        if not b[0] in arm.pose.bones:
            continue
        null_scale = Matrix(arm["deformed_rig"][b[0]]).decompose()[2]
        w0 = b[1]
        w1 = b[2]
        w2 = b[3]
        if len(b)>4 and b[4]=="inv":
            arm.pose.bones[b[0]].scale = Vector([null_scale[0]/(1+w0*x), null_scale[1]/(1+w1*x), null_scale[2]/(1+w2*x)])
        else:
            arm.pose.bones[b[0]].scale = Vector([null_scale[0]*(1+w0*x), null_scale[1]*(1+w1*x), null_scale[2]*(1+w2*x)])

    if "cf_J_Spine01_f_s" in arm.pose.bones:
        arm.pose.bones["cf_J_Spine01_f_s"].location[2] = 0.05*x*(0.5 if x>=0 else 1)
    if "cf_J_Kosi01_f_s" in arm.pose.bones:
        arm.pose.bones["cf_J_Kosi01_f_s"].location[2] = 0.10*x*(2 if x>=0 else 1)
    #ab["cf_J_Kosi01_f_s"].scale[0] = 1+0.015*x
    #ab["cf_J_Siri_s_L"].scale = Vector([1+x*0.1, 1, 1+fat*0.1])


def set_attr(name, x):
    if not (name in defaults):
        print("ERROR: set_attr with unknown attribute", name)
        raise "ERROR: set_attr with unknown attribute"
        return

    h = hs2object()
    if h is None:
        return

    h[name] = x
    if name == "Name":
        return

    if name=="Fat":
        set_fat(h, x)

    if name in ('Eagerness','Length', 'Girth','Volume'):
        set_equipment(h)

    if name=='Wet':
        for y in h.children:
            if y.type=='MESH':
                for m in y.data.materials:
                    if 'Injector' in m.name:
                        m.node_tree.nodes['Wetness'].outputs[0].default_value=1.0 if x else 0.0

    if name=='Neuter':
        for y in h.children:
            if y.type=='MESH':
                for m in y.data.materials:
                    if 'Injector' in m.name:
                        m.node_tree.nodes['Visible'].outputs[0].default_value=0.0 if x else 1.0

    if name=='Sheath':
        h["sheath_object"].hide_viewport=not x
        h["sheath_object"].hide_render=not x
    if name=='Exhaust':
        if not 'cf_J_ExhaustClench' in h.pose.bones:
            return
        h.pose.bones['cf_J_ExhaustClench'].scale=Vector([min(1,-2+3*x),1,min(1,-2+3*x)])

        w = max(x-1,0)
        h.pose.bones['cf_J_Ana'].scale = Vector([1+w*0.1,1,1+w*0.1])
        h.pose.bones['cf_J_ExhaustValve'].scale=Vector([1+w*0.5,1,1+w*0.15])
        h.pose.bones['cf_J_ExhaustValve'].location=Vector([0, 0, -0.002*w])
        h.pose.bones['cf_J_Exhaust'].scale=Vector([1,1,1])
        #h.pose.bones['cf_J_ExhaustValve'].rotation_euler[0]=max(0.0, (x-1)*0.04)
        #h.pose.bones['cf_J_ExhaustClench'].location=Vector([0,0.02*max(x-1,0), 0])
        #h.pose.bones['cf_J_ExhaustValve'].location=Vector([0,0,-0.0035*max(x-1,0)])
        h.pose.bones['cf_J_Exhaust'].location=Vector([-0.002*w, 0, 0])

    if name=="IK":
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
        # Would be nice to load all actual bone positions into FK when IK is turned off,
        # but I couldn't figure out how to do that correctly yet
        for b in ik_controlled_bones:
            if b in h.pose.bones:
                for c in h.pose.bones[b].constraints:
                    if c.type=='IK':
                        c.enabled=x
        if x:
            for b in ik_affected_bones:
                h.pose.bones[b].rotation_euler=Euler([0,0,0])
    if name=="Skin tone":
        body = h["body"]
        mean_skin_tone = Color(body.mean_skin_tone)
        x = Color(x)
        body.skin_tone_shift[0] = 50.0*(x.h - mean_skin_tone.h)
        if x.s>1e-8:
            body.skin_tone_shift[1] = math.log(x.s) / math.log(mean_skin_tone.s) - 1.0
        else:
            body.skin_tone_shift[1] = 5.0
        body.skin_tone_shift[2] = x.v - mean_skin_tone.v
    if name=="Hair color":
        color=(x[0],x[1],x[2],1.0)
        for mat in h['hair_mats']:
            if 'RGB' in mat.node_tree.nodes:
                mat.node_tree.nodes['RGB'].outputs[0].default_value = color
            else:
                mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color
    if name=="Eye color":
        body = h["body"]
        color = x
        eye_mat = [y for y in body.material_slots.keys() if ('Eyes' in y and not 'Eyeshadow' in y)]
        if len(eye_mat)>0:
            bpy.data.materials[eye_mat[0]].node_tree.nodes['RGB'].outputs[0].default_value = (color[0],color[1],color[2],1.0)

def reset_skin_tone():
    h = hs2object()
    if h is None:
        return
    body = h["body"]
    h["Skin tone"]=body.mean_skin_tone
    body.skin_tone_shift[0] = 0.0
    body.skin_tone_shift[1] = 0.0
    body.skin_tone_shift[2] = 0.0


def push_mat_attributes(v):
    h = hs2object()
    if h is None:
        return

    def push_value_attr(v, mat, name):
        if name in v:
            mat.node_tree.nodes[name].outputs[0].default_value = v[name]

    def push_input_attr(v, mat, name, node, input_name):
        if name in v:
            mat.node_tree.nodes[node].inputs[input_name].default_value = v[name]
    body = h["body"]
    head_mat = body["head_mat"]
    push_value_attr(v, head_mat, "Eyebrow scale",)
    push_value_attr(v, head_mat, "Eyebrow rotation")
    push_value_attr(v, head_mat, "Eyebrow X offset")
    push_value_attr(v, head_mat, "Eyebrow Y offset")
    push_value_attr(v, head_mat, "Eyebrow arch")

    torso_mat = body["torso_mat"]
    push_value_attr(v, torso_mat, "Booby scale")
    push_input_attr(v, torso_mat, "Torso bump scale", "Shader", "Bump scale")
    push_input_attr(v, torso_mat, "Torso bump scale 2", "Shader", "Bump scale 2")

    nails_mat = body["nails_mat"]
    push_input_attr(v, nails_mat, "Nail color", "Mix", "A")

    eye_mat = body["eye_mat"]
    push_value_attr(v, eye_mat, "Pupil size")
    push_value_attr(v, eye_mat, "Iris size")

    for x in ["fat"]:
        if x in v:
            h[x] = float(v[x])

    for x in ["pore_depth", "pore_intensity", "pore_density", "Gloss", "Alternate skin"]:
        if x in v:
            if isinstance(body[x], float):
                body[x] = float(v[x])
            else:
                body[x] = bool(v[x])

    for x in ['Eye shape', 'Adams apple delete', 'Upper lip trough', 'Lip arch', 'Eyelid crease', 'Temple depress',
        'Jaw soften', 'Jaw soften more', 'Nasolabial crease', 'Nails', 'Long fingernails', 'Long toenails']:
        if x in body.data.shape_keys.key_blocks and x in v:
            body.data.shape_keys.key_blocks[x].value = float(v[x])


def collect_mat_attributes():
    h = hs2object()
    if h is None:
        return {}

    # Return everything including attrs at defaults. Otherwise, preset writer
    # would need a full list of attributes, to determine which ones should be 
    # deleted upon save
    def pull_value_attr(v, mat, name):
        val = mat.node_tree.nodes[name].outputs[0].default_value
        v[name] = val

    def pull_input_attr(v, mat, name, node, input_name):
        val = mat.node_tree.nodes[node].inputs[input_name].default_value
        print(mat, name, val)
        if isinstance(val, float):
            v[name] = val
        else:
            v[name] = val[:]

    v={}
    body = h["body"]
    head_mat = body["head_mat"]
    pull_value_attr(v, head_mat, "Eyebrow scale")
    pull_value_attr(v, head_mat, "Eyebrow rotation")
    pull_value_attr(v, head_mat, "Eyebrow X offset")
    pull_value_attr(v, head_mat, "Eyebrow Y offset")
    pull_value_attr(v, head_mat, "Eyebrow arch")

    torso_mat = body["torso_mat"]
    pull_value_attr(v, torso_mat, "Booby scale")
    pull_input_attr(v, torso_mat, "Torso bump scale", "Shader", "Bump scale")
    pull_input_attr(v, torso_mat, "Torso bump scale 2", "Shader", "Bump scale 2")

    nails_mat = body["nails_mat"]
    #print("nails_mat", nails_mat)
    pull_input_attr(v, nails_mat, "Nail color", "Mix", "A")

    eye_mat = body["eye_mat"]
    pull_value_attr(v, eye_mat, "Pupil size")
    pull_value_attr(v, eye_mat, "Iris size")

    for x in ["fat"]:
        if x in h:
            v[x] = h[x]

    for x in ["pore_depth", "pore_intensity", "pore_density", "Gloss", "Alternate skin"]:
        if isinstance(body[x], float) or isinstance(body[x], bool):
            v[x] = body[x]
        else:
            v[x] = [float(y) for y in body[x]]

    for x in ['Eye shape', 'Adams apple delete', 'Upper lip trough', 'Lip arch', 'Eyelid crease', 'Temple depress',
        'Jaw soften', 'Jaw soften more', 'Nasolabial crease', 'Nails', 'Long fingernails', 'Long toenails']:
        if x in body.data.shape_keys.key_blocks:
            v[x] = body.data.shape_keys.key_blocks[x].value
    #print(v)
    return v