import bpy
import os
import sys
import bmesh
import math
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy
import json
import hashlib
import uuid

analyzer_enabled = True
normalizer_enabled = True

try:
    analyzer_py = os.path.dirname(__file__)+"/analyzer.py"
    print(analyzer_py)
    f=open(analyzer_py, "r")
    f.close()
    analyzer_enabled = True
except:
    analyzer_enabled = False

try:
    normalizer_py = os.path.dirname(__file__)+"/normalizer.py"
    f=open(normalizer_py, "r")
    f.close()
    normalizer_enabled = True
except:
    normalizer_enabled = False

if analyzer_enabled:
    from . import analyzer

if normalizer_enabled:
    from . import normalizer

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

bl_info = {
    "name": "HS2 character importer",
    "author": "",
    "version": (1, 0, 240312),
    "blender": (4, 0, 2),
    "description": "HS2 character importer",
    "tracker_url": "",
    "doc_url": "",
    "community": "",
    "downloads": "",
    "main_web": "",
    "category": "Object"
}

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

stored_json_preset_map=""

preset_map={}
waifus_path=""
presets_dirty = False

def get_preset_list(self, context):
    preset_list = []
    for k in preset_map:
        preset_list.append((str(k), preset_map[k].name, preset_map[k]["uuid"], k))
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

class Preset(dict):
    def __init__(self,name,path,eye_color,hair_color,uid=None):
        self.name=name
        self.path=path
        self.eye_color=eye_color
        self.hair_color=hair_color
        self["uuid"] = uid or str(uuid.uuid4())

    def get_path(self):
        if len(self.path)>0:
            if self.path[0]!='/':
                return waifus_path+self.path
            else:
                return self.path[1:]
        else:
            return ""
    def set_path(self, path):
        if path.startswith(waifus_path):
            path=path[len(waifus_path):]
            while path.startswith('/'):
                path=path[1:]
        else:
            path = "/" + path
        changed = (self.path != path)
        self.path = path
        return changed

    def set_eye_color(self, c):
        changed = any([abs(x[0]-x[1])>0.0001 for x in zip(self.eye_color, c)])
        self.eye_color = c
        return changed

    def set_hair_color(self, c):
        changed = any([abs(x[0]-x[1])>0.0001 for x in zip(self.hair_color, c)])
        self.hair_color = c
        return changed

    def as_dict(self):
        v={"name":self.name, "path":self.path, "eye_color":self.eye_color, "hair_color":self.hair_color}
        for x in self:
            v[x]=self[x]
        return v

def convert_preset(list_preset):
    return Preset(list_preset[0],list_preset[1],list_preset[2],list_preset[3])

def convert_preset_from_dict(dict_preset):
    pr=Preset(dict_preset["name"],dict_preset["path"],dict_preset["eye_color"],dict_preset["hair_color"],dict_preset["uuid"])
    dict_preset.pop("name")
    dict_preset.pop("path")
    dict_preset.pop("eye_color")
    dict_preset.pop("hair_color")
    dict_preset.pop("uuid")
    for x in dict_preset:
        pr[x]=dict_preset[x]
    return pr

def load_presets():
    print("load_presets")
    global preset_map, waifus_path, presets_dirty, stored_json_preset_map
    preset_map={}
    # Tricky! I can't write 'preset_list=[]', because there's a reference to the _original_ instance of preset_list
    # stored inside hs2rig_data.presets. And if I simply reassign it, the UI will keep on using the old list.
    #preset_list.clear()
    index=0
    presets_dirty = False
    loaded = False

    cfg_path = os.path.dirname(__file__)+"/assets/hs2blender.json"
    try:
        fp=open(cfg_path, "r")
        cfg = json.load(fp)
        fp.close()
        waifus_path = cfg["waifus_path"]
        json_preset_map = cfg["presets"]
        #stored_json_preset_map = json_preset_map
        for x in json_preset_map:
            preset_map[int(x)]=json_preset_map[x]
            if isinstance(preset_map[int(x)], list):
                preset_map[int(x)] = convert_preset(preset_map[int(x)])
            elif isinstance(preset_map[int(x)], dict):
                preset_map[int(x)] = convert_preset_from_dict(preset_map[int(x)])
            #elif isinstance(preset_map[int(x)], str):
            #    v = json.loads(preset_map[int(x)])
            #    preset_map[int(x)] = convert_preset_from_dict(v)
            else:
                print("Unexpected preset type")
        loaded = True
    except:
        pass
    if not loaded:
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
                preset_map[index]=Preset(x[0], y[0], colors[0:3], colors[3:6])
                #preset_list.append((str(index), x[0], x[0], index))
                index+=1
        except:
            pass
    n = 0

    #for x in preset_map:
    #    if not "uuid" in preset_map[x]:
    #        preset_map[x]["uuid"] = str(uuid.uuid4())

    #for k in preset_map:
    #    #preset_map[index]=[x[0], y[0], colors[0:3], colors[3:6], None]
    #    #print(k, type(k), preset_map[k][0])
    #    preset_list.append((str(k), preset_map[k].name, preset_map[k]["uuid"], k))

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
        dump_dir = preset_map[x].get_path()
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

in_preset_select = False
def preset_update(self, context):
    global presets_dirty, preset_map, waifus_path

    if in_preset_select:
        return

    export_dir = bpy.context.scene.hs2rig_data.export_dir
    if export_dir != waifus_path:
        waifus_path = export_dir
        presets_dirty = True

    v = attributes.collect_mat_attributes()
    p = find_preset(hs2object())
    if p is not None:
        for x in v:
            p[x]=v[x]

def save_presets():
    global presets_dirty
    preset_update(None,None)

    cfg_path = os.path.dirname(__file__)+"/assets/hs2blender.json"

    cfg = {
    "waifus_path":waifus_path,
    "presets":{x:preset_map[x].as_dict() for x in preset_map},
    }
    #print(preset_map)
    s = json.dumps(cfg, indent=4)
    importer.save_with_backup(s, cfg_path)
    presets_dirty = False
    return

def delete_preset():
    global preset_map, presets_dirty
    id=bpy.context.scene.hs2rig_data.presets
    print("delete_preset", id)
    preset_map.pop(int(id))
    if int(id)-1 in preset_map:
        bpy.context.scene.hs2rig_data.presets = str(int(id)-1)

def add_new_preset(h):
    if h is None:
        return
    global preset_map, presets_dirty
    value = len(preset_map)
    s = bpy.context.scene.hs2rig_data.char_name
    preset_map[value] = Preset(s, h["dump_dir"], h["Eye color"][:], h["Hair color"][:])
    #preset_list.append((str(value), s, preset_map[value]["uuid"], value))
    h["preset_uuid"] = preset_map[value]["uuid"]
    preset_update(None,None)

def find_preset(h):
    if h is None:
        return None
    if not "preset_uuid" in h:
        return None
    for p in preset_map:
        if preset_map[p]["uuid"]==h["preset_uuid"]:
            return preset_map[p]
    return None

analyzer_report=''


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
          ('cf_J_Shoulder_R',-25,0,-55),
          ('cf_J_ArmUp00_L',135,5,-60),
          ('cf_J_ArmUp00_R',-155,0,-20),
          ('cf_J_ArmLow01_L',40,-150,0),
          ('cf_J_ArmLow01_R',-45,145,0),
            ]),
('Crawl', 'assets/crawling.txt'),
('Cute', 'assets/cutev1.txt'),
('Half5', 'assets/pose_half5.txt'),
('Half6', 'assets/pose_half6.txt'),
]

standard_pose_list_names = [(x[0],x[0],x[0]) for x in standard_pose_list]

def get_mouth_open(self):
#    arm = bpy.context.active_object
    h = hs2object()
    try:
        return h["mouth_open"]
    except:
        return 0.0

def set_mouth_open(self, val):
    h = hs2object()
    if h is None:
        return
    h["mouth_open"]=val
    for x in h.children:
        if x.type != 'MESH':
            continue
        if x.data.shape_keys is None:
            continue
        for y in ['k03_open2', 'k10_open2']:
            if y in x.data.shape_keys.key_blocks:
                x.data.shape_keys.key_blocks[y].value = val * 0.01

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

def standard_pose_get(self):
    try:
        return self['standard_pose']
    except:
        return 0

def standard_pose_select(self, value):
   print("standard_pose_select", self, value)
   self['standard_pose']=value
   set_fixed_pose(bpy.context, value)

injector_options=[
("Auto","Auto","Autodetect"),
("Yes","Yes","Attach"),
("No","No","Do not attach")
]


def get_attr(name):
    return attributes.get_attr(name)

def set_attr(name, x, store=True):
    global presets_dirty
    if store:
        current = int(bpy.context.scene.hs2rig_data.presets)
        if current in preset_map:
            if name=="Eye color":
                if preset_map[current].set_eye_color(x):
                    presets_dirty = True
            elif name=="Hair color":
                if preset_map[current].set_hair_color(x):
                    presets_dirty = True
            else:
                if (not name in preset_map[current]) or (preset_map[current][name] != x):
                    preset_map[current][name] = x
                    presets_dirty = True

    attributes.set_attr(name, x)

def get_default_attr(name):
    try:
        return attributes.get_default_attr(name)
    except:
        return None

def WrapProperty(prop, name, store=True, **kwargs):
    return prop(name=name,
        get=lambda s: get_attr(name), 
        set=lambda s,x: set_attr(name,x,store=store),
        update=lambda self, context: None,
        default=get_default_attr(name),
        **kwargs)

class hs2rig_props(PropertyGroup):
    #
    #   Plugin-wide settings
    #
    export_dir: StringProperty(
        name="Export directory",
        default='c:\\temp\\hs2\\export',
        description='Export directory',
        get=get_export_dir,
        set=set_export_dir,
        subtype="DIR_PATH",
    )
    presets: bpy.props.EnumProperty(items=get_preset_list,
            description="description",
            default=None
        )
    standard_poses: bpy.props.EnumProperty(items=standard_pose_list_names,
            name="Standard poses",
            description="description of poses",
            default=None,
            get=standard_pose_get,
            set=standard_pose_select
        )
    run_analyzer: BoolProperty(name="Analyzer", default=False, description="Analyzer")

    #
    #  Import configuration, set by the user in the import box
    #
    refactor: BoolProperty(name="Refactor armature", 
        default=True,
        description="When checked, the armature will be recalculated so that all body shape adjustments become part of the pose. "
        " It is slower and it sometimes fails, but it makes imported clothing and hair interchangeable between characters"
        )
    extend_safe: BoolProperty(name="Extend (safe)", default=True,
        description="Apply various enhancements to the mesh and the rig")
    extend_full: BoolProperty(name="Extend (full)", default=False,
        description="Apply aggressive enhancements to the mesh and the rig. Will alter the appearance")
    replace_teeth: BoolProperty(name="Replace teeth", default=True, description="Replace exported teeth with a known-good version")
    add_injector: EnumProperty(name="Add an injector", 
        items=injector_options,
        default="Auto", 
        description="Add a prefabricated injector and attempt to stitch it onto the mesh")
    add_exhaust: BoolProperty(name="Add an exhaust", default=True, description="Add a prefabricated exhaust port and attempt to stitch it onto the mesh")
    wipe: BoolProperty(name="Wipe scene before import", default=False,
        description="When checked, all existing objects will be deleted from the scene before the new character is added")

    #
    #  Character posing and appearance adjustment
    #
    #
    # There's only one system-wide instance of hs2rig_props.hair_color, because there seems to be no way to add it dynamically to the object.
    # It is only an interface object with no owned data; the actual hair color is stored as a custom property of the armature.
    # Ditto length, exhaust, etc.
    #
    char_name: WrapProperty(StringProperty, "Name")

    finger_curl_scale: FloatProperty(
        name="Finger curl", min=0, max=100,
        default=10, precision=1,
        description="Finger curl",
        get=get_finger_curl,
        set=set_finger_curl
    )
    mouth_open: FloatProperty(name="Mouth open", min=0, max=100, description="Mouth open", get=get_mouth_open, set=set_mouth_open)
    ik: WrapProperty(BoolProperty,'IK')
    hair_color: WrapProperty(FloatVectorProperty, "Hair color", subtype='COLOR', min=0.0, max=1.0)
    eye_color: WrapProperty(FloatVectorProperty, "Eye color", subtype='COLOR', min=0.0, max=1.0)
    skin_tone: WrapProperty(FloatVectorProperty, "Skin tone", subtype='COLOR', min=0.0, max=1.0)
    eagerness: WrapProperty(FloatProperty, "Eagerness", soft_min=0.0, soft_max=100.0, step=1)
    length: WrapProperty(FloatProperty, "Length", soft_min=0.0, soft_max=100.0, step=1)
    girth: WrapProperty(FloatProperty, "Girth", soft_min=0.0, soft_max=100.0, step=1)
    volume: WrapProperty(FloatProperty, "Volume", soft_min=0.0, soft_max=100.0, step=1)
    exhaust: WrapProperty(FloatProperty, "Exhaust", soft_min=0.0, soft_max=10.0, store=False)
    sheath: WrapProperty(BoolProperty, "Sheath")
    wet: WrapProperty(BoolProperty, "Wet", store=False)
    neuter: WrapProperty(BoolProperty, "Neuter", store=False)

    command: StringProperty(
        name="Command", 
        default="", 
        description=""
    )
 
    def execute(self, context):
        return {'FINISHED'}


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
    attributes.set_attr("IK", False)
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
    if "deformed_rig" in arm:
        deformed_rig = arm["deformed_rig"]
        for x in arm.pose.bones:
            if x.name in ['balls','stick_01','stick_02','stick_03','stick_04','tip_base','fskin_bottom','fskin_top','fskin_left','fskin_right','sheath']:
                continue
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
        arm = hs2object()
        if arm is not None:
            if context.scene.hs2rig_data.command == 'eye_shape':
                add_extras.eye_shape(arm, arm["body"], None)
            else:
                getattr(normalizer, context.scene.hs2rig_data.command)(arm, arm["body"])
        return {'FINISHED'}

class hs2rig_OT_reset_cust(Operator):
    bl_idname = "object.reset_customization"
    bl_label = "Reset shape to vanilla"
    bl_description = "Resets the character shape to the original export"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        h = hs2object()
        for p in preset_map:
            print(preset_map[p])
            if preset_map[p]["uuid"]==h["preset_uuid"]:
                importer.reset_customization(h)
                #armature.set_drivers(h)
        return {'FINISHED'}

class hs2rig_OT_load_cust(Operator):
    bl_idname = "object.load_from_customization"
    bl_label = "Load shape from preset"
    bl_description = "Loads the character shape from the preset"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        h = hs2object()
        p = find_preset(h)
        if p is not None:
            importer.load_customization_from_string(h, p.get("customization") or "")
            #armature.set_drivers(h)
        return {'FINISHED'}

class hs2rig_OT_save_cust(Operator):
    bl_idname = "object.save_to_customization"
    bl_label = "Save shape to preset"
    bl_description = "Saves the character shape to the preset"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        h = hs2object()
        s = importer.customization_string(h, "cf_N_height")
        print("New customization string", s)
        p = find_preset(h)
        print("Preset", p)
        if p is not None:
            p["customization"]=s
        return {'FINISHED'}

class hs2rig_OT_name_to_preset(Operator):
    bl_idname = "object.name_to_preset"
    bl_label = "Save name to preset"
    bl_description = "Saves the character name to the preset"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        print("save_name_to_preset")
        h = hs2object()
        p = find_preset(h)
        if p is not None:
            p.name = h["Name"]
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

class hs2rig_OT_load_preset_character(Operator):
    bl_idname = "object.load_preset_character"
    bl_label = "Load preset char"
    bl_description = "Load preset character"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print("trying to import...")
        preset = None
        uuid = None
        name = ""
        preset = preset_map[int(bpy.context.scene.hs2rig_data.presets)]
        eye_color = preset.eye_color
        hair_color = preset.hair_color
        uuid = preset["uuid"]
        name = preset.name
        arm=importer.import_body(preset.get_path(),
            refactor=context.scene.hs2rig_data.refactor,
            do_extend_safe=context.scene.hs2rig_data.extend_safe,
            do_extend_full=context.scene.hs2rig_data.extend_full,
            replace_teeth=context.scene.hs2rig_data.replace_teeth,
            add_injector=context.scene.hs2rig_data.add_injector,
            add_exhaust=context.scene.hs2rig_data.add_exhaust,
            wipe=context.scene.hs2rig_data.wipe,
            c_eye=eye_color,
            c_hair=hair_color,
            name=name,
            customization=preset.get("customization")
            )
        if uuid is not None:
            arm["preset_uuid"] = uuid
        bpy.context.scene.hs2rig_data.standard_poses="T"
        if preset is not None:
            attributes.push_mat_attributes(preset)
        return {'FINISHED'}

class DirSelector(Operator):
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty(subtype="DIR_PATH")
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class FileSelector(Operator):
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class hs2rig_OT_load(FileSelector):
    def execute(self, context):
        print("self.filepath", self.filepath, "self.flags", self.flags)
        load_pose(context.active_object.name, self.filepath, self.flags)
        return {'FINISHED'}

class hs2rig_OT_save(FileSelector):
    def execute(self, context):
        try:
            of=open(self.filepath,"w")
            dump_pose(context.active_object.name, of, self.flags)
            of.close()
        except:
            pass
        return {'FINISHED'}

class hs2rig_OT_load_fk(hs2rig_OT_load):
    bl_idname = "object.load_pose_fk"
    bl_label = "Load pose from file"
    bl_description = "Loads the character pose from the file"
    flags = 1

class hs2rig_OT_load_shape(hs2rig_OT_load):
    bl_idname = "object.load_pose_soft"
    bl_label = "Load shape from file"
    bl_description = "Loads the character shape from the file"
    flags = 2

class hs2rig_OT_load_all(hs2rig_OT_load):
    bl_idname = "object.load_pose_all"
    bl_label = "Load armature from file"
    bl_description = "Loads the character pose and shape from the file"
    flags = 7

class hs2rig_OT_save_fk(hs2rig_OT_save):
    bl_idname = "object.save_pose_fk"
    bl_label = "Save pose to file"
    bl_description = "Saves the character pose to the file"
    flags = 1

class hs2rig_OT_save_shape(hs2rig_OT_save):
    bl_idname = "object.save_pose_soft"
    bl_label = "Save shape to file"
    bl_description = "Saves the character shape to the file"
    flags = 2

class hs2rig_OT_save_all(hs2rig_OT_save):
    bl_idname = "object.save_pose_all"
    bl_label = "Save armature to file"
    bl_description = "Saves the character pose and shape to the file"
    flags = 3


class hs2rig_OT_import(DirSelector):
    bl_idname = "object.import"
    bl_label = "Import new dump"
    bl_description = "Import new dump"

    def execute(self, context):
        print("trying to import...")
        preset = None
        uuid = None
        eye_color = (0.0, 0.0, 0.8)
        hair_color = (0.8, 0.8, 0.5)
        s = self.filepath
        while len(s) and (s[-1]=='/' or s[-1]=='\\'):
            s=s[:-1]
        name = os.path.basename(s)
        while len(name) and (name[0].isdigit() or name[0]=='_'):
            name=name[1:]
        arm=importer.import_body(self.filepath,
            refactor=context.scene.hs2rig_data.refactor,
            do_extend_safe=context.scene.hs2rig_data.extend_safe,
            do_extend_full=context.scene.hs2rig_data.extend_full,
            replace_teeth=context.scene.hs2rig_data.replace_teeth,
            add_injector=context.scene.hs2rig_data.add_injector,
            add_exhaust=context.scene.hs2rig_data.add_exhaust,
            wipe=context.scene.hs2rig_data.wipe,
            c_eye=eye_color,
            c_hair=hair_color,
            name = name,
            customization = None
            )
        bpy.context.scene.hs2rig_data.standard_poses="T"
        return {'FINISHED'}

class hs2rig_OT_import_all(Operator):
    bl_idname = "object.import_all"
    bl_label = "Load all presets"
    bl_description = "Load all preset characters"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print("trying to import...")
        count = 0
        for value in preset_map:
            preset = preset_map[value]
            eye_color = preset.eye_color
            hair_color = preset.hair_color
            arm = importer.import_body(preset.get_path(),
                refactor=context.scene.hs2rig_data.refactor,
                do_extend_safe=context.scene.hs2rig_data.extend_safe,
                do_extend_full=context.scene.hs2rig_data.extend_full,
                replace_teeth=context.scene.hs2rig_data.replace_teeth,
                add_injector=context.scene.hs2rig_data.add_injector,
                add_exhaust=context.scene.hs2rig_data.add_exhaust,
                wipe=context.scene.hs2rig_data.wipe,
                c_eye=preset.eye_color,
                c_hair=preset.hair_color,
                name=preset.name,
                customization=preset.get("customization")
                )

            if arm is not None:
                arm.location = Vector([count, 0, 0])
                count+=1
            if "uuid" in preset_map[value]:
                arm["preset_uuid"] = preset_map[value]["uuid"]

            attributes.push_mat_attributes(preset_map[value])
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

class hs2rig_OT_select_export_dir(Operator):
    bl_idname = "object.select_export_dir"
    bl_label = "select_export_dir"
    bl_description = ""
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return {'FINISHED'} 


class hs2rig_OT_save_presets(Operator):
    bl_idname = "object.save_presets"
    bl_label = "Save presets"
    bl_description = "Save all presets"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        save_presets()
        return {'FINISHED'} 

class hs2rig_OT_add_new_preset(Operator):
    bl_idname = "object.add_new_preset"
    bl_label = "Add as a new preset"
    bl_description = "Save current entries as a new preset"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        add_new_preset(hs2object())
        return {'FINISHED'} 

class hs2rig_OT_delete_preset(Operator):
    bl_idname = "object.delete_preset"
    bl_label = "Delete preset"
    bl_description = "Delete current preset"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        delete_preset()
        return {'FINISHED'}

class hs2rig_OT_reset_skin_tone(Operator):
    bl_idname = "object.reset_skin_tone"
    bl_label = "Reset"
    bl_description = "Reset the skin to default export value"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        attributes.reset_skin_tone()
        return {'FINISHED'} 

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
            preset = find_preset(arm)
            box = layout.box()
            box.prop(context.scene.hs2rig_data, "standard_poses")
            row = layout.row(align=True)
            row.operator("object.toggle_clothing")
            row = layout.row(align=True)
            row.prop(context.scene.hs2rig_data, "finger_curl_scale", slider=True)
            row.prop(context.scene.hs2rig_data, "mouth_open", slider=True)
            if not context.scene.hs2rig_data.neuter:
                row.prop(context.scene.hs2rig_data, "exhaust")
            if arm.type == 'ARMATURE' and ('stick_01' in arm.pose.bones):
                if not context.scene.hs2rig_data.neuter:
                    row1 = layout.row(align=True)
                    row1.prop(context.scene.hs2rig_data, "eagerness")
                    row1.prop(context.scene.hs2rig_data, "length")
                    row2 = layout.row(align=True)
                    row2.prop(context.scene.hs2rig_data, "girth")
                    row2.prop(context.scene.hs2rig_data, "volume")
                row3 = layout.row(align=True)
                row3.prop(context.scene.hs2rig_data, "ik")
                row3.prop(context.scene.hs2rig_data, "neuter")
                if not context.scene.hs2rig_data.neuter:
                    row3.prop(context.scene.hs2rig_data, "wet")
                    row3.prop(context.scene.hs2rig_data, "sheath")
            else:
                row = layout.row(align=True)
                row.prop(context.scene.hs2rig_data, "ik")

            if analyzer_enabled:
                row = layout.row(align=True)
                row.prop(context.scene.hs2rig_data, "command")
                row.operator("object.execute_command")
        
            row = layout.row(align=True)
            box = layout.box()

            row = layout.row(align=True)
            row.operator("object.reset_customization")
            row = layout.row(align=True)
            op = row.operator("object.load_from_customization")
            op = row.operator("object.save_to_customization")
            if preset is None:
                row.enabled = False

            #box.prop(context.scene.hs2rig_data, "file_path")
            row = box.row(align=True)
            row.operator("object.load_pose_fk")
            row.operator("object.save_pose_fk")
            row = box.row(align=True)
            row.operator("object.load_pose_soft")
            row.operator("object.save_pose_soft")
            row = box.row(align=True)
            row.operator("object.load_pose_all")
            row.operator("object.save_pose_all")

            box = layout.box()
            row = box.row(align=True)
            row.prop(context.scene.hs2rig_data, "char_name")
            subbox = row.box()
            op = subbox.operator("object.name_to_preset")
            if preset is None:
                subbox.enabled = False
            row = box.row(align=True)
            row.prop(context.scene.hs2rig_data, "hair_color")
            row.prop(context.scene.hs2rig_data, "eye_color")
            row = box.row(align=True)
            row.prop(context.scene.hs2rig_data, "skin_tone")
            row.operator("object.reset_skin_tone")
            row = box.row(align=True)
            row.operator("object.add_new_preset")

        box = layout.box()
        box.label(text="System settings")
        box.prop(context.scene.hs2rig_data, "export_dir")
        #params=bpy.data.FileSelectParams.new()
        #box.operator("object.select_export_dir")
        box.prop(context.scene.hs2rig_data, "presets")
        row = box.row(align=True)
        #b = row.box()
        row.operator("object.reload_presets")
        row.operator("object.save_presets")
        row.operator("object.delete_preset")
        if len(preset_map)==0:
            row.enabled=False
        row = box.row(align=True)
        row2 = row.row(align=True)
        op = row2.operator("object.load_preset_character")
        row2.operator("object.import_all")
        if len(preset_map)==0:
            row2.enabled=False
        row.operator("object.import")

        if analyzer_enabled:
            row = box.row(align=True)
            row.prop(context.scene.hs2rig_data, "run_analyzer")

        row = box.row(align=True)
        row.prop(context.scene.hs2rig_data, "wipe")
        row.prop(context.scene.hs2rig_data, "refactor")
        if context.scene.hs2rig_data.refactor:
            row = box.row(align=True)
            row.prop(context.scene.hs2rig_data, "replace_teeth")
            row = box.row(align=True)
            row.prop(context.scene.hs2rig_data, "extend_safe")
            if context.scene.hs2rig_data.extend_safe:
                row.prop(context.scene.hs2rig_data, "extend_full")
            row = box.row(align=True)
            op=row.prop_menu_enum(context.scene.hs2rig_data, "add_injector")
            op=row.prop(context.scene.hs2rig_data, "add_exhaust")
        row = box.row(align=True)
        row.label(text=importer.last_import_status)
        if analyzer_enabled and context.scene.hs2rig_data.run_analyzer:
            analyzer.analyzer(hs2object())
            if len(analyzer.analyzer_report)>0:
                v=analyzer.analyzer_report.split('\n')
                for y in v:
                    row = box.row(align=True)
                    row.label(text=y)

addon_classes=[
HS2RIG_PT_ui, 

#hs2rig_OT_standard_posing,
hs2rig_OT_clothing,
hs2rig_OT_load_fk,
hs2rig_OT_load_shape,
hs2rig_OT_load_all,
hs2rig_OT_save_fk,
hs2rig_OT_save_shape,
hs2rig_OT_save_all,
hs2rig_OT_save_cust,
hs2rig_OT_load_cust,
hs2rig_OT_reset_cust,
hs2rig_OT_import,
hs2rig_OT_import_all,
hs2rig_OT_save_presets,
hs2rig_OT_reload_presets,
hs2rig_OT_add_new_preset,
hs2rig_OT_delete_preset,
hs2rig_OT_reset_skin_tone,
hs2rig_OT_name_to_preset,
hs2rig_OT_load_preset_character,
hs2rig_props,
hs2rig_OT_execute,
#hs2rig_OT_select_export_dir,
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
    last_preset = None
    bpy.types.Scene.hs2rig_data = PointerProperty(type=hs2rig_props)
    print("Registering...")
    import importlib
    importlib.reload(add_extras)
    importlib.reload(attributes)
    importlib.reload(importer)
    importlib.reload(armature)
    if analyzer_enabled:
        importlib.reload(analyzer)
    if normalizer_enabled:
        importlib.reload(normalizer)
    importlib.reload(solve_for_deform)
