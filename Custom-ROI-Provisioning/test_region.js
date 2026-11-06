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
const nearEdge = [[1800, 1000], [1900, 1000], [1900, 1070]];
assert.ok(Region.scale(nearEdge, 3, size).every(([x, y]) => x >= 0 && x <= 1920 && y >= 0 && y <= 1080), "kept inside the picture");

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

// Straighten: a shaky hand-drawn outline becomes the regular, symmetric shape it was meant to be
const wobble = (pts, amount, seed = 1) => pts.map(([x, y], i) => [x + amount * Math.sin(i * 1.7 + seed), y + amount * Math.cos(i * 2.3 + seed)]);
const trace = (corners, perSide) => corners.flatMap((a, i) => {
    const b = corners[(i + 1) % corners.length];
    return Array.from({length: perSide}, (_, k) => [a[0] + (b[0] - a[0]) * k / perSide, a[1] + (b[1] - a[1]) * k / perSide]);
});
const drawn = (corners, shake = 5) => wobble(trace(corners, 40), shake);
const ngon = (k, r, rot = 0) => Array.from({length: k}, (_, i) => [960 + r * Math.cos(i * 2 * Math.PI / k - Math.PI / 2 + rot), 540 + r * Math.sin(i * 2 * Math.PI / k - Math.PI / 2 + rot)]);
const sideLengths = (p) => p.map((a, i) => Math.hypot(p[(i + 1) % p.length][0] - a[0], p[(i + 1) % p.length][1] - a[1]));
const angles = (p) => p.map((b, i) => {
    const a = p[(i - 1 + p.length) % p.length], c = p[(i + 1) % p.length], u = [a[0] - b[0], a[1] - b[1]], v = [c[0] - b[0], c[1] - b[1]];
    return Math.acos((u[0] * v[0] + u[1] * v[1]) / (Math.hypot(...u) * Math.hypot(...v))) * 180 / Math.PI;
});
// Equal to the pixel: points are whole pixels, so lengths can differ by rounding alone
const equal = (values, slack = 2) => Math.max(...values) - Math.min(...values) <= slack;
const near = (a, b, slack = 1.5) => Math.abs(a - b) <= slack;
const straight = (corners, shake) => Region.straighten(drawn(corners, shake), size);
// Level sides, wherever the corner list starts: how many sides run along the picture's x axis
const levelSides = (p) => p.filter((a, i) => near(a[1], p[(i + 1) % p.length][1])).length;
const inPicture = (p) => p.every(([x, y]) => Number.isInteger(x) && Number.isInteger(y) && x >= 0 && x <= 1920 && y >= 0 && y <= 1080);

let out = straight([[600, 250], [1080, 262], [1072, 735], [598, 728]]);
assert.equal(out.kind, "square");
assert.ok(equal(sideLengths(out.points)) && angles(out.points).every((a) => near(a, 90)) && inPicture(out.points));
assert.equal(levelSides(out.points), 2, "nearly level, so level");
out = straight([[400, 300], [1400, 310], [1395, 790], [402, 800]], 14);
assert.equal(out.kind, "rectangle", "a shaky rectangle");
const [w1, h1, w2, h2] = sideLengths(out.points);
assert.ok(near(w1, w2, 2) && near(h1, h2, 2) && angles(out.points).every((a) => near(a, 90)) && levelSides(out.points) === 2);
const tilt = 20 * Math.PI / 180;
const tilted = [[0, 0], [800, 0], [800, 400], [0, 400]].map(([x, y]) => [960 + (x - 400) * Math.cos(tilt) - (y - 200) * Math.sin(tilt), 540 + (x - 400) * Math.sin(tilt) + (y - 200) * Math.cos(tilt)]);
out = straight(tilted);
assert.equal(out.kind, "rectangle");
assert.ok(angles(out.points).every((a) => near(a, 90)) && levelSides(out.points) === 0, "a clearly tilted rectangle keeps its tilt, with right angles");

out = straight([[960, 190], [1340, 840], [570, 830]]);
assert.equal(out.kind, "equilateral triangle");
assert.ok(equal(sideLengths(out.points)) && angles(out.points).every((a) => near(a, 60)));
out = straight([[500, 250], [510, 820], [1300, 830]]);
assert.equal(out.kind, "right triangle");
assert.ok(angles(out.points).some((a) => near(a, 90, 0.5)));
out = straight([[500, 250], [505, 820], [1060, 815]]);
assert.equal(out.kind, "right isosceles triangle");
assert.ok(angles(out.points).some((a) => near(a, 90, 0.5)) && angles(out.points).filter((a) => near(a, 45, 0.5)).length === 2);
out = straight([[960, 150], [1250, 850], [650, 840]]);
assert.equal(out.kind, "isosceles triangle");
const tri = sideLengths(out.points).sort((a, b) => a - b);
assert.ok(near(tri[1], tri[2], 2) && !near(tri[0], tri[1], 20), "two equal sides");

out = straight([[700, 300], [1220, 310], [1500, 800], [420, 790]]);
assert.equal(out.kind, "isosceles trapezoid");
const legs = sideLengths(out.points);
const trapezoidLevel = out.points.map((a, i) => near(a[1], out.points[(i + 1) % 4][1]));
const leg = trapezoidLevel[0] ? [legs[1], legs[3]] : [legs[0], legs[2]];
assert.ok(levelSides(out.points) === 2 && near(leg[0], leg[1], 2), "equal legs, parallel sides level");
out = straight([[600, 300], [1300, 300], [1100, 700], [400, 700]]);
assert.equal(out.kind, "parallelogram");
const ps = sideLengths(out.points);
assert.ok(near(ps[0], ps[2], 2) && near(ps[1], ps[3], 2));
out = straight([[960, 200], [1300, 540], [960, 880], [620, 540]].map(([x, y], i) => [x + [0, 15, -10, 5][i], y + [10, -5, 0, 10][i]]));
assert.equal(out.kind, "square", "a diamond with right angles is a square standing on a corner");

for (const [k, name] of [[5, "regular pentagon"], [6, "regular hexagon"]]) {
    out = straight(ngon(k, 350, 0.05).map(([x, y], i) => [x + [0, 20, -15, 10, -20, 15][i], y + [10, -20, 15, 0, -10, 5][i]]));
    assert.equal(out.kind, name);
    assert.ok(equal(sideLengths(out.points)) && equal(angles(out.points), 1) && inPicture(out.points), `${name}: all sides and angles equal`);
}

// Hand-drawn round outlines, as the pencil leaves them (radius drifting, ends not meeting, the stroke simplified), become
// circles or ellipses: 5 or 6 corners also fit them within 3%, which once turned them into hexagons and pentagons
function hand(rx, ry, drift, gap, seed) {
    const pts = [];
    for (let i = 0; i < 300 * (1 - gap); i++) {
        const a = 2 * Math.PI * i / 300, r = 1 + drift * Math.sin(3 * a + seed) + drift * 0.5 * Math.sin(7 * a + seed * 2);
        pts.push([960 + rx * r * Math.cos(a), 540 + ry * r * Math.sin(a)]);
    }
    return Region.fit(Region.simplify(pts.map(([x, y]) => Region.toImage(x / 2, y / 2, 2, size)), 3), 100);
}
for (const [rx, ry, drift, gap, seed, kind] of [[300, 300, 0.03, 0.02, 1.3, "circle"], [300, 300, 0.06, 0.05, 1.3, "circle"], [250, 250, 0.07, 0.06, 0.4, "circle"],
                                                [120, 120, 0.05, 0.04, 1.3, "circle"], [450, 250, 0.04, 0.03, 1.3, "ellipse"], [180, 400, 0.05, 0.04, 2.1, "ellipse"]]) {
    out = Region.straighten(hand(rx, ry, drift, gap, seed), size);
    assert.equal(out.kind, kind, `hand-drawn ${rx}x${ry} round outline`);
    const c = Region.centroid(out.points), radii = out.points.map(([x, y]) => Math.hypot(x - c[0], y - c[1]));
    if (kind === "circle") assert.ok(equal(radii), "a true circle: every point the same distance from the centre, to the pixel");
    else assert.ok(out.points.some(([, y]) => near(y, c[1], 1)) && out.points.some(([x]) => near(x, c[0], 1)), "a nearly level ellipse is level");
}

// A scribble that is no simple shape is left alone
const star = Array.from({length: 10}, (_, i) => [960 + (i % 2 ? 150 : 450) * Math.cos(i * Math.PI / 5), 540 + (i % 2 ? 150 : 450) * Math.sin(i * Math.PI / 5)]);
assert.equal(Region.straighten(star, size), null, "a star is not forced into a simple shape");

// Stretching along one axis of the picture: a square stretched sideways is a rectangle of the same height
const sq = [[800, 400], [1000, 400], [1000, 600], [800, 600]];
assert.deepEqual(Region.stretch(sq, 0, 2, 800, size), [[800, 400], [1200, 400], [1200, 600], [800, 600]]);
assert.deepEqual(Region.stretch(sq, 1, 0.5, 600, size), [[800, 500], [1000, 500], [1000, 600], [800, 600]]);
assert.ok(inPicture(Region.stretch(sq, 0, 10, 800, size)), "stretching stops at the picture's edge");

console.log("straighten ok (square, rectangle and tilted rectangle with right angles, equilateral, right, right isosceles and isosceles triangles, isosceles trapezoid, parallelogram, regular pentagon and hexagon, circles and level ellipses, star left alone, one-axis stretch)");
