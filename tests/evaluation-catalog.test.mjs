import test from 'node:test';
import assert from 'node:assert/strict';
import {reconcileArtifacts} from '../aeroblade/web/evaluation.js';
test('completed dataset remains selectable when catalog response predates completion',()=>{
 const completed={kind:'dataset',status:'completed',result:{dataset_id:'new',created_at:2,summary:{accepted:3}}};
 const rows=reconcileArtifacts([{dataset_id:'old',created_at:1}],[completed],'dataset','dataset_id');
 assert.deepEqual(rows.map(r=>r.dataset_id),['new','old']);assert.equal(rows[0].summary.accepted,3);
});
test('running artifacts are excluded and catalog identities are not duplicated',()=>{
 const tasks=[{kind:'train',status:'running',result:{model_id:'not-ready'}},{kind:'train',status:'completed',result:{model_id:'ready',created_at:2}}];
 assert.deepEqual(reconcileArtifacts([{model_id:'ready',created_at:2}],tasks,'train','model_id').map(r=>r.model_id),['ready']);
});
