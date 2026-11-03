"""Verify SSH session discovery, legacy settings and simultaneous save routing."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"native"))
import broker
import connection


class BrokerTests(unittest.TestCase):
    def test_reuses_endpoint_not_existing_forwards(self) -> None:
        args = ["ssh","-T","-o","ControlMaster=no","-o","ControlPath=none","-R","forward",
                "-F","/tmp/custom config","-Jjump","-p","2222","lab","codex app-server"]
        host = broker.codex_profile(args)
        command = broker.worker_command(host)
        self.assertEqual(host["host"], "lab")
        self.assertEqual(host["config"], "/tmp/custom config")
        self.assertIn("jump", command)
        self.assertIn("2222", command)
        self.assertNotIn("forward", command)
        self.assertIsNone(broker.codex_profile(["ssh","lab","unrelated command"]))
        self.assertIn("snapshot_queue", command[-1])

    def test_legacy_and_independent_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"settings"
            a = {"config":"/a","host":"lab","installed":"/queue/a"}
            b = {"config":"/b","host":"lab","installed":"/queue/b"}
            path.write_text(json.dumps(a))
            with patch.object(connection,"settings_path",return_value=path):
                connection.update_profile("/b","lab",b)
                auto = dict(a,automatic=True,options=["-p","2222"])
                merged = broker.desired_profiles([auto],connection.read_profiles(path))
                self.assertEqual(len(merged),2)
                self.assertEqual(merged[("/a","lab")]["options"],["-p","2222"])
                connection.update_profile("/a","lab",None)
                self.assertEqual(connection.read_profiles(path),[b])
                targets=broker.desired_profiles([auto],connection.read_profiles(path))
                self.assertTrue(targets[("/a","lab")]["automatic"])

    def test_two_live_workers_acknowledge_only_the_origin(self) -> None:
        relay=broker.Broker()
        arrivals = threading.Event()
        messages=[]
        def collect(message: dict) -> None:
            messages.append(message)
            if len(messages)==2:
                arrivals.set()
        with tempfile.TemporaryDirectory() as folder, patch.object(relay,"send",collect):
            readers=[]
            for host in ("alpha","beta"):
                code="""import json,sys,pathlib
print(json.dumps({'kind':'ready'}),flush=True)
print(json.dumps({'kind':'snapshot','id':'same-id'}),flush=True)
pathlib.Path(sys.argv[1]).write_text(input())
"""
                process=subprocess.Popen([sys.executable,"-c",code,str(Path(folder)/host)],
                                         stdin=subprocess.PIPE,stdout=subprocess.PIPE)
                thread=threading.Thread(target=relay.relay,args=(("config",host),process))
                thread.start()
                readers.append(thread)
            self.assertTrue(arrivals.wait(5))
            outcomes={"alpha":"saved","beta":"cancelled"}
            replies=[dict(id=m["id"],route=m["route"],status=outcomes[m["route"][1]]) for m in messages]
            stream=io.TextIOWrapper(io.BufferedReader(io.BytesIO(
                b"".join((json.dumps(r)+"\n").encode() for r in reversed(replies)))))
            with patch.object(sys,"stdin",stream):
                relay.acknowledgments()
            for reader in readers:
                reader.join(5)
                self.assertFalse(reader.is_alive())
            for host,status in outcomes.items():
                self.assertEqual(json.loads((Path(folder)/host).read_text())["status"],status)

if __name__ == "__main__":
    unittest.main()
