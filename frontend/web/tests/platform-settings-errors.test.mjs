import test from 'node:test'
import assert from 'node:assert/strict'
import { platformError, platformStatus, validDouyinSource } from '../src/features/capture/platformSettings.ts'

test('empty, transport and schema failures never assert cookie expiry', () => {
  for (const code of ['source_empty_response', 'source_parse_failed', 'source_network_error', 'source_timeout', 'source_schema_changed', 'source_protocol_error']) {
    assert.ok(platformError(code).length > 0)
    assert.doesNotMatch(platformError(code), /Cookie 已过期|Cookie 失效|请更新 Cookie/)
  }
  assert.match(platformError('source_auth_required'), /核对登录及授权条件/)
  assert.doesNotMatch(platformError('source_auth_required'), /已过期|要求重新登录/)
  assert.equal(platformStatus.needs_update, '需要核对接入信息')
})
test('saved credentials and a successful parse remain distinct states', () => {
  assert.notEqual(platformStatus.unverified, platformStatus.verified)
  assert.match(platformStatus.unverified, /尚未验证/)
  assert.match(platformStatus.verified, /当次解析/)
})
test('only numeric PC room references pass; no signed streams or pasted secrets', () => {
  assert.equal(validDouyinSource('https://live.douyin.com/123456/'), true)
  for (const value of ['https://v.douyin.com/short', 'https://live.douyin.com/123?cookie=secret', 'https://other.example/123', 'sessionid=secret']) assert.equal(validDouyinSource(value), false)
})
test('unknown upstream strings are not echoed into the page', () => {
  assert.ok(!platformError('Cookie: sessionid=unsafe').includes('unsafe'))
  assert.equal(platformError(null), '')
})

test('unsafe sources explain policy instead of blaming credentials or suggesting retries', () => {
  assert.match(platformError('https_required'), /HTTPS/)
  assert.match(platformError('domain_not_allowed'), /未获允许/)
  assert.match(platformError('unsafe_stream_url'), /安全策略/)
  for (const code of ['https_required', 'domain_not_allowed', 'unsafe_stream_url']) assert.doesNotMatch(platformError(code), /过期|更新 Cookie|重试/)
})
