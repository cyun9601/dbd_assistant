import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_en_from_wiki as wiki
import update_patchnotes_from_steam as steam
from data_corrections import apply_corrections

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


class PatchParserTests(unittest.TestCase):
    def test_hotfix_suffix_is_preserved(self):
        self.assertEqual(steam.VERSION_RE.search('10.1.2a | Patch Notes')[1], '10.1.2a')

    def test_reworks_inline_descriptions_and_subheadings(self):
        body = ('[h3][b]Perk Updates[/b][/h3][h3][b]Survivor perks[/b][/h3]'
                '[list][*][p][b]Small Game[/b] [i](Rework)[/i][/p][/*]'
                '[*][p][b]Vigil [/b]All Survivors recover faster.[/p][/*][/list]'
                '[h2]Bug Fixes[/h2][list][*][p][b]Adrenaline[/b][/p][/*][/list]')
        self.assertEqual(steam.perks_changed(steam.to_blocks(body), steam.perk_index()),
                         ['Small_Game', 'Vigil'])

    def test_live_hotfix_changes_are_detected(self):
        note = next(p for p in read('patchnotes.json')['patches'] if p['version'] == '10.1.1')
        self.assertEqual(set(note['perk_updates']), {'RepressedAlliance', 'Vigil'})


class PendingTransitionTests(unittest.TestCase):
    def test_previous_release_is_promoted_before_next_ptb(self):
        perk = {'name': '퍽', 'owner': '공용', 'desc_text': '옛 설명',
                'desc_html': '옛 설명', 'desc_html_en': 'old', 'desc_text_en': 'old',
                'upcoming': True, 'upcoming_patch': '10.1.0', 'upcoming_date': '2026-08-25',
                'pending': {'desc_html': '현재 설명', 'desc_text': '현재 설명',
                            'desc_html_en': 'live', 'desc_text_en': 'live'}}
        self.assertTrue(wiki.promote_pending(perk, today='2026-09-21'))
        wiki.set_pending(perk, 'next', '10.2.0')
        self.assertEqual(perk['desc_text'], '현재 설명')
        self.assertEqual(perk['desc_text_en'], 'live')
        self.assertEqual(perk['pending']['desc_text_en'], 'next')
        self.assertEqual(perk['pending']['desc_text'], '')

    def test_changed_ptb_source_invalidates_old_translation(self):
        perk = {'upcoming_patch': '10.2.0', 'pending': {
            'desc_text_en': 'old PTB', 'desc_html': '옛 번역', 'desc_text': '옛 번역'}}
        wiki.set_pending(perk, 'new PTB', '10.2.0')
        self.assertEqual(perk['pending']['desc_text'], '')

    def test_unchanged_ptb_preserves_translation(self):
        perk = {'upcoming_patch': '10.2.0', 'pending': {
            'desc_text_en': 'PTB', 'desc_html': '번역', 'desc_text': '번역'}}
        wiki.set_pending(perk, '<b>PTB</b>', '10.2.0')
        self.assertEqual(perk['pending']['desc_text'], '번역')

    def test_live_notes_prevent_false_upcoming_when_dates_unavailable(self):
        data = {'patches': [
            {'version': '10.1.0', 'ptb': True, 'perk_updates': ['old']},
            {'version': '10.1.0', 'ptb': False, 'date': '2026-08-25'},
            {'version': '10.2.0', 'ptb': True, 'perk_updates': ['new']},
        ]}
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as tmp:
            Path(tmp, 'patchnotes.json').write_text(json.dumps(data), encoding='utf-8')
            with patch.object(wiki, 'HERE', tmp), patch.object(wiki, 'TODAY', '2026-09-21'), \
                    patch.object(wiki, 'patch_release_date', return_value=None):
                self.assertEqual(wiki.pending_perk_updates(), {'new': '10.2.0'})


class UpdatedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.perks = read('perks.json')
        cls.notes = read('patchnotes.json')
        cls.by_id = {p['id']: p for p in cls.perks}

    def test_10_2_0_live_notes_are_collected_and_pending_descriptions_promoted(self):
        live = next(p for p in self.notes['patches'] if p['version'] == '10.2.0' and not p['ptb'])
        ptb = next(p for p in self.notes['patches'] if p['version'] == '10.2.0' and p['ptb'])
        self.assertEqual((live['title'], live['date']), ('10.2.0 | Mid-Chapter', '2026-10-06'))
        self.assertEqual(len(live['perk_updates']), 58)
        self.assertEqual(set(live['perk_updates']), set(ptb['perk_updates']))
        self.assertTrue(set(live['perk_updates']) <= set(live['perk_ids']))
        # 정식 출시 → 예정 표시·예정본이 하나도 남지 않고, 변경 퍽 58개 모두 양쪽 설명을 가진다
        for p in self.perks:
            for k in ('upcoming', 'upcoming_kind', 'upcoming_patch', 'upcoming_date', 'pending'):
                self.assertNotIn(k, p, (p['id'], k))
        for pid in live['perk_updates']:
            for field in ('desc_html', 'desc_text', 'desc_html_en', 'desc_text_en'):
                self.assertTrue(self.by_id[pid][field], (pid, field))

    def test_promoted_descriptions_follow_the_live_notes_not_the_ptb(self):
        # 정식 노트에서 PTB와 달라진 수치. 위키는 아직 PTB 기준이라 영어는 data_corrections.json 으로 보정한다.
        expect = {
            'Bitter_Murmur': (['10초', '16/18/20'], ['10 seconds', '16/18/20']),
            'Dark_Sense': (['20미터', '13/14/15', '32미터 이내의 판자'], ['20 metres', '13/14/15', 'within 32 metres']),
            'S46P01': (['30/35/40'], ['30/35/40', '60/70/80']),
            'S30P02': (['30/35/40'], ['30/35/40']),
            'K40P01': (['70/80/90'], ['70/80/90']),
            'Hex_Thrill_Of_The_Hunt': (['4/5/6'], ['4/5/6', '20/25/30']),
            'InTheDark': (['2/3/4'], ['2/3/4']),
            'K32P03': (['8% 신속'], ['+8 %']),
            'Premonition': (['55/50/45'], ['55/50/45']),
            'S49P01': (['10% 증가'], ['+10 %']),
        }
        for pid, (ko, en) in expect.items():
            for needle in ko:
                self.assertIn(needle, self.by_id[pid]['desc_text'], (pid, needle))
            for needle in en:
                self.assertIn(needle, self.by_id[pid]['desc_text_en'], (pid, needle))
        self.assertNotIn('100%', self.by_id['S49P01']['desc_text'])
        self.assertNotIn('잃습니다', self.by_id['StakeOut']['desc_text'])
        self.assertNotIn('on miss', self.by_id['StakeOut']['desc_text_en'])
        # 이전 패치 데이터와 섞이지 않았는지
        self.assertIn('20/25/30', self.by_id['Vigil']['desc_text'])
        self.assertIn('24', self.by_id['K30P01']['desc_text'])
        self.assertIn('40/35/30', self.by_id['RepressedAlliance']['desc_text'])

    def test_ptb_to_live_developer_update_is_reflected_in_live_descriptions(self):
        by_id = self.by_id
        borrowed = by_id['BorrowedTime']          # 정식에서 리워크 철회 → 라이브 설명 유지
        self.assertIn('Endurance', borrowed['desc_text_en'])
        self.assertNotIn('Deep Wound', borrowed['desc_text_en'])
        self.assertIn('인내', borrowed['desc_text'])
        burden = by_id['S45P03']                  # 전체 비활성화 조건 삭제
        self.assertNotIn('deactivated', burden['desc_text_en'])
        self.assertNotIn('비활성화', burden['desc_text'])
        self.assertIn('160/140/120', burden['desc_text'])
        tinh = by_id['This_Is_Not_Happening']     # 대성공 구역 증가 삭제
        self.assertNotIn('Great', tinh['desc_text_en'])
        self.assertNotIn('대성공', tinh['desc_text'])
        self.assertIn('150/175/200', tinh['desc_text'])
        arrogance = by_id['K36P03']               # 공격 회복은 빗나간/막힌 공격만
        self.assertIn('missed and obstructed basic-attack recovery', arrogance['desc_text_en'])
        self.assertIn('빗나가거나 막힌 기본 공격', arrogance['desc_text'])
        windows = by_id['WindowsOfOpportunity']   # 위키 오타(40/35/30 seconds) → 24미터
        self.assertIn('within 24 metres', windows['desc_text_en'])
        self.assertNotIn('Pallets', windows['desc_text_en'])
        self.assertIn('24미터', windows['desc_text'])

    def test_live_corrections_cover_every_perk_that_differs_from_the_ptb(self):
        live_url = next(p for p in self.notes['patches'] if p['version'] == '10.2.0' and not p['ptb'])['url']
        corrections = [c for c in read('data_corrections.json') if c['dataset'] == 'perks' and c['reviewed'] == '2026-10-07']
        self.assertEqual({c['id'] for c in corrections}, {
            'Bitter_Murmur', 'Dark_Sense', 'S46P01', 'S30P02', 'K40P01', 'Hex_Thrill_Of_The_Hunt', 'InTheDark',
            'K32P03', 'Premonition', 'S49P01', 'StakeOut', 'BorrowedTime',
            'K36P03', 'S45P03', 'This_Is_Not_Happening', 'WindowsOfOpportunity'})
        for c in corrections:
            self.assertEqual((c['field'], c['source_url']), ('desc_html_en', live_url), c['id'])

    def test_live_changes_are_ignored_once_the_patch_is_released(self):
        self.assertEqual(wiki.live_changes('10.2.0', 'BorrowedTime', released={'10.2.0'}), (None, None))
        self.assertEqual(wiki.live_changes('10.2.0', 'Vigil'), (None, None))
        change = {'drop': [('deactivated', '비활성화')], 'replace': [('is', 'was'), ('이', '가')]}
        self.assertEqual(wiki.edit_lines('• A is x.<br>• B is deactivated.', change, 0), '• A was x.')
        self.assertEqual(wiki.edit_lines('이 줄<br>비활성화 줄', change, 1), '가 줄')

    def test_ids_icons_and_relationships_remain_valid(self):
        killers, addons = read('killers.json'), read('addons.json')
        self.assertEqual((len(self.perks), len(killers), len(addons)), (321, 44, 880))
        for data in (self.perks, killers, addons):
            self.assertEqual(len(data), len({p['id'] for p in data}))
            for p in data:
                for field in ('icon_file', 'portrait_file', 'power_icon'):
                    if p.get(field):
                        self.assertTrue((ROOT / p[field]).is_file(), p[field])
        addon_ids = {a['id'] for a in addons}
        killer_ids = {k['id'] for k in killers}
        for killer in killers:
            self.assertEqual(len(killer['addon_ids']), 20)
            self.assertTrue(set(killer['addon_ids']) <= addon_ids)
        self.assertTrue(all(a['killer_id'] in killer_ids for a in addons))

    def test_official_corrections_are_idempotent_and_detect_upstream_changes(self):
        for kind in ('perks', 'killers'):
            for p in read(kind + '.json'):
                before = copy.deepcopy(p)
                apply_corrections(p, kind)
                self.assertEqual(p, before)
        p = copy.deepcopy(next(p for p in self.perks if p['id'] == 'Celestial_Witness'))
        p['desc_text_en'] = 'Unexpected new upstream revision'
        with self.assertRaisesRegex(ValueError, '재검토'):
            apply_corrections(p, 'perks')


if __name__ == '__main__':
    unittest.main()
