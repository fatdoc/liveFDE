import test from 'node:test'
import assert from 'node:assert/strict'
import {recordingChoiceValid} from '../src/features/capture/captureLimitPolicy.ts'
test('server limits and current free budget constrain integer selections',()=>{const l={max_seconds:7200,max_bytes:1000,available_max_bytes:500};assert.equal(recordingChoiceValid(l,7200,500),true);for(const [s,b] of [[7201,500],[1.5,500],[1,501],[0,1],[1,0],[1,1.1],[Infinity,1]])assert.equal(recordingChoiceValid(l,s,b),false);assert.equal(recordingChoiceValid(undefined,1,1),false)})
