import bpy
import os
import bmesh
import math
import hashlib
from mathutils import Matrix, Vector, Euler, Quaternion
import struct
import numpy as np
import time

def bbox(x):
     rv=[[x[0].co[0],x[0].co[1],x[0].co[2]],
         [x[0].co[0],x[0].co[1],x[0].co[2]]]
     for y in x:
         for n in range(3):
             rv[0][n]=min(rv[0][n], y.co[n])
             rv[1][n]=max(rv[1][n], y.co[n])
     return rv

def to_int(v):
    return (int(v.co[0]*100000.), int(v.co[1]*100000.), int(v.co[2]*100000.))

def from_int(v):
    return Vector([v[0]/100000., v[1]/100000., v[2]/100000.])

messed_up_shape_key_warn=True 
def score_deform(b, depsgraph, undeformed, active_set):
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')
    bm = bmesh.new()
    bm.from_object( b, depsgraph )
    bm.verts.ensure_lookup_table()
    errors=[bm.verts[x].co - undeformed[x].co for x in active_set]
    bm.free()
    return errors

def try_load_solution_cache(path, b, expected_hash):
    try:
        f=open(path+"solution.cache","rb")
    except:
        return False, {}

    #t1=time.time()
    buf = f.read()
    f.close()
    hash=buf[:16]
    buf=buf[16:]
    if hash!=expected_hash:
        return False, {}
    buf=struct.unpack('%si' % (len(buf)//4), buf)
    map={}
    map2={}
    np_map = np.zeros([len(buf)//6,2],dtype=np.int64)
    np_map_out = np.zeros([len(buf)//6,3],dtype=float)
    for x in range(len(buf)//6):
        v1=(buf[x*6],buf[x*6+1],buf[x*6+2])
        v2=from_int(buf[x*6+3:x*6+6])
        map[v1]=v2
        index=v1[0]+1000000*v1[1]+1000000*1000000*v1[2]
        map2[index]=v2
        np_map[x,0]=index
        np_map[x,1]=x
        np_map_out[x,:]=v2
    order = np.argsort(np_map, axis=0)
    np_map = np_map[order[:,0]]
    solved=0
    unsolved=0
    for x in b:
        if x.data.shape_keys!=None:
            for k in x.data.shape_keys.key_blocks.keys():
                local_unsolved=0
                source=bpy.data.objects[x["ref"]].data.shape_keys.key_blocks[k].data
                target=x.data.shape_keys.key_blocks[k].data

                seq = np.zeros([len(source)*3], dtype=float)
                source.foreach_get("co", seq)
                iseq =(seq*100000.).astype(int).reshape([-1,3])
                iseq = iseq[:,0]+1000000*iseq[:,1]+1000000*1000000*iseq[:,2]

                indexes = np.searchsorted(np_map[:,0], iseq)
                hits = (np_map[indexes,0] == iseq)
                if np.all(hits):
                    indexes2 = np_map[indexes,1]
                    coords = np_map_out[indexes2,:].reshape([-1])
                    target.foreach_set("co", coords)
                    solved += len(source)
                    continue

                for y in range(len(source)):
                    v = to_int(source[y])
                    if v in map:
                        target[y].co=map[v]
                        solved+=1
                    else:
                        unsolved+=1
                        local_unsolved+=1
                if local_unsolved>0:
                    print(local_unsolved, "unsolved verts in", x, "shape key", k)
        else:
            source = bpy.data.objects[x["ref"]].data.vertices
            target = x.data.vertices
            local_unsolved=0
            for y in range(len(source)):
                v=to_int(source[y])
                if v in map:
                    target[y].co=map[v]
                    solved+=1
                else:
                    unsolved+=1
                    local_unsolved+=1
            if local_unsolved>0:
                print(local_unsolved, "unsolved verts in", x)
            target.update()
    print("Loaded ", solved, "of", solved+unsolved, "vertex coordinates from cache")
    return unsolved==0, map

def save_solution_cache(path, b, hash):
    of=open(path+"solution.cache","wb")
    map={}
    for x in b:
        #n=b.name.split('.')[0]
        if x.data.shape_keys!=None:
            for k in x.data.shape_keys.key_blocks.keys():
                source=bpy.data.objects[x["ref"]].data.shape_keys.key_blocks[k].data
                target=x.data.shape_keys.key_blocks[k].data

                seq = np.zeros([len(source)*3], dtype=float)
                seq2 = np.zeros([len(source)*3], dtype=float)
                source.foreach_get("co", seq)
                target.foreach_get("co", seq2)
                iseq =(seq*100000.).astype(int)
                iseq2 =(seq2*100000.).astype(int)

                for y in range(len(source)):
                    v1=(iseq[y*3+0],iseq[y*3+1],iseq[y*3+2])
                    v2=(iseq2[y*3+0],iseq2[y*3+1],iseq2[y*3+2])
                    #v1=to_int(source[y])
                    #v2=to_int(target[y])
                    map[v1]=v2
        else:
            source = bpy.data.objects[x["ref"]].data.vertices
            target = x.data.vertices
            for y in range(len(source)):
                v1=to_int(source[y])
                v2=to_int(target[y])
                map[v1]=v2
    vf=[]
    print(len(map), "points in the map")
    for x in map:
        vf.extend([x[0],x[1],x[2],map[x][0],map[x][1],map[x][2]])
    buf = struct.pack('%si' % len(vf), *vf)
    of.write(hash)
    of.write(buf)
    of.close()



# Given an object 'b' that is parented to an armature in a nontrivial pose, and a reference
# object with the same number of vertices, deforms the rest position of 'b' until it matches 'b2' in pose position.
def solve_for_deform(b, b2, shape_key=None, counter=None, scale=Vector([1,1,1]), map={}):
    npass=0
    nfail=0
    if shape_key is None:
        for mod in b.modifiers:
            if mod.type=='SUBSURF':
                #print("Disabling the subsurface modifier on ", b)
                mod.show_viewport=False
                mod.show_render=False
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bpy.context.view_layer.objects.active = b    
    print(b.name, shape_key) #, len(map))
    intl_step=1.0
    baseline=True
    if b.data.shape_keys!=None:
        basis=b.data.shape_keys.key_blocks['Basis'].data
        undeformed_basis=b2.data.shape_keys.key_blocks['Basis'].data
        if shape_key==None:
            ps, fail=solve_for_deform(b, b2, 'Basis', map=map)
            npass = ps
            nfail = fail
            c=0
            box1 = bbox(basis)
            box2 = bbox(undeformed_basis)
            dim1=[box1[1][0]-box1[0][0],box1[1][1]-box1[0][1],box1[1][2]-box1[0][2]]
            dim2=[box2[1][0]-box2[0][0],box2[1][1]-box2[0][1],box2[1][2]-box2[0][2]]
            scale=Vector([dim1[0]/dim2[0],dim1[1]/dim2[1],dim1[2]/dim2[2]])
            for x in b.data.shape_keys.key_blocks:
                if x.name=='Basis':
                    continue
                ps, fail=solve_for_deform(b, b2, x.name, c, scale, map=map)
                npass+=ps
                nfail+=fail
                c+=1
            for x in b.data.shape_keys.key_blocks:
                x.value=0.0
            for mod in b.modifiers:
                if mod.type=='SUBSURF':
                    #print("Reenabling the subsurface modifier on ", b)
                    #mod.show_viewport=True
                    mod.show_render=True
            return npass, nfail
        else:
            target=b.data.shape_keys.key_blocks[shape_key].data
            undeformed=b2.data.shape_keys.key_blocks[shape_key].data
            b.active_shape_key_index=b.data.shape_keys.key_blocks.find(shape_key)
            for x in b.data.shape_keys.key_blocks:
                x.value=0.0
            b.data.shape_keys.key_blocks[shape_key].value=1.0
            if shape_key!='Basis':
                baseline=False
                n=len(target)
                for x in range(n):
                    target[x].co=basis[x].co+(undeformed[x].co-undeformed_basis[x].co)*scale
    else:
        target=b.data.vertices
        undeformed=b2.data.vertices

    #global lead_time, total_time 
    #t1 = time.time()
    bpy.ops.object.mode_set(mode='EDIT')  
    bpy.ops.object.mode_set(mode='OBJECT')  
    n = min(len(target), len(undeformed))
    # return (int(v.co[0]*100000.), int(v.co[1]*100000.), int(v.co[2]*100000.))
    ui = [x.co for x in undeformed]
    ui = (np.array(ui)*100000.).astype(int)
    for x in range(n):
        #v = to_int(undeformed[x])
        v = (ui[x][0],ui[x][1],ui[x][2])
        if v in map:
            target[x].co = map[v]

    n = len(target)
    active_set = list(range(n))
    solved=[0]*n
    frozen=[0]*n
    osc=[0]*n
    #t2 = time.time()
    #lead_time += t2-t1
    for attempt in range(2 if baseline else 1):
        errors = score_deform(b, depsgraph, undeformed, active_set)
        for k in range(len(errors)):
            if errors[k].length<0.0001:
                frozen[active_set[k]] = 1
                solved[active_set[k]] = 1
        if attempt==1:
            # if we didn't get everything first time, try again but using solved vertexes as hints
            for k in range(len(errors)):
                x = active_set[k]
                if not frozen[x]:
                    nearest=None
                    for y in range(n):
                        if frozen[y] and (nearest==None or (undeformed[y].co-undeformed[x].co).length < (undeformed[nearest].co-undeformed[x].co).length):
                            nearest=y
                    if nearest is not None:
                        target[x].co=target[nearest].co + (undeformed[x].co-undeformed[nearest].co)
            errors = score_deform(b, depsgraph, undeformed, active_set)
        errors = {active_set[x]:errors[x] for x in range(len(active_set))}
        errors2={}
        active_set2=[]
        for x in active_set: #range(len(errors)):
            if frozen[x]==0:
                errors2[x]=errors[x]
                #errors2.append(errors[x])
                active_set2.append(x)
        errors=errors2
        active_set=active_set2
        if len(active_set)==0:
            break
        dirs={x: errors[x] for x in active_set}
        steps={x: intl_step for x in active_set}
        age={x:0 for x in active_set}
        residual=sum([errors[x].length for x in errors])
        print('Initial residual vertex error ', residual/len(active_set))
        last_max_residual_pos=-1
        last_max_residual=0.0
        solved=frozen[:]
        live=n-sum(frozen)
        for p in range(160 if baseline else 20):
            vsave = {x:target[x].co.copy() for x in active_set}
            for x in active_set:
                target[x].co=vsave[x]+dirs[x]*steps[x]*(-1 if (not (age[x] & 1)) else 1)/max(1, osc[x])
            errors2 = score_deform(b, depsgraph, undeformed, active_set)
            errors2 = {active_set[x]:errors2[x] for x in range(len(active_set))}
            if p>=15 and last_max_residual_pos in active_set:
                print("Worst vertex:", last_max_residual_pos, "Current fit:", vsave[last_max_residual_pos], "Next guess:", target[last_max_residual_pos].co, "New error:", errors2[last_max_residual_pos], errors2[last_max_residual_pos].length, 
                    "Dir", dirs[last_max_residual_pos], "step", steps[last_max_residual_pos], "age", age[last_max_residual_pos], "osc", osc[last_max_residual_pos])
            moved=0
            mean_step=0
            max_residual=0.0
            max_residual_pos=-1
            new_active_set=[]
            for k in range(len(active_set)):
                x=active_set[k]
                if errors[x][0]*errors2[x][0]+errors[x][1]*errors2[x][1]+errors[x][2]*errors2[x][2]>0.0:
                    osc[x]=0
                else:
                    osc[x]+=1
                #for x in active_set:
                #if frozen[x]:
                #    continue
                if errors2[x].length<errors[x].length:
                    delta=errors[x]-errors2[x]
                    delta/=delta.length
                    delta*=errors[x].length
                    cos_phi=delta.dot(errors[x])/(errors[x].length*delta.length)
                    beta=-0.5
                    if live<0.05*n:
                        beta = 0.25*((p%5)-2)
                    dirs[x]=errors2[x]+beta*delta*(1.0-cos_phi)
                    mean_step+=steps[x]
                    if steps[x]<1.3:
                        steps[x]*=1.25
                    errors[x]=errors2[x]
                    age[x]=0
                    moved+=1
                    if errors[x].length<0.0001:
                        map[to_int(undeformed[x])] = target[x].co
                        frozen[x]=1
                        solved[x]=1
                        live-=1
                        continue
                else:
                    age[x]+=1
                    if steps[x]>0.01:
                        target[x].co=vsave[x]
                        steps[x]/=2
                    else:
                        if age[x]<15:
                            target[x].co=vsave[x]
                            dirs[x]=Vector([dirs[x][1]*math.sin(p),dirs[x][2]*math.cos(p),dirs[x][0]])
                            steps[x]=intl_step
                        else:
                            # move anyway
                            age[x]=0
                            errors[x]=errors2[x]
                            #frozen[x]=1
                            #live-=1
                if errors[x].length>max_residual:
                    max_residual=errors[x].length
                    max_residual_pos=x
                new_active_set.append(x)
            active_set = new_active_set
            if len(active_set)==0:
                break
            last_residual = residual
            last_max_residual = max_residual
            last_max_residual_pos = max_residual_pos
            residual=sum([errors[x].length for x in errors])
            print("Pass ", p, ": residual vertex error %.6f %.6f, %.6f moved, " % (residual/len(active_set), max_residual, float(moved)/len(active_set)), 
                'mean step %.3f' % (mean_step/max(moved,1)), ', ', live, 'live')
            npass+=1
            if max_residual<0.0001 or live==0:
                break  
        print(sum(solved), "/", n, " vertices solved")
        if sum(solved) in (0, n):
            break
    #t3 = time.time()
    #total_time += t3-t1            
    if shape_key is None:
        for mod in b.modifiers:
            if mod.type=='SUBSURF':
                print("Reenabling the subsurface modifier on ", b)
                #mod.show_viewport=True
                mod.show_render=True
    return npass, n-sum(solved)
