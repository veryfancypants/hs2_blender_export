import bpy
import mathutils
import os
import bmesh
import math
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy
from .importer import replace_mat, set_tex, set_bump, join_meshes, disconnect_link
import time
import random

from . import armature

from .attributes import set_attr

def clamp01(x):
    return max(0.0, min(1.0, x))

def make_child_bone(arm, parent, name, offset, collection, rotation_mode='XYZ', tail_offset=None, copy=''):
    if name in arm.pose.bones:
        return
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.data.edit_bones.new(name)
    bone.parent = arm.data.edit_bones[parent]
    bone.head = arm.data.edit_bones[parent].head+offset
    if tail_offset is None:
        bone.tail = arm.data.edit_bones[parent].tail+offset
    else:
        bone.tail = bone.head+tail_offset
    arm.data.collections[collection].assign(bone)
    arm.data.collections['Everything'].assign(bone)
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones[name].rotation_mode='XYZ'
    try:
        arm["deformed_uncustomized_rig"][name]=arm.pose.bones[name].matrix_basis.copy()
    except:
        pass
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
    if vertex==843:
        print("set_weight", vertex, body.vertex_groups[group].name, weight)
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
        for g,w0 in zip(group, wts):
            add_weight(body, vertex, g, weight*w0/wtot)
        return

    if isinstance(group, str):
        group = body.vertex_groups[group].index
    if vertex==12306:
        print("add_weight", vertex, body.vertex_groups[group].name, weight)
    for g in body.data.vertices[vertex].groups:
        if g.group==group:
            g.weight+=weight
            return
    body.vertex_groups[group].add([vertex], weight, 'ADD')

def vgroup(obj, name, min_wt=None):
    if min_wt is None:
        min_wt = -1.0
    if isinstance(name, list):
        ids = [obj.vertex_groups[vg].index for vg in name if vg in obj.vertex_groups]
        return [x for x in range(len(obj.data.vertices)) if any([(g.group==id and g.weight>=min_wt) for g in obj.data.vertices[x].groups for id in ids])]

    if not name in obj.vertex_groups:
        return []

    id=obj.vertex_groups[name].index
    if min_wt is None:
        return [x for x in range(len(obj.data.vertices)) if id in [g.group for g in obj.data.vertices[x].groups]]
    else:
        return [x for x in range(len(obj.data.vertices)) if any([(g.group==id and g.weight>=min_wt) for g in obj.data.vertices[x].groups])]


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
        if x==12479:
            print("split_vgroup", x, name, vg, wold, frac)
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
    v = vgroup(body, vg)
    for x in v:
        uv = bm.verts[x].link_loops[0][lay].uv
        sk.data[x].co += func(uv=uv, vert=x, co=body.data.vertices[x].undeformed_co, norm=body.data.vertices[x].normal)
    body.data.shape_keys.key_blocks[name].value=1. if on else 0.
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


def curve_interp(curve, x, xsymm = None, cubic=False, debug=False):
    if debug:
        print(curve, x)
    if xsymm is not None and x>xsymm:
        x = xsymm - (x-xsymm)
    if x<=curve[0][0]:
        return curve[0][1]
    if x>=curve[-1][0]:
        return curve[-1][1]
    for k in range(len(curve)-1):
        if x>=curve[k][0] and x<curve[k+1][0]:
            if debug:
                print(x, curve[k][0], curve[k+1][0], curve[k][1], curve[k+1][1])
            return interpolate(curve[k][1], curve[k+1][1], curve[k][0], curve[k+1][0], x)


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

#
#
#  NEW SHAPE KEYS
#
#

def eye_shape(arm, body, bm, on=True):
    print("eye_shape")
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

    def formula(vert, co, norm, uv, **kwargs):#for x in set(list(v)):
        x=vert
        #co = body.data.vertices[x].co.copy()
        sign = -1 if co[0]>0 else 1

        if co[0]>0:
            co=Vector((co[0]*-1., co[1], 0.))
        #en = [None, 1e10, None]
        y = min(eyeball, key=lambda z: (co-body.data.vertices[z].co).length)
        r = co-body.data.vertices[y].co
        n = body.data.vertices[y].normal
        dot = n.dot(r)
        effect = Vector([0,0,0])
        if r.length<0.10 and dot<=0.01:
            effect = (co-eyeball_center)
            effect[2] = 0.0
            l=effect.length
            effect -= n*effect.dot(n)
            effect.normalize()
            effect *= l*interpolate(0.15, 0, 0.005, 0.010, dot)
            effect[0] *= sign

            w01 = get_weight(body, x, 'cf_J_Eye01_s_L')+get_weight(body, x, 'cf_J_Eye01_s_R')
            w02 = get_weight(body, x, 'cf_J_Eye02_s_L')+get_weight(body, x, 'cf_J_Eye02_s_R')
            w04 = get_weight(body, x, 'cf_J_Eye04_s_L')+get_weight(body, x, 'cf_J_Eye04_s_R')
            if w02<0.05 and w01+w04>0.800:
                #if x==12813:
                #    print("Correction", interpolate(0, -1, 0.800, 1.000, w01+w04), interpolate(1, 0, 0.2, 0.4, w04/(w01+w04)) )
                effect += effect*interpolate(0, -1, 0.800, 1.000, w01+w04) * bump(w04/(w01+w04), 0, 0.2, 0.4) * (2 if dot<0 else 1)
            #if vert==9742:
            #    print(vert, r.length, n, dot)

        if uv[0]>0.500:
            uv=(1-uv[0],uv[1])
        if uv[0]>=0.383 and uv[0]<=0.441 and uv[1]<0.518:
            lower_lid_fold = curve_interp(lower_lid_low_curve, uv[0])
            w_x = bump(uv[0], 0.383, 0.408, 0.441, shape='cos')
            w_y = max(0, 1.-abs(uv[1]-lower_lid_fold)/(0.518-lower_lid_fold))
            #if vert==9742:
            #    print(vert, w_x, w_y)
            effect[2] += -0.01*w_x*w_y

        return effect

    create_functional_shape_key(body, 'Eye shape', ['cf_J_Eye01_s_R','cf_J_Eye02_s_R','cf_J_Eye03_s_R','cf_J_Eye04_s_R',
        'cf_J_Eye01_s_L','cf_J_Eye02_s_L','cf_J_Eye03_s_L','cf_J_Eye04_s_L'], formula, on = on, bm = bm)
    #body.data.shape_keys.key_blocks["Eye shape"].value=1. if on else 0.


def find_nearest(mesh, v, cands):
    a=cands[0]
    for x in cands:
        if (mesh.vertices[x].co-v).length<(mesh.vertices[a].co-v).length:
            a=x
    return a

def tweak_nose(arm, body, bm, on):
    print("tweak_nose")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    #bpy.ops.object.mode_set(mode='EDIT')
    if not 'cf_J_Nose_tip' in body.vertex_groups:
        return
    idx_nose_base = body.vertex_groups['cf_J_NoseBase_s'].index
    idx_nose = body.vertex_groups['cf_J_Nose_t'].index
    idx_tip = body.vertex_groups['cf_J_Nose_tip'].index
    idx_l = body.vertex_groups['cf_J_NoseWing_tx_L'].index
    idx_r = body.vertex_groups['cf_J_NoseWing_tx_R'].index
    if 'cf_J_CheekMid_L' in body.vertex_groups:
        idx_cheek_l = body.vertex_groups['cf_J_CheekMid_L'].index
        idx_cheek_r = body.vertex_groups['cf_J_CheekMid_R'].index
    else:
        idx_cheek_l = body.vertex_groups['cf_J_CheekUp_L'].index
        idx_cheek_r = body.vertex_groups['cf_J_CheekUp_R'].index

    tip=vgroup(body, 'cf_J_Nose_tip')
    nose=vgroup(body, 'cf_J_Nose_t')

    sk = body.shape_key_add(name='Nostril pinch')
    sk.interpolation='KEY_LINEAR'
    for x in range(len(body.data.vertices)):
        sk.data[x].co = body.data.shape_keys.key_blocks["Basis"].data[x].co

    #create_functional_shape_key(body, 'Nostril pinch', ['cf_J_Nose_tip','cf_J_Nose_t'], formula)

    for x in tip:
        wc = get_weight(body, x, idx_tip)
        wl = get_weight(body, x, idx_l)
        wr = get_weight(body, x, idx_r)
        delta = min(wc, max(wl,wr))
        dp = body.data.vertices[x].normal[1] + body.data.vertices[x].normal[2]
        if dp>0:
            sk.data[x].co[0] -= 0.05*delta*dp*(-1 if wr>wl else 1)
            sk.data[x].co[2] -= 0.05*delta*dp

    deltas={}
    for x in nose:
        wn = get_weight(body, x, idx_nose)+get_weight(body, x, idx_nose_base)
        wch = get_weight(body, x, idx_cheek_l)+get_weight(body, x, idx_cheek_r)

        wc = get_weight(body, x, idx_tip)
        wl = get_weight(body, x, idx_l)
        wr = get_weight(body, x, idx_r)
        no = body.data.vertices[x].normal
        norm = -no[1]+no[2]
        if wl<wn and wr < wn and wc < wn and wn>0.1 and no[1]<0 and norm>0.8:
            effect = (1.0-max(wl,wr)/wn) * (1.-wc/wn) * sigmoid(norm, 1.1, 0.8) #min(1.0, (norm-1.0)/0.2)
            no2 = Vector([no[0], -1.0, 0.5])
            no2.normalize()
            deltas[x] = 0.02*effect*no2

        if wch>0.050 and wn>0.200 and wr>0.600 and no[2]>0.3 and no[0]<-0.3:
            deltas[x] = Vector([-0.01, 0, 0])*sigmoid(no[2], 0.6, 0.3)*sigmoid(no[0], -0.6, -0.3)
        if wch>0.050 and wn>0.200 and wl>0.600 and no[2]>0.3 and no[0]>0.3:
            deltas[x] = Vector([0.01, 0, 0])*sigmoid(no[2], 0.6, 0.3)*sigmoid(no[0], 0.6, 0.3)

    for x in deltas:
        sk.data[x].co -= deltas[x]

    body.data.shape_keys.key_blocks["Nostril pinch"].value=1. if on else 0.

def add_mouth_blendshape(body, bm):
    """
    obj=body
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = obj

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    """
    if not 'cf_J_CheekLow_L' in bpy.context.active_object.vertex_groups: # custom head
        return 
    if not 'cf_J_Mouthup' in bpy.context.active_object.vertex_groups: # custom head
        return 
    #idx_up = body.vertex_groups['cf_J_Mouthup'].index
    #idx_dn = body.vertex_groups['cf_J_MouthLow'].index

    cheek=vgroup(body, 'cf_J_CheekLow_L')
    mlow = vgroup(body, 'cf_J_MouthLow')
    mhigh = vgroup(body, 'cf_J_Mouthup')
    mcav = vgroup(body, 'cf_J_MouthCavity')

    # approximate location of the left mouth corner
    mcorn=weighted_center('cf_J_Mouth_L')
    mcorn[0]+=0.02

    # center of left cheek
    mcent=mcorn.copy()
    mcent[0]=0
    #ccent=0.5*(weighted_center('cf_J_CheekLow_L')+weighted_center('cf_J_CheekUp_L'))
    ccent=weighted_center('cf_J_CheekLow_L')

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
        if vert==13140 or vert==17875:
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
        (0.450,0.352),
        (0.485,0.371),
        ]
        wx = sigmoid(uv[0],0.465,0.450) * sigmoid(uv[0], 0.535, 0.550)
        effect1 = bump(uv[1], curve_interp(curve, uv[0],xsymm=True), None, 0.399, shape='cos') * Vector([0, -0.01, -0.01])
        return effect1
    boy = (body['Boy']>0.0)
    create_functional_shape_key(body, 'Upper lip trough', 'cf_J_Mouthup', formula, on = on and (not boy), bm = bm)

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
    create_functional_shape_key(body, 'Lip arch', ['cf_J_Mouthup','cf_J_MouthLow', 'cf_J_ChinTip_s', 'cf_J_MouthBase_s'], formula,
            max=2.0, on=on and not boy, bm = bm)

def eyelid_crease(arm, body, bm, on=True):
    print("eyelid_crease")
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
        r=Vector(uv)-Vector([0.265,0.567])
        r[1]*=0.5

        r2 = Vector(uv)-Vector([0.316, 0.540])
        if r2[1]<0.0:
            r2[1]=min(0.0, r2[1]+0.05)
        r2[1]*=0.5
        return (sigmoid(r.length, 0, 0.05)-sigmoid(r2.length,0,0.025)*0.5) * Vector([0.025*sign, 0, 0])

    create_functional_shape_key(body, 'Temple depress', ['cf_J_FaceUp_tz','cf_J_CheekUp_L','cf_J_CheekUp_R'], formula, on=on, bm = bm)

def jaw_soften(arm, body, bm, on=True):
    #if not 'Jaw edge' in body.vertex_groups:
    #    body.vertex_groups.new(name='Jaw edge')
    #idx = body.vertex_groups['Jaw edge'].index
    #exclude_vg = vgroup(body, ['cf_J_FaceRoot_s'])
    curve=[
    (0.223, 0.244),
    (0.326, 0.213),
    (0.418, 0.218),
    (0.500, 0.224)
    ]
    def formula(uv, vert, norm, co, **kwargs):
        #if vert in exclude_vg:
        #    return Vector([0,0,0])
        #set_weight(body, vert, idx, bump(norm[1], -0.9, -0.6, -0.3))
        #return norm * bump(norm[1], -0.9, -0.6, -0.3) * -0.01 * abs(co[0]*2)
        pos = uv[1] - curve_interp(curve, uv[0], xsymm=True)
        if uv[0]>0.5:
            uv=(1-uv[0],uv[1])
        effect = bump(pos, -2*width, 0, width, shape='cos') * (1. + bump(uv[0], 0.43, 0.46, 0.49, shape='cos'))
        if vert==6872:
            print(vert, uv, pos, bump(pos, -2*width, 0, width, shape='cos'), (1. + bump(uv[0], 0.43, 0.46, 0.49, shape='cos')) )

        return norm * -0.01 * effect

    width = 0.035
    create_functional_shape_key(body, 'Jaw soften', ['cf_J_ChinLow'], formula, on=False, bm=bm)
    width = 0.060
    create_functional_shape_key(body, 'Jaw soften more', ['cf_J_ChinLow'], formula, on=on, bm=bm)

def add_shape_keys(arm, body, on):
    t1=time.time()
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm_owned = True
    # these are off by default:
    # Smile shape key
    print(13509, body.data.vertices[13509].co, body.data.vertices[13509].undeformed_co)
    add_mouth_blendshape(body, bm)
    if body['Boy']>0:
        adams_apple_delete(arm, body, bm)
    # these are on by default (possibly depending on gender) unless "Extend" is off:
    tweak_nose(arm, body, bm, on=on)
    eye_shape(arm, body, bm, on=on)
    eyelid_crease(arm, body, bm, on=on)
    upper_lip_shapekey(arm, body, bm, on=on)
    lip_arch_shapekey(arm, body, bm, on=on)
    temple_depress(arm, body, bm, on=on)
    forehead_flatten(arm, body, bm, on=on)
    jaw_soften(arm, body, bm, on=on)
    print(13509, body.data.vertices[13509].co, body.data.vertices[13509].undeformed_co)
    bm.free()
    t2=time.time()
    print("%.3f s to add shape keys" % (t2-t1))
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

    #heights = [x.data.vertices[y].co[1] for y in v]
    #heights.sort()
    #hmid = heights[len(heights)//2]
    #hmid = 15.895
    #hmin = heights[0]

    bm = bmesh.new()
    bm.from_mesh(x.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Retag as 'mouth cavity' any verts in 'cf_J_MouthBase_s' with normals pointing toward char's back
    # (this corrects several verts inside mouth corners)
    for y in v2:
        #if y==7456:
        #    print("Normal", x.data.vertices[y].normal)
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

def add_skull_soft_neutral(arm, body):
    split_vgroup(body, "cf_J_ChinFront_s", 'cf_J_Chin_rs', lambda co, **kwargs: sigmoid(co[2], 0.40, 0.15))
    split_vgroup(body, "cf_J_FaceUpFront_ty", 'cf_J_FaceUp_ty', lambda co, **kwargs: max(0,min(0.5,(co[2]+0.25)*2.)))
    split_vgroup(body, 'cf_J_FaceRoot_r_s', "cf_J_FaceRoot_s", lambda co, **kwargs: 1.-max(0,min(1,(co[2]+0.25)*2.)))

    id_l = body.vertex_groups['cf_J_CheekUp_L'].index
    id_r = body.vertex_groups['cf_J_CheekUp_R'].index
    # Correct these two VGs by making sure they are only present on their respective sides
    v_l=vgroup(body, 'cf_J_CheekUp_L')
    for x in v_l:
        if body.data.vertices[x].co[0]<0 :
            print("Removing", x, body.data.vertices[x].co, "from CheekUp_L", get_weight(body, x, id_l))
            set_weight(body, x, id_l, 0.0)
    v_r=vgroup(body, 'cf_J_CheekUp_R')
    for x in v_r:
        if body.data.vertices[x].co[0]>0:
            set_weight(body, x, id_r, 0.0)

    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    v_r=vgroup(body, 'cf_J_CheekUp_R', min_wt=0.01)
    
    vs = body.data.vertices
    hl = [0.5*vs[y].co[1]+abs(vs[y].co[0]) for y in v_r]
    hl.sort()
    minpos = hl[0]
    midpos = hl[len(hl)//2]
    maxpos = hl[-1]
    #print("minpos", minpos, "midpos", midpos, "maxpos", maxpos)
    #vs = body.data.vertices
    def mid_fraction(co, vert, **kwargs):
        h = 0.5*co[1]+abs(co[0])
        return 1.-(h-minpos)/(maxpos-minpos)
    split_vgroup(body, 'cf_J_CheekMid_L', 'cf_J_CheekUp_L', mid_fraction, bm=bm)
    split_vgroup(body, 'cf_J_CheekMid_R', 'cf_J_CheekUp_R', mid_fraction, bm=bm)

    make_child_bone(arm, 'cf_J_Chin_rs', 'cf_J_ChinFront_s', Vector([0,0,0.02]), "Chin")
    make_child_bone(arm, 'cf_J_FaceUp_ty', 'cf_J_FaceUpFront_ty', Vector([0,0,0.02]), "Head internal")
    make_child_bone(arm, 'cf_J_FaceRoot_s', 'cf_J_FaceRoot_r_s', Vector([0,0,-0.02]), "Head internal")

    make_child_bone(arm, 'cf_J_FaceLow_s', 'cf_J_FaceLow_s_s', Vector([0, 0, 0.01]), "Head internal")
    make_child_bone(arm, 'cf_J_Nose_t', 'cf_J_Nose_t_s', Vector([0,0,0.02]), "Nose")

    make_child_bone(arm, 'cf_J_CheekUp_L', 'cf_J_CheekMid_L', Vector([-0.1, 0, 0]), "Cheeks")
    make_child_bone(arm, 'cf_J_CheekUp_R', 'cf_J_CheekMid_R', Vector([0.1, 0, 0]), "Constrained - soft", copy='lrs')

    body.vertex_groups['cf_J_FaceLow_s'].name = 'cf_J_FaceLow_s_s'
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
        t = co[1]-co[2]
        if t>=15.75 and co[1]-0.5*abs(co[0])>=16.45:
            wold = get_weight(body, v, id_nose_t) + get_weight(body, v, id_bridge)
            wb = min(wold, sigmoid(co[1], 16.45, 16.70))
            wold += get_weight(body, v, id_base)
            set_weight(body, v, id_base, 0.0)
            set_weight(body, v, id_nose_t, 0)
            set_weight(body, v, id_bridge, wb)
            add_weight(body, v, id_faceup, wold-wb)

def add_spine_rear_soft(arm, body):
    bpy.ops.object.mode_set(mode='OBJECT')  
    bpy.context.view_layer.objects.active = arm
    for n in ['1','2','3']:
        split_vgroup(body, 'cf_J_Spine0'+n+'_r_s', 'cf_J_Spine0'+n+'_s', lambda co,**kwargs: 1.-max(0,min(1,(co[2]+0.5)*2.)))
        # 15.63 -0.74 -> 15.27 0.08  0.36 
    split_vgroup(body, 'cf_J_NeckUp_s', 'cf_J_Neck_s', lambda co,**kwargs:  max(0,min(1,(co[1]+co[2]*0.44-15.30)/0.6+0.5)))
    split_vgroup(body, 'cf_J_NeckFront_s', 'cf_J_Neck_s', lambda co,**kwargs:  max(0,min(1,(co[2]+0.25)*2.)))
    bpy.ops.object.mode_set(mode='EDIT')
    for n in ['1','2','3']:
        make_child_bone(arm, 'cf_J_Spine0'+n+'_s', 'cf_J_Spine0'+n+'_r_s', Vector([0, 0, -0.02]), "Spine - soft")
    make_child_bone(arm, 'cf_J_Neck_s', 'cf_J_NeckFront_s', Vector([0,0,0.02]), "Spine - soft")
    make_child_bone(arm, 'cf_J_Neck_s', 'cf_J_NeckUp_s', Vector([0,0.1,0.02]), "Spine - soft")

def repaint_mouth_minimal(arm, body):
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

    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    lay = bm.loops.layers.uv['uv1']

    for n in mcands:
        uv = bm.verts[n].link_loops[0][lay].uv
        upper = (uv[1]>0.335) or (uv[1]>0.330 and body.data.vertices[n].normal[1]<0)
        if uv[1]>0.315 and uv[1]<0.355 and uv[0]>0.432 and uv[0]<0.568:
            wud=get_weight(body, n, "cf_J_MouthLow")+get_weight(body, n, "cf_J_Mouthup")
            set_weight(body, n, "cf_J_MouthLow", 0 if upper else wud)
            set_weight(body, n, "cf_J_Mouthup", wud if upper else 0)

    bm.free()

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

def repaint_face(arm, body):
    print("repaint_face")
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = arm
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
    
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Completely dissolve a pesky and inconvenient VG
    #dissolve_facelow_s(arm, body, bm)
    
    """
    for v, old_id, new_id, xw, c in ((v_l, old_id_l, new_id_l, -1.0, 'L'), (v_r, old_id_r, new_id_r, 1.0, 'R')):
        def mid_fraction(co, **kwargs):
            h = xw*0.5*co[1]+co[0]
            return (h-minpos)/(maxpos-minpos)

        split_vgroup(body, 'cf_J_CheekMid_'+c, 'cf_J_CheekUp_'+c, mid_fraction, bm=bm)
    """
    curve=[
    (0.332, 0.434),
    (0.394, 0.443),
    (0.450, 0.456),
    ]
    # VG with support along the lines from lip corners to nose corners
    def weight_nasolabial(uv, **kwargs):
        y_weight = bump(uv[1], 0.332, 0.391, 0.450, shape='cos')
        fold = curve_interp(curve, uv[1])
        if uv[0]>=0.5:
            uv=(1.0-uv[0], uv[1])
        if uv[0]>fold:
            x_weight = max(0.0, 1.-abs(uv[0]-fold)/(0.500-fold))
        else:
            x_weight = max(0.0, 1.-abs(uv[0]-fold)/0.060)
        return x_weight * x_weight * y_weight * 0.5
    print("Creating cf_J_Nasolabial_s")
    create_functional_vgroup(body, "cf_J_Nasolabial_s", ["cf_J_NoseBase_s", "cf_J_MouthBase_s"], weight_nasolabial, bm=bm)
    print("Creating cf_J_NoseCheek_s")
    def weight_nose_cheek(co, vert, **kwargs):
        return sigmoid(1-6.0*abs(co[0]), 0, 1) * sigmoid(co[1], 16.2, 16.0) * sigmoid(co[1], 16.4, 16.6)
    split_vgroup(body, 'cf_J_NoseCheek_s', ['cf_J_NoseBase_s','cf_J_NoseBridge_s'], weight_nose_cheek, bm = bm)
    """
    v=vgroup(body, ['cf_J_NoseBase_s','cf_J_NoseBridge_s'], min_wt=0.001)
    for y in v:
        co = vs[y].co
        frac = sigmoid(1-6.0*abs(co[0]), 0, 1) * sigmoid(co[1], 16.2, 16.0)
        old_weight = get_weight(body, y, id_base)
        old_wb = get_weight(body, y, id_bridge)
        #old_wb2 = get_weight(body, y, nb2)
        #if old_weight*frac>0.005:
        set_weight(body, y, id_base, old_weight*(1.-frac))
        set_weight(body, y, id_bridge, old_wb*(1.-frac))
        #set_weight(body, y, nb2, old_wb2*(1.-frac))
        set_weight(body, y, id_nosecheek, (old_weight+old_wb)*frac)
    """

    make_child_bone(arm, 'cf_J_FaceBase', 'cf_J_Nasolabial_s', Vector([0,-0.15,0.8]), "Nose", tail_offset=Vector([0, 0.1, 0]))
    make_child_bone(arm, 'cf_J_NoseBase_s', 'cf_J_NoseCheek_s', Vector([0, 0.2, 0.01]), "Nose")


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
    print("Candidate mesh:", mesh.name, "boundary", len(v), "verts")
    boundary=[min([Vector((body.matrix_world @ y.co)-z).length for z in v])<0.0015 for y in body.data.vertices]
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
    vm = vgroup(body, "Stitch Mesh")
    main_mesh = [x for x in range(len(body.data.vertices)) if not x in vm]
    vs = body.data.vertices

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bmd = bmesh.new()
    bmd.from_mesh(body.data)

    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    lay = bmd.loops.layers.uv['uv1']
    def uv(x):
        return bmd.verts[x].link_loops[0][lay].uv

    stitch = []
    for x in v:
        nearest = min([x for x in main_mesh], key=lambda y: (uv(y)-uv(x)).length)
        stitch.append([x,nearest]) #bmd.verts[x], bmd.verts[nearest]])

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

    if selected>=len(body.data.vertices)/4:
        erase=[]

    #for x in stitch:
    #    print("Joining", x)
    #    bmesh.ops.pointmerge(bmd, verts=[bmd.verts[x[0]],bmd.verts[x[1]]], merge_co=bmd.verts[x[0]].co)
    bmesh.ops.weld_verts(bmd,targetmap={bmd.verts[x[0]]:bmd.verts[x[1]] for x in stitch})
    bmd.verts.ensure_lookup_table()
    if len(erase)>0: 
        erase = [bmd.verts[y] for y in erase]
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
    old_id = body.vertex_groups['cf_J_Kosi02_s'].index
    #old_id_r = body.vertex_groups['cf_J_CheekUp_R'].index
    new_id =  body.vertex_groups['cf_J_Perineum'].index
    v=vgroup(body, 'cf_J_Kosi02_s')
    if not 'cf_J_Ana' in body.vertex_groups:
        body.vertex_groups.new(name='cf_J_Ana')
    id_ana = body.vertex_groups['cf_J_Ana'].index

    leg1 = body.vertex_groups['cf_J_LegUp01_s_L'].index
    leg2 = body.vertex_groups['cf_J_LegUp01_s_R'].index
    s1 = body.vertex_groups['cf_J_Siri_s_L'].index
    s2 = body.vertex_groups['cf_J_Siri_s_R'].index

    undef=body.data.shape_keys.key_blocks['Basis'].data

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
        if opts[0] is not None:
            adapter=clone_object(bpy.data.objects[opts[0]])
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
        print("Setting Subsurface failed")
        disconnect_link(mat, 'Subsurface')
    else:
        mat.node_tree.nodes['Group.004'].inputs['Subsurface/MainTex mix'].default_value=0.2

    
    if False:
        edge = vgroup(mesh, 'cf_J_ExhaustEdge')
        kosi = vgroup(body, 'cf_J_Kosi02_s')
        #arm.data.pose_position='REST'  
        #bpy.context.view_layer.objects.active = mesh
        #bpy.ops.object.mode_set(mode='EDIT')
        matrix_world_inv = mesh.matrix_world.inverted()
        bm = bmesh.new()
        bm.from_mesh(mesh.data)
        bm.verts.ensure_lookup_table()
        undeformed_basis=body.data.shape_keys.key_blocks['Basis'].data
        total_disp=Vector([0,0,0])
        for x in edge:
            #n = len(bm.verts)
            #errors=[bm.verts[x].co - undeformed[x].co for x in range(n)]        
            co = mesh.matrix_world @ mesh.data.vertices[x].co
            new_pos = co
            min_len=1e8
            for y in kosi:
                length = ((body.matrix_world @ undeformed_basis[y].co) - co).length
                if length < min_len:
                    min_len = length
                    new_pos = body.matrix_world @ undeformed_basis[y].co
            total_disp+=(matrix_world_inv @ new_pos)-bm.verts[x].co
        total_disp *= 1./len(edge)
        for x in bm.verts:
            x.co += total_disp
        for x in edge:
            co = mesh.matrix_world @ bm.verts[x].co
            new_pos = co
            min_len=1e8
            for y in kosi:
                length = ((body.matrix_world @ undeformed_basis[y].co) - co).length
                if length < min_len:
                    min_len = length
                    new_pos = body.matrix_world @ undeformed_basis[y].co
            disp = new_pos - co
            axis = Vector([0, -0.2, 0.98])
            disp = (disp @ axis) - 0.02
            #print(co, disp)
            disp = axis * disp
            co += disp
            bm.verts[x].co = matrix_world_inv @ co
        bm.to_mesh(mesh.data)

    #center = weighted_center('cf_J_ExhaustValve')
    center = Vector([0, 9.4, -0.5])
    bpy.context.view_layer.objects.active = arm
    arm.data.pose_position='POSE'  
    bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.data.edit_bones.new('cf_J_ExhaustValve')
    parent=arm.data.edit_bones['cf_J_Ana']
    bone.head = arm.data.edit_bones['cf_J_Ana'].head
    bone.tail = (arm.data.edit_bones['cf_J_Ana'].head+arm.data.edit_bones['cf_J_Ana'].tail)/2
    bone.parent = parent
    arm.data.collections['Genitals'].assign(bone)
    arm.data.collections['Everything'].assign(bone)
    #bone.layers = parent.layers

    bone = arm.data.edit_bones.new('cf_J_ExhaustClench')
    parent=arm.data.edit_bones['cf_J_Ana']
    bone.head = (arm.data.edit_bones['cf_J_Ana'].head+arm.data.edit_bones['cf_J_Ana'].tail)/2
    bone.tail = arm.data.edit_bones['cf_J_Ana'].tail
    bone.parent = parent
    arm.data.collections['Genitals'].assign(bone)
    arm.data.collections['Everything'].assign(bone)

    bone3 = arm.data.edit_bones.new('cf_J_Perineum')
    bone3.head = Vector([0, 9.4, -0.2])
    bone3.tail = bone3.head+Vector([0, 0.2, 0.0])
    bone3.parent = arm.data.edit_bones['cf_J_Kosi02_s']
    arm.data.collections['Genitals'].assign(bone3)
    arm.data.collections['Everything'].assign(bone3)

    #bpy.context.view_layer.objects.active = arm

    bpy.ops.object.mode_set(mode='OBJECT')
    arm.data.pose_position='REST'

    fit_mesh = [0,None]
    for m in cand_meshes:
        ratio = test_alignment(body, m)
        print(m, ratio)
        #ok = excise_neuter_mesh(body, m)
        if ratio>fit_mesh[0] or fit_mesh[1] is None:
            fit_mesh = [ratio, m]

    #return
    print("Fit:", fit_mesh)
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
    #mesh = fit_mesh

    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.object.active_shape_key_index = 0

    uv_stitch(body, fit_mesh[1])

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
    #return
    arm.select_set(True)
    injector.select_set(True)
    #print("Joining", injector, "to", arm)
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
    # can't join because I want to be able to turn it on and off
    #join_meshes([body.name, injector_sheath.name])

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

def paint_nostrils_v1(arm, body):
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    count=0
    lay = bm.loops.layers.uv['uv1']

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

    nl = 0
    print(len(v), "candidate nostril verts")
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

        # 'cf_J_Nose_tip' support: oval around (0.500,0.440), squished on the nostril side
        r4 = uv-Vector([0.5000,0.436])
        if r4[1]<0.0:
            r4[1]*=2.0
        else:
            r4[1] /= 2.0
        r4 = math.sqrt(r4[0]*r4[0]+r4[1]*r4[1])
        wttip = 0.5*sigmoid(r4, 0.036)

        wwl = get_weight(body, x, "cf_J_NoseWing_tx_L")
        wwr = get_weight(body, x, "cf_J_NoseWing_tx_R")
        w_nose_base = get_weight(body, x, "cf_J_NoseBase_s")
        w_nose_t = get_weight(body, x, id_tt)
        w_nose_tip = get_weight(body, x, id_t)
        #w_nose_bridge2 = get_weight(body, x, id_b)

        if x==12306:
            print("wtl", wtl, "wtr", wtr, "wtc", wtc, "wtt", wttip)
            for g in body.data.vertices[x].groups:
                print(body.vertex_groups[g.group].name, g.weight)

        s = wwl+wwr+wtl+wtr+wtc+wttip
        if s>0.001:
            budget = w_nose_t+w_nose_tip+wwr+wwl+w_nose_base #+w_nose_bridge2
            base_blend = sigmoid(uv[1], 0.385, 0.410)*sigmoid(uv[1], 0.450, 0.475)
            t_blend = 0.5*sigmoid(uv[1], 0.440, 0.420)+0.5*sigmoid(uv[1], 0.475, 0.450)
            blend = base_blend+t_blend
            wwl,wwr,wtl,wtr,wtc,wttip = [y*budget*(1-blend)/s for y in (wwl,wwr,wtl,wtr,wtc,wttip)]

            set_weight(body, x, id_l, wtl)
            set_weight(body, x, id_r, wtr)
            set_weight(body, x, id_c, wtc)
            set_weight(body, x, id_t, wttip)
            set_weight(body, x, id_wl, wwl)
            set_weight(body, x, id_wr, wwr)
            set_weight(body, x, id_base, budget*base_blend)
            set_weight(body, x, id_tt, budget*t_blend)
            #set_weight(body, x, "cf_J_Nose_t", 0)
        else:
            #delta = w_nose_t*tt_suppress
            if uv[1]<0.420:
                set_weight(body, x, id_base, w_nose_base+w_nose_t)
                set_weight(body, x, id_tt, 0)
            if uv[1]>0.475:
                set_weight(body, x, id_base, 0)
                set_weight(body, x, id_tt, w_nose_base+w_nose_t)
        """
                #wtt=0.0
                #wtbase=0.0
            else:
                wtt=1.0-(wtl+wtr+wtc+wttip)
                tt_suppress = sigmoid(uv[1], 0.400, 0.420)
                wtbase = wtt*tt_suppress
                wtt *= 1.-tt_suppress

            w_nose_t = get_weight(body, x, id_tt)
            w_nose_base = get_weight(body, x, "cf_J_NoseBase_s")
            w_nose_tip = get_weight(body, x, id_t)
            w_nose_wing_l = get_weight(body, x, "cf_J_NoseWing_tx_L")
            w_nose_wing_r = get_weight(body, x, "cf_J_NoseWing_tx_R")

            budget = w_nose_t+w_nose_base+w_nose_tip+w_nose_wing_l+w_nose_wing_r
            #if tt_suppress>0.0:
            #    budget += w_nose_t*tt_suppress
            #    w_nose_t *= (1.-tt_suppress)
            #effect = wtl+wtr+wtc+wtt

            #assert (wtl+wtr+wtc+wtt)*
            #check_sum = (wtl+wtr+wtc+wtt)*budget + (w_nose_wing_l+w_nose_wing_r+w_nose_base+w_nose_t)*(1-effect)
            #check_sum = effect*budget + (w_nose_wing_l+w_nose_wing_r+w_nose_base+w_nose_t)*(1-effect)

            set_weight(body, x, id_l, wtl*budget)
            set_weight(body, x, id_r, wtr*budget)
            set_weight(body, x, id_c, wtc*budget)
            set_weight(body, x, id_t, wttip*budget)
            set_weight(body, x, "cf_J_NoseWing_tx_L", w_nose_wing_l*(1-effect))
            set_weight(body, x, "cf_J_NoseWing_tx_R", w_nose_wing_r*(1-effect))
            set_weight(body, x, "cf_J_NoseBase_s", w_nose_base*(1-effect))
            set_weight(body, x, "cf_J_Nose_t", w_nose_t*(1-effect))
        """
        #if uv[1]<0.400:
        #    set_weight(body, x, id_tt, 0.0)

def paint_nostrils(arm, body):
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    count=0
    lay = bm.loops.layers.uv['uv1']

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

    nl = 0
    print(len(v), "candidate nostril verts")
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
        #w_nose_bridge2 = get_weight(body, x, id_b)

        effect = wtl+wtr+wtc

        transfer_tt_base = sigmoid(uv[1], 0.395, 0.420)#+sigmoid(uv[1], 0.475, 0.450)
        transfer_base_tt = sigmoid(uv[1], 0.475, 0.450)#+sigmoid(uv[1], 0.475, 0.450)

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


def add_nostrils(arm, body):
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
    paint_nostrils(arm, body)

    bpy.context.view_layer.objects.active = body
    bpy.ops.paint.weight_paint_toggle()
    bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=0.002)
    bpy.ops.paint.weight_paint_toggle()
    #bm.free()

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

# Not enabled, WIP
def tweak_nails(arm, body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.context.object.active_material_index = 1
    bpy.ops.object.material_slot_select()
    bpy.ops.mesh.region_to_loop()
    bpy.ops.mesh.subdivide(number_cuts=2, smoothness=1)

# Blur the transition from upper neck to head, making cf_J_FaceRoot_s somewhat more usable
def repaint_upper_neck(arm, body):
    print("Repainting upper neck ...")
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

