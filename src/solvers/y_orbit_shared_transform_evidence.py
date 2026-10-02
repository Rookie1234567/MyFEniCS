"""Complete storage-equivalence witnesses for the opt-in same80 transform bank.

No orientation formulas live here. The default collector and its six existing
public transforms provide the independent original record/panel controls.
"""
from __future__ import annotations

import hashlib
import json
import weakref
import numpy as np

from .y_orbit_transform_bank import _backing

SCHEMA = "task40extra.same80-shared-transform-equivalence.v1"
DIRECTIONS = ("primal_to_canonical", "primal_from_canonical", "dual_to_canonical",
              "dual_from_canonical", "functional_to_canonical", "functional_from_canonical")
ROLES = ("full", "twist_0", "twist_1")


def _hash(array):
    return hashlib.sha256(np.asarray(array).tobytes(order="C")).hexdigest()


def _plain(value):
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _relative(left, right):
    return float(np.linalg.norm(left-right) / max(np.linalg.norm(right), np.finfo(float).tiny))


class SharedTransformEvidence:
    def __init__(self, bank, *, save_array, event, allocation_gate, mapping_limit, direct_profile=None):
        self.bank, self.save, self.event, self.gate = bank, save_array, event, allocation_gate
        self.limit = float(mapping_limit)
        self.direct_profile=direct_profile
        if direct_profile is not None:
            from .y_orbit_direct_profile import direct_profile_metadata
            if direct_profile_metadata(direct_profile).name not in ('X','XZ'):raise ValueError('only directX/XZ shared evidence is admitted')
        self.roles, self.stages, self.named, self.owner_artifacts = [], [], {}, {}
        self.reference_artifacts = {}
        self.payload_artifacts = {}

    def snapshot(self, stage, *, extra=None, extra_facts=None):
        arrays = {**self.named, **(extra or {})}
        self.gate("shared_owner_receipt_"+stage, {"matrix_payload_bytes": 0,
            "workspace_bytes": (8 << 20) + 2048 * (len(arrays)+len(self.bank.named_arrays()))})
        receipt = self.bank.receipt(arrays, stage=stage)
        all_arrays = {**self.bank.named_arrays(), **arrays}
        views = {item["name"]: item for item in receipt["views"]}
        for owner in receipt["owners"]:
            token = owner["owner_id"]
            if token in self.owner_artifacts:
                if self.owner_artifacts[token]["sha256"] != owner["sha256"]:
                    raise ValueError("named numerical owner changed after evidence export")
                continue
            value = all_arrays[owner["borrowers"][0]]
            backing, _, _ = _backing(value)
            if isinstance(backing, np.ndarray):
                flat = backing.ravel(order="K")
                if backing.size and not np.shares_memory(flat, backing):
                    raise ValueError("exact owner payload must be exported without an implicit copy")
                raw = flat.view(np.uint8)
            else:
                raw = np.frombuffer(memoryview(backing), dtype=np.uint8)
            if int(raw.nbytes) != owner["allocation_nbytes"] or _hash(raw) != owner["sha256"]:
                raise ValueError("exact backing-owner byte span differs from receipt")
            content=(owner["sha256"],int(raw.nbytes))
            name=self.payload_artifacts.get(content)
            if name is None:
                name = "shared_owner_"+token.replace("-", "_")
                self.save(name, raw)
                self.payload_artifacts[content]=name
            self.owner_artifacts[token] = {"artifact": name, "sha256": owner["sha256"],
                                          "allocation_nbytes": int(raw.nbytes)}
        for name, view in views.items():
            if (name.startswith("bank.template.") or name.startswith(tuple(role+".record." for role in ROLES))
                    and name.endswith((".matrix", ".inverse"))):
                if view["writeable"] or view["owner_id"] not in self.owner_artifacts:
                    raise ValueError("shared transform borrower is mutable or missing")
        receipt["allocation_boundary"] = "shared_owner_receipt_"+stage
        receipt["owner_artifacts"] = {item["owner_id"]: self.owner_artifacts[item["owner_id"]]
                                      for item in receipt["owners"]}
        receipt.update(extra_facts or {})
        self.stages.append(receipt)
        self.event("shared_transform_owner_stage", {"stage": stage, "receipt_sha256": hashlib.sha256(
            json.dumps(receipt,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest(),
            "matrix_template_count": receipt["matrix_template_count"], "lazy_inverse_count": receipt["lazy_inverse_count"],
            "sum_view_nbytes_with_aliases": receipt["sum_view_nbytes_with_aliases"],
            "unique_backing_owner_nbytes": receipt["unique_backing_owner_nbytes"], "payload_is_RSS": False})
        return receipt

    def compare_streamed(self, role, shared, *, space, floquet, axes, frozen_context, load_array):
        """X/XZ actual records, one original-helper control at a time; no collector copy."""
        from .hcurl_canonical_vector_dolfinx import _physical_entity_transform
        if self.direct_profile not in ('X','XZ') or role not in ROLES or shared._transform_bank is not self.bank:
            raise ValueError('streamed controls require the exact directX/XZ run-local bank')
        if role in [item['role'] for item in self.roles]:raise ValueError('duplicate streamed role')
        n=len(shared.independent);cell_dim=int(space.element.space_dimension)
        self.gate('direct_streamed_native_partition_'+role,{'matrix_payload_bytes':3*shared.full_rows*8,'workspace_bytes':1<<20})
        expected=np.setdiff1d(np.arange(shared.full_rows),np.asarray(floquet.mpc.slaves))
        if not np.array_equal(expected,shared.independent):raise ValueError('actual complete native independent/slave partition differs')
        row_of={int(value):index for index,value in enumerate(shared.independent)}
        self.named.update(shared.named_backing_arrays(role));self.snapshot(role+'_streamed_controls_begin')
        before=self.bank.receipt(stage='lazy_before_'+role)['lazy_inverse_count']
        actual_arrays={}
        for name,array,signature in (('cell_info',space.mesh.topology.get_cell_permutation_info(),frozen_context['orientation']),
                                    ('geometry_x',space.mesh.geometry.x,frozen_context['mesh']['geometry_x'])):
            actual={'shape':list(array.shape),'dtype':str(array.dtype),'sha256':_hash(array)}
            if actual!={'shape':list(signature['shape']),'dtype':signature['dtype'],'sha256':signature['sha256']}:
                raise ValueError('fresh actual topology/orientation witness differs')
            artifact='shared_'+role+'_'+name;self.save(artifact,array);actual_arrays[name]={'artifact':artifact,'signature':actual}
        insertion={key:index for index,key in enumerate(shared.records,1)}
        records=[];rows_flat=[];references={};covered=[];canonical=[]
        grid=[np.asarray(axes[name],float) for name in ('x','y','z')]
        self.gate('direct_shared_one_state_control_'+role,{'matrix_payload_bytes':2*cell_dim*cell_dim*8+4*108*108*16,
            'workspace_bytes':4<<20,'one_state_control_only':True,'unshared_collector_created':False})
        for orbit in range(shared.ny):
            for base in shared.bases:
                record_key=(orbit,base);rows,matrix=shared.records[record_key];key=shared.transform_key(record_key)
                witness=shared.actual_state_witness(record_key);dimension=int(base[0]);positions=witness['positions']
                storage=np.asarray(space.dofmap.cell_dofs(witness['cell']))[positions]
                if not np.array_equal(rows,np.asarray([row_of[int(value)] for value in storage])):
                    raise ValueError('actual native ordered entity channels differ')
                coords=np.asarray(witness['native_coordinates'],float);indexed=[]
                for point in coords:
                    location=[]
                    for axis,value in zip(grid,point,strict=True):
                        matches=np.flatnonzero(np.abs(axis-value)<=1e-9)
                        if len(matches)!=1:raise ValueError('actual entity lacks unique original grid coordinate')
                        location.append(int(matches[0]))
                    indexed.append(tuple(location))
                anchor=min(point[1] for point in indexed)
                actual_base=(dimension,tuple(sorted((ix,iy-anchor,iz) for ix,iy,iz in indexed)))
                if actual_base!=base or anchor!=orbit:raise ValueError('actual orbit/base/slot geometry differs')
                transform_t=None
                if dimension in (1,2):
                    control,semantics=_physical_entity_transform(coords,dimension,4,1e-9)
                    if tuple(semantics)!=tuple(key.semantics):raise ValueError('original coefficient semantics differ')
                else:
                    raw=np.eye(cell_dim,dtype=float).ravel()
                    space.element.Tt_apply(raw,np.asarray([witness['cell_info']],dtype=np.uint32),cell_dim)
                    transform_t=raw.reshape(cell_dim,cell_dim)
                    control=np.linalg.inv(transform_t[np.ix_(positions,positions)]).astype(np.complex128)
                inverse_control=np.linalg.inv(control);inverse=self.bank.inverse(matrix);size=len(rows)
                if not records:self.snapshot(role+'_after_first_inverse_request')
                md,idiff=_relative(matrix,control),_relative(inverse,inverse_control)
                composition=float(np.linalg.norm(inverse@matrix-np.eye(size))/np.sqrt(size))
                if max(md,idiff,composition)>self.limit or _hash(matrix)!=_hash(control) or _hash(inverse)!=_hash(inverse_control):
                    raise ValueError('complete actual state matrix/inverse differs from original helper')
                template=self.bank.template_id_for(matrix)
                if template not in references:
                    prefix='shared_reference_'+role+'_'+template.replace('-','_')
                    self.save(prefix+'_matrix',control);self.save(prefix+'_inverse',inverse_control)
                    references[template]={'matrix_artifact':prefix+'_matrix','inverse_artifact':prefix+'_inverse',
                        'matrix_sha256':_hash(control),'inverse_sha256':_hash(inverse_control)}
                    if transform_t is not None:
                        self.save(prefix+'_full_Tt',transform_t)
                        references[template]['full_Tt_artifact']=prefix+'_full_Tt'
                elif references[template]['matrix_sha256']!=_hash(control) or references[template]['inverse_sha256']!=_hash(inverse_control):
                    raise ValueError('actual semantic keys collide with a different full control')
                first,count=shared.slots[base];offset=len(rows_flat);rows_flat.extend(map(int,rows));covered.extend(map(int,rows))
                canonical.extend(range(orbit*shared.width+first,orbit*shared.width+first+count))
                j=np.arange(size);x=np.cos(.31*j)+1j*np.sin(.47*j);d=np.sin(.29*j)+1j*np.cos(.41*j);f=np.cos(.23*j)+1j*np.sin(.37*j)
                pairing=float(max(abs(np.vdot(inverse.conj().T@d,matrix@x)-np.vdot(d,x)),
                                  abs(np.dot(inverse.T@f,matrix@x)-np.dot(f,x)))/max(np.linalg.norm(d)*np.linalg.norm(x),np.linalg.norm(f)*np.linalg.norm(x),1.))
                if not np.isfinite(pairing) or pairing>self.limit:raise ValueError('original non-Hermitian moment pairing failed')
                records.append({'orbit':int(orbit),'base':_plain(base),'dimension':dimension,'first':int(first),'size':int(count),
                    'rows_offset':offset,'rows_count':size,'template_id':template,'actual_key':_plain(key.__dict__),
                    'actual_state_witness':_plain(witness),'borrower_record_index':insertion[record_key],
                    'matrix_sha256':_hash(matrix),'inverse_sha256':_hash(inverse),'matrix_difference':md,'inverse_difference':idiff,
                    'inverse_composition':composition,'nonhermitian_pairing':pairing})
        control=inverse_control=transform_t=raw=None
        if sorted(covered)!=list(range(n)) or sorted(canonical)!=list(range(n)):
            raise ValueError('complete actual native and canonical partitions must occur exactly once')
        row_artifact='shared_'+role+'_record_rows'
        self.gate('direct_streamed_complete_row_export_'+role,{'matrix_payload_bytes':n*8,'workspace_bytes':1<<20})
        self.save(row_artifact,np.asarray(rows_flat,dtype=np.int64))
        self.gate('direct_streamed_six_operator_panels_'+role,{'matrix_payload_bytes':4*n*32*16,'workspace_bytes':8<<20,
            'all_record_columns':True,'one_state_control_only':True})
        groups={template:[item for item in records if item['template_id']==template] for template in references}
        directions=[]
        for direction in DIRECTIONS:
            ih=hashlib.sha256();oh=hashlib.sha256();nh=hashlib.sha256();difference=0.
            for start in range(0,108,32):
                columns=min(32,108-start);panel=np.zeros((n,columns),complex);expected_panel=np.empty_like(panel)
                for item in records:
                    if start>=item['size']:continue
                    rr=rows_flat[item['rows_offset']:item['rows_offset']+item['size']]
                    cr=list(range(item['orbit']*shared.width+item['first'],item['orbit']*shared.width+item['first']+item['size']))
                    source_rows=rr if direction.endswith('to_canonical') else cr;count=min(columns,item['size']-start)
                    panel[np.asarray(source_rows)[start:start+count],np.arange(count)]=1
                for template,items in groups.items():
                    control=load_array(references[template]['matrix_artifact']);inverse_control=load_array(references[template]['inverse_artifact'])
                    for item in items:
                        rr=rows_flat[item['rows_offset']:item['rows_offset']+item['size']]
                        cr=list(range(item['orbit']*shared.width+item['first'],item['orbit']*shared.width+item['first']+item['size']))
                        if direction==DIRECTIONS[0]:expected_panel[cr]=inverse_control@panel[rr]
                        elif direction==DIRECTIONS[1]:expected_panel[rr]=control@panel[cr]
                        elif direction==DIRECTIONS[2]:expected_panel[cr]=control.conj().T@panel[rr]
                        elif direction==DIRECTIONS[3]:expected_panel[rr]=inverse_control.conj().T@panel[cr]
                        elif direction==DIRECTIONS[4]:expected_panel[cr]=control.T@panel[rr]
                        else:expected_panel[rr]=inverse_control.T@panel[cr]
                    control=inverse_control=None
                actual=shared.transform(panel,direction=direction);difference=max(difference,_relative(actual,expected_panel))
                ih.update(panel.tobytes(order='C'));oh.update(expected_panel.tobytes(order='C'));nh.update(actual.tobytes(order='C'))
            if difference>self.limit or oh.hexdigest()!=nh.hexdigest():raise ValueError('complete six-direction streamed original action differs')
            directions.append({'direction':direction,'relative_difference':difference,'complete_columns':108,'panel_columns_max':32,
                'input_sha256':ih.hexdigest(),'default_action_sha256':oh.hexdigest(),'shared_action_sha256':nh.hexdigest()})
            if direction==DIRECTIONS[0]:
                self.named.update(shared.named_backing_arrays(role));self.snapshot(role+'_after_first_inverse_direction')
        self.named.update(shared.named_backing_arrays(role));complete=self.snapshot(role+'_after_all_six_directions')
        views={item['name']:item for item in complete['views']}
        for item in records:
            prefix=role+'.record.'+format(item['borrower_record_index'],'06d')
            for member in ('rows','matrix','inverse'):item[member+'_owner_id']=views[prefix+'.'+member]['owner_id']
        result={'role':role,'full_rows':int(shared.full_rows),'ny':int(shared.ny),'width':int(shared.width),'independent_rows':n,
            'dimension_counts':_plain(shared.dimension_counts),'record_count':len(records),'base_count':len(shared.bases),
            'records':records,'record_rows_artifact':row_artifact,'references':references,'directions':directions,'actual_arrays':actual_arrays,
            'lazy_inverse_before':before,'lazy_inverse_after':self.bank.receipt(stage='lazy_after_'+role)['lazy_inverse_count'],
            'complete_native_independent_partition_equal':True,'complete_orbit_base_slot_partition_equal':True,
            'every_actual_record_matrix_inverse_compared':True,'all_six_complete_operator_columns_compared':True,
            'shared_bank_instance_equal':True,'mutable_transform_borrow_detected':False,'key_collision_detected':False,
            'original_control_scope':'streamed actual original helpers; one state scratch; no unshared collector'}
        self.roles.append(result);self.event('shared_complete_role_equivalence_before_factor',result);return result

    def compare(self, role, shared, default, *, cell_info, geometry_x, frozen_context):
        if role not in ROLES or role in [item["role"] for item in self.roles]:
            raise ValueError("one complete comparison for each full/twist role required")
        if shared._transform_bank is not self.bank:
            raise ValueError("full/local borrowers must share the exact same run-local bank instance")
        if (shared.full_rows != default.full_rows or shared.ny != default.ny or shared.width != default.width
                or shared.bases != default.bases or shared.slots != default.slots
                or shared.dimension_counts != default.dimension_counts
                or list(shared.records) != list(default.records)
                or not np.array_equal(shared.independent, default.independent)
                or not np.array_equal(shared.y_widths, default.y_widths)):
            raise ValueError("complete native rows/orbit/base/slot/channel partition changed")
        self.named.update(shared.named_backing_arrays(role))
        self.snapshot(role+"_unshared_overlap", extra=default.named_backing_arrays("default_"+role))
        before = self.bank.receipt(stage="lazy_count_before_"+role)["lazy_inverse_count"]
        actual_arrays={}
        for name,array,expected in (("cell_info",cell_info,frozen_context["orientation"]),
                                   ("geometry_x",geometry_x,frozen_context["mesh"]["geometry_x"])):
            signature={"shape":list(array.shape),"dtype":str(array.dtype),"sha256":_hash(array)}
            if signature!={"shape":list(expected["shape"]),"dtype":expected["dtype"],"sha256":expected["sha256"]}:
                raise ValueError('actual state witness discrete geometry/orientation differs')
            artifact='shared_'+role+'_'+name
            self.save(artifact,array)
            actual_arrays[name]={"artifact":artifact,"signature":signature}
        records, reference_templates = [], {}
        insertion_indices = {key: index for index,key in enumerate(shared.records,1)}
        rows_flat = []
        for orbit in range(shared.ny):
            for base in shared.bases:
                record_key = (orbit, base)
                rows, matrix = shared.records[record_key]
                old_rows, old_matrix = default.records[record_key]
                if not np.array_equal(rows, old_rows):
                    raise ValueError("complete record native row order changed")
                key = shared.transform_key(record_key)
                self.bank.validate_borrow(key, matrix)
                template = self.bank.template_id_for(matrix)
                inverse = self.bank.inverse(matrix)
                if not records:
                    self.snapshot(role+"_after_first_inverse_request", extra=default.named_backing_arrays("default_"+role))
                old_inverse = np.linalg.inv(old_matrix)
                size = len(rows)
                matrix_difference, inverse_difference = _relative(matrix,old_matrix), _relative(inverse,old_inverse)
                composition = float(np.linalg.norm(inverse@matrix-np.eye(size))/np.sqrt(size))
                if max(matrix_difference,inverse_difference,composition)>self.limit:
                    raise ValueError("complete original matrix/inverse/composition changed")
                # Exact content comparisons also reject a key/content collision.
                if matrix.tobytes(order="C") != old_matrix.tobytes(order="C"):
                    raise ValueError("actual transform key refers to different complete default coefficients")
                if inverse.tobytes(order="C") != old_inverse.tobytes(order="C"):
                    raise ValueError("actual shared inverse differs from the complete default inverse")
                if template not in reference_templates:
                    prefix="shared_reference_"+role+"_"+template.replace("-","_")
                    self.save(prefix+"_matrix",old_matrix);self.save(prefix+"_inverse",old_inverse)
                    reference_templates[template]={"matrix_artifact":prefix+"_matrix", "inverse_artifact":prefix+"_inverse",
                        "matrix_sha256":_hash(old_matrix),"inverse_sha256":_hash(old_inverse)}
                elif (reference_templates[template]["matrix_sha256"]!=_hash(old_matrix)
                      or reference_templates[template]["inverse_sha256"]!=_hash(old_inverse)):
                    raise ValueError("same shared template contains incompatible default records")
                first,count=shared.slots[base];offset=len(rows_flat);rows_flat.extend(map(int,rows))
                j=np.arange(size);primal=np.cos(.31*j)+1j*np.sin(.47*j)
                dual=np.sin(.29*j)+1j*np.cos(.41*j);functional=np.cos(.23*j)+1j*np.sin(.37*j)
                pd=abs(np.vdot(inverse.conj().T@dual,matrix@primal)-np.vdot(dual,primal))
                fp=abs(np.dot(inverse.T@functional,matrix@primal)-np.dot(functional,primal))
                pairing_scale=max(np.linalg.norm(dual)*np.linalg.norm(primal),np.linalg.norm(functional)*np.linalg.norm(primal),1.)
                pairing=float(max(pd,fp)/pairing_scale)
                if not np.isfinite(pairing) or pairing>self.limit:raise ValueError("non-Hermitian moment pairing changed")
                records.append({"orbit":int(orbit),"base":_plain(base),"dimension":int(base[0]),
                    "first":int(first),"size":int(count),"rows_offset":offset,"rows_count":len(rows),
                    "template_id":template,"actual_key":_plain(key.__dict__),
                    "borrower_record_index":insertion_indices[record_key],
                    "actual_state_witness":_plain(shared.actual_state_witness(record_key)),
                    "matrix_sha256":_hash(matrix),"inverse_sha256":_hash(inverse),
                    "matrix_difference":matrix_difference,"inverse_difference":inverse_difference,
                    "inverse_composition":composition,"nonhermitian_pairing":pairing})
        row_artifact="shared_"+role+"_record_rows"
        self.gate("shared_record_row_inventory_"+role,{"matrix_payload_bytes":len(rows_flat)*8,"workspace_bytes":1<<20})
        self.save(row_artifact,np.asarray(rows_flat,dtype=np.int64))
        # Simultaneous block identity panels cover every column of every record.
        # Their disjoint exact row partition makes this an exhaustive operator proof.
        max_size=max(item["size"] for item in records);n=len(shared.independent)
        self.gate("shared_complete_six_direction_panels_"+role,{"matrix_payload_bytes":4*n*32*16,
            "workspace_bytes":16<<20,"panel_columns_max":32,"all_record_columns":True})
        directions=[]
        for direction in DIRECTIONS:
            source_hash=hashlib.sha256();old_hash=hashlib.sha256();new_hash=hashlib.sha256();difference=0.
            for start in range(0,max_size,32):
                columns=min(32,max_size-start);panel=np.zeros((n,columns),complex)
                for item in records:
                    if start>=item["size"]:continue
                    rows=rows_flat[item["rows_offset"]:item["rows_offset"]+item["rows_count"]]
                    count=min(columns,item["size"]-start)
                    source_rows=(rows if direction.endswith("to_canonical") else
                        range(item["orbit"]*shared.width+item["first"],item["orbit"]*shared.width+item["first"]+item["size"]))
                    panel[np.asarray(list(source_rows))[start:start+count],np.arange(count)]=1
                old=default.transform(panel,direction=direction);new=shared.transform(panel,direction=direction)
                difference=max(difference,_relative(new,old))
                source_hash.update(panel.tobytes(order="C"));old_hash.update(old.tobytes(order="C"));new_hash.update(new.tobytes(order="C"))
            if difference>self.limit or old_hash.hexdigest()!=new_hash.hexdigest():
                raise ValueError("complete original six-direction panel action changed")
            directions.append({"direction":direction,"relative_difference":difference,"complete_columns":max_size,
                "panel_columns_max":32,"input_sha256":source_hash.hexdigest(),
                "default_action_sha256":old_hash.hexdigest(),"shared_action_sha256":new_hash.hexdigest()})
            if direction==DIRECTIONS[0]:self.snapshot(role+"_after_first_inverse_direction",extra=default.named_backing_arrays("default_"+role))
        self.named.update(shared.named_backing_arrays(role))
        complete_stage=self.snapshot(role+"_after_all_six_directions",extra=default.named_backing_arrays("default_"+role))
        complete_views={item["name"]:item for item in complete_stage["views"]}
        for item in records:
            prefix=role+".record."+format(item["borrower_record_index"],"06d")
            for member in ("rows","matrix","inverse"):
                item[member+"_owner_id"]=complete_views[prefix+"."+member]["owner_id"]
        result={"role":role,"full_rows":int(shared.full_rows),"ny":int(shared.ny),"width":int(shared.width),
            "independent_rows":n,"dimension_counts":_plain(shared.dimension_counts),"record_count":len(records),
            "base_count":len(shared.bases),"records":records,"record_rows_artifact":row_artifact,
            "references":reference_templates,"directions":directions,"actual_arrays":actual_arrays,
            "lazy_inverse_before":before,
            "lazy_inverse_after":self.bank.receipt(stage="lazy_count_after_"+role)["lazy_inverse_count"],
            "complete_native_independent_partition_equal":True,"complete_orbit_base_slot_partition_equal":True,
            "every_actual_record_matrix_inverse_compared":True,"all_six_complete_operator_columns_compared":True,
            "shared_bank_instance_equal":True,"mutable_transform_borrow_detected":False,"key_collision_detected":False}
        self.roles.append(result)
        self.event("shared_complete_role_equivalence_before_factor",result)
        return result

    def add_layout(self, role, layout, entities):
        if layout._borrowed_entities is not entities or entities._transform_bank is not self.bank:
            raise ValueError("local layout must borrow the already collected exact entity object")
        self.named.update(layout.named_backing_arrays(role+"_layout"))
        self.snapshot(role+"_layout_after_build")

    def owner_weak_anchors(self, extra=None):
        arrays={**self.bank.named_arrays(),**self.named,**(extra or {})}
        result={}
        for value in arrays.values():
            owner,anchor,_=_backing(value)
            result[id(owner)]=weakref.ref(anchor)
        return tuple(result.values())

    def cleanup(self, anchors):
        self.named.clear()
        self.bank.close()
        live=sum(ref() is not None for ref in anchors)
        if live:raise ValueError('declared transform/map owners still have live borrowers during cleanup')
        self.snapshot('cleanup',extra_facts={'cleanup_live_declared_owner_anchors':int(live),
            'cleanup_all_declared_borrowers_released':True,'allocator_RSS_reclamation_claimed':False})

    def failure_cleanup(self, anchors, error_type):
        self.named.clear()
        self.bank.close()
        self.event('shared_transform_cleanup_failure_evidence',{
            'original_error_type':error_type,'bank_closed':True,
            'live_declared_owner_anchors':int(sum(ref() is not None for ref in anchors)),
            'complete_cleanup_qualification_claimed':False,'allocator_RSS_reclamation_claimed':False})

    def result(self):
        if [item["role"] for item in self.roles]!=list(ROLES) or not self.bank.receipt(stage="sealed_check")["sealed"]:
            raise ValueError("complete full/two-local comparisons and sealed bank required before factors")
        return {"schema":SCHEMA if self.direct_profile is None else "task40extra.direct-shared-transform-equivalence.v1",
            "direct_profile":self.direct_profile,"roles":self.roles,"owner_stages":self.stages,
            "owner_artifacts":self.owner_artifacts,"mapping_limit":self.limit,"shared_transforms":True,
            "same80_p4_only":self.direct_profile is None,"local_layout_borrows_existing_entities":True,
            "complete_before_any_factor":True,"payload_is_RSS":False,"target_savings_measured":False}
