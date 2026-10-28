"""Verify unchanged VASP names, server path handles and bounded reads."""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'plugin'))
from path_access import StructurePaths
import server


class PathAccessTests(unittest.TestCase):
    def test_bare_names_and_immutable_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            selected = StructurePaths()
            for name in ['POSCAR', 'CONTCAR', 'XDATCAR']:
                path = Path(directory) / name
                text = 'water\n1\n10 0 0\n0 10 0\n0 0 10\nO H\n1 2\nCartesian\n0 0 0\n1 0 0\n0 1 0\n'
                path.write_text(text)
                result = selected.open(str(path))
                self.assertEqual(result['file']['name'], name)
                token = result['file']['token']
                self.assertEqual(selected.read_source({'arguments': {'token': token}})['text'], text)
                self.assertEqual(path.read_text(), text)
                self.assertEqual(len(list(Path(directory).iterdir())), ['POSCAR', 'CONTCAR', 'XDATCAR'].index(name) + 1)

    def test_rejections(self) -> None:
        selected = StructurePaths()
        for path in ['relative/POSCAR', '/etc/passwd', '/definitely-missing/POSCAR']:
            with self.assertRaises(ValueError): selected.open(path)
        with self.assertRaises(ValueError): selected.bind({'arguments': {'token': 'unknown'}})
        with self.assertRaises(ValueError): selected.read_source({'arguments': {}})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'POSCAR'; path.mkdir()
            with self.assertRaises(ValueError): selected.open(str(path))
        self.assertTrue(selected.open(None)['browser'])

    def test_dispatch_and_trajectory_handle(self) -> None:
        tools = server.dispatch('tools/list', {})['tools']
        opener = next(tool for tool in tools if tool['name'] == 'open_structure_path')
        self.assertIn({'type': 'thread'}, opener['_meta']['openai/ui']['entrypoints'])
        self.assertIn('model', opener['_meta']['ui']['visibility'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'water.xyz'; path.write_text('1\n\nO 0 0 0\n')
            result = server.dispatch('tools/call', {'name': 'open_structure_path', 'arguments': {'path': str(path)}})
            token = result['structuredContent']['file']['token']
            batch = server.dispatch('tools/call', {'name': 'read_trajectory_frames', 'arguments': {'token': token, 'offset': 0, 'frameLimit': 1}})['structuredContent']
            self.assertEqual(batch['frameCount'], 1)
            self.assertTrue(batch['eof'])


if __name__ == '__main__':
    unittest.main()
