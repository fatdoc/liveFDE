import test from 'node:test'
import assert from 'node:assert/strict'
import {formatTimestamp,seekProblem,timestampOrigin} from '../src/features/sessions/transcriptionTimeline.ts'
test('millisecond precision is preserved in the displayed start and end',()=>{assert.equal(formatTimestamp(60420),'01:00.420');for(const v of [null,undefined,NaN,Infinity,-1])assert.equal(formatTimestamp(v),'时间未知')})
test('unknown, nonfinite, reversed, negative or out-of-range intervals cannot seek',()=>{for(const [a,b,d] of [[null,5,10],[NaN,5,10],[0,Infinity,10],[-1,5,10],[5000,2000,10],[1,1,10],[10000,11000,10],[9000,10001,10],[0,1000,null],[0,1000,Infinity]])assert.ok(seekProblem(a,b,d));assert.equal(seekProblem(420,5610,8),null);assert.equal(seekProblem(0,8000,8),null)})
test('VAD and provider boundaries never promise word alignment',()=>{assert.match(timestampOrigin({timestamp_source:'vad'}),/VAD.*非逐词/);assert.match(timestampOrigin({timestamp_source:'provider'}),/服务.*未验证逐词/);assert.match(timestampOrigin({}, {timestamp_sources:['vad']}),/VAD/);assert.match(timestampOrigin({}, {timestamp_sources:['vad','provider']}),/未确认/)})
