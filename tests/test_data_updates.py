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

    def test_all_57_ptb_perks_have_both_translations_and_live_descriptions(self):
        # PTB 58개 중 Borrowed Time 은 10.2.0 PTB→정식 개발자 업데이트에서 되돌려졌다.
        note = next(p for p in self.notes['patches'] if p['version'] == '10.2.0' and p['ptb'])
        pending = [p for p in self.perks if p.get('upcoming_patch') == '10.2.0']
        self.assertEqual(len(pending), 57)
        self.assertEqual(sum(p['role'] == 'killer' for p in pending), 27)
        self.assertEqual({p['id'] for p in pending} | {'BorrowedTime'}, set(note['perk_updates']))
        self.assertTrue(set(note['perk_updates']) <= set(note['perk_ids']))
        for p in pending:
            self.assertIsNone(p['upcoming_date'])
            self.assertEqual(p['upcoming_kind'], 'update')
            for field in ('desc_html', 'desc_text', 'desc_html_en', 'desc_text_en'):
                self.assertTrue(p[field], (p['id'], field))
                self.assertTrue(p['pending'][field], (p['id'], field))
            self.assertEqual(p['pending']['source_url'], note['url'])

    def test_current_and_pending_effects_are_distinct(self):
        by_id = {p['id']: p for p in self.perks}
        thrill = by_id['Hex_Thrill_Of_The_Hunt']
        self.assertIn('8/9/10', thrill['desc_text'])
        self.assertIn('6/7/8', thrill['pending']['desc_text'])
        windows = by_id['WindowsOfOpportunity']
        self.assertIn('Pallets', windows['desc_text_en'])
        self.assertNotIn('Pallets', windows['pending']['desc_text_en'])
        self.assertIn('20/25/30', by_id['Vigil']['desc_text'])
        self.assertNotIn('upcoming', by_id['Vigil'])
        self.assertIn('24', by_id['K30P01']['desc_text'])
        self.assertIn('40/35/30', by_id['RepressedAlliance']['desc_text'])

    def test_ptb_to_live_developer_update_is_reflected_in_pending(self):
        by_id = {p['id']: p for p in self.perks}
        url = wiki.PTB_LIVE_CHANGES['10.2.0']['url']
        # Borrowed Time: 정식에서 되돌림 → 예정본 없음, 라이브 설명 유지
        borrowed = by_id['BorrowedTime']
        self.assertNotIn('pending', borrowed)
        self.assertNotIn('upcoming', borrowed)
        self.assertIn('Endurance', borrowed['desc_text_en'])
        self.assertIn('인내', borrowed['desc_text'])
        # Shoulder the Burden: 전체 비활성화 조건 삭제
        burden = by_id['S45P03']['pending']
        self.assertNotIn('deactivated', burden['desc_text_en'])
        self.assertNotIn('비활성화', burden['desc_text'])
        self.assertIn('160/140/120', burden['desc_text'])
        self.assertEqual(burden['live_changes_url'], url)
        # This Is Not Happening: 대성공 구역 증가 삭제
        tinh = by_id['This_Is_Not_Happening']['pending']
        self.assertNotIn('Great', tinh['desc_text_en'])
        self.assertNotIn('대성공', tinh['desc_text'])
        self.assertIn('150/175/200', tinh['desc_text'])
        # Dark Arrogance: 공격 회복은 빗나간/막힌 공격만
        arrogance = by_id['K36P03']['pending']
        self.assertIn('missed and obstructed basic-attack recovery', arrogance['desc_text_en'])
        self.assertIn('빗나가거나 막힌 기본 공격', arrogance['desc_text'])
        # 변경이 반영된 퍽은 스크립트를 다시 돌려도 한글 예정본이 유지된다
        for pid in ('S45P03', 'This_Is_Not_Happening', 'K36P03'):
            p = copy.deepcopy(by_id[pid])
            change, change_url = wiki.live_changes('10.2.0', pid)
            before = p['pending']['desc_text']
            wiki.set_pending(p, wiki.edit_lines(p['pending']['desc_html_en'], change, 0), '10.2.0',
                             p['pending']['source_url'])
            wiki.apply_live_changes(p, change, change_url)
            self.assertEqual(p['pending']['desc_text'], before)
            self.assertEqual(p['pending']['live_changes_url'], url)

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
