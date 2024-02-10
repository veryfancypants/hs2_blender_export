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

from . import armature

from .attributes import (
    get_eagerness,
    get_length,
    get_girth,
    get_volume,
    get_wet,
    get_sheath,
    set_eagerness,
    set_length,
    set_girth,
    set_volume,
    set_wet,
    set_sheath,
)

def vgroup(obj, name, min_wt=None):
    id=obj.vertex_groups[name].index
    if min_wt is None:
        return [x for x in range(len(obj.data.vertices)) if id in [g.group for g in obj.data.vertices[x].groups]]
    else:
        return [x for x in range(len(obj.data.vertices)) if any([(g.group==id and g.weight>=min_wt) for g in obj.data.vertices[x].groups])]

def vgroup2(obj, name1, name2):
    id1=obj.vertex_groups[name1].index
    id2=obj.vertex_groups[name2].index
    v=[x for x in range(len(obj.data.vertices)) if id1 in [g.group for g in obj.data.vertices[x].groups]]
    return [x for x in v if id2 in [g.group for g in obj.data.vertices[x].groups]]


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
#  Set lower jaw to cf_J_MouthCavity=0.2 cf_J_Chin_rs=0.8, upper jaw to cf_J_MouthCavity=1.0
#
def repaint_teeth(x):
    bpy.context.view_layer.objects.active = x
    x.modifiers['Armature'].show_in_editmode=True
    x.modifiers['Armature'].show_on_cage=True

    x.vertex_groups.new(name='cf_J_UpperJaw')
    x.vertex_groups.new(name='cf_J_LowerJaw')

    if 'Lower jaw' in x.vertex_groups:
        lower = x.vertex_groups['Lower jaw'].index
        #x.vertex_groups.new(name='cf_J_Chin_rs')
        #cavity = x.vertex_groups['cf_J_Mouth'].index
        for y in x.data.vertices:
            if get_weight(x, y.index, lower) > 0.0:
                x.vertex_groups['cf_J_LowerJaw'].add([y.index], 1.0, 'ADD')
            else:
                x.vertex_groups['cf_J_UpperJaw'].add([y.index], 1.0, 'ADD')
        if 'cf_J_MouthCavity' in x.vertex_groups:
            x.vertex_groups.remove(x.vertex_groups['cf_J_MouthCavity'])
            #if len(y.groups)>1:
            #    for g in y.groups:
            #       if g.group!=lower:
            #            g.weight = 0.2
            #    x.vertex_groups[index].add([y.index], 0.8, 'ADD')
        #x.vertex_groups['cf_J_Chin_rs'].name='cf_J_LowerJaw'
        #x.vertex_groups['cf_J_MouthCavity'].name='cf_J_UpperJaw'
        #x.vertex_groups['cf_J_Chin_rs'].add([y.index for y in v], 0.8, 'ADD')
        return

    ymin = min([y.co[1] for y in x.data.vertices])
    #print(ymin)
    v=[y.index for y in x.data.vertices if y.co[1]<ymin+0.01]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_all(action='DESELECT')
    #print(v)
    bpy.ops.object.mode_set(mode='OBJECT')
    x.data.vertices.foreach_set("select", [(y in v) for y in range(len(x.data.vertices))])
    #for y in v:
    #    y.select=True
    x.data.update()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_linked()
    bpy.ops.object.mode_set(mode='OBJECT')
    #v=[y for y in x.data.vertices if y.select]

    for y in x.data.vertices:
        if y.select:
            x.vertex_groups['cf_J_LowerJaw'].add([y.index], 1.0, 'ADD')
        else:
            x.vertex_groups['cf_J_UpperJaw'].add([y.index], 1.0, 'ADD')
    #print(v)
    #bpy.ops.
    #for y in v:
    #    if len(y.groups)>0:
    #        #y.groups[0].weight=0.4
    
    #x.vertex_groups.new(name='cf_J_Chin_rs')
    #x.vertex_groups['cf_J_LowerJaw'].add([y.index for y in v], 0.6, 'ADD')

def get_or_create_id(x, name):
    if not name in x.vertex_groups:
        x.vertex_groups.new(name=name)
    return x.vertex_groups[name].index

def repaint_mouth_cavity(x):
    chin_id = get_or_create_id(x, 'cf_J_Chin_rs')
    mouth_id = get_or_create_id(x, 'cf_J_MouthCavity')
    mouthlow_id = get_or_create_id(x, 'cf_J_MouthLow')
    mouth2_id = get_or_create_id(x, 'cf_J_MouthBase_s')
    face_id = get_or_create_id(x, 'cf_J_FaceLow_s')

    v=vgroup(x, 'cf_J_MouthCavity')
    v2=vgroup(x, 'cf_J_MouthBase_s')

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
            #if z.group==mouth2_id:
            #    z.weight=0.0
            #if z.group==face_id:
            #    z.weight=0.0
        if old_chw==0.0 and chw>0.0:
            x.vertex_groups['cf_J_Chin_rs'].add([y], chw, 'ADD')
def repaint_tongue(x):            
    x.vertex_groups[0].name='cf_J_Chin_rs'

def sigmoid(x, x_full=None, x_min=None):
    if x_full is not None:
        x = (x-x_full) / (x_min-x_full)
    if x<0:
        return 1.
    if x>1:
        return 0.
    return 0.5*(math.cos(x*3.141526)+1.)



# broken and probably can't be made to work anyway 
def dissolve_FaceLow_S(arm, body):
    facelow_id = body.vertex_groups['cf_J_FaceLow_s'].index
    facelow_offset = arm.pose.bones['cf_J_FaceLow_s'].location
    facelow_scale = arm.pose.bones['cf_J_FaceLow_s'].scale
    print("Dissolving FaceLow_s with offset", facelow_offset, "scale", facelow_scale)
    mw0 = armature.matrix_world(arm, 'cf_J_FaceLow_s').decompose()
    for b in ['cf_J_CheekLow_L', 'cf_J_CheekMid_L', 'cf_J_CheekUp_L', 'cf_J_Chin_rs', 'cf_J_ChinLow']:
        bone = arm.pose.bones[b]
        mw = armature.matrix_world(arm, b).decompose()
        if b=='cf_J_CheekLow_L':
            w_f = 0.50
        elif b=='cf_J_CheekMid_L':
            w_f = 0.10
        elif b=='cf_J_CheekUp_L':
            w_f = 0.35
        else:
            w_f = 0.25
        w_c = 1.-w_f

        v1 = Vector([1,1,1])
        d_f = facelow_offset
        ds_f = facelow_scale - v1
        ds_c = bone.scale - v1

        v_0c = mw[0]-mw0[0]
        v_0c_ = Vector([v_0c[k] / facelow_scale[k] for k in range(3)]) - d_f 

        ds_c_ = ds_c + ds_f * (w_f/w_c)

        d_c = bone.location
        d_c_ = d_c - v_0c*ds_c + v_0c_*ds_c_ + d_f*(w_f/w_c)

        bone.location = d_c_
        bone.scale = v1 + ds_c_

        if b=='cf_J_Chin_rs':
            for bb in ['cf_J_MouthLow', 'cf_J_ChinTip_s']:
                for k in range(3):
                    arm.pose.bones[bb].scale[k] *= (1.+ds_c[k]) / (1.+ds_c_[k])
                print(bb, arm.pose.bones[bb].location, "=>", arm.pose.bones[bb].location - (d_c_-d_f))
                arm.pose.bones[bb].location -= d_c_-d_f
    arm.pose.bones['cf_J_FaceLow_s'].scale = Vector([1,1,1])
    arm.pose.bones['cf_J_FaceLow_s'].location = Vector([0,0,0])
    return
    for n in vgroup(body, 'cf_J_FaceLow_s'):
        wf = get_weight(body, n, facelow_id)
        for g in body.data.vertices[n].groups:
            if g.group==facelow_id:
                g.weight=0.0
            else:
                g.weight *= 1./(1.-wf)

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

def repaint_mouth(arm, body):
    print("Repainting mouth...")
    if not 'cf_J_MouthCavity' in body.vertex_groups:
        return
    teeth=[x for x in arm.children if x.name.startswith('o_tooth')]
    if len(teeth)>0:
        repaint_teeth(teeth[0])
        repaint_mouth_cavity(body)
    tongue=[x for x in arm.children if x.name.startswith('o_tang')]
    if len(tongue)>0:
        repaint_tongue(tongue[0])
    if not 'cf_J_Mouth_L' in body.vertex_groups:
        return
    #return
    #return
    #dissolve_FaceLow_S(arm, body)
    #return

    mesh=body.data
    bpy.ops.object.mode_set(mode='OBJECT')

    body.vertex_groups.new(name='Mouth Static')
    body.vertex_groups.new(name='Mouth Dynamic')
    body.vertex_groups.new(name='Not Mouth')
    body.vertex_groups.new(name='Mouth Blend')

    arm.data.pose_position='REST'
    #mouth_corners=[arm.data.bones['cf_J_Mouth_L'].head, arm.data.bones['cf_J_Mouth_R'].head]
    bpy.context.view_layer.objects.active = body
    #bpy.ops.object.mode_set(mode='EDIT')
    #bpy.ops.object.mode_set(mode='OBJECT')
    mc=weighted_center('cf_J_Mouth_L')
    mc=Vector([mc[0]+0.01, mc[1], mc[2]-0.04])
    mouth_corners=[mc, Vector([-mc[0],mc[1],mc[2]])]
    #idx_up = body.vertex_groups['cf_J_Mouthup'].index
    #idx_dn = body.vertex_groups['cf_J_MouthLow'].index
    cavity_id = get_or_create_id(body, 'cf_J_MouthCavity')
    facelow_id = get_or_create_id(body, 'cf_J_FaceLow_s')
    mouthbase_id = get_or_create_id(body, 'cf_J_MouthBase_s')
    mouthl_id = get_or_create_id(body, 'cf_J_Mouth_L')
    mouthr_id = get_or_create_id(body, 'cf_J_Mouth_R')
    mouthu_id = get_or_create_id(body, 'cf_J_Mouthup')
    mouthd_id = get_or_create_id(body, 'cf_J_MouthLow')
    chin_id = get_or_create_id(body, 'cf_J_Chin_rs')
    chintip_id = get_or_create_id(body, 'cf_J_ChinTip_s')
    chinlow_id = get_or_create_id(body, 'cf_J_ChinLow')

    cavity_set = vgroup(body, "cf_J_MouthCavity", 0.001)

    mcands = set(vgroup(body,'cf_J_MouthLow')+vgroup(body,'cf_J_Mouthup') 
        + vgroup(body, 'cf_J_Mouth_L') + vgroup(body, 'cf_J_Mouth_R')
        + vgroup(body, 'cf_J_MouthBase_s')
        + vgroup(body, 'cf_J_CheekLow_L')
        + vgroup(body, 'cf_J_CheekLow_R')
        + cavity_set
        )
    print(len(mcands), "verts in mouth repaint set")

    coord = {}
    for n in mcands:
        x=mesh.vertices[n].undeformed_co
        hpos_ext = (x[0]-mouth_corners[1][0]) / (mouth_corners[0][0]-mouth_corners[1][0])
        if x[0]>mouth_corners[1][0] and x[0]<mouth_corners[0][0]:
            hpos = (x[0]-mouth_corners[1][0]) / (mouth_corners[0][0]-mouth_corners[1][0])
            y = mouth_corners[1] + (mouth_corners[0]-mouth_corners[1])*hpos
            #y[2] += 0.2*abs(mc[0])*4*hpos*(1-hpos)
        elif x[0]<mouth_corners[1][0]:
            y=mouth_corners[1].copy()
            hpos = 0.0
        else:
            y=mouth_corners[0].copy()
            hpos = 1.0
        arc = 4*hpos*(1-hpos)
        # determine whether this is the upper lip or the lower lip. They overlap, so we have to
        # use normals when near the boundary.
        if x[1]>mc[1]+0.01*(1+2*arc):
            ypos=1.0
        elif x[1]<mc[1]-0.01*(1+2*arc):
            ypos=-1.0
        else:
            ypos=1.0 if (mesh.vertices[n].normal[1]<0) else -1.0
        coord[n] = (hpos, ypos, hpos_ext)

    # assume it exists and nonempty
    lip_centers=[None,None]
    mlow_set = vgroup(body, 'cf_J_MouthLow')
    mup_set  = vgroup(body, 'cf_J_Mouthup')
    lip_set = set(mlow_set+mup_set)
    for i in mcands:
        if abs(mesh.vertices[i].co[0])>0.01:
            continue
        if not (i in lip_set):
            continue
        if not (i in coord):
            continue
        if coord[i][1]<0.0:
            if lip_centers[0] is None or (mesh.vertices[i].co[1] > lip_centers[0][1]):
                lip_centers[0] = mesh.vertices[i].co
        else:
            if lip_centers[1] is None or (mesh.vertices[i].co[1] < lip_centers[1][1]):
                lip_centers[1] = mesh.vertices[i].co
    vl = vgroup(body, 'cf_J_Mouth_L')[0]
    offsets = {}
    for n in mcands:
        x=mesh.vertices[n].undeformed_co
        hpos, ypos, hpos_ext = coord[n]
        y=mouth_corners[1] + (mouth_corners[0]-mouth_corners[1])*hpos
        arc = 4*hpos*(1-hpos)

        if hpos>0.0 and hpos<1.0:
            ref_center = lip_centers[0 if ypos<0 else 1]
            #y = mouth_corners[1] + (mouth_corners[0]-mouth_corners[1])*hpos

            if ref_center is None: # we somehow didn't find lip centers - make a wild guess instead
                y[2] += 0.2*abs(mc[0])*arc
            else:
                y += (ref_center-(mouth_corners[0]+mouth_corners[1])*0.5)*arc

        full_strength_range = 0.03
        if ypos<0:
            full_strength_range += 0.02*arc
        effect_range = 0.15 # - full_strength_range
        if n in cavity_set:
            effect_range *= 2.0
        dist = (y-x).length-full_strength_range
        # This is how strongly dynamic bones (MouthL, R, Up, Low) will pull the vertex.
        strength = 0.5*sigmoid(dist/effect_range)

        # This is the blend rate between old weights and whatever we're generating.
        # We blend 100% new for up to 5 cm vertically, smoothly decaying to 0% new at 15 cm vertically.
        blend_rate = sigmoid(max(0, abs(x[1]-y[1])-0.05)/0.20)

        if blend_rate == 0.0:
            continue

        if ypos<0:
            wud = strength * math.cos((max(0, abs(hpos-0.5)-0.1)/0.4)*3.1415926/2)
        else:
            wud = strength * math.cos(max(0, abs(hpos-0.5)/0.5)*3.1415926/2)
        """
        if hpos>0.4 and hpos<0.6:
            wud = strength
        elif hpos>=0.6:
            wud = strength * math.cos(((hpos-0.6)/0.4)*3.1415926/2)
        else:
            wud = strength * math.cos(((0.4-hpos)/0.4)*3.1415926/2)
        """
        wl,wr = (strength - wud, 0.0) if hpos>0.5 else (0.0, strength - wud)
        wu, wd = (wud, 0.0) if ypos>0.0 else (0.0, wud)

        wchin = get_weight(body, n, chin_id)
        wchintip = get_weight(body, n, chintip_id)
        wchinlow = get_weight(body, n, chinlow_id)
        chintip_ratio = 0.0
        chinlow_ratio = 0.0
        if wchin+wchintip+wchinlow>0.001:
            chintip_ratio = wchintip / (wchin+wchintip+wchinlow)
            chinlow_ratio = wchinlow / (wchin+wchintip+wchinlow)

        # 0.5 below lower lip
        # 0.25 at lip corners
        # smoothly decaying into upper lip

        # wl,wr,wd subtract from wlowerjaw
        # whatever remains is divided between Chin_rs and ChinTip_s

        if ypos<0:
            wlowerjaw = 0.25 + 0.25*arc + (mc[1]-x[1])*(1.+arc)
        else:
            wlowerjaw = 0.5 - 0.5*arc + (mc[1]-x[1])

        if ypos<0:
            if hpos>0 and hpos<1:
                blend=1
            elif hpos==0:
                blend = interpolate(1, 2*strength, 0, -0.15, hpos_ext)
            else:
                blend = interpolate(1, 2*strength, 1, 1.15, hpos_ext)
        else:
            blend = 2*strength

        wlowerjaw = wlowerjaw * blend + (wchin+wchintip+wchinlow)*(1.-blend)

        if wlowerjaw<0:
            wlowerjaw=0
        if wlowerjaw>0.7:
            wlowerjaw=0.7
        wchin = wlowerjaw - (wl+wr+wd)
        if wchin<0:
            wchin=0
        if wu>0:
            wchin=0
        wchintip = wchin*chintip_ratio
        wchinlow = wchin*chinlow_ratio
        wchin = wchin*(1-chintip_ratio-chinlow_ratio)

        wstatic = 0.0
        wnonmouth = 0.0

        wcav = 0

        facelow_suppress = sigmoid((0.45-strength)/0.10)

        old_weights = {}
        new_weights = {}
        for g in mesh.vertices[n].groups:
            old_weights[body.vertex_groups[g.group].name] = g.weight
            if g.group==cavity_id:
                wcav = g.weight
            elif g.group==mouthbase_id:
                continue
            elif g.group in [mouthl_id, mouthr_id, mouthu_id, mouthd_id, chin_id, chintip_id, chinlow_id]:
                continue
            else:
                # FaceLow_s, Nose_t, CheekLow_s_L, etc.
                if g.group == facelow_id:
                    wnonmouth += g.weight*(1.-facelow_suppress)
                    new_weights[body.vertex_groups[g.group].name] = g.weight*(1.-facelow_suppress)
                else:
                    wnonmouth += g.weight
                    new_weights[body.vertex_groups[g.group].name] = g.weight
        wdynamic = wl+wr+wud+wchin+wchintip+wchinlow
        wstatic = 1.0-wnonmouth-wdynamic

        if wcav>0.0:
            wcav=new_weights["cf_J_MouthCavity"]=wstatic*max(0., min(1, (1.-1.8*strength+max(0.0, 10.*(mc[2]-x[2]+0.02)))))
            new_weights["cf_J_MouthBase_s"]=wstatic-new_weights["cf_J_MouthCavity"]
        else:
            new_weights["cf_J_MouthBase_s"]=wstatic
        delta=0.0
        if wcav>0.10 and (wl>0.25 or wr>0.25):
            mul = min(1, (wcav-0.10)/0.10)
            delta = wu+wd
            wu = wu*(1-mul) + wu*wu*4.*mul
            wd = wd*(1-mul) + wd*wd*4.*mul
            delta -= wu+wd
            if wl>wr:
                wl += delta
            else:
                wr += delta

        for s,w in [('cf_J_Mouth_L', wl),
            ('cf_J_Mouth_R', wr),
            ('cf_J_Mouthup', wu),
            ('cf_J_MouthLow', wd),
            ('cf_J_Chin_rs', wchin),
            ('cf_J_ChinTip_s', wchintip),
            ('cf_J_ChinLow', wchinlow)]:
            new_weights[s] = w
        keys = set(list(old_weights.keys())+list(new_weights.keys()))
        for k in keys:
            wt_old = old_weights[k] if (k in old_weights) else 0.0
            wt_new = new_weights[k] if (k in new_weights) else 0.0
            wt = wt_old * (1.-blend_rate) + wt_new * blend_rate
            if wt>0.001:
                set_weight(body, n, k, wt)
            else:
                body.vertex_groups[k].remove([n])
        if wcav>0.05 and wl>0.25:
            offsets[n] = Vector([(wcav-0.05)*(wl-0.25)*1.6, 0, -(wcav-0.05)*(wl-0.25)*1.6])
        if wcav>0.05 and wr>0.25:
            offsets[n] = Vector([-(wcav-0.05)*(wr-0.25)*1.6, 0, -(wcav-0.05)*(wr-0.25)*1.6])

    for n in offsets:
        mesh.shape_keys.key_blocks["Basis"].data[n].co += offsets[n]
        mesh.shape_keys.key_blocks["e00_defo"].data[n].co += offsets[n]

    bpy.ops.paint.weight_paint_toggle()
    bpy.ops.object.vertex_group_clean(group_select_mode='ALL', limit=0.001)
    bpy.ops.paint.weight_paint_toggle()

    arm.data.pose_position='POSE'
    #bpy.ops.object.mode_set(mode='OBJECT')

def get_weight(body, vertex, group):
    if isinstance(group, str):
        group = body.vertex_groups[group].index
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
    for g in body.data.vertices[vertex].groups:
        if g.group==group:
            g.weight+=weight
            return
    body.vertex_groups[group].add([vertex], weight, 'ADD')
    
def tweak_mouth(arm, body):
    bpy.ops.object.mode_set(mode='OBJECT')
    act=bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    chin = arm.pose.bones['cf_J_Chin_rs']
    chin.rotation_mode='XYZ'
    #arm.pose.bones['cf_J_Chin_rs'].rotation_euler=Euler([10.*3.14159/180, 0., 0.])
    #chin.rotation_euler=Euler([25.*3.14159/180., 0., 0.])
    chin.rotation_euler=Euler([0., 0., 0.])
    arm.pose.bones['cf_J_MouthBase_tr'].location += arm.pose.bones['cf_J_MouthBase_s'].location
    arm.pose.bones['cf_J_MouthBase_s'].location = Vector([0,0,0])

    mwChin = armature.matrix_world(arm, 'cf_J_Chin_rs').decompose()
    mw = armature.matrix_world(arm, 'cf_J_MouthLow').decompose()
    #print("MouthLow", mw)
    bpy.ops.object.mode_set(mode='EDIT')

    arm.data.edit_bones['cf_J_MouthLow'].parent = arm.data.edit_bones['cf_J_Chin_rs']

    v = arm.data.edit_bones['cf_J_Chin_rs'].tail-arm.data.edit_bones['cf_J_Chin_rs'].head
    arm.data.edit_bones['cf_J_Chin_rs'].head = arm.data.edit_bones['cf_J_FaceRoot_s'].tail.copy()
    arm.data.edit_bones['cf_J_Chin_rs'].tail = arm.data.edit_bones['cf_J_Chin_rs'].head+v

    mwChinNew = armature.matrix_world(arm, 'cf_J_Chin_rs').decompose()
    chin_head_delta = mwChinNew[0]-mwChin[0]
    #print("Induced chin tip displacement:", chin_head_delta*(chin.scale-Vector([1,1,1])))
    arm.pose.bones['cf_J_ChinTip_s'].location += chin_head_delta*(chin.scale-Vector([1,1,1]))
    bpy.ops.object.mode_set(mode='POSE')
    mwnew = armature.matrix_world(arm, 'cf_J_MouthLow').decompose()
    offset = mwnew[0]-mw[0]
    #print("MouthLow", mwnew)
    #print("Parent switch on cf_J_MouthLow induces scale change", mwnew[2]-mw[2], "offset change", offset)
    arm.pose.bones["cf_J_MouthLow"].location -= offset
    arm.pose.bones['cf_J_MouthLow'].scale += mw[2]-mwnew[2]

    repaint_mouth(arm, body)
    #return
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')
    try:
        for x in ['cf_J_Chin_rs', 'cf_J_ChinTip_s', 'cf_J_FaceLow_s', 
            'cf_J_MouthBase_tr', 'cf_J_MouthBase_s', 'cf_J_MouthLow', 'cf_J_Mouthup',
            'cf_J_Mouth_L', 'cf_J_CheekLow_L', 'cf_J_CheekMid_L', 'cf_J_CheekUp_L',
            'cf_J_LowerJaw', 'cf_J_UpperJaw']:
            if x in arm.pose.bones:
                arm["deformed_rig"][x]=arm.pose.bones[x].matrix_basis.copy()
    except: # fallback armature
        pass

    bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.data.edit_bones.new('cf_J_UpperJaw')
    bone.parent = arm.data.edit_bones['cf_J_MouthBase_tr']
    bone.head = arm.data.edit_bones['cf_J_MouthBase_tr'].tail
    bone.tail = bone.head+Vector([0, 0, 0.2])
    arm.data.collections["Mouth"].assign(bone)

    bone = arm.data.edit_bones.new('cf_J_LowerJaw')
    bone.parent = arm.data.edit_bones['cf_J_UpperJaw']
    bone.head = arm.data.edit_bones['cf_J_Chin_rs'].head #+Vector([0, 0.1, 0])
    bone.tail = bone.head+Vector([0, 0, 0.5])
    arm.data.collections["Mouth"].assign(bone)

    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones['cf_J_UpperJaw'].rotation_mode='XYZ'
    arm.pose.bones['cf_J_LowerJaw'].rotation_mode='XYZ'

    #return
    print("Adding drivers")

    # Can't get perfect behavior past 15 deg or so, but this is good enough

    # Pull mouth corners and lower lip down 
    armature.drive(arm, "cf_J_Mouth_L", "location", 1, "cf_J_Chin_rs", "ROT_X", "-var*0.4")
    armature.drive(arm, "cf_J_Mouth_R", "location", 1, "cf_J_Chin_rs", "ROT_X", "-var*0.4")
    armature.drive(arm, "cf_J_MouthLow", "location", 1, "cf_J_Chin_rs", "ROT_X", "-var*0.3")
    armature.drive(arm, "cf_J_MouthLow", "location", 1, "cf_J_Chin_rs", "ROT_X", "-var*0.3")
    # Pull lower lip forward
    armature.drive(arm, "cf_J_MouthLow", "location", 2, "cf_J_Chin_rs", "ROT_X", str(arm.pose.bones['cf_J_MouthLow'].location[2])+"+var*0.15")

    # This pulls lips toward the skull at 2 and 10 hours points
    #armature.drive(arm, "cf_J_Mouthup", "rotation_euler", 0, "cf_J_Chin_rs", "ROT_X", "var")

    # This pulls lips toward the skull (full strength from 3 to 9 hours, zero strength at 12 hours).
    # The effect is capped because the teeth are in the way.
    armature.drive(arm, "cf_J_MouthBase_s", "location", 2, "cf_J_Chin_rs", "ROT_X", "max(-0.035,-(1-cos(var)))")
    armature.drive(arm, "cf_J_Mouthup", "location", 2, "cf_J_Chin_rs", "ROT_X", str(arm.pose.bones['cf_J_Mouthup'].location[2])+"-max(-0.035,-(1-cos(var)))")

    # small tweaks
    #armature.drive(arm, "cf_J_Mouthup", "location", 1, "cf_J_Chin_rs", "ROT_X", "min(0.1,var*0.10)")
    save_scale=str(arm.pose.bones['cf_J_MouthLow'].scale[1])
    armature.drive(arm, "cf_J_MouthLow", "scale", 1, "cf_J_Chin_rs", "ROT_X", save_scale+"-max(var,0)*2.0")
    save_scale=str(arm.pose.bones['cf_J_MouthLow'].scale[2])
    armature.drive(arm, "cf_J_MouthLow", "scale", 2, "cf_J_Chin_rs", "ROT_X", save_scale+"-max(var,0)*1.0")


    # Copy rotation to the teeth (0.75 because we don't have full weight of Chin & child bones anywhere on the flesh,
    # so the flesh always lags the bone)
    armature.drive(arm, "cf_J_LowerJaw", "rotation_euler", 0, "cf_J_Chin_rs", "ROT_X", "var*0.75")


def repaint_cheeks(arm, body):
    #return
    if not 'cf_J_CheekUp_L' in body.vertex_groups:
        return
    bpy.ops.object.mode_set(mode='OBJECT')    
    bpy.context.view_layer.objects.active = arm
    body.vertex_groups.new(name='cf_J_CheekMid_L')
    body.vertex_groups.new(name='cf_J_CheekMid_R')

    old_id_l = body.vertex_groups['cf_J_CheekUp_L'].index
    old_id_r = body.vertex_groups['cf_J_CheekUp_R'].index
    nose =  body.vertex_groups['cf_J_NoseBase_s'].index
    v_l=vgroup(body, 'cf_J_CheekUp_L')
    for x in v_l:
        if body.data.vertices[x].co[0]<0:
            set_weight(body, x, old_id_l, 0.0)
    v_r=vgroup(body, 'cf_J_CheekUp_R')
    for x in v_r:
        if body.data.vertices[x].co[0]>0:
            set_weight(body, x, old_id_r, 0.0)
    
    
    v_l=vgroup(body, 'cf_J_CheekUp_L', min_wt=0.01)
    new_id_l = body.vertex_groups['cf_J_CheekMid_L'].index
    #print(old_id, new_id)
    v_r=vgroup(body, 'cf_J_CheekUp_R', min_wt=0.01)
    new_id_r = body.vertex_groups['cf_J_CheekMid_R'].index
    #print(old_id, new_id)
    #mouth_id = x.vertex_groups['cf_J_MouthCavity'].index
    for v, old_id, new_id, xw in ((v_l, old_id_l, new_id_l, -1.0), (v_r, old_id_r, new_id_r, 1.0)):
        heights = {y:0.5*body.data.vertices[y].co[1]+xw*body.data.vertices[y].co[0] for y in v}
        hl = list(heights.values())
        hl.sort()
        minpos = hl[0]
        midpos = hl[len(hl)//2]
        maxpos = hl[-1]
        #print(hl[0], midpos, maxpos)
        for y in v:
            #if heights[y]>midpos:
            frac = (heights[y]-minpos)/(maxpos-minpos)
            old_weight = get_weight(body, y, old_id)
            if old_weight*frac>0.005:
                #if old_weight*frac>0.20:
                #    print(y, body.data.vertices[y].co, heights[y], old_weight, frac, "=>", old_weight*(1.-frac), old_weight*frac)
                set_weight(body, y, old_id, old_weight*(1.-frac))
                set_weight(body, y, new_id, old_weight*frac)

    v=vgroup(body, 'cf_J_NoseBase_s', min_wt=0.01)
    for y in v:
        frac = min(1.0, 2.0*abs(body.data.vertices[y].co[0]))
        old_weight = get_weight(body, y, nose)
        if old_weight*frac>0.005:
            set_weight(body, y, nose, old_weight*(1.-frac))
            add_weight(body, y, (new_id_l if body.data.vertices[y].co[0]>0 else new_id_r), old_weight*frac)

    bpy.ops.object.mode_set(mode='EDIT')
    bone = arm.data.edit_bones.new('cf_J_CheekMid_L')
    bone.head = arm.data.edit_bones['cf_J_CheekUp_L'].head-Vector([0.02, 0, 0])
    bone.tail = arm.data.edit_bones['cf_J_CheekUp_L'].tail-Vector([0.02, 0, 0])
    bone.parent = arm.data.edit_bones['cf_J_FaceLow_s']
    for c in arm.data.collections:
        if 'cf_J_CheekUp_L' in c:
            c.assign(bone)
    #bone.layers = arm.data.edit_bones['cf_J_CheekUp_L'].layers
    bone = arm.data.edit_bones.new('cf_J_CheekMid_R')
    bone.head = arm.data.edit_bones['cf_J_CheekUp_R'].head-Vector([0.02, 0, 0])
    bone.tail = arm.data.edit_bones['cf_J_CheekUp_R'].tail-Vector([0.02, 0, 0])
    bone.parent = arm.data.edit_bones['cf_J_FaceLow_s']
    #bone.layers = arm.data.edit_bones['cf_J_CheekUp_R'].layers
    for c in arm.data.collections:
        if 'cf_J_CheekUp_R' in c:
            c.assign(bone)
    bpy.ops.object.mode_set(mode='OBJECT')        
    
    #x.vertex_groups['cf_J_Chin_rs'].add([y.index for y in v], 1.0, 'ADD')

def find_nearest(mesh, v, cands):
    a=cands[0]
    for x in cands:
        if (mesh.vertices[x].co-v).length<(mesh.vertices[a].co-v).length:
            a=x
    return a

def tweak_nose(body):
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
    """
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    for x in tip:
        #if body.data.vertices[x].co[0]>0:
        wc = get_weight(body, x, idx_tip)
        wl = get_weight(body, x, idx_l)
        wr = get_weight(body, x, idx_r)
        delta = min(wc, max(wl,wr))
        if delta>0.0:
            print(x, delta)
        #body.data.shape_keys.key_blocks['Basis'].data[x].co[2] -= 0.05*delta
        #body.data.shape_keys.key_blocks['Basis'].data[x].co[2] -= 0.05*delta
        #body.data.vertices[x].co[2] -= 0.05*delta
        bm.verts[x].co[0] -= 0.05*delta*(-1 if wr>wl else 1)
        bm.verts[x].co[2] -= 0.05*delta
    bm.to_mesh(body.data)
    #body.data.vertices.update()
    """
    for x in tip:
        #if body.data.vertices[x].co[0]>0:
        wc = get_weight(body, x, idx_tip)
        wl = get_weight(body, x, idx_l)
        wr = get_weight(body, x, idx_r)
        delta = min(wc, max(wl,wr))
        #if delta>0.0:
        #    print(x, delta)
        #body.data.shape_keys.key_blocks['Basis'].data[x].co[2] -= 0.05*delta
        #body.data.shape_keys.key_blocks['Basis'].data[x].co[2] -= 0.05*delta
        #body.data.vertices[x].co[2] -= 0.05*delta
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
        #if x==12388 or x==12394 or x==11994 or (wl>0.069 and wl<0.071 and wn>0.700 and wn<0.705):
        #    print(x, "wch", wch, "wl", wl, "wr", wr, "wc", wc, "wn", wn, body.data.vertices[x].normal)
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
        sk.data[x].co -= deltas[x] #0.02*effect*body.data.vertices[x].normal
            #sk.data[x].co[2] -= 0.005*effect


    body.data.shape_keys.key_blocks["Nostril pinch"].value=1.

def draw_crease(mesh, crease, nearest):
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bmd = bmesh.new()
    bmd.from_mesh(mesh)
    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    bmd.faces.ensure_lookup_table()
    cuts=[]
    for side in range(2):
        top=None
        bot=None
        for x in crease:
            if mesh.vertices[x[0]].co[0]*(1 if side==0 else -1) < 0:
                continue
            if top is None or mesh.vertices[x[0]].co[1]>mesh.vertices[top].co[1]:
                top = x[0]
            if bot is None or mesh.vertices[x[0]].co[1]<mesh.vertices[bot].co[1]:
                bot = x[0]
        cuts.append([bmd.verts[nearest[side]], bmd.verts[top]])
        #cuts.append([bmd.verts[nearest[side]], bmd.verts[bot]])
    for c in cuts:
        edges = bmesh.ops.connect_vert_pair(bmd,verts=c)
        #print(edges)
        for e in edges["edges"]:
            e.smooth = False
        #bmd.verts.ensure_lookup_table()
        #bmd.edges.ensure_lookup_table()
        #bmd.faces.ensure_lookup_table()
        #connected.add((x,y))
    bmd.to_mesh(mesh)
    return

    discard=set()

    for x in crease:
        for y in crease:
            if x[0]==y[0]:
                continue
            if x[3][0]*y[3][0]<0:
                continue
            offset = y[3]-x[3]
            normal = x[2]
            offset.normalize()
            normal.normalize()
            if abs(offset.dot(normal))>0.5:
                print(x[0], x[3], x[1], "vs", y[0], y[3], y[1], "dot", offset.dot(normal))
                if abs(x[1])<abs(y[1]):
                    if not y[0] in discard:
                        print("discarding", y[0])
                    discard.add(y[0])
                else:
                    if not x[0] in discard:
                        print("discarding", x[0])
                    discard.add(x[0])

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bmd = bmesh.new()
    bmd.from_mesh(mesh)
    bmd.verts.ensure_lookup_table()
    bmd.edges.ensure_lookup_table()
    bmd.faces.ensure_lookup_table()
    connected=set()
    print(len(crease), "verts in the crease set, ", len(discard), "discarded")
    for x,_,_,_ in crease:
        if x in discard:
            continue
        xf = bmd.verts[x].link_faces
        xe = bmd.verts[x].link_edges
        xfe = [e for f in xf for e in f.edges]
        #xv = [v for v in e.verts for e in xe]
        for y,_,_,_ in crease:
            if y==x:
                continue
            if (y,x) in connected:
                continue
            if y in discard:
                continue
            #if y in xv:
            #    continue
            adjacent=False
            for e in xe:
                if bmd.verts[y] in e.verts:
                    if phase==1:
                        e.smooth=False
                    adjacent=True
                    break
            if adjacent:
                continue
            if phase==1:
                continue
            yf = bmd.verts[y].link_faces
            ye = bmd.verts[y].link_edges
            yfe = [e for f in yf for e in f.edges]
            for e in xfe:
                if e in yfe:
                    #bmesh.ops.subdivide_edges(bmd, edges=[e], cuts=1)
                    #bmesh.ops.bisect_edges(bmd, edges=[e])
                    adjacent=True
                    #break
            if adjacent:
                edges = bmesh.ops.connect_vert_pair(bmd,verts=[bmd.verts[x],bmd.verts[y]])
                #print(edges)
                #for e in edges["edges"]:
                #    e.smooth = False
                bmd.verts.ensure_lookup_table()
                bmd.edges.ensure_lookup_table()
                bmd.faces.ensure_lookup_table()
                connected.add((x,y))
    bmd.to_mesh(mesh)

def add_mouth_blendshape(body):
    obj=body
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = obj

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')

    mesh=obj.data
    if not 'cf_J_CheekLow_L' in bpy.context.active_object.vertex_groups: # custom head
        return 
    if not 'cf_J_Mouthup' in bpy.context.active_object.vertex_groups: # custom head
        return 
    idx_up = body.vertex_groups['cf_J_Mouthup'].index
    idx_dn = body.vertex_groups['cf_J_MouthLow'].index

    cheek=vgroup(obj, 'cf_J_CheekLow_L')
    mlow = vgroup(obj, 'cf_J_MouthLow')
    mhigh = vgroup(obj, 'cf_J_Mouthup')
    mcav = vgroup(obj, 'cf_J_MouthCavity')

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

    #find the nearest vertex to that point
    ccorn_nearest=mesh.vertices[0].co
    for x in mesh.vertices:
        if (x.co-ccorn).length<(ccorn_nearest-ccorn).length:
            ccorn_nearest=x.co
    ccorn=ccorn_nearest
    
    ccent=(ccorn+mcorn)*0.5
    vmc=ccent-mcorn
    yneg_cutoff=-(mcent-mcorn).dot(vmc)/(vmc.length*vmc.length)

    sk = obj.shape_key_add(name='better_smile')
    sk.interpolation='KEY_LINEAR'

    vg = body.vertex_groups.new(name='nasolabial_crease')


    #normals2=[None,None]
    #normals=[None,None]
    #vmcs=[None,None]
    ccent=(mcorn+ccorn)*0.5
    vmc=ccent-mcorn
    vmm=mcorn-mcent
    normal=Vector([vmc[2], 0, -vmc[0]])
    normal /= normal.length

    normal2=vmc.cross(normal)
    normal2/=normal2.length

    for phase in range(2):
        crease = []
        nearest=[None,None]

        for side in range(2):
            smult = Vector([-1 if side else 1, 1, 1])
            mod=[x for x in range(len(mesh.vertices)) if (mesh.vertices[x].co-ccent*smult).length<1.5*vmc.length or (mesh.vertices[x].co-mcorn*smult).length<1.5*vmm.length or x in mlow or x in mhigh]
            print("Phase", phase, "side", side, ":", len(mod), "verts")
            for x in mod:
                if get_weight(body, x, 'cf_J_MouthCavity') > 0.1:
                    continue
                v = obj.data.vertices[x]

                if nearest[side] is None:
                    nearest[side] = x
                else:
                    l1=(v.co-mcorn*smult).length
                    l2=(obj.data.vertices[nearest[side]].co-mcorn*smult).length
                    if l1<l2:
                        nearest[side]=x

                y=(v.co-mcorn*smult).dot(vmc*smult)/(vmc.length*vmc.length)
                z=(v.co-mcorn*smult).dot(normal2*smult)/vmc.length
                if y<0:
                    y/=yneg_cutoff

                if y>=-0.5 and y<=0.5:
                    set_weight(body, x, vg.index, y+0.5)
                if abs(y)<0.10 and abs(z) > 0.05 and abs(z) < 0.8:
                    crease.append((x, y, vmc*smult, obj.data.vertices[x].co))

                if phase<1:
                    continue

                #  we pull the vertex toward the ear, maximal effect at lip corner and smoothly decaying 
                #  until we hit 0 at lip center or cheek center.
                z = sigmoid(abs(z))
                deform=0.2
                stretch_dir = vmc*smult
                #if y>0.0:
                stretch_dir[1]*=interpolate(2,4,0,0.5,y)
                stretch_effect = stretch_dir*max(0.0, 1.0-abs(y))*deform*z
                lip_zone = y+abs(z)
                sk.data[x].co+=stretch_effect*max(0.0, min(1.0, 1.0+5.0*lip_zone))
                if y>0.0:
                    #  for positive y (cheek), we also displace the vertex away from the face,
                    # trying to create a 'bulge' right next to the lip corner.
                    #if abs(y)<0.05 and z > 0.25:
                    #    crease.append(x)
                    if not (x in mcav):
                        #phi = (y-1.0) * -0.25 * (1 if side==1 else -1)
                        #norm = Vector([normal[0]*math.cos(phi)+normal[2]*math.sin(phi), 0, -normal[0]*math.sin(phi)+normal[2]*math.cos(phi)]) #mesh.vertices[x].normal
                        norm = Vector([v.co[0], 0, v.co[2]])
                        norm.normalize()
                        #if x in (9398, 12725, 12784):
                        #    print(x, "pos", v.co, "y", y, "norm", norm)
                        tslope = 1.0
                        if y>2.0:
                            tfun=0.0
                        else:
                            tfun = tslope*(math.sqrt(max(0.0,y))*0.25*(y-2)*(y-2)) # - 0.25*sigmoid(abs(y), 0, 0.2))
                        sk.data[x].co+=norm*tfun*deform*z

                if y<0:
                    #yz = abs(y)

                    # positive if in front of line connecting lip corners
                    fd=(sk.data[x].co[2]-mcorn[2])
                    if fd>0:
                        # pull lip centers toward teeth
                        sk.data[x].co[2]-=0.5*(fd*fd)*abs(z)*(-y)

                        # determine which lip it is
                        # pull upper lip up, lower lip down
                        lip_id = -1.0 if (x in mlow) else 1.0
                        sk.data[x].co[1]+=0.005*abs(z)*(-y)*lip_id

        if phase < 1:
            draw_crease(mesh, crease, nearest)

            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.object.mode_set(mode='OBJECT')

            mlow = vgroup(obj, 'cf_J_MouthLow')
            mhigh = vgroup(obj, 'cf_J_Mouthup')
            mcav = vgroup(obj, 'cf_J_MouthCavity')


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


def excise_neuter_mesh(body, injector_mesh):
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
    with bpy.data.libraries.load(os.path.dirname(__file__)+"/assets/prefab_materials_meshexporter.blend") as (data_from, data_to):
        data_to.objects = data_from.objects

    body.vertex_groups.new(name='cf_J_Perineum')
    old_id = body.vertex_groups['cf_J_Kosi02_s'].index
    #old_id_r = body.vertex_groups['cf_J_CheekUp_R'].index
    new_id =  body.vertex_groups['cf_J_Perineum'].index
    v=vgroup(body, 'cf_J_Kosi02_s')
    if not 'cf_J_Ana' in body.vertex_groups:
        body.vertex_groups.new(name='cf_J_Ana')
    id_ana =  body.vertex_groups['cf_J_Ana'].index

    leg1 = body.vertex_groups['cf_J_LegUp01_s_L'].index
    leg2 = body.vertex_groups['cf_J_LegUp01_s_R'].index
    s1 = body.vertex_groups['cf_J_Siri_s_L'].index
    s2 = body.vertex_groups['cf_J_Siri_s_R'].index
    for x in v:
        if abs(body.data.vertices[x].co[0])<0.25:
            f = (1. - abs(body.data.vertices[x].co[0]) / 0.25) * max(0.0, min(1.0, body.data.vertices[x].co[2]*2+1))
            w = get_weight(body, x, old_id)
            f *= w
            supp = get_weight(body, x, leg1) + get_weight(body, x, leg2) + get_weight(body, x, s1) + get_weight(body, x, s2) 
            f -= supp
            if f>0:
                set_weight(body, x, old_id, w-f)
                set_weight(body, x, new_id, f)
        L = body.data.vertices[x].co-Vector([0, 9.4, -0.56])
        if L.length<0.4: # and get_weight(body, x, id_ana)==0.0:
            set_weight(body, x, id_ana, 0.4*(math.cos(3.14159*L.length/0.4)+1))

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
        mat.node_tree.nodes['Group.004'].inputs['Subsurface/MainTex mix'].default_value=0.5

    
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

    fit_mesh = None
    for m in cand_meshes:
        ok = excise_neuter_mesh(body, m)
        if ok:
            fit_mesh = m
            break
    #return
    print("Fit:", fit_mesh)
    if fit_mesh is None:
        print("None of the exhaust meshes is a perfect fit")
        bpy.ops.object.mode_set(mode='OBJECT')
        return
    for m in cand_meshes:
        try:
            if m!=fit_mesh:
                print("Removing", m)
                bpy.data.objects.remove(m)
        except:
            pass
    #mesh = fit_mesh

    bpy.context.view_layer.objects.active = body
    bpy.context.object.active_shape_key_index = 0

    arm.data.pose_position='POSE'
    arm["exhaust"]=1.0
    bpy.ops.object.mode_set(mode='OBJECT')


def attach_injector(arm, body):
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
    set_wet(arm, False)
    set_sheath(arm, True)
    set_eagerness(arm, 5.0)
    set_length(arm, 50.0)
    set_girth(arm, 30.0)
    set_volume(arm, 50.0)

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
    print("Torso texture", maintex.filepath)
    print("Sample coord x", int(w*0.125), "y", int(h*0.581))
    # 0.253 0.139 0.090
    # 0.5477 0.4095
    print("Pixel:", pixel)
    pixel = pixel.from_srgb_to_scene_linear()
    print("Converted pixel:", pixel)
    print("Converted pixel HSV:", pixel.h, pixel.s, pixel.v)

    pixel.v = math.pow(pixel.v, 0.25)
    print("Adjusted pixel:", pixel.v, pixel)
    c0 = mathutils.Color([0.87, 0.42, 0.28])
    correction = [pixel[k]/c0[k] for k in range(3)]
    print("Correction:", correction)
    mat.node_tree.nodes["Vector Math"].inputs[1].default_value = correction

    excise_neuter_mesh(body, injector_mesh)

    # can't join because I want to be able to turn it on and off
    #join_meshes([body.name, injector_sheath.name])

def paint_scalp(body):
    vg=body.vertex_groups.new(name="Scalp")
    faceup = vgroup(body,"cf_J_FaceUp_ty")
    for v in faceup:
        if get_weight(body, v, "cf_J_FaceUp_tz")>0.1:
            continue
        if get_weight(body, v, "cf_J_EarBase_s_L")>0.2:
            continue
        if get_weight(body, v, "cf_J_EarBase_s_R")>0.2:
            continue
        if get_weight(body, v, "cf_J_EarLow_L")>0.0:
            continue
        if get_weight(body, v, "cf_J_EarLow_R")>0.0:
            continue
        if get_weight(body, v, "cf_J_FaceLow_s")>0.0:
            continue
        if get_weight(body, v, "cf_J_FaceRoot_s")>0.0 and body.data.vertices[v].co[2]>-0.5:
            continue
        if get_weight(body, v, "cf_J_Eye01_s_L")>0.0:
            continue
        if get_weight(body, v, "cf_J_Eye02_s_L")>0.0:
            continue
        if get_weight(body, v, "cf_J_Eye03_s_L")>0.0:
            continue
        if get_weight(body, v, "cf_J_Eye01_s_R")>0.0:
            continue
        if get_weight(body, v, "cf_J_Eye02_s_R")>0.0:
            continue
        if get_weight(body, v, "cf_J_Eye03_s_R")>0.0:
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

def eyelid_crease(body):
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.objects.active = body
    #bpy.ops.object.mode_set(mode='EDIT')
    if 'Eyelid crease' in body.data.shape_keys.key_blocks:
        #return
        body.shape_key_remove(key=body.data.shape_keys.key_blocks['Eyelid crease'])
    if not 'cf_J_Eye02_s_R' in body.vertex_groups:
        return

    eyeball = vgroup(body, 'cf_J_eye_rs_R')
    print("eyeball", len(eyeball))

    v=set(vgroup(body, 'cf_J_Eye01_s_R')+vgroup(body, 'cf_J_Eye02_s_R')+vgroup(body, 'cf_J_Eye03_s_R')
        +vgroup(body, 'cf_J_Eye01_s_L')+vgroup(body, 'cf_J_Eye02_s_L')+vgroup(body, 'cf_J_Eye03_s_L'))
    vv=set(vgroup(body, 'cf_J_Eye04_s_R')+vgroup(body, 'cf_J_Eye04_s_L') + vgroup(body, 'cf_J_CheekUp_L')
        + vgroup(body, 'cf_J_CheekUp_R'))

    vl=set(vgroup(body, 'cf_J_Eye01_s_R')+vgroup(body, 'cf_J_Eye04_s_R')+vgroup(body, 'cf_J_Eye03_s_R')
        +vgroup(body, 'cf_J_Eye01_s_L')+vgroup(body, 'cf_J_Eye04_s_L')+vgroup(body, 'cf_J_Eye03_s_L'))
    #vv=set(vgroup(body, 'cf_J_Eye04_s_R')+vgroup(body, 'cf_J_Eye04_s_L') + vgroup(body, 'cf_J_CheekUp_L')
    #    + vgroup(body, 'cf_J_CheekUp_R'))
    eyelid_curve=[]
    for x in v:
        if x in vv:
            continue
        if body.data.vertices[x].co[0]>0:
            continue
        wup = get_weight(body, x, "cf_J_FaceUp_tz")
        w02 = get_weight(body, x, 'cf_J_Eye02_s_L')+get_weight(body, x, 'cf_J_Eye02_s_R')
        w03 = get_weight(body, x, 'cf_J_Eye03_s_L')+get_weight(body, x, 'cf_J_Eye03_s_R')
        if w02 < 0.2:
            continue
        if w02 <= w03+0.001:
            continue
        if wup > 0.02:
            continue
        en = (None, 1e10, None)
        for y in eyeball:
            l = (body.data.vertices[x].co-body.data.vertices[y].co)
            if l.length<en[1]:
                en=(y, l.length, l)
        if en[2].dot(body.data.vertices[en[0]].normal)<0.0:
            continue
        if abs(body.data.vertices[x].co[0]+0.4097)<0.001:
            print(x, body.data.vertices[x].co)
        eyelid_curve.append([body.data.vertices[x].co[0], body.data.vertices[x].co[1]])

    eyelid_curve_lower=[]
    for x in vl:
        if body.data.vertices[x].co[0]>0:
            continue
        wup = get_weight(body, x, "cf_J_FaceUp_tz")
        w04 = get_weight(body, x, 'cf_J_Eye04_s_L')+get_weight(body, x, 'cf_J_Eye04_s_R')
        w01 = get_weight(body, x, 'cf_J_Eye01_s_L')+get_weight(body, x, 'cf_J_Eye01_s_R')
        w03 = get_weight(body, x, 'cf_J_Eye03_s_L')+get_weight(body, x, 'cf_J_Eye03_s_R')
        if w01+w03+w04<0.5:
            continue
        if w04 < 0.2:
            continue
        #if w04 <= w03+0.001:
        #    continue
        if wup > 0.02:
            continue
        en = (None, 1e10, None)
        for y in eyeball:
            l = (body.data.vertices[x].co-body.data.vertices[y].co)
            if l.length<en[1]:
                en=(y, l.length, l)
        if en[2].dot(body.data.vertices[en[0]].normal)<0.0:
            continue
        eyelid_curve_lower.append([body.data.vertices[x].co[0], body.data.vertices[x].co[1]])

    while True:
        eyelid_curve2=[]
        for x in eyelid_curve:
            bad=False
            for y in eyelid_curve:
                for z in eyelid_curve:
                    if y==x or y==z or z==x:
                        continue
                    if x[0]<min(y[0],z[0]) or x[0]>max(y[0],z[0]):
                        continue
                    if abs(y[0]-z[0]) > 0.06:
                        continue
                    #def interpolate(y1, y2, x1, x2, x):
                    pred = interpolate(y[1], z[1], y[0], z[0], x[0])
                    if pred<x[1] and x[1]-pred>0.25*max(abs(x[0]-y[0]),abs(x[0]-z[0])):
                        bad=True
                        break
            if not bad:
                eyelid_curve2.append(x)
        if len(eyelid_curve2)==len(eyelid_curve):
            break
        eyelid_curve=eyelid_curve2[:]

    while True:
        eyelid_curve2=[]
        for x in eyelid_curve_lower:
            bad=False
            for y in eyelid_curve_lower:
                for z in eyelid_curve_lower:
                    if y==x or y==z or z==x:
                        continue
                    if x[0]<min(y[0],z[0]) or x[0]>max(y[0],z[0]):
                        continue
                    if abs(y[0]-z[0]) > 0.06:
                        continue
                    #def interpolate(y1, y2, x1, x2, x):
                    pred = interpolate(y[1], z[1], y[0], z[0], x[0])
                    if pred>x[1] and pred-x[1]>0.25*max(abs(x[0]-y[0]),abs(x[0]-z[0])):
                        bad=True
                        break
            if not bad:
                eyelid_curve2.append(x)
        if len(eyelid_curve2)==len(eyelid_curve_lower):
            break
        eyelid_curve_lower=eyelid_curve2[:]

        """
        if abs(body.data.vertices[x].normal[2])<0.1:
            if body.data.vertices[x].co[0]<0:
                print(body.data.vertices[x].co, body.data.vertices[x].normal)
            eyelid_curve[body.data.vertices[x].co[0]] = body.data.vertices[x].co[2]
        """

    #for k in eyelid_curve:
    #    print(k, eyelid_curve[k])

    eyelid_curve.sort()
    eyelid_curve_lower.sort()
    print("Final curve")
    print(eyelid_curve)
    print(eyelid_curve_lower)

    if 'Eyelashes' in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups["Eyelashes"])
    body.vertex_groups.new(name="Eyelashes")
    if 'Eyelid curve' in body.vertex_groups:
        body.vertex_groups.remove(body.vertex_groups["Eyelid curve"])
    body.vertex_groups.new(name="Eyelid curve")

    for x in range(len(body.data.vertices)):
        wt=0.0
        for y in eyelid_curve+eyelid_curve_lower:
            if abs(body.data.vertices[x].co[0]-y[0])+abs(body.data.vertices[x].co[1]-y[1])<0.001:
                wt=1.0
        if wt>0:
            set_weight(body, x, "Eyelid curve", 1.0)

    sk = body.shape_key_add(name='Eyelid crease')
    sk.interpolation='KEY_LINEAR'
    for x in range(len(body.data.vertices)):
        sk.data[x].co = body.data.shape_keys.key_blocks["Basis"].data[x].co
    for x in v:
        if x in vv:
            continue
        wup = get_weight(body, x, "cf_J_FaceUp_tz")
        w02 = get_weight(body, x, 'cf_J_Eye02_s_L')+get_weight(body, x, 'cf_J_Eye02_s_R')
        w03 = get_weight(body, x, 'cf_J_Eye03_s_L')+get_weight(body, x, 'cf_J_Eye03_s_R')
        if w02 < 0.2:
            continue
        if w02 <= w03+0.001:
            continue
        #if wup > 0.02:
        #    continue

        co = body.data.vertices[x].co.copy()
        if co[0]>0:
            co[0]*=-1.
        en = (None, 1e10, None)
        for y in eyeball:
            l = (co-body.data.vertices[y].co)
            if l.length<en[1]:
                en=(y, l.length, l)
        if en[2].dot(body.data.vertices[en[0]].normal)<0.0:
            continue

        pred = None
        xp = -abs(body.data.vertices[x].co[0])
        yp = body.data.vertices[x].co[1]

        y1 = None
        y2 = None
        for y in eyelid_curve:
            if y[0]<xp and (y1 is None or y[0]>y1[0]):
                y1 = y
            if y[0]>xp and (y2 is None or y[0]<y2[0]):
                y2 = y

        if y1 is not None and y2 is not None:
            pred = interpolate(y1[1], y2[1], y1[0], y2[0], xp)
        effect = 0.0
        if pred is not None:
            effect = max(0.0, 0.02-abs(yp-(pred+0.04))) * interpolate(0, 1, 0.5, 0.25, w03)
        sk.data[x].co[2] -= effect

    cands=[]
    for x in set(list(v)+list(vl)):
        #wup = get_weight(body, x, "cf_J_FaceUp_tz")
        w02 = get_weight(body, x, 'cf_J_Eye02_s_L')+get_weight(body, x, 'cf_J_Eye02_s_R')
        w03 = get_weight(body, x, 'cf_J_Eye03_s_L')+get_weight(body, x, 'cf_J_Eye03_s_R')
        w04 = get_weight(body, x, 'cf_J_Eye04_s_L')+get_weight(body, x, 'cf_J_Eye04_s_R')

        co = body.data.vertices[x].co.copy()
        if co[0]>0:
            co[0]*=-1.
        en = (None, 1e10, None)
        for y in eyeball:
            l = (co-body.data.vertices[y].co)
            if l.length<en[1]:
                en=(y, l.length, l)
        if en[2].dot(body.data.vertices[en[0]].normal)<-0.02:
            if abs(body.data.vertices[x].co[0]+0.44016)<0.001:
                print(x, body.data.vertices[x].co, "eyeball reject")
            continue

        pred = None
        xp = -abs(body.data.vertices[x].co[0])
        yp = body.data.vertices[x].co[1]

        y1 = None
        y2 = None

        if w02 > w04:
            sign = 1.0
            for y in eyelid_curve:
                if y[0]<=xp and (y1 is None or y[0]>y1[0]):
                    y1 = y
                if y[0]>=xp and (y2 is None or y[0]<y2[0]):
                    y2 = y
        else:
            sign = -1.0
            for y in eyelid_curve_lower:
                if y[0]<=xp and (y1 is None or y[0]>y1[0]):
                    y1 = y
                if y[0]>=xp and (y2 is None or y[0]<y2[0]):
                    y2 = y

        if y1 is not None and y2 is not None:
            pred = interpolate(y1[1], y2[1], y1[0], y2[0], xp)

        if pred is not None:
            if abs(yp-pred)<0.005 and body.data.vertices[x].normal[2]>0.0 and body.data.vertices[x].normal[1]*sign<0:
                cands.append(x)

    for x in cands:
        co = body.data.vertices[x].co.copy()
        sign = 1.0
        if co[0]>0:
            co[0]*=-1.
            sign = -1.0
        en = (None, 1e10, None)
        for y in eyeball:
            l = (co-body.data.vertices[y].co)
            if l.length<en[1]:
                en=(y, l.length, l)
        #if en[2].dot(body.data.vertices[en[0]].normal)<-0.02:
        enorm = Vector(body.data.vertices[en[0]].normal[:])
        enorm[0]*=sign
        enorm.normalize()

        dup=False
        for y in cands:
            if y==x:
                continue
            dv=body.data.vertices[y].co-body.data.vertices[x].co
            #if dv[2] >= 0.5*dv.length and abs(dv[0])<0.25*dv.length:
            if dv.length<0.10 and dv.dot(enorm) >= 0.5*dv.length:
                dup=True
        if not dup:
            set_weight(body,  x, "Eyelashes", 1.0)

    body.data.shape_keys.key_blocks["Eyelid crease"].value=1.
