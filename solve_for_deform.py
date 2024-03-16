import bpy
import os
import math
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy as np
import time

#
# This simply calculates:
#
# for x in range(len(target)):
#       target[x].co = mats[x] @ undeformed[x].co
#
def np_solve(target, undeformed, np_mats):
    np_undeformed = np.zeros([len(target)*3], dtype=np.float32)
    undeformed.foreach_get("co", np_undeformed)
    np_undeformed = np_undeformed.reshape([-1,3])
    np_undeformed = np.concatenate([np_undeformed, np.ones([np_undeformed.shape[0],1],dtype=np.float32)], axis=1)
    out = np.einsum("Bac,Bc->Ba",np_mats,np_undeformed)
    out = (out[:,:3]/out[:,3:]).reshape([-1])
    target.foreach_set("co", out)

# Given an object 'b' that is parented to an armature 'arm' in a nontrivial pose, and a reference
# object with the same number of vertices, deforms the rest position of 'b' until it matches 'b2' in pose position.
def solve_for_deform(arm, b, b2):
    np_mats = np.zeros([len(b.data.vertices), 4, 4], dtype=np.float32)
    totwts = np.zeros([len(b.data.vertices), 1, 1], dtype=np.float32)

    bone_mats = [None]*len(b.vertex_groups)
    for y in b.vertex_groups:
        if y.name in arm.pose.bones:
            bone_mats[y.index] = arm.pose.bones[y.name].matrix_channel
    z=Matrix()
    z.zero()

    # The effect of armature deformation on a vertex 'v' is
    # v_.co = sum([g.weight * arm.pose.bones[b.vertex_groups[g.group].name].matrix_channel for g in v.groups]) @ v.co
    # (assuming that vertex weights are normalized.)
    # We calculate the sum and then invert the matrix.
    for x in range(len(b.data.vertices)):
        deform = z.copy()
        totwt = 0.0
        for y in b.data.vertices[x].groups:
            m = bone_mats[y.group]
            if m is not None:
                deform += m*y.weight
                totwt += y.weight
        totwts[x,0,0] = totwt
        np_mats[x] = deform if totwt>0.0 else Matrix()

    # an extra step is needed if the object is offset / rotated relative to the armature
    dm_fwd = np.array(b.matrix_local, dtype=np.float32)
    dm_inv = np.array(b.matrix_local.inverted(), dtype=np.float32)
    np_mats = np.array([np.linalg.inv(x) for x in np_mats]) * totwts
    np_mats = np.einsum("ca,Bae,ed->Bcd", dm_inv, np_mats, dm_fwd)

    if b.data.shape_keys!=None:
        for y in b.data.shape_keys.key_blocks:
            target=b.data.shape_keys.key_blocks[y.name].data
            undeformed=b2.data.shape_keys.key_blocks[y.name].data
            np_solve(target, undeformed, np_mats)
    else:
        target=b.data.vertices
        undeformed=b2.data.vertices
        np_solve(target, undeformed, np_mats)

