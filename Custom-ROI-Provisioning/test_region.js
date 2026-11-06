// Checks for the region page's geometry (static/region.js). Run: node Custom-ROI-Provisioning/test_region.js
const assert = require("node:assert/strict");
const Region = require("./static/region.js");

const size = [1920, 1080];

// A click on a picture shown at half size lands on full-resolution pixels, inside the picture
assert.deepEqual(Region.toImage(100.4, 50.6, 2, size), [201, 101]);
assert.deepEqual(Region.toImage(-5, 9999, 2, size), [0, 1080]);

const square = [[100, 100], [300, 100], [300, 300], [100, 300]];
assert.deepEqual(Region.centroid(square), [200, 200]);
assert.equal(Region.area(square), 40000);

// Scaling is about the centroid: twice the size keeps the centre, and the server's edge limit holds
assert.deepEqual(Region.scale(square, 2, size), [[0, 0], [400, 0], [400, 400], [0, 400]]);
assert.deepEqual(Region.centroid(Region.scale(square, 0.5, size)), [200, 200]);
const near = [[1800, 1000], [1900, 1000], [1900, 1070]];
assert.ok(Region.scale(near, 3, size).every(([x, y]) => x >= 0 && x <= 1920 && y >= 0 && y <= 1080), "kept inside the picture");

// Moving stops at the edges without changing the shape
assert.deepEqual(Region.translate(square, -500, 50, size), [[0, 150], [200, 150], [200, 350], [0, 350]]);
assert.deepEqual(Region.translate(square, 5000, 0, size)[1], [1920, 100]);

assert.ok(Region.inside([150, 150], square) && !Region.inside([350, 150], square));

// A freehand stroke of 2000 points along a circle fits the server's 3 to 100 points and keeps its shape
const circle = Array.from({length: 2000}, (_, i) => [960 + 400 * Math.cos(i * 2 * Math.PI / 2000), 540 + 400 * Math.sin(i * 2 * Math.PI / 2000)]);
const fitted = Region.fit(circle, 100);
assert.ok(fitted.length >= 3 && fitted.length <= 100, fitted.length);
const ratio = Region.area(fitted) / Region.area(circle);
assert.ok(ratio > 0.97 && ratio <= 1.0001, `area kept: ${ratio}`);
// A straight drag along a line simplifies to its ends
assert.deepEqual(Region.simplify([[0, 0], [5, 0.1], [10, 0]], 1), [[0, 0], [10, 0]]);
assert.equal(Region.fit(square, 100), square, "small shapes untouched");

console.log(`region geometry ok (full-resolution clicks, centroid scaling kept in the picture, moves stopped at edges, a 2000-point stroke fitted to ${fitted.length} points)`);
