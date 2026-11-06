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

// Shape correction: a shaky hand-drawn outline becomes the clean shape it was meant to be
const wobble = (pts, amount, seed = 1) => pts.map(([x, y], i) => [x + amount * Math.sin(i * 1.7 + seed), y + amount * Math.cos(i * 2.3 + seed)]);
const trace = (corners, perSide) => corners.flatMap((a, i) => {
    const b = corners[(i + 1) % corners.length];
    return Array.from({length: perSide}, (_, k) => [a[0] + (b[0] - a[0]) * k / perSide, a[1] + (b[1] - a[1]) * k / perSide]);
});
const shapes = {
    rectangle: [[400, 300], [1400, 300], [1400, 800], [400, 800]],
    quadrilateral: [[500, 300], [1300, 350], [1500, 850], [300, 750]],
    triangle: [[960, 200], [1500, 850], [420, 850]],
};
for (const [kind, corners] of Object.entries(shapes)) {
    const drawn = wobble(trace(corners, 40), 6);
    const fixed = Region.straighten(drawn, size);
    assert.equal(fixed.kind, kind, `${kind} recognised as ${fixed.kind}`);
    assert.equal(fixed.points.length, corners.length);
    assert.ok(fixed.points.every(([x, y]) => Number.isInteger(x) && Number.isInteger(y) && x >= 0 && x <= 1920 && y >= 0 && y <= 1080));
    // Each corner lands within 15 px of the intended one
    for (const c of corners) assert.ok(fixed.points.some((p) => Math.hypot(p[0] - c[0], p[1] - c[1]) < 15), `${kind} corner ${c}`);
}
// A tilted rectangle stays tilted, with right angles
const tilt = Math.PI / 9, rotate = ([x, y]) => [960 + (x - 960) * Math.cos(tilt) - (y - 540) * Math.sin(tilt), 540 + (x - 960) * Math.sin(tilt) + (y - 540) * Math.cos(tilt)];
const tilted = Region.straighten(wobble(trace(shapes.rectangle.map(rotate), 40), 6), size);
assert.equal(tilted.kind, "rectangle");
const [a, b, c] = tilted.points, dot = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]);
assert.ok(Math.abs(dot) / (Math.hypot(b[0] - a[0], b[1] - a[1]) * Math.hypot(c[0] - b[0], c[1] - b[1])) < 0.02, "right angle kept");
// A round outline becomes an ellipse, not a hexagon
const round = Region.straighten(wobble(circle.filter((_, i) => i % 20 === 0), 5), size);
assert.equal(round.kind, "circle");
assert.ok(Math.abs(Region.area(round.points) / Region.area(circle) - 1) < 0.05, "ellipse keeps the area");
// Hand-drawn round outlines, as the pencil leaves them (radius drifting, ends not meeting, the stroke simplified), become
// ellipses: 5 or 6 corners also fit them within 3%, which once turned them into hexagons and pentagons
function hand(rx, ry, drift, gap, seed) {
    const pts = [];
    for (let i = 0; i < 300 * (1 - gap); i++) {
        const t = 2 * Math.PI * i / 300, r = 1 + drift * Math.sin(3 * t + seed) + drift * 0.5 * Math.sin(7 * t + seed * 2);
        pts.push([960 + rx * r * Math.cos(t), 540 + ry * r * Math.sin(t)]);
    }
    return Region.fit(Region.simplify(pts.map(([x, y]) => Region.toImage(x / 2, y / 2, 2, size)), 3), 100);
}
for (const [rx, ry, drift, gap, seed, kind] of [[300, 300, 0.03, 0.02, 1.3, "circle"], [300, 300, 0.06, 0.05, 1.3, "circle"], [250, 250, 0.07, 0.06, 0.4, "circle"],
                                                [120, 120, 0.05, 0.04, 1.3, "circle"], [450, 250, 0.04, 0.03, 1.3, "ellipse"], [180, 400, 0.05, 0.04, 2.1, "ellipse"]]) {
    const out = Region.straighten(hand(rx, ry, drift, gap, seed), size);
    assert.equal(out.kind, kind, `hand-drawn ${rx}x${ry} round outline`);
    if (kind === "circle") {
        const c = Region.centroid(out.points), radii = out.points.map(([x, y]) => Math.hypot(x - c[0], y - c[1]));
        assert.ok(Math.max(...radii) - Math.min(...radii) <= 2, "a true circle: every point the same distance from the centre, to the pixel");
    }
}
// ...while drawn polygons keep their corners, a shaky rectangle and a hexagon included
const ngon = (k, r) => Array.from({length: k}, (_, i) => [960 + r * Math.cos(i * 2 * Math.PI / k - Math.PI / 2), 540 + r * Math.sin(i * 2 * Math.PI / k - Math.PI / 2)]);
assert.equal(Region.straighten(wobble(trace(shapes.rectangle, 40), 14), size).kind, "rectangle");
assert.equal(Region.straighten(wobble(trace(ngon(5, 350), 30), 5), size).kind, "pentagon");
assert.equal(Region.straighten(wobble(trace(ngon(6, 350), 30), 5), size).kind, "hexagon");
// A scribble that is no simple shape is left alone
const star = Array.from({length: 10}, (_, i) => [960 + (i % 2 ? 150 : 450) * Math.cos(i * Math.PI / 5), 540 + (i % 2 ? 150 : 450) * Math.sin(i * Math.PI / 5)]);
assert.equal(Region.straighten(star, size), null, "a star is not forced into a simple shape");
console.log("shape correction ok (wobbly rectangle, quadrilateral and triangle straightened to their corners, tilted rectangle kept square, hand-drawn circles to true circles and ovals to ellipses, pentagon and hexagon kept, star left alone)");
