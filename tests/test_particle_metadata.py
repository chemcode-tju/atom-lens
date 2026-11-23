"""Source metadata must survive topology extraction and static conversion."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin"))
from gmx_topology import parse_tpr_dump
from ase_convert import data_frame, frame_text


class ParticleMetadataTests(unittest.TestCase):
    def test_tpr_preserves_numeric_types_names_and_residues(self) -> None:
        text = '''pbc = xyz
atom[0]={type= 0, typeB= 0, ptype= Atom, m= 12.011, q=-.2, mB=12.011, qB=-.2, resind=0, atomnumber=6}
atom[1]={type= 1, typeB= 1, ptype= Atom, m= 13.0, q=.2, mB=13.0, qB=.2, resind=0, atomnumber=6}
atom[0]={name="C1"}
atom[1]={name="C2"}
type[0]={name="CA",nameB="CA"}
type[1]={name="CT",nameB="CT"}
residue[0]={name="MOL", nr=7, ic=' '}
'''
        atoms = parse_tpr_dump(text)["atoms"]
        self.assertEqual([atom["type"] for atom in atoms], ["0", "1"])
        self.assertEqual([atom["typeName"] for atom in atoms], ["CA", "CT"])
        self.assertEqual(atoms[1]["mass"], 13.0)
        self.assertEqual(atoms[1]["charge"], 0.2)
        self.assertEqual(atoms[1]["name"], "C2")
        self.assertEqual(atoms[1]["residue"], "MOL")
        self.assertEqual(atoms[1]["resid"], 7)

    def test_lammps_data_retains_types_and_original_box_origin(self) -> None:
        text = '''LAMMPS data

2 atoms
2 atom types

-3 7 xlo xhi
4 14 ylo yhi
5 15 zlo zhi

Masses

1 12.011
2 13.0

Atoms # atomic

1 1 -2 5 6
2 2 0 7 8
'''
        atoms = data_frame(text, ["C", "C"], "real", "atomic")
        self.assertEqual(atoms.info["cell_origin"], [-3, 4, 5])
        for value in atoms.positions[0]:
            self.assertAlmostEqual(value, 1)
        output = frame_text(atoms)
        self.assertIn("atom_type:S:1", output)
        self.assertTrue(output.splitlines()[2].endswith('"1"'))
        self.assertTrue(output.splitlines()[3].endswith('"2"'))

    def test_data_charge_survives_conversion(self) -> None:
        from ase import Atoms
        atoms = Atoms("OH", positions=[[0, 0, 0], [1, 0, 0]])
        atoms.set_initial_charges([-0.5, 0.5])
        output = frame_text(atoms)
        self.assertIn("charge:S:1", output)
        self.assertTrue(output.splitlines()[2].endswith('"-0.5"'))


if __name__ == "__main__":
    unittest.main()
