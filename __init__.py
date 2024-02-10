import bpy
import os
import bmesh
import math
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy
import json
import hashlib

from .armature import (
    reshape_armature, 
    reshape_armature_fallback, 
    load_pose, 
    dump_pose, 
    recompose, 
    rot_mode, 
    bone_class,
    rescale_one_bone
)

from . import add_extras, importer, armature, solve_for_deform, attributes

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    PointerProperty,
    StringProperty,
    FloatVectorProperty
)
from bpy.types import (
    Operator,
    Panel,
    PropertyGroup,
)

from .attributes import (
    get_eagerness,
    get_length,
    get_girth,
    get_volume,
    get_wet,
    get_sheath,
    get_exhaust,
    set_eagerness,
    set_length,
    set_girth,
    set_volume,
    set_wet,
    set_sheath,
    set_exhaust,
    get_ik,
    set_ik,
    get_custom_geo,
    set_custom_geo,
    get_daisy_protocol,
    set_daisy_protocol,
)

bl_info = {
    "name": "HS2 character importer",
    "author": "",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "description": "HS2 character importer",
    "tracker_url": "",
    "doc_url": "",
    "community": "",
    "downloads": "",
    "main_web": "",
    "category": "Object"
}


name='Unnamed'

#
#
#  EYE/HAIR COLOR
#
#

#eye_color=None
#hair_color=None

def hs2object():
    arm = bpy.context.active_object
    if arm is None:
        return None
    if arm.type=='MESH':
        arm = arm.parent
    if arm.type!='ARMATURE':
        return None
    return arm



def get_hair_color(self):
    #print('get_hair_color', self)
    h = hs2object()
    try:
        return h['hair_color']
    except:
        return (0.8, 0.8, 0.5)

def set_hair_color(self, color):
    h = hs2object()
    if h is None:
        return
    h['hair_color']=color
    color=(color[0],color[1],color[2],1.0)
    for mat in h['hair_mats']:
        if 'RGB' in mat.node_tree.nodes:
            mat.node_tree.nodes['RGB'].outputs[0].default_value = color
        else:
            mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color

def get_eye_color(self):
    h = hs2object()
    try:
        color = h['eye_color']
        return color
    except:
        return (0.0, 0.0, 0.8)

def set_eye_color(self, color):
    print("set_eye_color", color)
    h = hs2object()
    if h is None:
        return
    h['eye_color']=color
    for body in h.children:
        if body.type!="MESH":
            continue
        eye_mat = [x for x in body.material_slots.keys() if ('Eyes' in x and not 'Eyeshadow' in x)]
        if len(eye_mat)>0:
            bpy.data.materials[eye_mat[0]].node_tree.nodes['RGB'].outputs[0].default_value = (color[0],color[1],color[2],1.0)
        #else:
        #    print("No eye mat")



preset_list=[]
preset_map={}
waifus_path=""
presets_dirty = False

def get_preset_list(self, context):
    return preset_list

def get_export_dir(self):
    return waifus_path

def set_export_dir(self, x):
    global waifus_path, presets_dirty
    if x!=waifus_path:
        presets_dirty = True
    waifus_path=x


#
#
#   PRESET LIST
#
#  


def load_presets():
    global preset_list, preset_map, waifus_path, presets_dirty
    preset_map={}
    # Tricky! I can't write 'preset_list=[]', because there's a reference to the _original_ instance of preset_list
    # stored inside hs2rig_data.presets. And if I simply reassign it, the UI will keep on using the old list.
    preset_list.clear()
    index=0
    presets_dirty = False
    if False:
        cfg_path = os.path.dirname(__file__)+"/assets/hs2blender.json"
        try:
            fp=open(cfg_path, "r")
            cfg = json.load(fp)
            fp.close()
            waifus_path = cfg["waifus_path"]
            json_preset_map = cfg["presets"]
            for x in json_preset_map:
                preset_map[int(x)]=json_preset_map[x]

            for k in preset_map:
                #preset_map[index]=[x[0], y[0], colors[0:3], colors[3:6], None]
                #print(k, type(k), preset_map[k][0])
                preset_list.append((str(k), preset_map[k][0], preset_map[k][0], k))

        except:
            pass
    else:
        try:
            cfg=open(config_path,"r").readlines()
            waifus_path=cfg[0].strip()
            cfg=[x.strip().split(' ',7) for x in cfg[1:]]
            for x in cfg:
                if len(x)<2:
                    continue
                y = x[1:]
                #if len(y)==1:
                #    conf[x[0]]=(y[0],)
                #else:
                colors=[float(z) for z in y[1:7]]
                #if y[0][0]!='/':
                #    y[0]=waifus_path+y[0]
                #else:
                #    y[0]=y[0][1:]
                extras = x[7] if len(x)>7 else None
                preset_map[index]=[x[0], y[0], colors[0:3], colors[3:6], None]
                preset_list.append((str(index), x[0], x[0], index))
                index+=1
        except:
            pass
    
    print(preset_list)
    n = 0


    map_path = os.path.dirname(__file__)+"/assets/hash_map.txt"
    textures=set()
    try:
        f=open(map_path, "r").readlines()
        for x in f:
            x=x.strip().split(' ', 1)
            importer.hash_to_file_map[x[1]]=x[0]
            textures.add(x[0])
    except:
        pass

    saved_hash_map=None
    try:
        saved_hash_map=open(map_path, "a")
    except:
        pass

    if saved_hash_map is None:
        try:
            saved_hash_map=open(config_path, "w")
        except:
            print("Failed to open the saved hash map file for writing")
            return

    #textures=set(importer.hash_to_file_map.values())
    #print(preset_map)
    print(len(textures), "previously indexed textures")
    #print(textures.pop())
    for x in preset_map:
        dump_dir = preset_map[x][1]
        if dump_dir[0]=='/':
            dump_dir = dump_dir[1:]
        else:
            dump_dir = waifus_path+dump_dir
        try:
            print(dump_dir+'/Textures/')
            v=os.listdir(dump_dir+'/Textures/')
        except:
            pass
        for f in v:
            if f.endswith('.png'):
                ff=dump_dir+'/Textures/'+f
                #if n<3:
                #    print(ff, ff in textures)
                if ff in textures:
                    continue
                try:
                    md5=hashlib.md5(open(ff,'rb').read()).hexdigest()
                except:
                    pass
                n+=1
                importer.hash_to_file_map[md5] = ff
                saved_hash_map.write(ff+" "+md5+"\n")
    saved_hash_map.close()
    print(n, "newly indexed textures, ", len(importer.hash_to_file_map), "unique hashes")
    preset_list.append((str(index), "<New>", "<New>", index))
    preset = 0
    try:
        preset = int(bpy.context.scene.hs2rig_data.presets)
    except:
        pass
    try:
        #print("Reloaded presets; trying to reapply", bpy.context.scene.hs2rig_data.presets)
        preset_select(None, preset)
    except:
        pass

in_preset_select = False
def preset_update(self, context):
    #print("preset_update")
    global presets_dirty, preset_map, waifus_path

    if in_preset_select:
        return

    export_dir = bpy.context.scene.hs2rig_data.export_dir
    if export_dir != waifus_path:
        waifus_path = export_dir
        presets_dirty = True

    current = int(bpy.context.scene.hs2rig_data.presets)
    #print("current", current, type(current))
    #print("preset_map", preset_map)
    #print("included", current in preset_map)
    if current in preset_map:
        #print("In the map")
        #name, path, eye_color, hair_color, _ = preset_map[current]
        s = bpy.context.scene.hs2rig_data.char_name
        if preset_map[current][0] != s:
            preset_map[current][0] = s
            preset_list[current]=(str(current),s,s,current)
            presets_dirty = True
        path = bpy.context.scene.hs2rig_data.dump_dir[:]
        if path.startswith(waifus_path):
            path=path[len(waifus_path):]
            while path.startswith('/'):
                path=path[1:]
        else:
            path = "/" + path
        if path != preset_map[current][1]:
            preset_map[current][1] = path
            presets_dirty = True
        c = list(bpy.context.scene.hs2rig_data.preset_eye_color[:])
        if any([abs(x[0]-x[1])>0.0001 for x in zip(preset_map[current][2], c)]):
            preset_map[current][2] = c
            presets_dirty = True
        c = list(bpy.context.scene.hs2rig_data.preset_hair_color[:])
        if any([abs(x[0]-x[1])>0.0001 for x in zip(preset_map[current][3], c)]):
            preset_map[current][3] = c
            presets_dirty = True

def save_presets():
    global presets_dirty
    preset_update(None,None)

    cfg_path = os.path.dirname(__file__)+"/assets/hs2blender.json"
    backup_path = cfg_path + ".bak"
    current_md5 = None
    backup_md5 = None
    try:
        backup_md5=hashlib.md5(open(backup_path,'rb').read()).hexdigest()
    except:
        pass
    try:
        current_md5=hashlib.md5(open(cfg_path,'rb').read()).hexdigest()
    except:
        pass

    if (current_md5 is not None) and os.stat(cfg_path).st_size>0 and (backup_md5 != current_md5):
        try:
            os.remove(backup_path+".bak")
        except:
            pass
        try:
            os.remove(backup_path+".bak")
        except:
            pass
        try:
            os.remove(backup_path)
        except:
            pass
        try:
            os.rename(cfg_path, backup_path)
        except:
            pass

    fp=open(cfg_path, "w")
    cfg = {
    "waifus_path":waifus_path,
    "presets":preset_map
    }
    #print(preset_map)
    json.dump(cfg, fp, indent=4)
    fp.close()
    presets_dirty = False
    return

def replace_preset(index, name, path, hair_color, eye_color):
    return

def add_new_preset(name, path, hair_color, eye_color):
    return

def preset_get(self):
    try:
        return self['presets']
    except:
        return 0

def preset_select(self, value):
    global in_preset_select, preset_list, preset_map
    #print("preset_select", self, type(self), value, type(value), value in preset_map)
    if self is not None:
        self['presets']=value
    if value == len(preset_map):
        s = "<New>"
        preset_map[value] = [s, "", bpy.context.scene.hs2rig_data.preset_eye_color[:], bpy.context.scene.hs2rig_data.preset_hair_color[:], None]
        #print("Old preset list tail", preset_list[-1])
        preset_list.pop()
        preset_list.append((str(value), s, s, value))
        value+=1
        preset_list.append((str(value), "<New>", "<New>", value))
        in_preset_select = True
        bpy.context.scene.hs2rig_data.char_name = s
        bpy.context.scene.hs2rig_data.dump_dir = waifus_path+"/"
        in_preset_select = False
        #print("New preset list tail", preset_list[-1])
        return
    if value in preset_map:
        in_preset_select = True
        name, path, eye_color, hair_color, _ = preset_map[value]
        bpy.context.scene.hs2rig_data.char_name = name
        if len(path)>0:
            if path[0]!='/':
                path=waifus_path+path
            else:
                path=path[1:]
        bpy.context.scene.hs2rig_data.dump_dir = path
        bpy.context.scene.hs2rig_data.preset_eye_color = eye_color
        #print("Eye color", eye_color)
        bpy.context.scene.hs2rig_data.preset_hair_color = hair_color
        in_preset_select = False

#
#
#   STANDARD POSES
# 
#

standard_pose_list=[
('Sit',[('cf_J_LegUp00_L', -90, 0, 0), 
    ('cf_J_LegLow01_L', 90, 0, 0), 
    ('cf_J_ArmUp00_L', 0, 0, -75, -1),
    ('cf_J_ArmLow01_L', 10, 0, 0),
    ]),
('Kneel',[('cf_J_LegUp00_L', -20, 0, 45, -1), 
    ('cf_J_LegLow01_L', 120, 0, 0), 
    ('cf_J_ArmUp00_L', 0, 0, -75, -1),
    ('cf_J_ArmLow01_L', 10, 0, 0),
    ('cf_J_Foot01_L', 20, 0, 0),
    ('cf_J_Foot02_L', 40, 0, 0),
    ]),
('T',[]),
('A',[('cf_J_LegUp00_L', 0, 0, 20, -1), 
    ('cf_J_ArmUp00_L', 0, 0, -60, -1),
    ]),
('Attention', [('cf_J_LegUp00_L', 0, 0, 0, -1), 
    ('cf_J_Shoulder_L', 0, 0, -10, -1),
    ('cf_J_ArmUp00_L', 0, 0, -70, -1),
    ]),
('Pray', [('cf_J_LegUp00_L', -70,0,0),
         ('cf_J_LegLow01_L', 160, 0, 0),
         ('cf_J_Foot01_L', -20, 0, 0),
         ('cf_J_Foot02_L', 30, 0, 0),
         ('cf_J_Shoulder_L', 10,0,-10,-1),
         ('cf_J_ArmUp00_L', 45, -75, -100, -1),
         ('cf_J_ArmLow01_L', 0, -90, 0, -1),
         ('cf_J_Hand_L', 0, 0, 30, -1),
         ('cf_J_Spine01', 15, 0, 0),
         ('cf_J_Spine02', 15, 0, 0)
    ]),
('Yoga', [('cf_J_LegUp00_L', -80,105,35),
          ('cf_J_LegUp00_R', -80,-105,-35),
          ('cf_J_LegLow01_L',130,0,0),
          ('cf_J_LegLow01_R',145,0,0),
          ('cf_J_Foot01_L',0,0,0),
          ('cf_J_Foot01_R',20,30,20),
          ('cf_J_Foot02_L',40,0,0),
          ('cf_J_Foot02_R',25,0,0),
          ('cf_J_Shoulder_L',15,0,-25),
          ('cf_J_Shoulder_R',-25,0,-45),
          ('cf_J_ArmUp00_L',135,5,-75),
          ('cf_J_ArmUp00_R',-140,0,-50),
          ('cf_J_ArmLow01_L',20,-150,0),
          ('cf_J_ArmLow01_R',-45,145,0),
            ]),
('Crawl', 'assets/crawling.txt'),
('Cute', 'assets/cutev1.txt'),
('Half5', 'assets/pose_half5.txt'),
('Half6', 'assets/pose_half6.txt'),
]

standard_pose_list_names = [(x[0],x[0],x[0]) for x in standard_pose_list]

def get_finger_curl(self):
#    arm = bpy.context.active_object
    try:
        return self["finger_curl"]
    except:
        return 10.0
    
def set_finger_curl(self, x):
#    print("set_finger_curl", self, arm, x)
    self["finger_curl"]=x
    arm = bpy.context.active_object
    if arm.type == 'MESH':
        arm = arm.parent
    if arm.type != 'ARMATURE':
        return
    bones = [('cf_J_Hand_'+a+'0'+str(b)+'_L', 0, 0, -x, -1   ) for a in ('Index','Middle','Ring','Little') for b in range(1,4)]
    for x in bones:
        #arm.pose.bones[x[0]].rotation_mode=rot_mode
        arm.pose.bones[x[0]].rotation_euler=Euler((x[1]*math.pi/180., x[2]*math.pi/180., x[3]*math.pi/180.), rot_mode)
        mult = -1.0 if len(x)>4 else 1.0
        #arm.pose.bones[x[0][:-1]+'R'].rotation_mode=rot_mode
        arm.pose.bones[x[0][:-1]+'R'].rotation_euler=Euler((x[1]*math.pi/180., mult*x[2]*math.pi/180., mult*x[3]*math.pi/180.), rot_mode)

#    eval('bpy.ops.' + self.primitive + '()')

def standard_pose_get(self):
    try:
        return self['standard_pose']
    except:
        return 0

def standard_pose_select(self, value):
   print("standard_pose_select", self, value)
   self['standard_pose']=value
   set_fixed_pose(bpy.context, value)
    
class hs2rig_props(PropertyGroup):
    #
    #   Plugin-wide settings
    #
    export_dir: StringProperty(
        name="Export directory",
        default='c:\\temp\\hs2\\export',
        description='Export directory',
        get=get_export_dir,
        set=set_export_dir
    )
    presets: bpy.props.EnumProperty(items=get_preset_list,
            description="description",
            default=None,
            get=preset_get,
            set=preset_select
        )
    standard_poses: bpy.props.EnumProperty(items=standard_pose_list_names,
            description="description of poses",
            default=None,
            get=standard_pose_get,
            set=standard_pose_select
        )
    #
    #  Import configuration, read from the preset and/or set by the user in the import box
    #
    char_name: StringProperty(name="Name", default="BR-Chan",update=preset_update)
    dump_dir: StringProperty(
        name="Char directory",
        default='c:\\temp\\hs2\\export\\BR-Chan',
        description='Char directory',
        update=preset_update
    )
    refactor: BoolProperty(name="Refactor armature", 
        default=True,
        description="When checked, the armature will be recalculated so that all body shape adjustments become part of the pose."
        " It is slower and it sometimes fails, but it makes imported clothing and hair interchangeable between characters"
        )
    tweak_mouth: BoolProperty(name="Tweak mouth", default=False,
        description="Tweak mouth and chin bones and weights to make it possible to operate the mouth with the cf_J_Chin_rs bone."
        "Will slightly alter the appearance."
        )
    tweak_cheeks: BoolProperty(name="Tweak cheeks", default=True,
        description="Add new bones to improve control over cheek shapes."
        "Will slightly alter the appearance."
        )
    replace_teeth: BoolProperty(name="Replace teeth", default=True, description="Replace exported teeth with a known-good version")
    add_injector: BoolProperty(name="Add an injector", default=False, description="Add a prefabricated injector and attempt to stitch it onto the mesh")
    add_exhaust: BoolProperty(name="Add an exhaust", default=True, description="Add a prefabricated exhaust port and attempt to stitch it onto the mesh")
    wipe: BoolProperty(name="Wipe scene before import", default=True,
        description="When checked, all existing objects will be deleted from the scene before the new character is added")
    preset_hair_color: FloatVectorProperty(name="Preset hair color", default=(0,0,0), subtype='COLOR', min=0.0, max=1.0, update=preset_update)
    preset_eye_color: FloatVectorProperty(name="Preset eye color", default=(0.8,0.8,0.5), subtype='COLOR', min=0.0, max=1.0, update=preset_update)

    #
    # Character shape customization
    #

    custom_geo: FloatProperty(
        name="Body customization", min=0, max=2,
        default=1, precision=2,
        description="Morphs between default body shape and character specific body shape",
        get=get_custom_geo,
        set=set_custom_geo
    )
    daisy_protocol: FloatProperty(name="Daisy protocol",
        default=0.0, soft_min=0.0, soft_max=1.5,
        description="Don't ask",
        get=get_daisy_protocol, set=set_daisy_protocol)

    #
    #  Character posing and appearance adjustment
    #
    #
    # There's only one system-wide instance of hs2rig_props.hair_color, because there seems to be no way to add it dynamically to the object.
    # It is only an interface object with no owned data; the actual hair color is stored as a custom property of the armature.
    # Ditto length, exhaust, etc.
    #

    finger_curl_scale: FloatProperty(
        name="Finger curl", min=0, max=100,
        default=10, precision=1,
        description="Finger curl",
        get=get_finger_curl,
        set=set_finger_curl        
    )
    ik: BoolProperty(name='IK', default=True, get=get_ik, set=set_ik)
    hair_color: FloatVectorProperty(name="Hair color", default=(0,0,0), subtype='COLOR', min=0.0, max=1.0, get=get_hair_color, set=set_hair_color)
    eye_color: FloatVectorProperty(name="Eye color", default=(0.8,0.8,0.5), subtype='COLOR', min=0.0, max=1.0, get=get_eye_color, set=set_eye_color)
    eagerness: FloatProperty(name="Eagerness", default=25.0, soft_min=0.0, soft_max=100.0, step=1, get=get_eagerness, set=set_eagerness)
    length: FloatProperty(name="Length", default=75.0, soft_min=0.0, soft_max=100.0, step=1, get=get_length, set=set_length)
    girth: FloatProperty(name="Girth", default=50.0, soft_min=0.0, soft_max=100.0, step=1, get=get_girth, set=set_girth)
    volume: FloatProperty(name="Volume", default=75.0, soft_min=0.0, soft_max=100.0, step=1, get=get_volume, set=set_volume)
    exhaust: FloatProperty(name="Exhaust", default=1.0, soft_min=0.0, soft_max=10.0, get=get_exhaust, set=set_exhaust)
    sheath: BoolProperty(name="Sheath", default=True, get=get_sheath, set=set_sheath)
    wet: BoolProperty(name="Wet", default=False, get=get_wet, set=set_wet)
    file_path: StringProperty(
        name="Pose file", 
        default='c:\\temp\\pose.txt', 
        description="Pose file"
    )

    command: StringProperty(
        name="Command", 
        default="", 
        description=""
    )
 
    def execute(self, context):
        return {'FINISHED'}

    #def poll(self, context):
    #    print("Poll")
    #    return {'FINISHED'}


def finger_curl(x):
    return [('cf_J_Hand_'+a+'0'+str(b)+'_L', 0, 0, -x, -1   ) for a in ('Index','Middle','Ring','Little') for b in range(1,4)]


def set_fixed_pose(context, pose):
    arm = context.active_object
    if arm is None:
        return
    if arm.type=='MESH':
        arm = arm.parent
    if arm.type!='ARMATURE':
        return
    set_ik(arm, False)
    v=[]
    if isinstance(pose, int):
        v = standard_pose_list[pose][1][:]
    else:
        for x in standard_pose_list:
            if x[0]==pose:
                v=x[1][:]
    if isinstance(v, str):
        load_pose(arm.name, v, 1)
        return {'FINISHED'}
    v+=finger_curl(0.0 if (pose=='T' or pose=='Pray') else context.scene.hs2rig_data.finger_curl_scale)
    #print(v)
    # todo: clear all bones
    deformed_rig = arm["deformed_rig"]
    for x in arm.pose.bones:
        if x.name in deformed_rig and armature.bone_class(x.name, 'rotation')=='f':
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
    return {'FINISHED'}

#
#
#   POSE/SHAPE LOADING AND SAVING
#
#

class hs2rig_OT_execute(Operator):
    bl_idname = "object.execute_command"
    bl_label = "Execute arbitrary command"
    bl_description = ""
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if context.scene.hs2rig_data.command == "eyelid_crease":
            arm = hs2object()
            if arm is not None:
                for y in arm.children:
                    if y.type=='MESH' and "pore_density" in y:
                        save_object = bpy.context.view_layer.objects.active
                        try:
                            add_extras.eyelid_crease(y)
                        except:
                            pass
                        bpy.context.view_layer.objects.active = save_object

        #load_pose(context.active_object.name, context.scene.hs2rig_data.file_path, 1)
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
        load_pose(context.active_object.name, context.scene.hs2rig_data.file_path, 7)
        return {'FINISHED'}

class hs2rig_OT_save_fk(Operator):
    bl_idname = "object.save_pose_fk"
    bl_label = "Save pose"
    bl_description = "Saves the character pose to the file"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        of=open(context.scene.hs2rig_data.file_path,"w")
        dump_pose(context.active_object.name, of, flags=1)
        of.close()
        return {'FINISHED'}

class hs2rig_OT_save_soft(Operator):
    bl_idname = "object.save_pose_soft"
    bl_label = "Save shape"
    bl_description = "Saves the character shape to the file"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        of=open(context.scene.hs2rig_data.file_path,"w")
        dump_pose(context.active_object.name, of, flags=2)
        of.close()
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

#
#
#   MAIN UI
#
#

class hs2rig_OT_clothing(Operator):
    bl_idname = "object.toggle_clothing"
    bl_label = "Toggle clothing"
    bl_description = "Set selected scale"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        arm = context.active_object
        if arm.type=='MESH':
            arm=arm.parent
        if arm.type!='ARMATURE':
            return {'FINISHED'}
        for x in arm.children:
            if x.type=='ARMATURE' or x.type=='LIGHT':
                continue
            if 'Prefab ' in x.name:
                continue
            if 'hair' in x.name:
                continue
            if x.type=='MESH' and len(x.data.materials)>0 and x.data.materials[0].name.startswith('Injector'):
                continue
            if x.type=='MESH' and len(x.data.materials)>0 and 'hair' in x.data.materials[0].name:
                continue
            if x.name.startswith('o_tang'):
                continue
            if x.name.startswith('o_tooth'):
                continue
            if x.name.startswith('o_body'):
                continue
            x.hide_viewport = not x.hide_viewport
        return {'FINISHED'}

class hs2rig_OT_import(Operator):
    bl_idname = "object.import"
    bl_label = "Import model"
    bl_description = "Import model"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print("trying to import...")
        importer.import_body(context.scene.hs2rig_data.dump_dir, 
            refactor=context.scene.hs2rig_data.refactor, 
            do_tweak_mouth=context.scene.hs2rig_data.tweak_mouth, 
            do_tweak_cheeks=context.scene.hs2rig_data.tweak_cheeks, 
            replace_teeth=context.scene.hs2rig_data.replace_teeth, 
            add_injector=context.scene.hs2rig_data.add_injector, 
            add_exhaust=context.scene.hs2rig_data.add_exhaust, 
            wipe=context.scene.hs2rig_data.wipe, 
            c_eye=context.scene.hs2rig_data.preset_eye_color, 
            c_hair=context.scene.hs2rig_data.preset_hair_color,
            name=context.scene.hs2rig_data.char_name
            )
        bpy.context.scene.hs2rig_data.standard_poses="T"
        return {'FINISHED'}

class hs2rig_OT_import_all(Operator):
    bl_idname = "object.import_all"
    bl_label = "Import all models"
    bl_description = "Import all models"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print("trying to import...")
        count = 0
        for value in preset_map:
            name, path, eye_color, hair_color, _ = preset_map[value]
            if path[0]!='/':
                path=waifus_path+path
            else:
                path=path[1:]
            bpy.context.scene.hs2rig_data.dump_dir = path
            bpy.context.scene.hs2rig_data.preset_eye_color = eye_color
            bpy.context.scene.hs2rig_data.preset_hair_color = hair_color

            arm = importer.import_body(path,
                refactor=context.scene.hs2rig_data.refactor, 
                do_tweak_mouth=context.scene.hs2rig_data.tweak_mouth,
                do_tweak_cheeks=context.scene.hs2rig_data.tweak_cheeks,
                replace_teeth=context.scene.hs2rig_data.replace_teeth,
                add_injector=None,
                add_exhaust=context.scene.hs2rig_data.add_exhaust,
                wipe=False,
                c_eye=eye_color,
                c_hair=hair_color,
                name=name
                )
            if arm is not None:
                arm.location = Vector([count, 0, 0])
                count+=1

        bpy.context.scene.hs2rig_data.standard_poses="T"
        return {'FINISHED'}

class hs2rig_OT_reload_presets(Operator):
    bl_idname = "object.reload_presets"
    bl_label = "Reload presets"
    bl_description = "Reload all presets"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        load_presets()
        return {'FINISHED'} 


class hs2rig_OT_save_presets(Operator):
    bl_idname = "object.save_presets"
    bl_label = "Save presets"
    bl_description = "Save all presets"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        save_presets()
        return {'FINISHED'} 

"""
class hs2rig_OT_import_preset(Operator):
    bl_idname = "object.import_preset"
    bl_label = "Import preset"
    bl_description = "Import preset"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print("trying to import...")
        #self['presets']=value
        value = int(context.scene.hs2rig_data.presets)
        print("Value", value)
        #print(preset_map)
        if value in preset_map:
            name, path, eye_color, hair_color = preset_map[value]
            print(path)
            importer.import_body(path, context.scene.hs2rig_data.refactor, 
                context.scene.hs2rig_data.tweak_mouth, 
                context.scene.hs2rig_data.tweak_cheeks, 
                context.scene.hs2rig_data.add_extra, 
                context.scene.hs2rig_data.wipe, 
                eye_color, hair_color,
                name)
            print('Done')
        else:
            print('Not in the map')
        return {'FINISHED'} 
"""

#@classmethod
#def main(context):
#    print("execute")
    
class HS2RIG_PT_ui(Panel):
    bl_idname = "HS2RIG_PT_ui"
    bl_label = "HS2 rig"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HS2Rig"
    bl_context = ""
    bl_options = {'DEFAULT_CLOSED'}


    def draw(self, context):
        layout = self.layout
        scene = context.scene
        arm = context.active_object #bpy.data.objects['Armature']
        if arm is not None and arm.type == 'MESH':
            arm = arm.parent

        if arm is not None and arm.type == 'ARMATURE' and arm.get("default_rig")!=None:
            box = layout.box()    
            box.prop(context.scene.hs2rig_data, "standard_poses")
            #row = box.row(align=True)
            #row.operator("object.save_preset")
            #row.enabled=False
            #row = box.row(align=True)
            #row.operator("object.standard_pose")
            """
            row = layout.row(align=True)
            row.operator("object.set_pose")
            row.operator("object.set_pose2")
            row.operator("object.set_pose3")
            row.operator("object.set_pose4")
            row.operator("object.set_pose5")
            """
            row = layout.row(align=True)
            #row.operator("object.apply_scale")
            row.operator("object.toggle_clothing")
            row = layout.row(align=True)
            row.prop(context.scene.hs2rig_data, "finger_curl_scale", slider=True)
                #row = layout.row(align=True)
            row.prop(context.scene.hs2rig_data, "exhaust")
            #row.prop(context.scene.hs2rig_data, "custom_geo", slider=True)
            #row.prop(context.scene.hs2rig_data, "daisy_protocol", slider=True)
            if arm.type == 'ARMATURE' and ('stick_01' in arm.pose.bones):
                try:
                    row = layout.row(align=True)
                    row.prop(context.scene.hs2rig_data, "eagerness")
                    row.prop(context.scene.hs2rig_data, "length")
                    row = layout.row(align=True)
                    row.prop(context.scene.hs2rig_data, "girth")
                    row.prop(context.scene.hs2rig_data, "volume")
                    row = layout.row(align=True)
                    row.prop(context.scene.hs2rig_data, "wet")
                    row.prop(context.scene.hs2rig_data, "sheath")
                except:
                    print('Failed to add stick controls')
            row = layout.row(align=True)
            row.prop(context.scene.hs2rig_data, "ik")
            row = layout.row(align=True)
            #row.prop(context.scene.hs2rig_data, "command")
            #row.operator("object.execute_command")
        
            row = layout.row(align=True)
            row.prop(context.scene.hs2rig_data, "file_path")
            row = layout.row(align=True)
            row.operator("object.load_pose_fk")
            row.operator("object.load_pose_soft")
            row.operator("object.load_pose_all")
            row.operator("object.save_pose_fk")
            row.operator("object.save_pose_soft")
            row.operator("object.save_pose_all")
            
            #row.operator("object.load_unity")
        if (arm is not None) and (arm.get("hair_color") is not None):
            box = layout.box()
            row = box.row(align=True)
            #global hair_color
            #if hair_color is None:
            hair_color = arm["hair_color"]
            eye_color = arm["eye_color"]
            try:
                #if not 'hair_color' in dir(arm):
                #    arm.hair_color = FloatVectorProperty(name="Hair color", default=hair_color[:3], subtype='COLOR', min=0.0, max=1.0, get=get_hair_color, set=set_hair_color)
                #    arm.eye_color = FloatVectorProperty(name="Eye color", default=eye_color[:3], subtype='COLOR', min=0.0, max=1.0, get=get_eye_color, set=set_eye_color)                
                row.prop(context.scene.hs2rig_data, "hair_color")
                row.prop(context.scene.hs2rig_data, "eye_color")
            except:
                print('Failed to add color controls')

        box = layout.box()
        box.label(text="System settings")
        box.prop(context.scene.hs2rig_data, "export_dir")
        box.prop(context.scene.hs2rig_data, "presets")
        row = box.row(align=True)
        b = row.box()
        op = b.operator("object.reload_presets")
        if not presets_dirty:
            b.enabled = False
        b = row.box()
        op = b.operator("object.save_presets")
        if not presets_dirty:
            b.enabled = False
        #row.enabled=False
        row = box.row(align=True)
        #row.operator("object.import_preset")
        #print(context.scene.hs2rig_data.presets)
        #if not (int(context.scene.hs2rig_data.presets) in preset_map):
        #    row.enabled=False

        box = box.box()
        #box.label(text="Character import")
        box.prop(context.scene.hs2rig_data, "dump_dir")
        row = box.row(align=True)
        row.prop(context.scene.hs2rig_data, "char_name")
        row = box.row(align=True)
        row.prop(context.scene.hs2rig_data, "preset_hair_color")
        row.prop(context.scene.hs2rig_data, "preset_eye_color")
        row = box.row(align=True)
        row.prop(context.scene.hs2rig_data, "wipe")
        row.prop(context.scene.hs2rig_data, "refactor")
        row = box.row(align=True)
        row.prop(context.scene.hs2rig_data, "tweak_mouth")
        row.prop(context.scene.hs2rig_data, "tweak_cheeks")
        row = box.row(align=True)
        row.prop(context.scene.hs2rig_data, "add_injector")
        row.prop(context.scene.hs2rig_data, "add_exhaust")
        row.prop(context.scene.hs2rig_data, "replace_teeth")
        row = box.row(align=True)
        row.operator("object.import")
        row.operator("object.import_all")
        row = box.row(align=True)
        row.label(text=importer.last_import_status)

addon_classes=[
#hs2rig_OT_standard_posing,
hs2rig_OT_clothing,
hs2rig_OT_load_fk,
hs2rig_OT_load_shape,
hs2rig_OT_load_all,
hs2rig_OT_save_fk,
hs2rig_OT_save_soft,
hs2rig_OT_save_all,
hs2rig_OT_import,
hs2rig_OT_import_all,
hs2rig_OT_save_presets,
hs2rig_OT_reload_presets,
#hs2rig_OT_import_preset,
HS2RIG_PT_ui, 
hs2rig_props,
hs2rig_OT_execute,
]

def unregister():
    for x in addon_classes: 
        try:
            bpy.utils.unregister_class(x)    
        except:
            pass
    
def register():
    global config_path
    config_path = os.path.dirname(__file__)+"/assets/hs2blender.cfg"
    load_presets()

    for x in addon_classes: 
        bpy.utils.register_class(x)
        
    bpy.types.Scene.hs2rig_data = PointerProperty(type=hs2rig_props)
    print("Registering...")
    import importlib
    importlib.reload(add_extras)
    importlib.reload(attributes)
    importlib.reload(importer)
    importlib.reload(armature)
    importlib.reload(solve_for_deform)

