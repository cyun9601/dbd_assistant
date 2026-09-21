"""공식 패치노트로 확인한 위키 누락을 보완한다. 원문이 바뀌면 재검토한다."""
import hashlib
import html
import json
import re
from pathlib import Path


def text_hash(text):
    return hashlib.sha256(' '.join(text.split()).encode('utf-8')).hexdigest()


def apply_corrections(record, dataset):
    path = Path(__file__).with_name('data_corrections.json')
    if not path.exists():
        return
    for correction in json.loads(path.read_text(encoding='utf-8')):
        if correction['dataset'] != dataset or correction['id'] != record['id']:
            continue
        field = correction['field']
        text_field = field.replace('_html', '_text')
        current = text_hash(record[text_field])
        if current == correction['corrected_text_sha256']:
            continue
        if current != correction['expected_text_sha256']:
            raise ValueError(f"{record['id']} {field}: 위키 원문이 바뀌었습니다. "
                             "data_corrections.json의 공식 패치 보완 내용을 재검토하세요.")
        value = record[field]
        for old, new in correction.get('replace', []):
            if old not in value:
                raise ValueError(f"{record['id']}: 보정 대상 문구가 없습니다: {old}")
            value = value.replace(old, new)
        value += correction.get('append_html', '')
        record[field] = value
        plain = re.sub(r'<br\s*/?>', ' ', value)
        record[text_field] = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', plain)).replace('•', '')).strip()
        if text_hash(record[text_field]) != correction['corrected_text_sha256']:
            raise ValueError(f"{record['id']}: 공식 패치 보정 결과가 예상과 다릅니다.")
