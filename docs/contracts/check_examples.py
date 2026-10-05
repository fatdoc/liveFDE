"""Validate synthetic draft contracts; this is not an API implementation."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).parent
SCHEMA = json.loads((ROOT / 'draft.schema.json').read_text())
FIXTURES = json.loads((ROOT / 'examples.json').read_text())
SEGMENTS = {row['id']: row for row in FIXTURES['source_segments']}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def semantic(kind, data):
    if kind == 'Evidence':
        start, end = data['start_ms'], data['end_ms']
        require(start is None or end >= start, 'reversed evidence interval')
        if data['kind'] == 'transcript_quote':
            source = SEGMENTS.get(data['segment_id'])
            require(source is not None, 'unknown source segment')
            require(data['source_id'] == source['source_id'], 'wrong source material')
            require(data['source_revision_id'] == source['source_revision_id'], 'wrong source revision')
            require(data['quote'] == source['text'], 'quote differs from source')
            require((start, end) == (source['start_ms'], source['end_ms']), 'invented timing')
    elif kind == 'PrepReference':
        if data['current_status'] == 'withdrawn':
            require(data['withdrawal_warning'] and not data['can_reconfirm'], 'withdrawn reference is usable')
    elif kind == 'ProviderResult':
        evidence = {row['id']: row for row in data['evidence']}
        require(len(evidence) == len(data['evidence']), 'duplicate evidence id')
        for row in evidence.values():
            semantic('Evidence', row)
        for row in data['assertions']:
            require(set(row['evidence_ids']) <= evidence.keys(), 'unknown assertion evidence')
        for row in data['candidate_assets']:
            source = evidence.get(row['evidence_id'])
            require(source is not None and source['kind'] == 'transcript_quote', 'candidate lacks original quote')
            require(row['quote'] == source['quote'], 'candidate changed quote')
            require(row['status'] == 'pending_review', 'provider approved candidate')
    elif kind == 'ReportSnapshot':
        start = datetime.fromisoformat(data['start_utc'].replace('Z', '+00:00')).astimezone(ZoneInfo(data['timezone']))
        end = datetime.fromisoformat(data['end_exclusive_utc'].replace('Z', '+00:00')).astimezone(ZoneInfo(data['timezone']))
        require(end > start, 'invalid report range')
        if data['kind'] == 'weekly':
            require(start.weekday() == 0 and start.hour == start.minute == start.second == start.microsecond == 0, 'week must start Monday midnight')
            require(end == start + timedelta(days=7), 'week must span seven local dates')
        for row in data['included'] + data['excluded']:
            semantic('SessionTime', row)
            require(row['streamer_id'] == data['streamer_id'], 'wrong report streamer')
            require(start.date().isoformat() <= row['session_local_date'] < end.date().isoformat(), 'source outside report dates')
        included = [row['session_id'] for row in data['included']]
        excluded = [row['session_id'] for row in data['excluded']]
        require(bool(included), 'report needs analyzed sources')
        require(len(set(included + excluded)) == len(included + excluded), 'duplicate report source')
        require((data['coverage'] == 'partial') == bool(excluded), 'coverage mismatch')
    elif kind == 'SessionTime':
        require((data['time_precision'] == 'date') == (data['started_at'] is None), 'date precision cannot invent time')
        if data['started_at']:
            local = datetime.fromisoformat(data['started_at'].replace('Z', '+00:00')).astimezone(ZoneInfo(data['timezone']))
            require(local.date().isoformat() == data['session_local_date'], 'local date mismatch')
    elif kind == 'AssetDraftEdit':
        before, after = data['before'], data['after']
        require(after['published_revision_id'] == before['published_revision_id'], 'pending draft displaced published asset')
        require(after['latest_revision_id'] != before['latest_revision_id'], 'edit needs new immutable revision')
        require(after['revision'] == before['revision'] + 1, 'concurrency revision must advance')
        require(after['latest_status'] == 'pending_review', 'edit must await review')


def validate(case):
    require(case['fixture'] is True, 'missing synthetic label')
    validator = Draft202012Validator({'$ref': '#/$defs/' + case['schema'], '$defs': SCHEMA['$defs']}, format_checker=FormatChecker())
    validator.validate(case['data'])
    semantic(case['schema'], case['data'])


def main():
    Draft202012Validator.check_schema(SCHEMA)
    for case in FIXTURES['valid']:
        validate(case)
    for case in FIXTURES['invalid']:
        try:
            validate(case)
        except (ValueError, ValidationError):
            continue
        raise AssertionError('negative fixture accepted: ' + case['name'])
    print(f"PASS: {len(FIXTURES['valid'])} valid fixtures; {len(FIXTURES['invalid'])} negative fixtures rejected")


if __name__ == '__main__':
    main()
