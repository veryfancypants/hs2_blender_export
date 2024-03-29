import bpy
import mathutils
import os
import bmesh
import math
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy as np
from .importer import replace_mat, set_tex, set_bump, join_meshes, disconnect_link
import time
import random

from . import armature

from .attributes import set_attr

def clamp01(x):
    return max(0.0, min(1.0, x))

def find_nearest_vertices(body, subset1, subset2):
    cos = np.zeros([len(body.data.vertices)*3], dtype=np.float32)
    body.data.vertices.foreach_get("co", cos)
    cos = cos.reshape([-1,3])
    ys = cos[subset1].reshape([1,-1,3])
    xs = cos[subset2].reshape([-1,1,3])
    xy = xs-ys
    xy *= xy
    xy = np.sqrt(xy[:,:,0]+xy[:,:,1]+xy[:,:,2])
    return np.argmin(xy, axis=1)


def make_child_bone(arm, parent, name, offset, collection, rotation_mode='XYZ', 
        parent_head=True, tail_offset=None, copy='',
        inherit_scale=True):
    if name in arm.pose.bones:
        return
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.data.edit_bones.new(name)
    bone.parent = arm.data.edit_bones[parent]
    if parent_head:
        bone.head = arm.data.edit_bones[parent].head+offset
    else:
        bone.head = offset
    if tail_offset is None:
        bone.tail = arm.data.edit_bones[parent].tail+offset
    else:
        bone.tail = bone.head+tail_offset
    arm.data.collections[collection].assign(bone)
    arm.data.collections['Everything'].assign(bone)
    if not inherit_scale:
        bone.inherit_scale='NONE'
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones[name].rotation_mode='XYZ'
    try:
        arm["deformed_uncustomized_rig"][name]=arm.pose.bones[name].matrix_basis.copy()
    except:
        pass
    if "deformed_rig" in arm:
        arm["deformed_rig"][name]=arm.pose.bones[name].matrix_basis.copy()
    if copy!='':
        assert name[-1]=='R'
    if 'l' in copy:
        armature.copy_location(arm, name[:-1])
    if 's' in copy:
        armature.copy_scale(arm, name[:-1])
    if 'r' in copy:
        armature.copy_rotation(arm, name)


def get_weight(body, vertex, group):
    if isinstance(group, str):
        group = body.vertex_groups[group].index
    if isinstance(group, list) or isinstance(group, tuple):
        return sum([get_weight(body, vertex, x) for x in group])
    for g in body.data.vertices[vertex].groups:
        if g.group==group:
            return g.weight
    return 0.0

def set_weight(body, vertex, group, weight):
    if isinstance(group, str):
        group = body.vertex_groups[group].index
    for g in body.data.vertices[vertex].groups:
        if g.group==group:
            g.weight=weight
            return
    if group>=0:
        body.vertex_groups[group].add([vertex], weight, 'ADD')

def add_weight(body, vertex, group, weight):
    if isinstance(group, tuple) or isinstance(group, list):
        wts = [get_weight(body, vertex, g) for g in group]
        wtot = sum(wts)
        if wtot==0.0:
            for g,w0 in zip(group, wts):
                add_weight(body, vertex, g, weight/len(group))
        else:
            for g,w0 in zip(group, wts):
                add_weight(body, vertex, g, weight*w0/wtot)
        return

    if isinstance(group, str):
        group = body.vertex_groups[group].index
    for g in body.data.vertices[vertex].groups:
        if g.group==group:
            g.weight+=weight
            return
    body.vertex_groups[group].add([vertex], weight, 'ADD')

def vgroup(obj, name, min_wt=None):
    if min_wt is None:
        min_wt = 0.0
    if isinstance(name, list):
        ids = [obj.vertex_groups[vg].index for vg in name if vg in obj.vertex_groups]
        return [x for x in range(len(obj.data.vertices)) if any([(g.group==id and g.weight>min_wt) for g in obj.data.vertices[x].groups for id in ids])]

    if not name in obj.vertex_groups:
        return []

    id=obj.vertex_groups[name].index
    if min_wt is None:
        return [x for x in range(len(obj.data.vertices)) if id in [g.group for g in obj.data.vertices[x].groups]]
    else:
        return [x for x in range(len(obj.data.vertices)) if any([(g.group==id and g.weight>min_wt) for g in obj.data.vertices[x].groups])]


# Calls 'func' for each vertex in 'vg' (which is an index, a string, or a list of vertex groups), to calculate 'wt' (a value in 0 to 1 range).
# Assigns weight 'wt' to the newly created VG and reduces weights of all other VGs on that vertex, without changing their relative weights.
def create_functional_vgroup(body, name, vg, func, bm = None):
    if name in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups[name])
    new_group = body.vertex_groups.new(name=name)
    new_id  = new_group.index
    if bm is None:
        bm = bmesh.new()
        bm.from_mesh(body.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm_owned = True
    else:
        bm_owned = False
    lay = bm.loops.layers.uv['uv1']
    v = vgroup(body, vg)
    for x in v:
        uv = bm.verts[x].link_loops[0][lay].uv
        wt = func(uv=uv, vert=x, co=body.data.vertices[x].undeformed_co, norm=body.data.vertices[x].normal)
        if wt > 0:
            s = 0
            for g in body.data.vertices[x].groups:
                s += g.weight
            for g in body.data.vertices[x].groups:
                g.weight *= (1-wt)/s
            add_weight(body, x, new_id, wt)
    if bm_owned:
        bm.free()

# Similar to 'create_functional_vgroup', except that it reduces weights of _only_ vertex groups specified in 'vg'.
def split_vgroup(body, name, vg, func, bm = None):
    if not name in body.vertex_groups:
        body.vertex_groups.new(name=name)
    if isinstance(vg, list):
        old_id = [body.vertex_groups[x].index for x in vg]
    else:
        old_id = [body.vertex_groups[vg].index]
    new_id = body.vertex_groups[name].index
    if bm is None:
        bm = bmesh.new()
        bm.from_mesh(body.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm_owned = True
    else:
        bm_owned = False
    lay = bm.loops.layers.uv['uv1']
    v = vgroup(body, vg)
    for x in v:
        uv = bm.verts[x].link_loops[0][lay].uv
        wold = [get_weight(body, x, y) for y in old_id]
        frac = func(uv=uv, vert=x, co=body.data.vertices[x].undeformed_co, norm=body.data.vertices[x].normal)
        for k in range(len(old_id)):
            set_weight(body, x, old_id[k], wold[k]*(1.-frac))
        set_weight(body, x, new_id, sum(wold)*frac)
    if bm_owned:
        bm.free()

def create_functional_shape_key(body, name, vg, func, on=True, max=1.0, bm=None):
    if name in body.data.shape_keys.key_blocks:
        body.shape_key_remove(key=body.data.shape_keys.key_blocks[name])
    sk = body.shape_key_add(name=name)
    sk.interpolation='KEY_LINEAR'
    for x in range(len(body.data.vertices)):
        sk.data[x].co = body.data.shape_keys.key_blocks["Basis"].data[x].co
    if bm is None:
        bm = bmesh.new()
        bm.from_mesh(body.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm_owned = True
    else:
        bm_owned = False
    lay = bm.loops.layers.uv['uv1']

    if isinstance(vg, list) and isinstance(vg[0], int):
        v = vg
    else:
        v = vgroup(body, vg)

    for i, x in enumerate(v):        
        uv = bm.verts[x].link_loops[0][lay].uv if len(bm.verts[x].link_loops)>0 else (0,0)
        sk.data[x].co += func(uv=uv, vert=x, co=body.data.vertices[x].undeformed_co, norm=body.data.vertices[x].normal, set_id=i)
    body.data.shape_keys.key_blocks[name].value=0.
    body.data.shape_keys.key_blocks[name].slider_max=max
    if bm_owned:
        bm.free()


def sigmoid(x, x_full=None, x_min=None):
    if x_full is not None:
        if x_min is None:
            x /= x_full
        else:
            x = (x-x_full) / (x_min-x_full)
    elif x_min is not None:
        x /= x_min
    if x<0:
        return 1.
    if x>1:
        return 0.
    return 0.5*(math.cos(x*3.141526)+1.)

def bump(x, x0, x1, x2, shape='sigmoid'):
    if x0>x2:
        t = x0
        x0 = x2
        x2 = t
    if x<x0 or x>x2:
        return 0.0
    if x1 is None:
        x1 = (x0+x2)/2.
    if x<x1:
        x = (x-x1) / (x1-x0)
    else:
        x = (x-x1) / (x2-x1)
    if shape=='sigmoid':
        return 0.5*(math.cos(x*3.141526)+1.)
    else:
        return math.cos(x*3.141526/2.)

def interpolate(y1, y2, x1, x2, x):#1, 2*strength, 1, 1.15, hpos_ext)
    if x1>x2:
        t=y1
        y1=y2
        y2=t
        t=x1
        x1=x2
        x2=t
    if x<=x1:
        return y1
    elif x>=x2:
        return y2
    else:
        return y1 + (y2-y1) * (x-x1) / (x2-x1)


def d2(x,y):
    return (x[0]-y[0])*(x[0]-y[0])+(x[1]-y[1])*(x[1]-y[1])

def curve_find_nearest(curve, v, debug=False):
    index = 0
    for j in range(1, len(curve)):
        if d2(curve[j],v)<d2(curve[index],v):
            index=j
    p1 = Vector(curve[index])
    p2 = Vector(curve[index])
    frac1 = index
    frac2 = index
    t1 = (curve[index][0]-curve[index-1][0], curve[index][1]-curve[index-1][1]) if index>0 else (curve[index+1][0]-curve[index][0], curve[index+1][1]-curve[index][1])
    t2 = t1
    if debug:
        print("curve_find_nearest", v, index, curve[index])
    if index>0:
        p1_, frac1_ = mathutils.geometry.intersect_point_line(Vector(v), Vector(curve[index][:2]), Vector(curve[index-1][:2]))
        if debug:
            print(Vector(v), Vector(curve[index][:2]), Vector(curve[index-1]), "=>", p1_, frac1_)
        if frac1_>=0 and frac1_<1.0:
            p1 = p1_
            frac1 = index-frac1_
            t1 = (curve[index][0]-curve[index-1][0], curve[index][1]-curve[index-1][1])
    if index+1<len(curve):
        p2_, frac2_ = mathutils.geometry.intersect_point_line(Vector(v), Vector(curve[index][:2]), Vector(curve[index+1][:2]))
        if debug:
            print(Vector(v), Vector(curve[index][:2]), Vector(curve[index+1][:2]), "=>", p2_, frac2_)
        if frac2_>=0 and frac2_<1.0:
            p2 = p2_
            frac2 = index+frac2_
            t2 = (curve[index+1][0]-curve[index][0], curve[index+1][1]-curve[index][1])
    if debug:
        print("Distances", d2(p1,v), d2(p2,v))
    if d2(p1,v)<d2(p2,v):
        p,t,frac = p1,t1,frac1
    else:
        p,t,frac = p2,t2,frac2
    side = (p[0]-v[0])*t[1] - (p[1]-v[1])*t[0]
    dist = math.sqrt((p[0]-v[0])*(p[0]-v[0])+(p[1]-v[1])*(p[1]-v[1]))
    return p,t,frac,side,dist

def curve_interp(curve, x, xsymm = False, cubic=False, debug=False):
    if debug:
        print(curve, x)
    if xsymm and x>0.500:
        x = 0.500 - (x-0.500)

    if isinstance(curve[0], float):
        if x<=0:
            return curve[0]
        if x>=len(curve)-1:
            return curve[-1]
        k = int(math.floor(x))
        return curve[k] + (curve[k+1]-curve[k]) * (x-k)

    if x<=curve[0][0]:
        return curve[0][1]
    if x>=curve[-1][0]:
        return curve[-1][1]
    for k in range(len(curve)-1):
        if x>=curve[k][0] and x<curve[k+1][0]:
            if debug:
                print(x, curve[k][0], curve[k+1][0], curve[k][1], curve[k+1][1])
            return interpolate(curve[k][1], curve[k+1][1], curve[k][0], curve[k+1][0], x)


def weighted_center(body, name):
    id=body.vertex_groups[name].index
    mesh=body.data
    vs=vgroup(body, name)
    s=Vector()
    wt=0.0
    for x in vs:
        for y in mesh.vertices[x].groups:
            if y.group==id:
                s+=mesh.vertices[x].co*y.weight
                wt+=y.weight
    return s*(1.0/wt)

#
#
#  NEW SHAPE KEYS
#
#

def eye_shape(arm, body, bm, on=True):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    #if 'Eye shape' in body.data.shape_keys.key_blocks:
    #    body.shape_key_remove(key=body.data.shape_keys.key_blocks['Eye shape'])
    if not 'cf_J_Eye02_s_R' in body.vertex_groups:
        return

    eyeball = vgroup(body, 'cf_J_eye_rs_R', 0.5)
    #sk = body.shape_key_add(name='Eye shape')
    #sk.interpolation='KEY_LINEAR'
    #for x in range(len(body.data.vertices)):
    #    sk.data[x].co = body.data.shape_keys.key_blocks["Basis"].data[x].co

    eyeball_center_x = sum([body.data.vertices[y].co.x for y in eyeball])/len(eyeball)
    eyeball_center_y = sum([body.data.vertices[y].co.y for y in eyeball])/len(eyeball)
    eyeball_center = Vector([eyeball_center_x,eyeball_center_y,0])
    #print("Eyeball center:", eyeball_center)

    #if 'Eye near' in body.vertex_groups:
    #    body.vertex_groups.remove(body.vertex_groups["Eye near"])
    #body.vertex_groups.new(name="Eye near")

    lower_lid_low_curve=[
    (0.383, 0.488),
    (0.408, 0.493),
    (0.441, 0.516),
    ]
    lower_lid_top_curve=[
    (0.383, 0.518),
    (0.441, 0.518)
    ]
    id01l = body.vertex_groups['cf_J_Eye01_s_L'].index
    id02l = body.vertex_groups['cf_J_Eye02_s_L'].index
    id04l = body.vertex_groups['cf_J_Eye04_s_L'].index
    id01r = body.vertex_groups['cf_J_Eye01_s_R'].index
    id02r = body.vertex_groups['cf_J_Eye02_s_R'].index
    id04r = body.vertex_groups['cf_J_Eye04_s_R'].index

    eye_soft = vgroup(body, ['cf_J_Eye01_s_R','cf_J_Eye02_s_R','cf_J_Eye03_s_R','cf_J_Eye04_s_R',
        'cf_J_Eye01_s_L','cf_J_Eye02_s_L','cf_J_Eye03_s_L','cf_J_Eye04_s_L'])

    nearest_eye_verts = find_nearest_vertices(body, eyeball, eye_soft)
    print(len(nearest_eye_verts), len(eye_soft))

    def formula(vert, co, norm, uv, set_id, **kwargs):#for x in set(list(v)):
        x=vert
        sign = -1 if co[0]>0 else 1

        if co[0]>0:
            co=Vector((co[0]*-1., co[1], co[2]))
        #y = min(eyeball, key=lambda z: (co-body.data.vertices[z].co).length)
        y = eyeball[nearest_eye_verts[set_id]]
        r = co-body.data.vertices[y].co
        n = body.data.vertices[y].normal
        dot = n.dot(r)
        effect = Vector([0,0,0])

        d = body.data.vertices[x].normal.dot(n)

        # if we are <0.01 from eyeball surface and <0.10 from the nearest eyeball vertex, 
        # push the vertex perpendicular to eyeball surface, tucking it under the eyelid
        r_range = 0.010
        if r.length<0.10 and dot<=0.010:
            effect = body.data.vertices[x].normal.copy()
            effect -= n*d
            effect.normalize()
            effect *= - sigmoid(d, 0.50, 1.0)
            effect *= interpolate(0.0075, 0, 0.0, r_range, dot)
            effect[0] *= sign

        """
        # pull back the inner corner of the lower eyelid, forming a crease at 45 degree angle
        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        if uv[0]>=0.383 and uv[0]<=0.441 and uv[1]<0.518:
            lower_lid_fold = curve_interp(lower_lid_low_curve, uv[0])
            w_x = bump(uv[0], 0.383, 0.408, 0.441, shape='cos')
            w_y = max(0, 1.-abs(uv[1]-lower_lid_fold)/(0.518-lower_lid_fold))
            effect[2] += -0.01*w_x*w_y
        """
        return effect

    create_functional_shape_key(body, 'Eye shape', eye_soft, formula, on = on, bm = bm)

def tweak_nose(arm, body, bm, on):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    #bpy.ops.object.mode_set(mode='EDIT')
    if not 'cf_J_Nose_tip' in body.vertex_groups:
        return

    curve = [
        (0.500, 0.402, 0.0, 1.0, -1),
        (0.465, 0.401, 0.2, 1.0, -1),
        (0.453, 0.411, 0.6, 0.6, -1),
        (0.450, 0.420, 1.0, 0.0, -1),
        (0.455, 0.435, 1.0, -0.5, -1),
        (0.457, 0.441, 0.7, -0.8, -1),
        (0.463, 0.448, 0.5, -1.0, -1),
        (0.472, 0.451, 0.5, -1.0, -1),
        (0.480, 0.445, 0.5, -1.0, -1),
    ]

    normals_x = [x[2] for x in curve]
    normals_y = [x[3] for x in curve]

    def formula(co, vert, uv, norm, **kwargs):
        sign = 1 if uv[0]<0.5 else -1
        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        pos, t, coord, side, dist = curve_find_nearest(curve, uv, debug=(vert==21185 or vert==32309))
        n = Vector([curve_interp(normals_x, coord)*sign, curve_interp(normals_y, coord), -1])
        n.normalize()
        effect = n * sigmoid(dist, 0, 0.01) * 0.008
        return effect

    create_functional_shape_key(body, 'Nostril pinch', ['cf_J_Nose_tip','cf_J_Nose_t','cf_J_NoseBase_s'], formula, max=2.0)

def add_mouth_blendshape(body, bm):
    if not 'cf_J_CheekLow_L' in body.vertex_groups: # custom head
        return 
    if not 'cf_J_Mouthup' in body.vertex_groups: # custom head
        return 

    cheek=vgroup(body, 'cf_J_CheekLow_L')
    mlow = vgroup(body, 'cf_J_MouthLow')
    mhigh = vgroup(body, 'cf_J_Mouthup')
    mcav = vgroup(body, 'cf_J_MouthCavity')

    # approximate location of the left mouth corner
    mcorn=weighted_center(body, 'cf_J_Mouth_L')
    mcorn[0]+=0.02

    # center of left cheek
    mcent=mcorn.copy()
    mcent[0]=0
    #ccent=0.5*(weighted_center('cf_J_CheekLow_L')+weighted_center('cf_J_CheekUp_L'))
    ccent=weighted_center(body, 'cf_J_CheekLow_L')

    # draw the line from mouth corner to cheek center, and continue it for the same distance
    ccorn=mcorn + (ccent-mcorn)*2.0

    mesh=body.data

    #find the nearest vertex to that point
    ccorn_nearest=mesh.vertices[0].co
    for x in mesh.vertices:
        if (x.co-ccorn).length<(ccorn_nearest-ccorn).length:
            ccorn_nearest=x.co
    ccorn=ccorn_nearest
    
    ccent=(ccorn+mcorn)*0.5
    vmc=ccent-mcorn
    yneg_cutoff=-(mcent-mcorn).dot(vmc)/(vmc.length*vmc.length)

    ccent=(mcorn+ccorn)*0.5
    vmc=ccent-mcorn
    vmm=mcorn-mcent

    curve=[
    (0.329, 0.424),
    (0.394, 0.432),
    (0.435, 0.447),
    (0.486, 0.490),
    ]

    def formula(vert, co, uv, norm, **kwargs):
        x=vert
        if get_weight(body, x, 'cf_J_MouthCavity') > 0.2:
            return Vector([0,0,0])
        smult = Vector([-1 if co[0]<0 else 1, 1, 1])
        #v = body.data.vertices[x]

        # UV coordinates of the lip-cheek line
        curve2=[
        (0.284, 0.426),
        #(0.354, 0.429),
        (0.424, 0.332),
        ]
        if uv[0]>0.500:
            uv = (1.0-uv[0], uv[1])

        fold = curve_interp(curve, uv[1])

        # 'y': horizontal(ish) coordinate
        #-1 at lip center
        # 0 at lip corner
        # 1 at cheek center
        # 2 at the furthest deformed point (somewhere below eye corner)

        if uv[0]<fold:
            y = (fold-uv[0]) / 0.150
        else:
            y = (fold-uv[0]) / (0.500-fold)
        if y>2.0:
            return Vector([0,0,0])

        lip_id = 1.0 if ((uv[1]>0.335) or (uv[1]>0.330 and norm[1]<0)) else -1.0

        nose_curve=[
        (0.432, 0.444),
        (0.452, 0.404),
        (0.500, 0.393),
        ]
        if lip_id > 0:
            wy_neg = sigmoid(uv[1], interpolate(0.352, 0.371, 0.432, 0.500, uv[0]), curve_interp(nose_curve, uv[0]))
        else:
            wy_neg = sigmoid(uv[1], interpolate(0.332, 0.308, 0.432, 0.500, uv[0]), 0.285)
        bump_range_curve=[
        (0.0, 0.1),
        (0.5, 0.2),
        (2.0, 0.2),
        ]
        wy_pos = sigmoid(abs(uv[1]-curve_interp(curve2, uv[0]))/curve_interp(bump_range_curve, y))

        wy = interpolate(wy_neg, wy_pos, -0.25, 0.25, y)

        stretch_dir = vmc*smult
        stretch_dir[1] *= 2.+bump(y,-1.0,0,1.0) #interpolate(2,4,0,0.5,y)
        effect = 0.2*stretch_dir*max(0.0, 1.0-abs(y))*wy
        if vert==12986 or vert==12982:
            print(vert, uv, y, wy, effect)
        #set_weight(body, vert, vg.index, clamp01(y+0.5))
        if y>0.0:
            #  for positive y (cheek), we also displace the vertex away from the face,
            # trying to create a 'bulge' right next to the lip corner.
            if not (x in mcav):
                norm = Vector([co[0], 0, co[2]])
                norm.normalize()
                tfun = (math.sqrt(max(0.0,y))*0.03*(y-2)*(y-2)) # - 0.25*sigmoid(abs(y), 0, 0.2))
                effect += norm*tfun*wy
        else:
            # positive if in front of line connecting lip corners
            fd=(co[2]-mcorn[2])
            if fd>0:
                # pull lip centers toward teeth
                effect += Vector([0,0,-0.5*(fd*fd)*wy*(-y)])

                # pull upper lip up, lower lip down
                
                # and pull centers of both lips up (otherwise we end up with a sharp crease in the center)
                # (this effect stops at the upper border of the upper lip)
                center_pull = 0.02*y*y*wy * sigmoid(uv[1], 0.332, 0.371)

                effect += Vector([0, 0.005*wy*(-y)*lip_id + center_pull, 0])
        return effect

    create_functional_shape_key(body, 'better_smile', ['cf_J_MouthBase_s','cf_J_MouthLow','cf_J_Mouthup','cf_J_CheekLow_L','cf_J_CheekLow_R',
        'cf_J_CheekUp_L','cf_J_CheekUp_R'], formula, on=False, bm=bm)

def adams_apple_delete(arm, body, bm):
    def formula(uv, **kwargs):
        if uv[0]>=0.115 and uv[0]<=0.135 and uv[1]>=0.970 and uv[1]<=0.991:
            return Vector([0,0,-0.02-0.02*bump(uv[1],0.970,0.980,0.990)])
        return Vector([0,0,0])
    create_functional_shape_key(body, 'Adams apple delete', ['cf_J_Neck_s'], formula, on=False, bm=bm)


# Pushes the flesh between the upper lip and the nose smoothly toward the skull, creating a trough.
def upper_lip_shapekey(arm, body, bm, on=True):
    def formula(uv, norm, **kwargs):
        curve=[
        (0.442,0.352),
        (0.485,0.371),
        ]
        wx = sigmoid(uv[0],0.470,0.440) * sigmoid(uv[0], 0.530, 0.560)
        effect1 = wx * bump(uv[1], curve_interp(curve, uv[0], xsymm=True), None, 0.399, shape='cos') * Vector([0, -0.01, -0.01])
        return effect1
    boy = (body['Boy']>0.0)
    create_functional_shape_key(body, 'Upper lip trough', ['cf_J_Mouthup','cf_J_MouthBase_s_s'], formula, on = on and (not boy), bm = bm)

# Smoothly arches the lips
def lip_arch_shapekey(arm, body, bm, on=True):
    boy = (body['Boy']>0.0)

    # There are only a few rows of verts in the lips, 
    # and their locations are slighly different for M an F meshes
    push_curve=[
    (-2.8, 0),
    (-2.4, -0.4),
    (-2, -1),
    (-1.5, -2),
    (-1, -1.5),
    (-0.54, -1.5),
    (-0.11, -1.0),
    (-0.001, -1.0),
    (0.001, -1.8),
    (0.58, -1.5),
    (1.0, -0.6),
    (1.15, 0),
    (1.29, 0),
    (1.43, 0),
    (1.56, 0)
    ]
    spread_curve_f = [
    (-2.2, 0),
    (-1.8, 0.6),
    (-1.5, 1),
    (-1.2, 1.2),
    (-0.11, 1.2),
    (-0.035, 0.6),
    (-0.001, 0.0),
    (0.000, 0.0),
    (0.001, 1.5),
    (0.040, 2.2),
    (0.084, 2.2),
    (0.35, 2.2),
    (0.58, 1.8),
    (0.76, 1.8),
    (1.0, 2.5),
    (1.15, 2.25),
    (1.29, 1.6),
    (1.43, 1.2),
    (1.56, 0.8),
    (2.0, 0.0),
    ]
    spread_curve_m = [
    (-1.8, 0),
    (-1.5, 1),
    (-1.2, 1.3),
    (-1.0, 1.3),
    (-0.80, 1.3),
    (-0.506, 1.5),
    (-0.035, 1.7),
    (-0.001, 2.0),

    (0.001, 2.0),
    (0.02, 2.2),
    (0.08, 2.4),
    (0.28, 2.2),
    (0.58, 2.2),
    (0.78, 2.2),
    (1.0, 2.0),
    (1.15, 1.6),
    (1.29, 1.0),
    (1.43, 0.4),
    (1.56, 0.0),
    ]
    spread_curve = spread_curve_m if boy else spread_curve_f
    # upper border of the upper lip
    curve_upper=[
    (0.432,0.340),
    (0.450,0.352),
    (0.485,0.371),
    ]
    curve_lower=[
    # lower border of the lower lip
    (0.443,0.315),
    (0.456,0.310),
    (0.472,0.308),
    (0.500,0.308),
    ]

    def formula(vert, uv, norm, **kwargs):
        # The effect is at full strength in the center, at zero above lip corners
        wx = bump(uv[0],0.434,None,0.566,shape='cos')
        upper = (uv[1]>0.335) or (uv[1]>0.330 and norm[1]<0)
        if upper: 
            center = curve_interp(curve_upper, uv[0], xsymm = True)
            y_pos = max(0.001, (uv[1]-0.332)/(center-0.332))
            #if y_pos<1.0:
            #   set_weight(body, vert, vgl.index, y_pos)
            #else:
            #set_weight(body, vert, vgl.index, y_pos*0.1)
        else:
            center = curve_interp(curve_lower, uv[0], xsymm = True)
            y_pos = min(-0.001, (uv[1]-0.330)/(0.330-center))
            #set_weight(body, vert, vgl.index, max(0, -y_pos*0.1))
        #set_weight(body, vert, vglx.index, wx)
        return wx*Vector([0, 0.01*curve_interp(spread_curve, y_pos), 0.01*curve_interp(push_curve, y_pos)]) + Vector([0, 0, 0.0075*(bump(uv[0],0.432,None,0.500)+bump(uv[0],0.500,None,0.568)) * bump(y_pos, -4.0, -2.0, 0.0)])
    create_functional_shape_key(body, 'Lip arch', ['cf_J_Mouthup','cf_J_MouthLow', 'cf_J_ChinTip_s', 'cf_J_MouthBase_s_s'], formula,
            max=2.0, on=on and not boy, bm = bm)

def eyelid_crease(arm, body, bm, on=True):
    curve_upper = [
    (0.338,0.5590),
    (0.349,0.5626),
    (0.359,0.5655),
    (0.369,0.5676),
    (0.380,0.5689),
    (0.391,0.5687),
    (0.403,0.5668),
    (0.414,0.5639),
    (0.424,0.5591),
    (0.433,0.5533),
    (0.439,0.5447),
    ]
    def formula(uv, **kwargs):
        if uv[0]>0.5:
            uv=(1-uv[0],uv[1])
        if uv[0]<curve_upper[0][0] or uv[0]>=curve_upper[-1][0]:
            return Vector([0.0, 0.0, 0.0])
        if uv[0]<curve_upper[1][0]:
            wx = sigmoid(uv[0], curve_upper[1][0], curve_upper[0][0])
        elif uv[0]>curve_upper[-2][0]:
            wx = sigmoid(uv[0], curve_upper[-2][0], curve_upper[1][0])
        else:
            wx=1.0
        ynear=curve_interp(curve_upper,uv[0])
        wy = bump(uv[1], ynear-0.002, ynear, ynear+0.002)
        return Vector([0,0,-wx*wy*0.02])

    create_functional_shape_key(body, 'Eyelid crease', ['cf_J_Eye02_s_L','cf_J_Eye02_s_R'], formula, on=on, bm=bm)


def forehead_flatten(arm, body, bm, on=True):
    if not "cf_J_FaceUp_tz" in body.vertex_groups:
        return
    ftz_id = body.vertex_groups["cf_J_FaceUp_tz"].index
    def formula(uv, vert, norm, co, **kwargs):
        #w = get_weight(body, vert, ftz_id)
        w = min(1.0, 2*abs(co[0])-0.2)*0.06
        w *= bump(uv[1], 0.580, 0.620, 0.90)
        w *= sigmoid(norm[2], 1.0, 0.2)
        return Vector([0,0,w])

    create_functional_shape_key(body, 'Forehead flatten', ['cf_J_FaceUp_tz','cf_J_FaceUpFront_ty'], formula, on=on, bm=bm)

def temple_depress(arm, body, bm, on=True):
    def formula(uv, **kwargs):
        if uv[0]>0.500:
            uv=(1-uv[0], uv[1])
            sign = -1.0
        else:
            sign = 1.0
        # Push vertices on the temple inward, creating a depression
        r=Vector(uv)-Vector([0.253,0.585])
        r[1]*=0.5

        # Pull the outer edge of the eye socket outward
        r2 = Vector(uv)-Vector([0.316, 0.540])
        if r2[1]<0.0:
            r2[1]=min(0.0, r2[1]+0.05)
        r2[1]*=0.5
        return (sigmoid(r.length, 0, 0.08)-sigmoid(r2.length,0,0.025)*0.5) * Vector([0.025*sign, 0, 0])

    create_functional_shape_key(body, 'Temple depress', ['cf_J_FaceUp_tz','cf_J_CheekUp_L','cf_J_CheekUp_R'], formula, on=on, bm = bm)

def jaw_soften(arm, body, bm, on=True):
    curve_m=[
    (0.223, 0.244),
    (0.326, 0.213),
    (0.418, 0.218),
    (0.500, 0.224)
    ]
    curve_f=[
    (0.223, 0.282),
    (0.326, 0.258),
    (0.418, 0.230),
    (0.500, 0.230)
    ]
    curve = curve_m if body["Boy"]>0 else curve_f
    def formula(uv, vert, norm, co, **kwargs):
        pos = uv[1] - curve_interp(curve, uv[0], xsymm=True)
        if uv[0]>0.5:
            uv=(1-uv[0],uv[1])
        effect = bump(pos, -2*width, 0, width, shape='cos') * (1. + bump(uv[0], 0.43, 0.46, 0.49, shape='cos')) * sigmoid(uv[0], 0.225, 0.150)
        return norm * -0.01 * effect
    width = 0.035
    create_functional_shape_key(body, 'Jaw soften', ['cf_J_Chin_rs', 'cf_J_ChinLow','cf_J_ChinFront_s'], formula, on=False, bm=bm)
    width = 0.060
    create_functional_shape_key(body, 'Jaw soften more', ['cf_J_Chin_rs', 'cf_J_ChinLow','cf_J_ChinFront_s'], formula, on=on, bm=bm)

# Explicitly subdivide the mesh before trying to build new shape keys.
# Necessary to produce good quality shape keys in sensitive areas (e.g. around the nose).
def subdivide(arm, body):
    if len(body.data.vertices)>60000:
        return
    t1 = time.time()
    # None of the 'direct' subdivision methods (bpy.ops.mesh.subdivide and bmesh.ops.subdivide_edges) do a good job subdividing
    # a mesh with weight groups.
    # It's not possible to simply apply the subdivision surface modifier to a mesh with shape keys.
    # It is possible to make copies of original mesh and apply subdivision modifiers on each,
    # but it's very slow.
    # This is a simple way to get around all the restrictions and get the job done fairly quickly.
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body

    for key in body.data.shape_keys.key_blocks:
        key.value=0.0

    dups={}
    n=0

    for mod in body.modifiers:
        if mod.type=='ARMATURE':
            mod.show_viewport = False

    subsurf = None
    for mod in body.modifiers:
        if mod.type=='SUBSURF':
            subsurf = mod
            break

    if subsurf is None:
        subsurf = body.modifiers.new("subsurf", "SUBSURF")
    subsurf.levels = 1
    subsurf.render_levels = 1
    # Subdiv time (Orange2):
    # Simple: 14.8 s
    #   No "Optimal" (show_only_control_edges=False): 14.8 s
    #   use_limit_surface=False: 9.1 s
    #   uv_smooth='NONE': 12.0 s
    #   use_apply_on_spline = True: 14.7 s
    #   use_limit_surface=False and uv_smooth='NONE': 9.8 s
    # Catmull-Clark + limit_surface: 56 s
    # Catmull-Clark + no limit_surface: 9 s
    subsurf.subdivision_type = 'CATMULL_CLARK'
    subsurf.use_limit_surface = False
    subsurf.show_viewport = True

    bpy.ops.object.modifier_move_to_index(modifier="subsurf", index=0)
    bpy.ops.object.duplicate()
    body_copy = bpy.context.view_layer.objects.active 
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    bpy.ops.object.modifier_apply(modifier="subsurf")
    sk = body.shape_key_add(name="Basis")
    for key in body_copy.data.shape_keys.key_blocks:
        if key.name=='Basis':
            continue
        bpy.context.view_layer.objects.active = body_copy
        s=0
        for k in body_copy.data.shape_keys.key_blocks:
            k.value = 1.0 if k.name==key.name else 0.0
            s+=k.value
        depsgraph = bpy.context.evaluated_depsgraph_get()
        dup = body_copy.evaluated_get(depsgraph)
        #bpy.qwerty()
        sk = body.shape_key_add(name=key.name)
        dup.data.vertices.update()
        sk.interpolation='KEY_LINEAR'
        coords = np.zeros([len(body.data.vertices)*3], dtype=np.float32)
        dup.data.vertices.foreach_get("co", coords)
        sk.data.foreach_set("co", coords)

    bpy.data.objects.remove(body_copy)
    bpy.context.view_layer.objects.active = body

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    for i, slot in enumerate(body.material_slots):
        if slot.material in [body["eyelash_mat"], body["eye_mat"], body["eyeshadow_mat"]]:
            body.active_material_index = i
            bpy.ops.object.material_slot_select()
    eye_mask = [False]*len(body.data.vertices)
    bpy.ops.object.mode_set(mode='OBJECT')
    body.data.vertices.foreach_get("select", eye_mask)

    #spine01 = vgroup(body, 'cf_J_Spine01_s')
    #for x in spine01:
    #    if (body.data.vertices[x].co-Vector([0, 11.54, 0.67])).length < 0.30:
    #        eye_mask[x] = True

    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    def should_dissolve(x):
        # Don't subdivide eyes and eyelashes
        if eye_mask[x]:
            return True
        co = bm.verts[x].co
        # Preserve detail in the face
        if co[1]>=15.45 and co[2]>0.0:
            return False
        # Keep subdivision of the navel
        if (co-Vector([0, 11.54, 0.67])).length < 0.30:
            return False
        # Keep hands
        if abs(co[0])>6.0:
            return False
        # Keep toes
        if co[1]<0.5 and co[2]>0.6:
            return False
        # Dissolve everything else
        return True


    rank_3_verts = [bm.verts[x] for x in range(len(bm.verts)) if should_dissolve(x) and len(bm.verts[x].link_edges)==3]
    # dissolve rank 3 verts
    bmesh.ops.dissolve_verts(bm, verts=rank_3_verts)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    rank_2_verts = [x for x in bm.verts if len(x.link_edges)==2]
    # dissolve rank 2 verts
    bmesh.ops.dissolve_verts(bm, verts=rank_2_verts)
    bm.to_mesh(body.data)
    bm.free()

    for mod in body.modifiers:
        if mod.type=='ARMATURE':
            mod.show_viewport = True

    t2 = time.time()
    print("Subdivision done in %.3f s" % (t2-t1))

def add_shape_keys(arm, body, on):
    #bpy.qwerty()
    t1=time.time()
    t0=t1
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm_owned = True
    # these are off by default:
    # Smile shape key
    add_mouth_blendshape(body, bm)
    t2=time.time()
    print("Mouth: %.3f s" % (t2-t1))
    t1=t2
    if body['Boy']>0:
        adams_apple_delete(arm, body, bm)
    # these are on by default (possibly depending on gender) unless "Extend" is off:
    tweak_nose(arm, body, bm, on=on)
    t2=time.time()
    print("Nose: %.3f s" % (t2-t1))
    t1=t2
    eye_shape(arm, body, bm, on=on)
    t2=time.time()
    print("Eye: %.3f s" % (t2-t1))
    t1=t2
    eyelid_crease(arm, body, bm, on=on)
    t2=time.time()
    print("Eyelid: %.3f s" % (t2-t1))
    t1=t2
    upper_lip_shapekey(arm, body, bm, on=on)
    t2=time.time()
    print("Upper lip: %.3f s" % (t2-t1))
    t1=t2
    lip_arch_shapekey(arm, body, bm, on=False)
    t2=time.time()
    print("Lip arch: %.3f s" % (t2-t1))
    t1=t2
    temple_depress(arm, body, bm, on=on)
    t2=time.time()
    print("temple_depress: %.3f s" % (t2-t1))
    t1=t2
    forehead_flatten(arm, body, bm, on=on)
    t2=time.time()
    print("forehead_flatten: %.3f s" % (t2-t1))
    t1=t2
    jaw_soften(arm, body, bm, on=False)
    t2=time.time()
    print("jaw_soften: %.3f s" % (t2-t1))
    t1=t2
    nasolabial_crease(arm, body, bm)
    bm.free()
    t2=time.time()
    print("%.3f s to add shape keys" % (t2-t0))
#
#
#  MODS
#
#


def get_or_create_id(x, name):
    if not name in x.vertex_groups:
        x.vertex_groups.new(name=name)
    return x.vertex_groups[name].index

def repaint_mouth_cavity(x):
    chin_id = get_or_create_id(x, 'cf_J_Chin_rs')
    mouth_id = get_or_create_id(x, 'cf_J_MouthCavity')
    mouthlow_id = get_or_create_id(x, 'cf_J_MouthLow')
    mouth2_id = get_or_create_id(x, 'cf_J_MouthBase_s')
    if 'cf_J_FaceLow_s_s' in x.vertex_groups:
        face_id = get_or_create_id(x, 'cf_J_FaceLow_s_s')
    else:
        face_id = get_or_create_id(x, 'cf_J_FaceLow_s')

    v=vgroup(x, 'cf_J_MouthCavity')
    v2=vgroup(x, 'cf_J_MouthBase_s')
    vnose=vgroup(x, 'cf_J_NoseBase_s')

    bm = bmesh.new()
    bm.from_mesh(x.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Retag as 'mouth cavity' any verts in 'cf_J_MouthBase_s' with normals pointing toward char's back
    # (this corrects several verts inside mouth corners)
    for y in v2:
        if y in vnose:
            continue
        min_dot=1.0
        for i in bm.verts[y].link_faces:
            for j in bm.verts[y].link_faces:
                min_dot =min(min_dot, i.normal.dot(j.normal))
        if x.data.vertices[y].normal[2]<0.0 or min_dot<0.0:
            v.append(y)
            #if not y in x.vertex_groups['cf_J_MouthCavity']:
            x.vertex_groups['cf_J_MouthCavity'].add([y], 1.0, 'ADD')

    for y in v:
        old_chw = 0.0

        lip = False
        for z in x.data.vertices[y].groups:
            if z.group==mouth2_id and z.weight>0.001:
                lip = True

        chw = x.data.vertices[y].normal[1]
        if lip:
            chw = min(chw, 0.5)
        if chw<0.0:
            chw=0.0

        for z in x.data.vertices[y].groups:
            if z.group==chin_id:
                old_chw = z.weight
                z.weight=chw
            elif z.group==mouth_id:
                z.weight=1.-chw
            else:
                z.weight = 0.0
        if old_chw==0.0 and chw>0.0:
            x.vertex_groups['cf_J_Chin_rs'].add([y], chw, 'ADD')

def patch_cheekup_transitions(arm, body, bm):
    print("patch_cheekup_transitions")
    lay = bm.loops.layers.uv['uv1']

    v_l=vgroup(body, ['cf_J_CheekUp_L','cf_J_CheekUp_R'])
    id_upl=body.vertex_groups['cf_J_CheekUp_L'].index
    id_upr=body.vertex_groups['cf_J_CheekUp_R'].index
    id_eye01l=body.vertex_groups['cf_J_Eye01_s_L'].index
    id_eye01r=body.vertex_groups['cf_J_Eye01_s_R'].index
    id_eye03l=body.vertex_groups['cf_J_Eye03_s_L'].index
    id_eye03r=body.vertex_groups['cf_J_Eye03_s_R'].index
    id_eye04l=body.vertex_groups['cf_J_Eye04_s_L'].index
    id_eye04r=body.vertex_groups['cf_J_Eye04_s_R'].index

    lower_eyelid_curve = [
    (0.275, 0.600),
    (0.349728, 0.538342),
    (0.354214, 0.533685),
    (0.360798, 0.529784),
    (0.367451, 0.527293),
    (0.374289, 0.525233),
    (0.381788, 0.524786),
    (0.389005, 0.524344),
    (0.396661, 0.524351),
    (0.403030, 0.525056),
    (0.408908, 0.526381),
    (0.413607, 0.527972),
    (0.417926, 0.529866),
    (0.422486, 0.532201),
    (0.425371, 0.536379),
    ]

    curve_nl=[
    (0.332, 0.424),
    (0.394, 0.433),
    (0.450, 0.446),
    (0.484, 0.460),
    ]

    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    for i, slot in enumerate(body.material_slots):
        if slot.material in [body["eyelash_mat"], body["eye_mat"], body["eyeshadow_mat"]]:
            body.active_material_index = i
            bpy.ops.object.material_slot_select()
    eyelash_mask = [False]*len(body.data.vertices)
    bpy.ops.object.mode_set(mode='OBJECT')
    body.data.vertices.foreach_get("select", eyelash_mask)

    def cheek_excess_fraction(uv, co, vert, **kwargs):
        if vert==13717:
            print("cheek_excess_fraction", vert, eyelash_mask[vert])
        if eyelash_mask[vert]:
            return 0
        eye_dist = curve_interp(lower_eyelid_curve, uv[0], xsymm=True)-uv[1]
        eye_dist = clamp01(eye_dist / 0.060)
        w_cheek = get_weight(body, vert, id_upl if uv[0]>0.500 else id_upr)
        if w_cheek < 0.001:
            return 0
        cap_y = math.sin(eye_dist*3.14159/2)
        cap_x = clamp01(6*(abs(co[0])-0.16))
        w_cheek_max = 0.4 * cap_x * cap_y #max(0.0, min(0.5*cap_y, 0.5*cap_x))
        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        cap_x2 = curve_interp(curve_nl, uv[1]) - uv[0]
        cap_x2 = 0.4 * sigmoid(cap_x2, 0.08, 0.0)
        w_cheek_max = min(w_cheek_max, cap_x2)
        return max(0.0, w_cheek - w_cheek_max) / w_cheek

    split_vgroup(body, 'cf_J_CheekUp2_L', 'cf_J_CheekUp_L', cheek_excess_fraction, bm=bm)
    split_vgroup(body, 'cf_J_CheekUp2_R', 'cf_J_CheekUp_R', cheek_excess_fraction, bm=bm)
    make_child_bone(arm, 'cf_J_FaceLow_s', 'cf_J_CheekUp2_L', Vector([0.32, 0.40, 0.19]), "Cheeks")
    make_child_bone(arm, 'cf_J_FaceLow_s', 'cf_J_CheekUp2_R', Vector([-0.32, 0.40, 0.19]), "Constrained - soft", copy='lrs')

def patch_cheekup_transitions_part2(arm, body, bm):
    lay = bm.loops.layers.uv['uv1']
    # Touch up weights of CheekLow at the cheek / nose boundary
    v_l=vgroup(body, ['cf_J_CheekUp_L','cf_J_CheekUp_R'])
    id = body.vertex_groups['cf_J_FaceLow_s'].index
    for x in v_l:
        uv = bm.verts[x].link_loops[0][lay].uv
        if uv[0]>0.500:
            g='cf_J_CheekLow_L'
            uv=(1.-uv[0], uv[1])
        else:
            g='cf_J_CheekLow_R'
        tx = uv[0]+uv[1]*0.5
        ty = uv[1]-uv[0]-0.017
        if tx > 0.630:
            old_weight = get_weight(body, x, g)
            new_weight = max(0.0, 0.125 - 3*(tx-0.622) - 34*ty*ty)
            if new_weight > old_weight:
                delta = new_weight - old_weight
                wfl = get_weight(body, x, id)
                delta = min(delta, wfl)
                set_weight(body, x, g, old_weight + delta)
                set_weight(body, x, id, wfl + delta)

def patch_cheeklow_transitions(arm, body, bm):
    lay = bm.loops.layers.uv['uv1']
    # Touch up weights of CheekLow at the cheek / chin boundary
    v_l=vgroup(body, ['cf_J_CheekLow_L','cf_J_CheekLow_R'])
    for x in v_l:
        uv = bm.verts[x].link_loops[0][lay].uv
        if uv[0]>0.500:
            g='cf_J_CheekLow_L'
        else:
            g='cf_J_CheekLow_R'
            uv=(1.-uv[0], uv[1])
        t = uv[0]-0.581+(uv[1]-0.292)*1.2
        if t<0.002:
            old_weight = get_weight(body, x, g)
            new_weight = max(0., 0.095+t*3)
            set_weight(body, x, g, min(old_weight, new_weight))

def create_cheekmid(arm, body, bm):
    vs = body.data.vertices
    v_r=vgroup(body, 'cf_J_CheekUp_R', min_wt=0.01)
    hl = [vs[y].co[1]+0.5*abs(vs[y].co[0]) for y in v_r]
    hl.sort()
    minpos = hl[0]
    midpos = hl[len(hl)//2]
    maxpos = hl[-1]
    def mid_fraction(co, vert, **kwargs):
        h = co[1]+0.5*abs(co[0])
        return clamp01(1.5-2.*(h-minpos)/(maxpos-minpos))

    split_vgroup(body, 'cf_J_CheekMid_L', 'cf_J_CheekUp_L', mid_fraction, bm=bm)
    split_vgroup(body, 'cf_J_CheekMid_R', 'cf_J_CheekUp_R', mid_fraction, bm=bm)
    make_child_bone(arm, 'cf_J_CheekUp_L', 'cf_J_CheekMid_L', Vector([-0.1, 0, 0]), "Cheeks")
    make_child_bone(arm, 'cf_J_CheekUp_R', 'cf_J_CheekMid_R', Vector([0.1, 0, 0]), "Constrained - soft", copy='lrs')

def add_skull_soft_neutral(arm, body):
    vs = body.data.vertices
    split_vgroup(body, "cf_J_ChinFront_s", 'cf_J_Chin_rs', lambda co, **kwargs: sigmoid(co[2], 0.40, 0.15))
    split_vgroup(body, "cf_J_FaceUpFront_ty", 'cf_J_FaceUp_ty', lambda co, **kwargs: max(0,min(0.5,(co[2]+0.25)*2.)))
    split_vgroup(body, 'cf_J_FaceRoot_r_s', "cf_J_FaceRoot_s", lambda co, **kwargs: 1.-max(0,min(1,(co[2]+0.25)*2.)))
    make_child_bone(arm, 'cf_J_Chin_rs', 'cf_J_ChinFront_s', Vector([0,0,0.02]), "Chin")
    make_child_bone(arm, 'cf_J_FaceUp_ty', 'cf_J_FaceUpFront_ty', Vector([0,0,0.02]), "Head internal")
    make_child_bone(arm, 'cf_J_FaceRoot_s', 'cf_J_FaceRoot_r_s', Vector([0,0,-0.02]), "Head internal")

    clean_cheeks(arm, body)

    id_l = body.vertex_groups['cf_J_CheekUp_L'].index
    id_r = body.vertex_groups['cf_J_CheekUp_R'].index

    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    patch_cheekup_transitions(arm, body, bm)
    patch_cheekup_transitions_part2(arm, body, bm)
    patch_cheeklow_transitions(arm, body, bm)

    create_cheekmid(arm, body, bm)

    # This is irreversible but harmless (fixing upper/lower lip identifications.)
    repaint_mouth_minimal(arm, body, bm)

    make_child_bone(arm, 'cf_J_FaceLow_s', 'cf_J_FaceLow_s_s', Vector([0, 0, 0.01]), "Head internal")
    make_child_bone(arm, 'cf_J_MouthBase_s', 'cf_J_MouthBase_s_s', Vector([0, 0, 0.01]), "Mouth")
    make_child_bone(arm, 'cf_J_Nose_t', 'cf_J_Nose_t_s', Vector([0,0,0.02]), "Nose")

    body.vertex_groups['cf_J_FaceLow_s'].name = 'cf_J_FaceLow_s_s'
    body.vertex_groups['cf_J_MouthBase_s'].name = 'cf_J_MouthBase_s_s'
    body.vertex_groups['cf_J_Nose_t'].name = 'cf_J_Nose_t_s'

    bm.free()


# Above pupil level, partially transfer nose weight to faceup 
# (because, as painted, NoseBridge's effect extends well into the forehead)
def repaint_nose_bridge(arm, body):
    id_nose_t = body.vertex_groups['cf_J_Nose_t_s'].index
    id_base = body.vertex_groups['cf_J_NoseBase_s'].index
    id_bridge = body.vertex_groups['cf_J_NoseBridge_s'].index
    id_faceup = body.vertex_groups['cf_J_FaceUp_tz'].index

    for v in range(len(body.data.vertices)):
        co = body.data.vertices[v].co
        #t = co[1]-co[2]
        #if t>=15.75 and co[1]-0.5*abs(co[0])>=16.45:
        if co[1]>16.30:
            wold = get_weight(body, v, id_bridge)
            wbase = get_weight(body, v, id_base)
            wt = get_weight(body, v, id_nose_t)
            base_transition = sigmoid(co[1], 16.60, 16.30)
            wold += wbase*base_transition
            wold += wt*base_transition
            set_weight(body, v, id_base, wbase*(1-base_transition))
            set_weight(body, v, id_nose_t, wt*(1-base_transition))
            wb = min(wold, sigmoid(co[1], 16.45, 16.70))
            set_weight(body, v, id_bridge, wb)
            add_weight(body, v, id_faceup, wold-wb)

def repaint_torso(body):
    for n in ['1','2','3']:
        split_vgroup(body, 'cf_J_Spine0'+n+'_r_s', 'cf_J_Spine0'+n+'_s', lambda co,**kwargs: 1.-max(0,min(1,(co[2]+0.5)*2.)))
    split_vgroup(body, 'cf_J_NeckUp_s', 'cf_J_Neck_s', lambda co,**kwargs:  max(0,min(1,(co[1]+co[2]*0.44-15.30)/0.6+0.5)))
    split_vgroup(body, 'cf_J_NeckFront_s', 'cf_J_Neck_s', lambda co,**kwargs:  max(0,min(1,(co[2]+0.25)*2.)))

def add_spine_rear_soft(arm, body):
    bpy.ops.object.mode_set(mode='OBJECT')
    repaint_torso(body)

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for n in ['1','2','3']:
        make_child_bone(arm, 'cf_J_Spine0'+n+'_s', 'cf_J_Spine0'+n+'_r_s', Vector([0, 0, -0.02]), "Spine - soft")
    make_child_bone(arm, 'cf_J_Neck_s', 'cf_J_NeckFront_s', Vector([0,0,0.02]), "Spine - soft")
    make_child_bone(arm, 'cf_J_Neck_s', 'cf_J_NeckUp_s', Vector([0,0.1,0.02]), "Spine - soft")

    rib_curve=[
        (0.000, 0.735),
        (0.037, 0.720),
        (0.060, 0.726),
        (0.069, 0.734),
        (0.088, 0.752),
        (0.107, 0.784),
        (0.125, 0.795),
        (0.143, 0.784),
        (0.162, 0.752),
        (0.181, 0.734),
        (0.190, 0.726),
        (0.213, 0.720),
        (0.250, 0.735),
    ]
    iliac_curve=[
        (0.000, 0.690),
        (0.028, 0.683),
        (0.043, 0.665), 
        (0.064, 0.641),
        (0.085, 0.606),
        (0.125, 0.585),
        (0.165, 0.605),
        (0.186, 0.641),
        (0.207, 0.665),
        (0.222, 0.683),
        (0.250, 0.690),
    ]
    def front_belly_lower_weight(co, uv, vert, **kwargs):
        return sigmoid(uv[1]-curve_interp(iliac_curve, uv[0]), 0.02, -0.02) * max(0,min(1,(co[2]+0.5)*2.))
    def front_belly_upper_weight(co, uv, vert, **kwargs):
        return sigmoid(uv[1]-curve_interp(rib_curve, uv[0]), -0.02, 0.02) * max(0,min(1,(co[2]+0.5)*2.))
    split_vgroup(body, 'cf_J_Kosi01_f_s', 'cf_J_Kosi01_s', front_belly_lower_weight)
    split_vgroup(body, 'cf_J_Spine01_f_s', 'cf_J_Spine01_s', front_belly_upper_weight)
    make_child_bone(arm, 'cf_J_Kosi01_s', 'cf_J_Kosi01_f_s', Vector([0,-0.1,0.04]), "Spine - soft")
    make_child_bone(arm, 'cf_J_Spine01_s', 'cf_J_Spine01_f_s', Vector([0,0.1,0.04]), "Spine - soft")

def repaint_mouth_minimal(arm, body, bm):
    print("Repainting mouth...")
    if not 'cf_J_MouthCavity' in body.vertex_groups:
        return

    teeth=[x for x in arm.children if x.name.startswith('o_tooth')]
    if len(teeth)>0:
        x = teeth[0]
        if not 'cf_J_MouthCavity' in x.vertex_groups:
            x.vertex_groups.new(name='cf_J_MouthCavity')
        if 'Lower jaw' in x.vertex_groups:
            x.vertex_groups['Lower jaw'].name='cf_J_LowerJaw'
        for y in x.data.vertices:
            x.vertex_groups['cf_J_MouthCavity'].add([y.index], 1.0, 'ADD')

        make_child_bone(arm, "cf_J_MouthCavity", "cf_J_LowerJaw", Vector([0,0,-0.05]), "Mouth", tail_offset=Vector([0,0,0.1]))
    tongue=[x for x in arm.children if x.name.startswith('o_tang')]
    if len(tongue)>0:
        tongue[0].vertex_groups[0].name='cf_J_MouthCavity'
    if not 'cf_J_Mouth_L' in body.vertex_groups:
        return
    mcands = set(vgroup(body, ['cf_J_MouthLow','cf_J_Mouthup']))
    coord = {}

    lay = bm.loops.layers.uv['uv1']
    for n in mcands:
        uv = bm.verts[n].link_loops[0][lay].uv
        upper = (uv[1]>0.335) or (uv[1]>0.330 and body.data.vertices[n].normal[1]<0)
        if uv[1]>0.315 and uv[1]<0.355 and uv[0]>0.432 and uv[0]<0.568:
            wud=get_weight(body, n, "cf_J_MouthLow")+get_weight(body, n, "cf_J_Mouthup")
            set_weight(body, n, "cf_J_MouthLow", 0 if upper else wud)
            set_weight(body, n, "cf_J_Mouthup", wud if upper else 0)


def dissolve_facelow_s(arm, body, bm):
    print("dissolve_facelow_s")
    for vg in ['cf_J_CheekLow_L', 'cf_J_CheekLow_R', 'cf_J_CheekUp_L', 'cf_J_CheekUp_R', 'cf_J_CheekMid_L', 'cf_J_CheekMid_R', 
        'cf_J_Chin_rs', 'cf_J_ChinTip_s', 'cf_J_ChinLow']:
        v = vgroup(body, vg, min_wt=0.01)
        min_facelow_ratio = 10.0
        for x in v:
            w1 = get_weight(body, x, vg)
            w2 = max(get_weight(body, x, 'cf_J_FaceLow_s_s'), 0.02)
            min_facelow_ratio = min(min_facelow_ratio, w2/w1)
        for x in v:
            w1 = get_weight(body, x, vg)
            w2 = get_weight(body, x, 'cf_J_FaceLow_s_s')
            delta = min(w2, w1*min_facelow_ratio)
            set_weight(body, x, vg, w1+delta)
            set_weight(body, x, 'cf_J_FaceLow_s_s', w2-delta)

    v = vgroup(body, 'cf_J_FaceLow_s_s', min_wt=0.001)

    t1=time.time()
    facelow_id = body.vertex_groups['cf_J_FaceLow_s_s'].index
    all_add_weights={}
    for y in v:
        geom = {y}
        total_geom = {y}
        for it in range(3):
            edges = [e for z in geom for e in bm.verts[z].link_edges]
            verts = [z.index for e in edges for z in e.verts]
            verts = set(verts) - total_geom
            total_geom = total_geom | verts
            geom = verts

        yco = body.data.vertices[y].co
        wylow = get_weight(body, y, facelow_id)
        add_weights={}

        for it in total_geom:
            vert = body.data.vertices[it]
            co = vert.co
            wt = sigmoid((co-yco).length, 0, 0.3)
            wlow = 0.001
            for g in vert.groups:
                if g.group == facelow_id:
                    wlow = g.weight
            for g in vert.groups:
                if g.group != facelow_id:
                    w = g.weight * wt / (1-wlow)
                    if g.group in add_weights:
                        add_weights[g.group]+=w
                    else:
                        add_weights[g.group]=w
        norm = sum(add_weights.values())
        all_add_weights[y]={z:add_weights[z]*wylow/norm for z in add_weights}
    #bm.free()
    for y in v:
        #wlow = get_weight(body, y, facelow_id)
        add_weights = all_add_weights[y]
        #norm = sum(add_weights.values())
        for z in add_weights:
            add_weight(body, y, z, add_weights[z])
        set_weight(body, y, facelow_id, 0.0)
    t2=time.time()
    print("%3f s to dissolve facelow" % (t2-t1))

def create_nasolabial(arm, body, bm):
    print("nasolabial")
    curve=[
    (0.332, 0.420),
    (0.394, 0.433),
    (0.450, 0.446),
    ]
    # VG with support along the lines from lip corners to nose corners
    def weight_nasolabial(vert, uv, **kwargs):
        y_weight = bump(uv[1], 0.332, 0.391, 0.450, shape='cos')
        fold = curve_interp(curve, uv[1])
        if uv[0]>=0.5:
            uv=(1.0-uv[0], uv[1])
        if uv[0]>fold:
            x_weight = max(0.0, 1.-abs(uv[0]-fold)/(0.500-fold))
        else:
            x_weight = max(0.0, 1.-abs(uv[0]-fold)/0.060)
        return x_weight * x_weight * y_weight * 0.5
    create_functional_vgroup(body, "cf_J_Nasolabial_s", ["cf_J_NoseBase_s", "cf_J_MouthBase_s_s"], weight_nasolabial, bm=bm)
    make_child_bone(arm, 'cf_J_FaceBase', 'cf_J_Nasolabial_s', Vector([0,-0.15,0.8]), "Nose", tail_offset=Vector([0, 0.1, 0]))

def create_nose_cheek(arm, body, bm):
    #print("Creating cf_J_NoseCheek_s")
    def weight_nose_cheek(co, vert, **kwargs):
        return sigmoid(1-6.0*abs(co[0]), 0, 1) * sigmoid(co[1], 16.2, 16.0) * sigmoid(co[1], 16.4, 16.6)
    split_vgroup(body, 'cf_J_NoseCheek_s', ['cf_J_NoseBase_s','cf_J_NoseBridge_s'], weight_nose_cheek, bm = bm)
    make_child_bone(arm, 'cf_J_NoseBase_s', 'cf_J_NoseCheek_s', Vector([0, 0.2, 0.01]), "Nose")

def restrict_nosebase(arm, body, bm):
    # Remove verts outside nasolabial folds from cf_J_NoseBase_s
    id_base = body.vertex_groups['cf_J_NoseBase_s'].index
    v=vgroup(body, 'cf_J_NoseBase_s', min_wt=0.001)
    vs=body.data.vertices
    for y in v:
        co = vs[y].co
        wmax = sigmoid(abs(co[0]), 0.16, 0.24)
        old_weight = get_weight(body, y, id_base)
        if old_weight>wmax:
            for g in vs[y].groups:
                if g.group==id_base:
                    g.weight = wmax
                else:
                    g.weight *= (1.-wmax) / (1.-old_weight)


def clean_cheeks(arm, body):
    id_l = body.vertex_groups['cf_J_CheekUp_L'].index
    id_r = body.vertex_groups['cf_J_CheekUp_R'].index

    # Correct these two WGs by making sure they are only present on their respective sides
    v_l=vgroup(body, 'cf_J_CheekUp_L')
    for x in v_l:
        if body.data.vertices[x].co[0]<0:
            set_weight(body, x, id_l, 0.0)
    v_r=vgroup(body, 'cf_J_CheekUp_R')
    for x in v_r:
        if body.data.vertices[x].co[0]>0:
            set_weight(body, x, id_r, 0.0)

def jaw_edge(arm, body, bm):
    curve=[
    (0.154, 0.333),
    (0.212, 0.260),
    (0.255, 0.220),
    #(0.227, 0.228),
    (0.283, 0.212),
    (0.311, 0.220),
    (0.339, 0.240),
    ]
    curve2=[
    (0.500, 0.110),
    (0.333, 0.154),
    (0.260, 0.212),
    (0.232, 0.239),
    (0.212, 0.283),
    (0.212, 0.311),
    (0.212, 0.339),
    ]

    id_chin = body.vertex_groups['cf_J_Chin_rs'].index
    id_chinlow = body.vertex_groups['cf_J_ChinLow'].index
    id_root = body.vertex_groups['cf_J_FaceRoot_s'].index
    id_root_r = body.vertex_groups['cf_J_FaceRoot_r_s'].index
    v=vgroup(body, ['cf_J_Chin_rs','cf_J_ChinLow'], min_wt=0.001)
    vs=body.data.vertices
    lay = bm.loops.layers.uv['uv1']
    for y in v:
        uv = bm.verts[y].link_loops[0][lay].uv
        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        fold = curve_interp(curve, uv[1])
        pos, t, coord, side, dist = curve_find_nearest(curve2, uv)
        if side>0:
            decay_rate = 12.0 * (0.33 + 0.67*sigmoid(coord, 3, 1))
            max_chin = max(0.0, 1 - 0.3*sigmoid(coord, 5, 3) - dist*decay_rate)
            old_chin = get_weight(body, y, id_chin)
            old_low = get_weight(body, y, id_chinlow)
            old_root = get_weight(body, y, id_root)
            old_root_r = get_weight(body, y, id_root_r)
            delta = old_chin+old_low-max_chin
            if delta>0:
                add_weight(body, y, id_chin, -delta*old_chin/(old_chin+old_low))
                add_weight(body, y, id_chinlow, -delta*old_low/(old_chin+old_low))
                frac = 1.-max(0,min(1,(vs[y].co[2]+0.25)*2))
                add_weight(body, y, id_root, delta*(1-frac))
                add_weight(body, y, id_root_r, delta*frac)

def reassign_cheekup2(arm, body, bm):
    id_2l = body.vertex_groups['cf_J_CheekUp2_L'].index
    id_2r = body.vertex_groups['cf_J_CheekUp2_R'].index
    v_l=vgroup(body, ['cf_J_CheekUp2_L','cf_J_CheekUp2_R'])
    id_nasolabial = body.vertex_groups['cf_J_Nasolabial_s'].index
    id_nosecheek = body.vertex_groups['cf_J_NoseCheek_s'].index
    lay = bm.loops.layers.uv['uv1']
    for x in v_l:
        uv = bm.verts[x].link_loops[0][lay].uv
        wnl = get_weight(body, x, id_nasolabial)
        wnc = get_weight(body, x, id_nosecheek)
        if wnl+wnc>0.002:
            old_weight = get_weight(body, x, [id_2l,id_2r])
            set_weight(body, x, id_nasolabial, wnl+old_weight*wnl/(wnl+wnc))
            set_weight(body, x, id_nosecheek, wnc+old_weight*wnc/(wnl+wnc))
            set_weight(body, x, id_2l, 0)
            set_weight(body, x, id_2r, 0)


def create_chin_cheek(arm, body, bm):
    def weight_chin_cheek(uv, co, vert, **kwargs):
        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        uv=(uv[0]-0.415,uv[1]-0.300)
        return sigmoid(math.sqrt(uv[0]*uv[0]+0.5*uv[1]*uv[1]-0.25*uv[0]*uv[1]), 0.0, 0.04)
    #create_functional_vgroup(body, 'cf_J_ChinCheek_s', 'cf_J_ChinFront_s', weight_chin_cheek, bm = bm)
    split_vgroup(body, 'cf_J_ChinCheek_s', 'cf_J_ChinFront_s', weight_chin_cheek, bm = bm)
    make_child_bone(arm, 'cf_J_ChinFront_s', 'cf_J_ChinCheek_s', Vector([0,0,0.02]), "Chin")


# does not work very well without subdivision, because we lack the level of detail in the area
def nasolabial_crease(arm, body, bm):
    curve=[
    (0.420, 0.332),
    (0.421, 0.362),
    (0.433, 0.394),
    (0.448, 0.438),
    (0.458, 0.448),
    (0.468, 0.453),
    (0.475, 0.449),
    ]

    weight_curve=[
    (0, 0),
    (1, 0.5),
    (2, 1.0),
    (3, 0.4),
    (4, 0.3),
    (5, 0.2),
    (6, 0.2),
    ]
    def weight_nasolabial_crease(uv, co, vert, **kwargs):
        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        pos, t, coord, side, dist = curve_find_nearest(curve, uv, debug=(vert==12693 or vert==93711 or vert==56446))
        #side = (pos[0]-uv[0])*t[1] - (pos[1]-uv[1])*t[0]
        def func(coord, pos, uv, dist):
            #distance = math.sqrt((pos[0]-uv[0])*(pos[0]-uv[0])+(pos[1]-uv[1])*(pos[1]-uv[1]))
            y_weight = curve_interp(weight_curve, coord) #bump(coord, 0, (len(curve)-1)/2., len(curve)-1, shape='cos')
            if y_weight<0.002:
                return 0.0
            x = dist * (20.0 if side<0.0 else 10.0) / y_weight
            if side>0.0 and uv[0]>pos[0]:
                x *= 2.
            if side<0.0:
                x *= 0.5 + 0.5*sigmoid(coord, 4, 2)
            if vert==12693 or vert==93711:
                print("Vert", vert, "coord", coord, "pos", pos, "uv", uv, "dist", dist, "side", side, "x", x)
            x = max(0.0, 1. - x)
            return y_weight * (-0.5 + x*x) * sigmoid(1.-x)
        effect = func(coord, pos, uv, dist)
        """
        for i, k in enumerate(curve):
            dist2 = math.sqrt((k[0]-uv[0])*(k[0]-uv[0])+(k[1]-uv[1])*(k[1]-uv[1]))
            effect2 = func(i, k, uv, dist2)
            if dist2<1.6*dist and effect2<effect:
                effect=effect2
        """
        return Vector([0, 0, -0.05*effect])

    create_functional_shape_key(body, 'Nasolabial crease', ['cf_J_FaceLow_s_s','cf_J_MouthBase_s_s', 'cf_J_NoseBase_s',
        'cf_J_NoseWing_tx_L', 'cf_J_NoseWing_tx_R','cf_J_Mouth_L','cf_J_Mouth_R'], weight_nasolabial_crease, 
        on = True, bm = None)
    body.data.shape_keys.key_blocks['Nasolabial crease'].value=1.

def clone_object(x):
    x_data_copy = x.data.copy()
    x_copy = x.copy()
    x_copy.data = x_data_copy
    bpy.context.view_layer.active_layer_collection.collection.objects.link(x_copy)
    return x_copy

def unparent(x):
    bpy.ops.object.select_all(action='DESELECT')
    x.select_set(True)
    bpy.context.view_layer.objects.active=x
    bpy.ops.object.parent_clear()

def parent_arm(arm, x):
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    x.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE')

def test_alignment(body, mesh):
    body.data.vertices.update()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    #body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.context.object.active_shape_key_index = 0
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')

    bpy.ops.object.mode_set(mode='OBJECT')

    bmd = bmesh.new()
    bmd.from_mesh(mesh.data)
    bmd.verts.ensure_lookup_table()
    v=set()
    for x in bmd.edges:
        if x.is_boundary:
            if x.verts[0].co[1]<1.0:
                vc = x.verts[0].co.copy()
                vc.freeze()
                v.add(vc)
                vc = x.verts[1].co.copy()
                vc.freeze()
                v.add(vc)

    #print("Body:", body, len(body.data.vertices))
    #boundary=[min([Vector((body.matrix_world @ y.co)-z).length for z in v])<0.0015 for y in body.data.vertices]
    boundary = [min([Vector((body.matrix_world @ y.co)-z).length for y in body.data.vertices])<0.0015 for z in v]
    print("Candidate mesh:", mesh.name, "boundary", sum(boundary), "/", len(v), "verts")
    marked = sum(boundary)
    bmd.free()
    return float(marked)/len(v)

def uv_stitch(body, mesh):
    bmd = bmesh.new()
    bmd.from_mesh(mesh.data)
    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    #v=set()

    vg = mesh.vertex_groups.new(name="Stitch Boundary")
    vg2 = mesh.vertex_groups.new(name="Stitch Mesh")
    vg2.add(list(range(len(mesh.data.vertices))), 1.0, 'ADD')
    for x in bmd.edges:
        if x.is_boundary:
            if x.verts[0].co[1]<1.0:
                vg.add([x.verts[0].index], 1.0, 'ADD')
                vg.add([x.verts[1].index], 1.0, 'ADD')
    bmd.free()
    body.data.update()
    mesh.data.update()
    join_meshes([body.name, mesh.name])
    v = vgroup(body, "Stitch Boundary")
    vm = set(vgroup(body, "Stitch Mesh"))
    #main_mesh = set(range(len(body.data.vertices))) ^ vm #[x for x in range(len(body.data.vertices)) if not x in vm]
    main_mesh = set(vgroup(body, 'cf_J_Kosi02_s')) - vm
    vs = body.data.vertices

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bmd = bmesh.new()
    bmd.from_mesh(body.data)

    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    lay = bmd.loops.layers.uv['uv1']
    def uv(x, k):
        return bmd.verts[x].link_loops[k % len(bmd.verts[x].link_loops)][lay].uv

    stitch = []
    stitch_verts=[]
    t1 = time.time()

    cos = np.zeros([len(body.data.vertices)*3], dtype=np.float32)
    body.data.vertices.foreach_get("co", cos)
    cos = cos.reshape([-1,3])
    xs = cos[v].reshape([-1,1,3])
    main_mesh_list = [z for z in main_mesh]
    ys = cos[main_mesh_list].reshape([1,-1,3])
    xy = xs-ys
    xy *= xy
    xy = np.sqrt(xy[:,:,0]+xy[:,:,1]+xy[:,:,2])
    v_nearest = np.argmin(xy, axis=1)
    t2 = time.time()
    for i, x in enumerate(v):
        nearest_xyz = main_mesh_list[v_nearest[i]]
        if (bmd.verts[x].co-bmd.verts[nearest_xyz].co).length < 0.002:
            nearest = nearest_xyz
        else:
            nearest_uv = min([z for z in main_mesh], key=lambda y: min([(uv(y,k)-uv(x,0)).length for k in range(6)]))
            nearest = nearest_uv
        stitch.append([x,nearest])
        stitch_verts.append(bmd.verts[x])
        stitch_verts.append(bmd.verts[nearest])
    t3 = time.time()
    print("find_nearest: %.3f + %.3f s" % (t2-t1, t3-t2))
    main_boundary = [x[1] for x in stitch]
    boundary_mask = [False]*len(vs)
    for x in main_boundary:
        boundary_mask[x] = True
    erase = []
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    body.data.vertices.foreach_set('select', boundary_mask)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.loop_to_region()
    bpy.ops.object.mode_set(mode='OBJECT')
    selected=0
    for x in main_mesh:
        if vs[x].select and not (x in main_boundary):
            erase.append(x)
            selected+=1

    if selected>=len(main_mesh)/4:
        print("Old exhaust inner region detect fail")
        erase=[]

    #bpy.ops.object.mode_set(mode='EDIT')
    #bpy.ops.mesh.select_all(action='DESELECT')
    #bpy.ops.object.mode_set(mode='OBJECT')

    #for x in stitch:
    #    print("Joining", x)
    #    bmesh.ops.pointmerge(bmd, verts=[bmd.verts[x[0]],bmd.verts[x[1]]], merge_co=bmd.verts[x[0]].co)

    bmesh.ops.weld_verts(bmd,targetmap={bmd.verts[x[0]]:bmd.verts[x[1]] for x in stitch})
    bmd.verts.ensure_lookup_table()
    if len(erase)>0: 
        erase = [bmd.verts[y] for y in erase if not (bmd.verts[y] in stitch_verts)]
        #print("Erasing:", [x.index for x in erase])
        bmesh.ops.delete(bmd, geom=erase)

    bmd.to_mesh(body.data)
    bmd.free()

    body.vertex_groups.remove(body.vertex_groups["Stitch Boundary"])
    body.vertex_groups.remove(body.vertex_groups["Stitch Mesh"])


# stitch=True: merge into the body even if there's no edge alignment
def excise_neuter_mesh(body, injector_mesh, stitch=False):
    print("Excising neuter for", injector_mesh.name)
    body.data.vertices.update()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    #body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.context.object.active_shape_key_index = 0
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')

    bpy.ops.object.mode_set(mode='OBJECT')

    bmd = bmesh.new()
    bmd.from_mesh(injector_mesh.data)
    bmd.verts.ensure_lookup_table()
    v=set()
    for x in bmd.edges:
        if x.is_boundary:
            if x.verts[0].co[1]<1.0:
                vc = x.verts[0].co.copy()
                vc.freeze()
                v.add(vc)
                vc = x.verts[1].co.copy()
                vc.freeze()
                v.add(vc)

    #print("Body:", body, len(body.data.vertices))
    #print("New mesh: 
    boundary=[min([Vector((body.matrix_world @ y.co)-z).length for z in v])<0.0015 for y in body.data.vertices]
    marked = sum(boundary)
    print(marked, "/", len(v), "excision vertices found")
    #if marked > 0 and marked < len(v):
    #    for z in v:
    #        print(z.co, min([Vector((body.matrix_world @ y.co)-z).length for y in body.data.vertices]))
    if marked < len(v):
        if stitch:
            join_meshes([body.name, injector_mesh.name])
        return False
    body.data.vertices.foreach_set('select',boundary)
    bpy.ops.object.mode_set(mode='EDIT')

    bpy.ops.mesh.loop_to_region()
    bpy.ops.object.mode_set(mode='OBJECT')
    selected=0
    for x in body.data.vertices:
        if x.select:
            selected+=1

    #print(selected)
    if selected<len(body.data.vertices)/4:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.delete(type='FACE')
        
        join_meshes([body.name, injector_mesh.name])
        bpy.ops.object.mode_set(mode='OBJECT')

        bmd = bmesh.new()
        bmd.from_mesh(body.data)
        bmd.verts.ensure_lookup_table()
        new_boundary=set()
        for x in bmd.edges:
            if x.is_boundary:
                vc=x.verts[0].co.copy()
                vc.freeze()
                new_boundary.add(vc)
                vc=x.verts[1].co.copy()
                vc.freeze()
                new_boundary.add(vc)

        boundary=[min([Vector((body.matrix_world @ y.co)-z).length for z in v])<0.0015 for y in body.data.vertices]
        print("Near the slit:", sum(boundary), "verts")
        
        for x in range(len(body.data.vertices)):
            if not boundary[x]:
                continue
            y=body.data.vertices[x].co
            if min([Vector(y-z).length for z in new_boundary])>0.00001:
                boundary[x]=False
        print("Boundary:", sum(boundary), "verts")

        body.data.vertices.foreach_set('select', boundary)

        #return True
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.remove_doubles(use_unselected=False, threshold = 0.01)
        bpy.ops.object.mode_set(mode='OBJECT')

        #injector_mesh = body
        #bpy.ops.object.mode_set(mode='OBJECT')
    return True

def attach_exhaust(arm, body):
    print("Attaching exhaust...")
    t1=time.time()
    with bpy.data.libraries.load(os.path.dirname(__file__)+"/assets/prefab_materials_meshexporter.blend") as (data_from, data_to):
        data_to.objects = data_from.objects

    bpy.ops.object.mode_set(mode='OBJECT')
    #arm.data.pose_position='REST'
    body.active_shape_key_index = 0
    body.data.update()

    body.vertex_groups.new(name='cf_J_Perineum')
    body.vertex_groups.new(name='cf_J_Exhaust')
    body.vertex_groups.new(name='cf_J_ExhaustValve')
    old_id = body.vertex_groups['cf_J_Kosi02_s'].index
    #old_id_r = body.vertex_groups['cf_J_CheekUp_R'].index
    #new_id =  body.vertex_groups['cf_J_Perineum'].index
    v=vgroup(body, 'cf_J_Kosi02_s')
    if not 'cf_J_Ana' in body.vertex_groups:
        body.vertex_groups.new(name='cf_J_Ana')
    id_ana = body.vertex_groups['cf_J_Ana'].index

    leg1 = body.vertex_groups['cf_J_LegUp01_s_L'].index
    leg2 = body.vertex_groups['cf_J_LegUp01_s_R'].index
    s1 = body.vertex_groups['cf_J_Siri_s_L'].index
    s2 = body.vertex_groups['cf_J_Siri_s_R'].index

    undef=body.data.shape_keys.key_blocks['Basis'].data
    """
    for x in v:
        if abs(undef[x].co[0])<0.25:
            f = (1. - abs(undef[x].co[0]) / 0.25) * max(0.0, min(1.0, undef[x].co[2]*2+1))
            f *= sigmoid(undef[x].co[2], 0.25, 0.45)
            if f<0.001:
                continue
            w = get_weight(body, x, old_id)
            f *= w
            supp = get_weight(body, x, leg1) + get_weight(body, x, leg2) + get_weight(body, x, s1) + get_weight(body, x, s2) 
            f -= supp
            if f>0:
                set_weight(body, x, old_id, w-f)
                set_weight(body, x, new_id, f)
        L = undef[x].co-Vector([0, 9.4, -0.56])
        if L.length<0.4:
            set_weight(body, x, id_ana, 0.8*sigmoid(L.length,0,0.4))
    """
    mat=bpy.data.materials["Exhaust Material"].copy()
    mat.name = 'Exhaust_' + arm.name
    #replace_mat(mesh, mat)

    cand_meshes = []
    for opts in [
        (None, Vector([0, 0, 0.0])),
        ('Prefab exhaust pipe Adapter Female', Vector([0,0,0.001])),
        ('Prefab exhaust pipe Adapter Male', Vector([0,0,-0.003])),
        ]:
        #bpy.data.objects['Prefab exhaust pipe'].hide_set(False)
        m=clone_object(bpy.data.objects['Prefab exhaust pipe'])
        m.data.materials[0] = mat
        m.location = opts[1]
        m.vertex_groups.new(name='cf_J_Exhaust')


        v = vgroup(m, 'cf_J_Perineum')
        for x in v:
            # Weights in the prefab are somewhat messed up, 
            # this is easier than properly repainting it
            w = 0
            for g in m.data.vertices[x].groups:
                w += g.weight
            if w<1:
                add_weight(m, x, 'cf_J_ExhaustValve', 1-w)
            elif w>1:
                wc = get_weight(m, x, "cf_J_ExhaustClench")
                wc -= w-1
                if wc<0:
                    wc=0
                set_weight(m, x, "cf_J_ExhaustClench", wc)

            # Reassign the mass of the exhaust pipe (above the valve) from Perineum to Exhaust
            if m.data.vertices[x].co[2]<9.52:
                continue
            w = get_weight(m, x, 'cf_J_Perineum')
            ws =sigmoid(m.data.vertices[x].co[2], 9.6, 9.85)
            set_weight(m, x, 'cf_J_Perineum', w*(1-ws))
            set_weight(m, x, 'cf_J_Exhaust', w*ws)

        if opts[0] is not None:
            adapter=clone_object(bpy.data.objects[opts[0]])
            #adapter.location = Vector([0,0,0.001])
            #adapter.location = opts[1]
            adapter.data.materials[0] = mat
            name = m.name
            m = join_meshes([m.name, adapter.name])
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            m.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold = 0.0001)
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        m.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)

        bpy.ops.object.mode_set(mode='OBJECT')
        parent_arm(arm, m)
        cand_meshes.append(m)
        #print(m)

    maintex = set_tex(mat, 'MainTex', 'skin_body', 'MainTex', alpha='NONE')
    set_tex(mat, 'DetailGlossMap', 'skin_body', 'DetailGlossMap', csp='Non-Color')
    set_bump(mat, 'BumpMap', 'skin_body', '')
    set_bump(mat, 'BumpMap2', 'skin_body', '2')
    set_tex(mat, 'Texture2', 'skin_body', 'Texture2', csp='Non-Color')    
    if set_tex(mat, 'Subsurface', 'skin_body', 'SubsurfaceAlbedo', csp='Non-Color') is None:
        print("Torso subsurface texture not found")
        disconnect_link(mat, 'Subsurface')
    else:
        mat.node_tree.nodes['Group.004'].inputs['Subsurface/MainTex mix'].default_value=0.2

    bpy.context.view_layer.objects.active = arm
    arm.data.pose_position='POSE'  
    bpy.ops.object.mode_set(mode='EDIT')
    r_exh = Vector([0, 0.2, 0.05])
    make_child_bone(arm, 'cf_J_Ana', 'cf_J_ExhaustValve', Vector([0,0,0]), 'Genitals', tail_offset=r_exh)
    make_child_bone(arm, 'cf_J_ExhaustValve', 'cf_J_ExhaustClench', r_exh, 'Genitals', tail_offset=r_exh)
    make_child_bone(arm, 'cf_J_Ana', 'cf_J_Exhaust', r_exh*2, 'Genitals', tail_offset=r_exh)
    make_child_bone(arm, 'cf_J_Kosi02_s', 'cf_J_Perineum', Vector([0, 9.4, -0.2]),  'Genitals', parent_head=False, tail_offset=Vector([0, 0.2, 0.0]))

    bpy.ops.object.mode_set(mode='OBJECT')
    arm.data.pose_position='REST'

    fit_mesh = [0,None]
    for m in cand_meshes:
        ratio = test_alignment(body, m)
        #print(m, ratio)
        if ratio>fit_mesh[0] or fit_mesh[1] is None:
            fit_mesh = [ratio, m]

    #print("Fit:", fit_mesh)
    #    if fit_mesh is None:
    #        print("None of the exhaust meshes is a perfect fit")
    #        bpy.ops.object.mode_set(mode='OBJECT')
    #        return
    for m in cand_meshes:
        try:
            if m!=fit_mesh[1]:
                print("Removing", m)
                bpy.data.objects.remove(m)
        except:
            pass

    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.object.active_shape_key_index = 0

    t1=time.time()
    uv_stitch(body, fit_mesh[1])
    t2=time.time()
    print("%.3f s to UV stitch" % (t2-t1))
    """
    bmd = bmesh.new()
    bmd.from_mesh(body.data)
    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    lay = bmd.loops.layers.uv['uv1']
    exh = set(vgroup(body, 'cf_J_ExhaustValve'))
    for x in set(vgroup(body, ["cf_J_Kosi02_s", "cf_J_Ana"])) - exh:
        uv = bmd.verts[x].link_loops[0][lay].uv
        r = (uv-Vector([0.126,0.498])).length / 0.006
        if r<2.0:
            r = 0.5*sigmoid(r, 1.0, 2.0)
            w=0
            for g in body.data.vertices[x].groups:
                if '_Ana' in body.vertex_groups[g.group].name:
                    w += g.weight
            set_weight(body, x, 'cf_J_ExhaustValve', w*r)
            for g in body.data.vertices[x].groups:
                if '_Ana' in body.vertex_groups[g.group].name:
                    g.weight = 1-r
    """


    bpy.context.view_layer.objects.active = body
    bpy.context.object.active_shape_key_index = 0

    arm.data.pose_position='POSE'
    arm["exhaust"]=1.0
    bpy.ops.object.mode_set(mode='OBJECT')
    t2=time.time()
    print("%.3f s to attach exhaust" % (t2-t1))

def attach_injector(arm, body):
    print("Attaching injector...")
    t1=time.time()
    bpy.ops.object.mode_set(mode='OBJECT')
    with bpy.data.libraries.load(os.path.dirname(__file__)+"/assets/prefab_materials_meshexporter.blend") as (data_from, data_to):
        data_to.objects = data_from.objects
        data_to.node_groups = data_from.node_groups
    injector=clone_object(bpy.data.objects['Prefab Dongle'])
    injector_mesh=clone_object(bpy.data.objects['Prefab Dongle Mesh'])
    injector_mesh.name='Injector'
    injector_sheath=clone_object(bpy.data.objects["Prefab Dongle Skirt"])
    injector_sheath.name='Sheath'
    injector_mesh.add_rest_position_attribute=True
    injector_sheath.add_rest_position_attribute=True
    injector_mesh.hide_viewport=False
    injector_sheath.hide_viewport=False

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    injector_mesh.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    unparent(injector_mesh)
    unparent(injector_sheath)
    parent_arm(arm, injector_mesh)
    parent_arm(arm, injector_sheath)
    arm.select_set(True)
    injector.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.join()

    arm["sheath_object"] = injector_sheath

    #mat = bpy.data.materials["Dongle Texture"].copy()
    mat = injector_mesh.material_slots[0].material.copy()
    mat.name = 'Injector_' + arm.name

    replace_mat(injector_mesh, mat)
    replace_mat(injector_sheath, mat)
    
    maintex = set_tex(injector_mesh, 'MainTex', 'skin_body', 'MainTex', alpha='NONE')
    set_tex(injector_mesh, 'DetailGlossMap', 'skin_body', 'DetailGlossMap', csp='Non-Color')
    set_bump(injector_mesh, 'BumpMap', 'skin_body', '')
    set_bump(injector_mesh, 'BumpMap2', 'skin_body', '2')

    body["injector_mat"] = mat
    
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    arm.data.edit_bones['fk_dik'].parent=arm.data.edit_bones['cf_J_Kosi02_s']

    bones=['fk_dik']
    while len(bones)>0:
        #arm.data.edit_bones[bones[0]].layers=array
        arm.data.collections['Genitals'].assign(arm.data.edit_bones[bones[0]])
        arm.data.collections['Everything'].assign(arm.data.edit_bones[bones[0]])
        bones += [x.name for x in arm.data.edit_bones[bones[0]].children]
        bones=bones[1:]

    bpy.ops.object.mode_set(mode='OBJECT')

    mod=body.modifiers.new(name='Copy attrs', type='NODES')

    # For some reason, vertex groups already on the mesh aren't always visible to the material.
    # Possibly a bug in Blender. Adding a geonode tree to make sure.
    mod.node_group=bpy.data.node_groups['HS2 Injector Copy attributes']

    # Correct the colors of the injector mesh for color-match the torso mesh.
    w = maintex.size[0]
    h = maintex.size[1]
    index = ( int(h*0.581)* w + int(w*0.125) ) * 4
    maintex.colorspace_settings.name="Non-Color"
    pixel = mathutils.Color((
        maintex.pixels[index], # RED
        maintex.pixels[index + 1], # GREEN
        maintex.pixels[index + 2], # BLUE
    ))
    maintex.colorspace_settings.name="sRGB"
    pixel = pixel.from_srgb_to_scene_linear()
    pixel.v = math.pow(pixel.v, 0.25)
    c0h = 0.03954
    c0s = 0.6782
    c0v = 0.8700

    mat.node_tree.nodes["Skin effect"].inputs["Tone shift"].default_value[0] = 50.0*(pixel.h-c0h)
    if pixel.s>1e-6:
        mat.node_tree.nodes["Skin effect"].inputs["Tone shift"].default_value[1] = math.log(pixel.s) / math.log(c0s) - 1.0
    else:
        mat.node_tree.nodes["Skin effect"].inputs["Tone shift"].default_value[1] = -5.0
    mat.node_tree.nodes["Skin effect"].inputs["Tone shift"].default_value[2] = pixel.v-c0v

    body.data.vertices.update()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = body
    bpy.context.object.active_shape_key_index = 0
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    uv_stitch(body, injector_mesh)
    body.active_shape_key_index = 0
    body.data.update()
    t2=time.time()
    print("%.3f s to attach injector" % (t2-t1))

def paint_scalp(arm, body):
    vg=body.vertex_groups.new(name="Scalp")
    faceup = vgroup(body,"cf_J_FaceUp_ty")
    ignore = set(vgroup(body,['cf_J_EarLow_L','cf_J_EarLow_R',
#        'cf_J_EarBase_s_L','cf_J_EarBase_s_R',
        'cf_J_FaceLow_s', 'cf_J_FaceLow_s_s', 'cf_J_Chin_rs',
        'cf_J_CheekUp_L', 'cf_J_CheekUp_R',
        'cf_J_Eye01_s_L','cf_J_Eye02_s_L','cf_J_Eye03_s_L',
        'cf_J_Eye01_s_R','cf_J_Eye02_s_R','cf_J_Eye03_s_R']))
    for v in faceup:
        if v in ignore:
            continue
        if get_weight(body, v, "cf_J_FaceUp_tz")>0.1:
            continue
        if get_weight(body, v, "cf_J_EarBase_s_L")>0.2:
            continue
        if get_weight(body, v, "cf_J_EarBase_s_R")>0.2:
            continue
        if get_weight(body, v, "cf_J_FaceRoot_s")>0.0 and body.data.vertices[v].co[2]>-0.5:
            continue
        vg.add([v], 1.0, 'ADD')

def mesh_hair_to_curves(body, hair):
    #paint_scalp(body)
    vg = vgroup(body, "Scalp")

    body.data.vertices.foreach_set("select", [(y in vg) for y in range(len(x.data.vertices))])
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.region_to_loop()
    bpy.ops.mesh.mark_seam(clear=False)

    bpy.context.view_layer.objects.active = body
    bpy.ops.mesh.uv_texture_add()
    layer = body.data.uv_layers[-1]
    layer.name="HairUV"
    layer.active_render = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.unwrap(method='CONFORMAL', margin=0)
    bpy.ops.object.mode_set(mode='OBJECT')
    body.data.uv_layers[0].active_render = True
    # add "empty hair" to body
    # add "mesh hair to curves" geonode to curves
    # set Object = hair, Name = (read 1st UV map on hair)
    # in geonode defaults: set Y=1, Image=None, Subdiv=0
    # Optionally detect alpha on hair
    # Set 'Curves'->'Additional Subdivision' to at least 2 in renderer settings
    # Create hair material and connect hair color to interface


def paint_nostrils(arm, body, bm):
    id_l=body.vertex_groups['cf_J_Nostril_L'].index
    id_r=body.vertex_groups['cf_J_Nostril_R'].index
    id_c=body.vertex_groups['cf_J_Nose_Septum'].index
    id_t=body.vertex_groups['cf_J_Nose_tip'].index
    #id_b=body.vertex_groups['cf_J_NoseBridge2_s'].index
    id_tt=body.vertex_groups['cf_J_Nose_t_s'].index

    id_wl = body.vertex_groups['cf_J_NoseWing_tx_L'].index
    id_wr = body.vertex_groups['cf_J_NoseWing_tx_R'].index
    id_base = body.vertex_groups['cf_J_NoseBase_s'].index

    v = vgroup(body,['cf_J_NoseWing_tx_L','cf_J_NoseWing_tx_R','cf_J_Nose_tip',
        'cf_J_Nose_t_s',
        'cf_J_Nostril_L','cf_J_Nostril_R',
        'cf_J_Nose_Septum', 'cf_J_NoseBase_s'])

    lay = bm.loops.layers.uv['uv1']

    #print(len(v), "candidate nostril verts")
    boy = (body['Boy']>0.0)
    uv_skew = 0.0 if boy else 0.7
    for x in v:
        uv = bm.verts[x].link_loops[0][lay].uv
        septum_bump = bump(uv[0], 0.490, 0.500, 0.510)
        # 'cf_J_Nostril_*' support: ovals around (0.4826,0.4195) 
        # (geometry is slightly different between M and F)

        r = (uv-Vector([1-0.4826,0.4195]))
        r = math.sqrt(r[0]*r[0] + r[1]*r[1] + uv_skew*r[0]*r[1])
        wtl = sigmoid(r, 0.006, 0.018) * (1-septum_bump)

        r2 = uv-Vector([0.4826,0.4195])
        r2 = math.sqrt(r2[0]*r2[0] + r2[1]*r2[1] - uv_skew*r2[0]*r2[1])
        wtr = sigmoid(r2, 0.006, 0.018) * (1-septum_bump)

        # 'cf_J_Nose_Septum' support: oval around (0.500,0.406) .. (0.500,0.418) 
        r3 = uv-Vector([0.5000,0.418])
        if r3[1]<0.0:
            r3[1] = min(0.0, r3[1]+0.012)
        else:
            r3[1] *= 2.0
        wtc = sigmoid(r3.length, 0.000, 0.036)

        w_nose_t = get_weight(body, x, id_tt)
        w_nose_wl = get_weight(body, x, id_wl)
        w_nose_wr = get_weight(body, x, id_wr)
        w_nose_base = get_weight(body, x, id_base)
        w_nose_tip = get_weight(body, x, id_t)

        effect = wtl+wtr+wtc

        transfer_tt_base = sigmoid(uv[1], 0.395, 0.420)
        transfer_base_tt = sigmoid(uv[1], 0.475, 0.450)

        w_nose_t, w_nose_base = w_nose_t-w_nose_t*transfer_tt_base+w_nose_base*transfer_base_tt, w_nose_base+w_nose_t*transfer_tt_base-+w_nose_base*transfer_base_tt

        budget = w_nose_t+w_nose_base+w_nose_wl+w_nose_wr+w_nose_tip

        if effect>1:
            wtl,wtr,wtc = [y/effect for y in (wtl,wtr,wtc)]
            effect = 1

        budget = w_nose_t+w_nose_base+w_nose_tip+w_nose_wl+w_nose_wr
        wtl,wtr,wtc = [y*budget for y in (wtl,wtr,wtc)]
        w_nose_t,w_nose_base,w_nose_tip,w_nose_wl,w_nose_wr = [y*(1-effect) for y in (w_nose_t,w_nose_base,w_nose_tip,w_nose_wl,w_nose_wr)]

        set_weight(body, x, id_l, wtl)
        set_weight(body, x, id_r, wtr)
        set_weight(body, x, id_c, wtc)
        set_weight(body, x, id_t, w_nose_tip)
        set_weight(body, x, id_wl, w_nose_wl)
        set_weight(body, x, id_wr, w_nose_wr)
        set_weight(body, x, id_base, w_nose_base)
        set_weight(body, x, id_tt, w_nose_t)


def add_nostrils(arm, body, bm):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    make_child_bone(arm, 'cf_J_Nose_t', 'cf_J_Nostril_L', Vector([0.07, -0.065, 0.07]), "Nose")
    make_child_bone(arm, 'cf_J_Nose_t', 'cf_J_Nose_Septum', Vector([0.0,-0.04,0.08]), "Nose")
    make_child_bone(arm, 'cf_J_Nose_t', 'cf_J_Nostril_R', Vector([-0.07, -0.065, 0.07]), "Constrained - soft", copy='lrs')

    if 'cf_J_Nostril_L' in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups['cf_J_Nostril_L'])
    if 'cf_J_Nostril_R' in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups['cf_J_Nostril_R'])
    if 'cf_J_Nose_Septum' in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups['cf_J_Nose_Septum'])
    vgl = body.vertex_groups.new(name='cf_J_Nostril_L')
    vgr = body.vertex_groups.new(name='cf_J_Nostril_R')
    vgs = body.vertex_groups.new(name='cf_J_Nose_Septum')
    paint_nostrils(arm, body, bm)

    bpy.context.view_layer.objects.active = body
    bpy.ops.paint.weight_paint_toggle()
    bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=0.002)
    bpy.ops.paint.weight_paint_toggle()

# memorize coordinates and normals of all verts in T-pose (used by the skin generator, 
# to correctly distribute skin pores and to tan upward-facing skin)
def add_t_pos(arm, body):
    armature.set_fk_pose(arm, [])
    bpy.context.view_layer.objects.active = body
    if "T-position" in body.data.attributes:
        body.data.attributes.remove(body.data.attributes["T-position"])
    attr = body.data.attributes.new(name="T-position", type="FLOAT_VECTOR", domain="POINT")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object( body, depsgraph )
    bm.verts.ensure_lookup_table()
    verts = [y for x in range(len(body.data.vertices)) for y in bm.verts[x].co]
    verts = verts[:]
    # attribute is a float vector, but foreach_set expects a flattened float array
    attr.data.foreach_set("vector", verts)
    if "T-normal" in body.data.attributes:
        body.data.attributes.remove(body.data.attributes["T-normal"])
    attrn = body.data.attributes.new(name="T-normal", type="FLOAT_VECTOR", domain="POINT")
    verts = [y for x in range(len(body.data.vertices))  for y in bm.verts[x].normal]
    verts = verts[:]
    #print(verts[:6])
    attrn.data.foreach_set("vector", verts)
    bm.free()

def get_linked_by_material(body, x, bm):
    v=set({x})
    mat = bm.verts[x].link_faces[0].material_index

    v_out=set({x})
    while len(v)>0:
        v_next=set({})
        for y in v:
            for z in bm.verts[y].link_edges:
                for w in z.verts:
                    if w.index in v_out:
                        continue
                    if any([f.material_index==mat for f in w.link_faces]):
                        v_next.add(w.index)
        v_out = v_out | v_next
        v = v_next
    return v_out

    """
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    body.data.vertices[x].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_linked(delimit={'MATERIAL'})
    bpy.ops.object.mode_set(mode='OBJECT')
    v = [False]*len(body.data.vertices)
    body.data.vertices.foreach_get("select", v)
    return set([x for x in range(len(v)) if v[x]])
    """

def tweak_nails(arm, body):
    t1=time.time()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    for key in body.data.shape_keys.key_blocks:
        key.value=0.0
    body.active_shape_key_index = 0
    arm.data.pose_position='REST'
    body.modifiers["Armature"].show_in_editmode = False

    body.data.vertices.update()

    key_exists = "Nails" in body.data.shape_keys.key_blocks

    if key_exists:
        body.shape_key_remove(key=body.data.shape_keys.key_blocks["Nails"])
    if "Long fingernails" in body.data.shape_keys.key_blocks:
        body.shape_key_remove(key=body.data.shape_keys.key_blocks["Long fingernails"])
    if "Long toenails" in body.data.shape_keys.key_blocks:
        body.shape_key_remove(key=body.data.shape_keys.key_blocks["Long toenails"])

    # Select every vertex in 'Nails' material
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')

    material_index = 0
    for i, slot in enumerate(body.material_slots):
        if slot.material == body["nails_mat"]:
            body.active_material_index = i
            material_index = i
            bpy.ops.object.material_slot_select()

    # Extrude them inwards a bit
    if not key_exists:
        # do it twice to create two loops of vertices
        bpy.ops.mesh.extrude_region_shrink_fatten(TRANSFORM_OT_shrink_fatten={"value":-0.001})
        bpy.ops.mesh.extrude_region_shrink_fatten(TRANSFORM_OT_shrink_fatten={"value":-0.00001})
        #bpy.ops.mesh.extrude_region_shrink_fatten(
        #    MESH_OT_extrude_region={"use_normal_flip":False, "use_dissolve_ortho_edges":False, "mirror":False}, 
        #    TRANSFORM_OT_shrink_fatten={"value":-0.001, "use_even_offset":False, "mirror":False, "use_proportional_edit":False, 
        #    "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "use_proportional_connected":False, "use_proportional_projected":False, 
        #    "snap":False, "release_confirm":False, "use_accurate":False})
        #
        #bpy.ops.mesh.extrude_region_shrink_fatten(
        #    MESH_OT_extrude_region={"use_normal_flip":False, "use_dissolve_ortho_edges":False, "mirror":False}, 
        #    TRANSFORM_OT_shrink_fatten={"value":-0.00001, "use_even_offset":False, "mirror":False, "use_proportional_edit":False, 
        #    "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "use_proportional_connected":False, "use_proportional_projected":False, 
        #    "snap":False, "release_confirm":False, "use_accurate":False})
        bpy.ops.mesh.select_more()
        bpy.ops.object.material_slot_assign()

    bpy.ops.object.mode_set(mode='OBJECT')
    mask_full = [False]*len(body.data.vertices)
    body.data.vertices.foreach_get("select", mask_full)
    vs_full = set([x for x in range(len(mask_full)) if mask_full[x]])
    bpy.ops.object.mode_set(mode='EDIT')

    # Deselect rims (because get_linked_by_material() only works correctly
    # when starting from a vertex entirely inside the nail)
    for i, slot in enumerate(body.material_slots):
        if slot.material == body["torso_mat"]:
            body.active_material_index = i
            bpy.ops.object.material_slot_deselect()

    # Get the list of all 'core' nail vertices
    bpy.ops.object.mode_set(mode='OBJECT')
    mask = [False]*len(body.data.vertices)
    body.data.vertices.foreach_get("select", mask)
    vs = set([x for x in range(len(mask)) if mask[x]])

    vs_rim = vs_full-vs

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_less()
    bpy.ops.mesh.select_less()
    bpy.ops.object.mode_set(mode='OBJECT')
    mask2 = [False]*len(body.data.vertices)
    body.data.vertices.foreach_get("select", mask2)
    vs2 = set([x for x in range(len(mask2)) if mask2[x]])
    vs_rim2 = vs - vs2

    if not key_exists:
        # If we are doing this for the first time on the char, mark nail rims as sharp and creased
        bpy.ops.object.mode_set(mode='EDIT')
        for i, slot in enumerate(body.material_slots):
            if slot.material == body["nails_mat"]:
                body.active_material_index = i
                bpy.ops.object.material_slot_select()
        bpy.ops.mesh.region_to_loop()
        bpy.ops.mesh.mark_sharp()
        bpy.ops.transform.edge_crease(value=1)

    # Create the shape key
    bpy.ops.object.mode_set(mode='OBJECT')
    sk = body.shape_key_add(name="Nails")
    sk.interpolation='KEY_LINEAR'
    sk2 = body.shape_key_add(name="Long fingernails")
    sk2.interpolation='KEY_LINEAR'
    sk3 = body.shape_key_add(name="Long toenails")
    sk3.interpolation='KEY_LINEAR'
    for x in range(len(body.data.vertices)):
        sk.data[x].co = body.data.shape_keys.key_blocks["Basis"].data[x].co
        sk2.data[x].co = body.data.shape_keys.key_blocks["Basis"].data[x].co
    sets = []
    body.data.vertices.update()

    bm = bmesh.new()
    bm.from_mesh( body.data )
    bm.verts.ensure_lookup_table()

    while len(vs)>0:
        body.data.vertices.update()
        nail = get_linked_by_material(body, vs.pop(), bm)
        sets.append(nail)
        vs = vs-nail 

    bm.free()
    ext_sets = []
    for nail in sets:
        v0 = sum([body.data.vertices[x].normal for x in nail], Vector([0,0,0]))
        v0.normalize()
        c0 = sum([body.data.vertices[x].co for x in nail], Vector([0,0,0]))
        c0 /= len(nail)

        mat=Matrix([[0,0,0],[0,0,0],[0,0,0]])

        toenail = abs(c0[0])<5.0
        thumb = (v0[2]>0.5) and not toenail
        scale = (1, 1.1, 0.95)
        angle=0.08
        if toenail:
            v1 = Vector([1.0*(0.95-abs(c0[0]))*(1 if c0[0]>0 else -1), 0, 1])
        elif thumb:
            v1 = Vector([1 if c0[0]>0 else -1, 0, 0.3])
        else:
            v1 = Vector([1 if c0[0]>0 else -1, -0.10, 0.1*(c0[2]+0.20)])

        # Doing this with bpy.ops.transform.resize/rotate/etc. does not work well (possible Blender bugs?)
        v1.normalize()
        v0 -= v1*v0.dot(v1)
        v0.normalize()

        v2 = v0.cross(v1)
        offset = v1*0.006

        for c in range(3):
            v = Vector([0,0,0])
            v[c] = 1.0
            v = Vector([v.dot(v0), v.dot(v1), v.dot(v2)])
            v = Vector([v[0]*scale[0], v[1]*scale[1], v[2]*scale[2]])
            v = Vector([v[0]*math.cos(angle)-v[1]*math.sin(angle), v[0]*math.sin(angle)+v[1]*math.cos(angle), v[2]])
            v = v0*v[0]+v1*v[1]+v2*v[2]
            mat[c] = v

        max_z = 0.0
        max_x = 0.0
        phi = 0.5

        for x in nail:
            co = body.data.shape_keys.key_blocks["Basis"].data[x].co.copy()

            # Scale the nail bed by 1.1x lengthwise, 0.95x widthwise, 
            # rotate it by 0.08 radians and move it towards the fingertip
            co = (mat @ (co - c0)) + c0 + offset

            dv = co-c0
            r = dv.normalized()
            dot = r.dot(v1)

            # Flatten tips of the nails
            dv -= v0*dv.dot(v0)*max(dot, 0.0)*0.5

            # Basic (short nail) form
            sk.data[x].co = c0+dv

            # Long fingernails/toenails:
            effect = Vector([0,0,0])

            if dot>phi:
                # Extrude the outer edge of the nail
                if x in vs_rim:
                    effect = v1*(dot-phi)*0.1 + v0*(dot-phi)*(-0.02 if toenail else 0.0)

                # Move the next row of vertexes in the same direction
                if x in vs_rim2:
                    effect = v1*(dot-phi)*0.01 + v0*(dot-phi)*0.003

                if toenail:
                    sk3.data[x].co += effect
                else:
                    sk2.data[x].co += effect

            max_z = max(max_z, (co-c0).dot(v1))
            max_x = max(max_x, (co-c0).dot(v2))
        ext_sets.append((nail, c0, v0, v1, v2, max_x, max_z))

        for x in nail:
            r = sk.data[x].co-c0

            r.normalize()
            dot = r.dot(v1)
            phi = 0.5 if (thumb or toenail) else 0.66
            if x in vs_rim or x in vs_rim2:
                if dot>phi:
                    if toenail:
                        # Fix the weird shape of toenail front rims
                        sk.data[x].co = c0 + r*max_z*(0.95 if x in vs_rim2 else 1.0)

    bm = bmesh.new()
    bm.from_mesh( body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    lay = bm.loops.layers.uv['uv1']
    for nail, c0, v0, v1, v2, max_x, max_z in ext_sets:
        toenail = abs(c0[0])<5.0
        thumb = (v0[2]>0.5) and not toenail
        for x in nail:
            r = sk.data[x].co-c0
            r.normalize()
            dot = r.dot(v1)
            phi = 0.5 if (thumb or toenail) else 0.66
            #if dot>0.0:
            if toenail:
                uv = (0.954 + 0.034*(sk.data[x].co-c0).dot(v2)/max_x, 0.355 - 0.030 * (sk.data[x].co-c0).dot(v1)/max_z)
            else:
                uv = (0.892 + 0.014*(sk.data[x].co-c0).dot(v2)/max_x, 0.346 - 0.022 * (sk.data[x].co-c0).dot(v1)/max_z)
            for loop in bm.verts[x].link_loops:
                if loop.face.material_index == material_index:
                    loop[lay].uv = uv

    bm.to_mesh(body.data)
    bm.free()

    bpy.ops.object.mode_set(mode='OBJECT')
    arm.data.pose_position='POSE'
    body.modifiers["Armature"].show_in_editmode = True
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')

    sk.value = 1.0
    sk2.value = 0.2
    sk3.value = 0.2
    #t1 = time.time()


def insert_adapter_bone(arm, bone, adapter_name):
    old_parent = arm.data.bones[bone].parent
    make_child_bone(arm, old_parent.name, adapter_name, Vector([0,0,0]), 'Correctives')
    bpy.ops.object.mode_set(mode='EDIT')
    arm.data.edit_bones[bone].parent = arm.data.edit_bones[adapter_name]

def add_helper_jc_bones(arm):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    for s in 'L','R':
        insert_adapter_bone(arm, 'cf_J_LegUp01_s_'+s, 'cf_J_LegUp01_dam_'+s)
        insert_adapter_bone(arm, 'cf_J_LegUp02_s_'+s, 'cf_J_LegUp02_dam_'+s)
        insert_adapter_bone(arm, 'cf_J_LegLow01_s_'+s, 'cf_J_LegLow01_dam_'+s)
        insert_adapter_bone(arm, 'cf_J_LegLow02_s_'+s, 'cf_J_LegLow02_dam_'+s)
    bpy.ops.object.mode_set(mode='OBJECT')

def repaint_upper_neck(arm, body):
    vg = vgroup(body, ["cf_J_Head_s","cf_J_FaceRoot_s","cf_J_FaceRoot_r_s"])
    for x in vg:
        wf = get_weight(body, x, "cf_J_FaceRoot_s") 
        wr = get_weight(body, x, "cf_J_FaceRoot_r_s")
        w = get_weight(body, x, "cf_J_Head_s") + wf + wr
        co = body.data.vertices[x].co
        z = co[1]-15.348+(co[2]-0.08128)*0.2
        span = 0.40 - 0.40*co[2]
        set_weight(body, x, "cf_J_Head_s", w*sigmoid(z, 0, span))
        rear_ratio = 1.-max(0,min(1,(co[2]+0.25)*2.))
        set_weight(body, x, "cf_J_FaceRoot_s", w*(1.-sigmoid(z, 0, span))*(1.-rear_ratio))
        set_weight(body, x, "cf_J_FaceRoot_r_s", w*(1.-sigmoid(z, 0, span))*rear_ratio)


def repaint_head(arm, body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Blur the transition from upper neck to head, making cf_J_FaceRoot_s somewhat more usable
    repaint_upper_neck(arm, body)

    # Above pupil level, partially transfer nose weight to faceup 
    # (because, as painted, NoseBridge's effect extends well into the forehead)
    repaint_nose_bridge(arm, body)

    # Completely dissolve a pesky and inconvenient VG
    #dissolve_facelow_s(arm, body, bm)

    create_nasolabial(arm, body, bm)
    create_nose_cheek(arm, body, bm)
    restrict_nosebase(arm, body, bm)
    jaw_edge(arm, body, bm)

    #reassign_cheekup2(arm, body, bm)
    create_chin_cheek(arm, body, bm)

    add_nostrils(arm, body, bm)

    bm.free()
