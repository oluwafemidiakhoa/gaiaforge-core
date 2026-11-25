import json
import tempfile
import unittest
from pathlib import Path

from gaiaforge.ledger import append_record
from gaiaforge.protocol import ProtocolError, freeze_protocol, verify_experiment


IMAGE = 'python@sha256:' + 'a' * 64


class FrozenProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'tests').mkdir(parents=True)
        (self.repo / 'tests' / 'test_thing.py').write_text('import unittest\n', encoding='utf-8')
        self.protocol_file = self.root / 'frozen.json'
        self.protocol = freeze_protocol(self.repo, self.protocol_file, image=IMAGE, protocol_id='experiment_1')
        self.baseline = self._report('baseline', 'b', False)
        self.candidate = self._report('candidate', 'c', True)

    def _report(self, name, snap, passing):
        p = self.root / (name + '.json')
        ledger = self.root / (name + '.jsonl')
        report = {
            'backend': 'docker', 'passed': passing, 'exit_code': 0 if passing else 1,
            'timed_out': False, 'release_authorized': False,
            'suite_sha256': self.protocol['suite_sha256'],
            'snapshot_sha256': snap * 64, 'output_sha256': 'e' * 64,
            'image': IMAGE, 'check': 'unittest', 'output_excerpt': 'mock test output',
        }
        entry = append_record(ledger, 'container_verification',
                              {k: v for k, v in report.items() if k != 'output_excerpt'})
        report['ledger_hash'] = entry['hash']
        p.write_text(json.dumps(report), encoding='utf-8')
        return p, ledger

    def _check(self, **kwargs):
        return verify_experiment(self.protocol_file, *self.baseline, *self.candidate, **kwargs)

    def test_frozen_experiment_newly_passing_is_review_only(self):
        result = self._check()
        self.assertTrue(result['newly_passing'])
        self.assertEqual(result['decision'], 'human_review_required')
        self.assertFalse(result['release_authorized'])
        self.assertFalse(result['automatic_promotion'])
        self.assertFalse(result['execution_authenticated'])

    def test_anchored_head_marks_anchor_checked_not_authenticated(self):
        heads = []
        for report_file, _ in (self.baseline, self.candidate):
            heads.append(json.loads(report_file.read_text())['ledger_hash'])
        result = self._check(expected_baseline_head=heads[0], expected_candidate_head=heads[1])
        self.assertTrue(result['external_anchors_checked'])
        self.assertFalse(result['execution_authenticated'])

    def test_invalid_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'anchor'):
            self._check(expected_baseline_head='0' * 64)

    def test_protocol_modification_detected(self):
        data = json.loads(self.protocol_file.read_text())
        data['suite_sha256'] = 'f' * 64
        self.protocol_file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ProtocolError, 'checksum mismatch'):
            self._check()

    def test_modified_report_detected(self):
        report_file, _ = self.candidate
        data = json.loads(report_file.read_text())
        data['output_sha256'] = 'f' * 64
        report_file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self._check()

    def test_mismatched_frozen_suite_rejected_with_matching_receipt(self):
        report_file, ledger_file = self.candidate
        data = json.loads(report_file.read_text())
        data['suite_sha256'] = 'f' * 64
        ledger_file.unlink()
        entry = append_record(ledger_file, 'container_verification',
                              {k: v for k, v in data.items() if k not in ('output_excerpt', 'ledger_hash')})
        data['ledger_hash'] = entry['hash']
        report_file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ProtocolError, 'deviates'):
            self._check()

    def test_same_snapshot_rejected(self):
        report_file, ledger_file = self.candidate
        data = json.loads(report_file.read_text())
        data['snapshot_sha256'] = 'b' * 64
        ledger_file.unlink()
        entry = append_record(ledger_file, 'container_verification',
                              {k: v for k, v in data.items() if k not in ('output_excerpt', 'ledger_hash')})
        data['ledger_hash'] = entry['hash']
        report_file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ProtocolError, 'identical'):
            self._check()

    def test_no_improvement_not_eligible(self):
        baseline_report, baseline_ledger = self.baseline
        data = json.loads(baseline_report.read_text())
        data['passed'] = True
        data['exit_code'] = 0
        baseline_ledger.unlink()
        entry = append_record(baseline_ledger, 'container_verification',
                              {k: v for k, v in data.items() if k not in ('output_excerpt', 'ledger_hash')})
        data['ledger_hash'] = entry['hash']
        baseline_report.write_text(json.dumps(data))
        result = self._check()
        self.assertEqual(result['decision'], 'not_eligible')

    def test_freeze_refuses_to_overwrite(self):
        with self.assertRaises(FileExistsError):
            freeze_protocol(self.repo, self.protocol_file, image=IMAGE, protocol_id='experiment_1')

    def test_freeze_refuses_inside_repository(self):
        with self.assertRaisesRegex(ProtocolError, 'outside'):
            freeze_protocol(self.repo, self.repo / 'frozen.json', image=IMAGE, protocol_id='bad')

    def test_freeze_detects_suite_change(self):
        (self.repo / 'tests' / 'test_thing.py').write_text('import sys\n')
        another = freeze_protocol(self.repo, self.root / 'other.json', image=IMAGE, protocol_id='other')
        self.assertNotEqual(another['suite_sha256'], self.protocol['suite_sha256'])

    def test_bad_image_blocked(self):
        with self.assertRaisesRegex(ProtocolError, 'digest-pinned'):
            freeze_protocol(self.repo, self.root / 'bad.json', image='python:latest', protocol_id='bad')

    def test_missing_ledger_fails_closed(self):
        self.candidate[1].unlink()
        with self.assertRaises((ValueError, OSError)):
            self._check()


if __name__ == '__main__':
    unittest.main()
