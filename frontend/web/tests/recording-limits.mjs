import test from 'node:test'
import assert from 'node:assert/strict'
import {recordingChoiceValid,readableBytes,readableDuration} from '../src/features/capture/captureLimitPolicy.ts'
const MiB=1024**2
test('server limits and free budget constrain integer byte selections with 1 MiB minimum',()=>{const l={max_seconds:7200,max_bytes:4*MiB,available_max_bytes:2*MiB};assert.equal(recordingChoiceValid(l,7200,2*MiB),true);assert.equal(recordingChoiceValid(l,1,MiB),true);for(const [s,b] of [[7201,MiB],[1.5,MiB],[1,2*MiB+1],[0,MiB],[1,MiB-1],[1,MiB+0.1],[Infinity,MiB]])assert.equal(recordingChoiceValid(l,s,b),false);assert.equal(recordingChoiceValid(undefined,1,MiB),false)})
test('human readable units preserve familiar default and presets',()=>{assert.equal(readableBytes(8*1024**3),'8 GiB');assert.equal(readableBytes(512*MiB),'512 MiB');assert.deepEqual([1800,3600,7200,14400].map(readableDuration),['30分钟','1小时','2小时','4小时'])})
