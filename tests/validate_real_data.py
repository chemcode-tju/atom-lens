"""Compare every coordinate and cell in the local training fixture against ASE."""

# Configuration
input_file = "test-data/train.extxyz"

from pathlib import Path
import json
import subprocess
import tempfile

import numpy as np
from ase.io import iread


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / input_file
    if not path.is_file():
        raise FileNotFoundError(f"Local-only test data is missing: {path}")
    script = """
const fs=require('node:fs');
const {StructureDocument}=require(process.env.PARSER_PATH);
const text=fs.readFileSync(process.env.FIXTURE_PATH,'utf8');
const document=new StructureDocument('train.extxyz',text);
if(document.serialize()!==text)throw Error('Unedited round trip changed the file');
fs.writeFileSync(process.env.RESULT_PATH,JSON.stringify(Array.from({length:document.count},(_,i)=>document.frame(i))));
"""
    import os
    with tempfile.TemporaryDirectory(prefix="structure-viewer-test-") as directory:
        result = Path(directory) / "result.json"
        environment = dict(os.environ, PARSER_PATH=str(root / "plugin/web/parser.js"),
                           FIXTURE_PATH=str(path), RESULT_PATH=str(result))
        subprocess.run(["node", "-e", script], env=environment, check=True)
        actual = json.loads(result.read_text())
        expected = list(iread(path, format="extxyz"))
        assert len(actual) == len(expected)
        for index, (frame, atoms) in enumerate(zip(actual, expected)):
            assert [atom["elem"] for atom in frame["atoms"]] == atoms.get_chemical_symbols(), index
            np.testing.assert_allclose([[atom[key] for key in ("x", "y", "z")] for atom in frame["atoms"]], atoms.positions, atol=1e-12)
            np.testing.assert_allclose(frame["cell"], atoms.cell.array, atol=1e-12)
            assert frame["pbc"] == atoms.pbc.tolist(), index
    print(f"PASS: all {len(expected)} frames match ASE (elements, positions, cell and PBC); exact unedited round trip.")


if __name__ == "__main__":
    main()
