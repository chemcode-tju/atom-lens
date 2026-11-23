"""Use real append/overwrite operations through the same MCP routes as the UI."""
from pathlib import Path
import sys
import os
import struct
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
import server
from file_snapshot import block_size, open_snapshot
from trajectory import read_frames, file_version

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

    def test_trr_index_skips_velocity_only_frames_and_excludes_incomplete_tail(self) -> None:
        def frame(step: int, width: int, has_coordinates: bool) -> bytes:
            sizes = (0, 0, 9 * width, 0, 0, 0, 0, 3 * width if has_coordinates else 0, 3 * width, 0)
            return (struct.pack('>3i', 1993, 13, 12) + b'GMX_trn_file'
                    + struct.pack('>13i', *sizes, 1, step, 0) + bytes(2 * width + sum(sizes)))

        path = self.root / 'run.trr'
        initial, velocity, final = frame(10, 4, True), frame(11, 8, False), frame(12, 8, True)
        path.write_bytes(initial + velocity + final + frame(13, 4, True)[:-3])
        with path.open('rb') as stream:
            from md_import import read_md_index
            first = read_md_index(stream, 'trr', 0, True, frozen=True, frame_limit=2)
            rest = read_md_index(stream, 'trr', first['nextOffset'], True, frozen=True)
        self.assertEqual(first['nextOffset'], len(initial) + len(velocity))
        self.assertEqual([(item['step'], item['width']) for item in first['frames'] + rest['frames']], [(10, 4), (12, 8)])
        self.assertTrue(rest['eof'])

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

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS native file panel metadata')
    def test_native_metadata_changes_do_not_invalidate_content(self) -> None:
        path = self.root / 'metadata.xyz'
        path.write_text(XYZ * 3)
        token = self.token(path)
        first = self.call('read_trajectory_frames', token=token, frameLimit=1)
        original = path.stat()
        fingerprint = file_version(original)
        subprocess.run(['/usr/bin/xattr', '-w', 'com.atomlens.test-lastused', 'updated', str(path)], check=True)
        self.assertEqual(path.stat().st_mtime_ns, original.st_mtime_ns)
        self.assertNotEqual(path.stat().st_ctime_ns, original.st_ctime_ns)
        self.assertEqual(file_version(path.stat()), fingerprint)
        second = self.call('read_trajectory_frames', token=token, version=first['version'],
                           offset=first['nextOffset'], frameLimit=1)
        self.assertEqual(second['text'], XYZ)
        # Even if a writer restores mtime, previously observed bytes must match.
        path.write_text(XYZ.replace('H 0', 'H 1') * 3)
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, '改变'):
            self.call('read_trajectory_frames', token=token, version=first['version'], frameLimit=1)


if __name__ == '__main__':
    unittest.main()
