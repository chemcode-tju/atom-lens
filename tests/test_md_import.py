"""Exercise the actual path/token/frame interface used on a connected host."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
import server


class HostImportTests(unittest.TestCase):
    def test_index_fetch_and_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            companion = root / 'in.sim'
            companion.write_text('units metal\n')
            for fmt, name, frame in [
                ('gromacs', 'sample.gro', 'title\n1\n    1SOL      O    1   0.100   0.200   0.300\n1 1 1\n'),
                ('lammps-dump-text', 'dump.run', 'ITEM: UNITS\nmetal\nITEM: TIMESTEP\n0\nITEM: NUMBER OF ATOMS\n1\nITEM: BOX BOUNDS pp pp ff\n0 10\n0 10\n0 10\nITEM: ATOMS id element x y z\n1 O 1 2 3\n'),
            ]:
                path = root / name
                path.write_bytes((frame * 4).replace('\n','\r\n').encode())
                opened = server.dispatch('tools/call', {'name':'open_structure_path','arguments':{
                    'path':str(path),'companions':[str(companion)]}})['structuredContent']['file']
                self.assertEqual(opened['companions'][0]['name'],companion.name)

                def call(**args: object) -> dict:
                    return server.dispatch('tools/call', {'name':'structure_import','arguments':{
                        'token':opened['token'], **args}})['structuredContent']

                version = call(action='stat')['version']
                first = call(action='frames',format=fmt,version=version,offset=0)
                self.assertFalse(first['eof'])
                self.assertEqual(first['text'].replace('\r\n','\n'),frame)
                index = call(action='frames',format=fmt,version=version,offset=first['nextOffset'],indexOnly=True)
                self.assertTrue(index['eof'])
                self.assertEqual(index['text'],'')
                self.assertEqual(len(index['offsets']),3)
                self.assertEqual(call(action='frames',format=fmt,version=version,offset=index['offsets'][-1])['text'],first['text'])
                path.write_text(frame)
                with self.assertRaisesRegex(ValueError,'改变'):
                    call(action='frames',format=fmt,version=version,offset=0)


if __name__ == '__main__':
    unittest.main()
