import test from 'node:test'
import assert from 'node:assert/strict'
import {changed, savePayload, safeReason, statusText, validTimeout} from '../src/features/llm/settings.ts'
const saved={revision:'rev1',base_url:'https://example.com/v1',model:'test',timeout_seconds:60}
const draft={base_url:saved.base_url,model:saved.model,timeout_seconds:60}
test('empty key is omitted while replacement is explicit and revision bound',()=>{assert.equal('api_key' in savePayload(saved,draft,''),false);assert.equal(savePayload(saved,draft,'synthetic').api_key,'synthetic');assert.equal(savePayload(saved,draft,'').expected_revision,'rev1')})
test('draft/key changes invalidate test eligibility',()=>{assert.equal(changed(saved,draft,''),false);assert.equal(changed(saved,draft,'synthetic'),true);assert.equal(changed(saved,{...draft,model:'new'},''),true)})
test('errors never echo unknown content and status is connection scoped',()=>{assert.doesNotMatch(safeReason('raw-private-secret'),/raw-private-secret/);assert.equal(statusText('verified'),'连接测试成功');assert.match(statusText('unknown'),/禁止重复/);assert.match(safeReason('llm_auth_failed'),/鉴权失败/)})

test('diagnostic timeout accepts only inclusive 1–120 integer seconds',()=>{for(const n of [0,-1,1.5,120.1,121,NaN,Infinity])assert.equal(validTimeout(n),false);for(const n of [1,60,120])assert.equal(validTimeout(n),true)})
