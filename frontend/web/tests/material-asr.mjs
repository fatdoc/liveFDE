import test from 'node:test'
import assert from 'node:assert/strict'
import {materialBlocker,cloudBudgetValid,providerReason} from '../src/features/sessions/materialASR.ts'
const t={provider:'tencent',configured:true,reason:null,max_duration_seconds:156,max_audio_bytes:5000000,network_checked:false}
test('cloud duration unknown and too long blocked; local actual limit enforced',()=>{for(const d of [null,NaN,Infinity,0,157])assert.ok(materialBlocker(t,d));assert.equal(materialBlocker(t,156),null);assert.ok(materialBlocker({...t,provider:'local',max_duration_seconds:100},101))})
test('unconfigured service and untrusted reason never reveal paths',()=>{assert.ok(materialBlocker({...t,configured:false},1));assert.doesNotMatch(providerReason('/private/key'),/private/);assert.ok(materialBlocker({...t,max_duration_seconds:null},1))})
test('cloud budget requires bounded integer calls and finite positive amount',()=>{assert.equal(cloudBudgetValid('1','0.1'),true);for(const [n,c] of [['0','1'],['11','1'],['1.5','1'],['1',''],['1','101'],['1','Infinity']])assert.equal(cloudBudgetValid(n,c),false)})
