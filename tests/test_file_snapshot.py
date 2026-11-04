"""Use real append/overwrite operations through the same MCP routes as the UI."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
import server
from file_snapshot import block_size, open_snapshot
from trajectory import read_frames

DUMP = ('ITEM: TIMESTEP\n0\nITEM: NUMBER OF ATOMS\n1\n'
        'ITEM: BOX BOUNDS pp pp ff\n0 10\n0 10\n0 10\n'
        'ITEM: ATOMS id type x y z\n1 1 0 0 0\n')
GRO = 'water\n1\n    1SOL      O    1   0.100   0.200   0.300\n1 1 1\n'
XYZ = '1\ni = 0\nH 0 0 0\n'
VASP_HEADER = 'H\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\n'
VASP_FRAME = 'Direct configuration= 1\n0 0 0\n'


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def call(self, name: str, **args: object) -> dict:
        return server.dispatch('tools/call', {'name': name, 'arguments': args})['structuredContent']

    def token(self, path: Path) -> str:
        return self.call('open_structure_path', path=str(path))['file']['token']

    def test_md_append_while_indexing_and_after_eof(self) -> None:
        for name, fmt, frame in [('run.dump', 'lammps-dump-text', DUMP), ('run.gro', 'gromacs', GRO)]:
            with self.subTest(fmt=fmt):
                path = self.root / name
                path.write_text(frame * 3 + frame[:18])
                token = self.token(path)
                meta = self.call('structure_import', token=token, action='stat')
                def read(**args: object) -> dict:
                    return self.call('structure_import', token=token, version=meta['version'], action='frames', format=fmt, **args)
                first = read(offset=0)
                with path.open('a') as output:
                    output.write(frame[18:] + frame * 2)
                index = read(offset=first['nextOffset'], indexOnly=True)
                self.assertEqual(len(index['offsets']), 2)
                self.assertTrue(index['eof'])
                self.assertTrue(index['incompleteTail'])
                self.assertEqual(index['nextOffset'], meta['size'])
                for offset in [0, *index['offsets']]:
                    self.assertEqual(read(offset=offset)['text'], frame)
                # Reopening sees the now complete six frames.
                new = self.call('structure_import', token=token, action='stat')
                all_frames = self.call('structure_import', token=token, version=new['version'], action='frames', format=fmt, offset=0, indexOnly=True)
                self.assertEqual(len(all_frames['offsets']), 6)

    def test_xyz_and_vasp_partial_tail_remain_navigable(self) -> None:
        for name, header, frame in [('run.xyz', '', XYZ), ('XDATCAR', VASP_HEADER, VASP_FRAME)]:
            with self.subTest(name=name):
                path = self.root / name
                path.write_text(header + frame * 3 + frame[:-6])
                params = {'_meta': {'openai/resource': {'path': str(path)}}}
                first = read_frames({**params, 'arguments': {'frameLimit': 1}})
                with path.open('a') as output:
                    output.write(frame[-6:] + frame)
                index = read_frames({**params, 'arguments': {'version': first['version'], 'offset': first['nextOffset'], 'indexOnly': True}})
                self.assertEqual(index['frameCount'], 2)
                self.assertTrue(index['eof'])
                for offset in [0, *index['offsets']]:
                    batch = read_frames({**params, 'arguments': {'version': first['version'], 'offset': offset, 'frameLimit': 1}})
                    self.assertEqual(batch['text'], header + frame)

    def test_xyz_tiny_partial_tail_terminates(self) -> None:
        for tail in ('1', '1\n', '1\ncomment', '1\ncomment\nH 0'):
            path = self.root / 'tail.xyz'
            path.write_text(XYZ + tail)
            params = {'_meta': {'openai/resource': {'path': str(path)}}}
            first = read_frames({**params, 'arguments': {'frameLimit': 1}})
            batch = read_frames({**params, 'arguments': {'version': first['version'], 'offset': first['nextOffset'], 'indexOnly': True}})
            self.assertTrue(batch['eof'], tail)
            self.assertEqual(batch['frameCount'], 0)

    def test_log_and_cell_keep_opening_boundary(self) -> None:
        path = self.root / 'run.cell'
        path.write_text('0 0 3 0 0 0 3 0 0 0 3\n1 0 4')
        xyz = self.root / 'run.xyz'
        xyz.write_text(XYZ * 2)
        opened = self.call('open_structure_path', path=str(xyz), companions=[str(path)])['file']
        cell = opened['companions'][0]['token']
        meta = self.call('structure_import', token=cell, action='stat')
        first = self.call('read_trajectory_frames', token=opened['token'], cellToken=cell, cellVersion=meta['version'], frameLimit=1)
        with path.open('a') as output:
            output.write(' 0 0 0 4 0 0 0 4\n')
        second = self.call('read_trajectory_frames', token=opened['token'], cellToken=cell, cellVersion=meta['version'], version=first['version'], offset=first['nextOffset'], frameLimit=1)
        self.assertEqual(second['text'], first['text'])
        log = self.root / 'log.lammps'
        log.write_text('units real\n')
        token = self.token(log)
        meta = self.call('structure_import', token=token, action='stat')
        with log.open('a') as output:
            output.write('Step Temp\n1000 300\n')
        import base64
        result = self.call('structure_import', token=token, version=meta['version'], action='range', offset=0, length=1024)
        self.assertEqual(base64.b64decode(result['data']), b'units real\n')

    def test_replacement_truncation_and_indexed_block_rewrite_rejected(self) -> None:
        for mutation in ('replace', 'truncate', 'overwrite_and_append'):
            with self.subTest(mutation=mutation):
                path = self.root / 'blocks.xyz'
                path.write_bytes(b'a' * block_size * 5)
                with open_snapshot(path) as (stream, snapshot):
                    stream.seek(block_size * 2)
                    self.assertEqual(stream.read(1), b'a')
                if mutation == 'replace':
                    other = self.root / 'other'
                    other.write_bytes(path.read_bytes())
                    other.replace(path)
                elif mutation == 'truncate':
                    path.write_bytes(b'a')
                else:
                    with path.open('r+b') as stream:
                        stream.seek(block_size * 2)
                        stream.write(b'b')
                        stream.seek(0, 2)
                        stream.write(b'append')
                with self.assertRaisesRegex(ValueError, '改变'):
                    with open_snapshot(path, snapshot.version) as (stream, _):
                        stream.seek(block_size * 2)
                        stream.read(1)


if __name__ == '__main__':
    unittest.main()
