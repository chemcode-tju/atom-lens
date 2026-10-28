"""Exercise real encoding, chunk order, large images, and safe output destinations."""
from pathlib import Path
import base64
import json
import struct
import sys
import tempfile
import time
import unittest
import zlib
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from media_export import MediaExports, ffmpeg_executable


def png(red: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    data = (b'\0' + bytes([red, 32, 64]) * 32) * 32
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',32,32,8,2,0,0,0)) + chunk(b'IDAT',zlib.compress(data)) + chunk(b'IEND',b'')


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exports = MediaExports()

    def tearDown(self) -> None:
        for identifier in list(self.exports.jobs):
            self.exports.cancel({'id': identifier})

    def send(self, identifier: str, data: bytes) -> None:
        middle = len(data) // 2
        for index, part in enumerate([data[:middle], data[middle:]]):
            self.exports.append({'id': identifier, 'data': base64.b64encode(part).decode(), 'chunk': index, 'last': index == 1})

    def test_movie_formats_duration_and_real_decode(self) -> None:
        for suffix in ['mp4', 'mov', 'gif']:
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as output:
                job = self.exports.begin({'kind': 'animation', 'name': f'trajectory.{suffix}', 'fps': 10})
                for red in [0,60,120,180]:
                    self.send(job['id'], png(red))
                self.exports.finish(job)
                deadline = time.monotonic() + 30
                while self.exports.status(job)['state'] == 'encoding' and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertEqual(self.exports.status(job)['state'], 'ready', self.exports.status(job))
                result = self.exports.save({'arguments': {**job, 'destination': 'server', 'directory': output}})
                probe = str(Path(ffmpeg_executable()).with_name('ffprobe'))
                metadata = json.loads(subprocess.check_output([probe, '-v','error','-count_frames','-show_entries','stream=nb_read_frames,duration','-of','json',result['path']]))
                self.assertEqual(int(metadata['streams'][0]['nb_read_frames']),4)
                self.assertAlmostEqual(float(metadata['streams'][0]['duration']),.4,places=2)
                subprocess.run([ffmpeg_executable(),'-v','error','-i',result['path'],'-f','null','-'],check=True)

    def test_large_snapshot_and_chunk_order(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            job = self.exports.begin({'kind': 'image', 'name': 'large.png'})
            with self.assertRaisesRegex(ValueError,'顺序'):
                self.exports.append({**job, 'chunk': 1,'data':'AA=='})
            payload = png(20) + b'\0' * (19 * 1048576)
            self.send(job['id'],payload)
            params = {'arguments': {**job, 'destination':'server','directory': output}}
            first = self.exports.save(params)
            second = self.exports.save(params)
            self.assertEqual(Path(first['path']).read_bytes(),payload)
            self.assertNotEqual(first['path'],second['path'])
            self.exports.cancel(job)
            with self.assertRaises(ValueError):
                self.exports.status(job)

    def test_invalid_type_and_name(self) -> None:
        for arguments in [{'kind':'image','name':'../a.png'}, {'kind':'animation','name':'a.png'}, {'kind':'image','name':'a.mp4'}]:
            with self.assertRaises(ValueError):
                self.exports.begin(arguments)


if __name__ == '__main__':
    unittest.main()
