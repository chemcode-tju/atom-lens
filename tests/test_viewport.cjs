const assert = require('node:assert/strict');
const {projectToView, viewQuaternions} = require('../plugin/web/viewport.js');
const {radius, palette, vesta} = require('../plugin/web/appearance.js');
function close(actual, expected) { actual.forEach((n,i) => assert.ok(Math.abs(n-expected[i]) < 1e-10)); }
close(projectToView([1,0,0], viewQuaternions.xz), [1,0,0]);
close(projectToView([0,0,1], viewQuaternions.xz), [0,1,0]);
close(projectToView([0,1,0], viewQuaternions.yz), [-1,0,0]);
close(projectToView([0,0,1], viewQuaternions.yz), [0,1,0]);
const frame = [10,10,45];
close(projectToView(frame, viewQuaternions.yz), [-10,45,-10]);
assert.equal(radius('H'), .46);
assert.equal(radius('Cu'), 1.28);
assert.equal(radius('O'), .74);
assert.equal(radius('unknown'), 1.2);
assert.ok(Number.isInteger(vesta.Cu));
assert.deepEqual(palette('rasmol', {Jmol:{H:1,Cu:2,Og:3}, rasmol:{H:4}}), {H:4,Cu:2,Og:3});
console.log('View geometry: XZ/YZ axes and tall-cell projection; OVITO display radii and palette fallback passed.');
