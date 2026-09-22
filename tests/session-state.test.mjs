import test from 'node:test';import assert from 'node:assert/strict';
import {IdentityEpoch} from '../aeroblade/web/session-state.js';
test('different authenticated accounts invalidate responses',()=>{const s=new IdentityEpoch();s.update('a');const old=s.capture();s.update('b');assert.throws(()=>s.check(old),{name:'AbortError'});});
test('logout invalidates prior requests; same account refresh does not',()=>{const s=new IdentityEpoch();s.update('a');const old=s.capture();s.update('a');s.check(old);s.update(null);assert.throws(()=>s.check(old),{name:'AbortError'});});
