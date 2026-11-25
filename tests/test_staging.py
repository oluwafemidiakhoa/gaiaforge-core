import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gaiaforge.ledger import read_verified
from gaiaforge.staging import ProposalError, stage_proposal


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'main.py').write_text('value = 1\n')
        self.dest = self.root / 'staged'
        self.proposal = self.root / 'proposal.json'

    def make_proposal(self, path='main.py', content='value = 2\n', digest='auto'):
        if digest == 'auto':
            data = (self.source / path).read_bytes() if (self.source / path).exists() else None
            digest = hashlib.sha256(data).hexdigest() if data else None
        self.proposal.write_text(json.dumps({'proposal_id':'test-1','operations':[
            {'path': path, 'previous_sha256':digest, 'content':content}]}))

    def test_stage_preserves_baseline_and_records_evidence(self):
        self.make_proposal()
        ledger = self.root / 'ledger.jsonl'
        result = stage_proposal(self.source, self.proposal, self.dest, evidence_ledger=ledger)
        self.assertEqual((self.source / 'main.py').read_text(), 'value = 1\n')
        self.assertEqual((self.dest / 'main.py').read_text(), 'value = 2\n')
        self.assertTrue(result['static_checks_passed'])
        self.assertFalse(result['sandboxed'])
        self.assertEqual(len(read_verified(ledger)), 1)

    def test_new_file_allowed_and_syntax_checked(self):
        self.make_proposal('new.py', 'def greeting():\n    return "hi"\n')
        self.assertTrue(stage_proposal(self.source, self.proposal, self.dest)['static_checks_passed'])

    def test_invalid_syntax_is_not_passing(self):
        self.make_proposal(content='def broken(:\n')
        result = stage_proposal(self.source, self.proposal, self.dest)
        self.assertFalse(result['static_checks_passed'])
        self.assertEqual(result['status'], 'review_required')

    def test_stale_digest_rejected_without_workspace(self):
        self.make_proposal(digest='0'*64)
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)
        self.assertFalse(self.dest.exists())

    def test_traversal_rejected(self):
        self.make_proposal('../escape.py', digest=None)
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)

    def test_hidden_credential_file_rejected(self):
        self.make_proposal('.env', digest=None)
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)

    def test_symlink_in_source_rejected(self):
        (self.source / 'evil.py').symlink_to(self.root / 'outside')
        self.make_proposal()
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)

    def test_workspace_inside_source_rejected(self):
        self.make_proposal()
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.source / 'nested')

    def test_preexisting_workspace_rejected(self):
        self.make_proposal()
        self.dest.mkdir()
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)

    def test_duplicate_operations_rejected(self):
        self.make_proposal()
        record = json.loads(self.proposal.read_text())
        record['operations'].append(record['operations'][0])
        self.proposal.write_text(json.dumps(record))
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)

    def test_windows_style_paths_rejected(self):
        self.make_proposal('..\\private.py', digest=None)
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)

    def test_source_symlink_directory_rejected(self):
        (self.source / 'outside').symlink_to(self.root, target_is_directory=True)
        self.make_proposal()
        with self.assertRaises(ProposalError):
            stage_proposal(self.source, self.proposal, self.dest)


if __name__ == '__main__':
    unittest.main()
