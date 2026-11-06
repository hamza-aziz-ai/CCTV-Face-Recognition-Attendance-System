// Polygon geometry for the region page, in full-resolution image pixels: what the server stores and validates (3 to 100
// integer points within the snapshot's size). Plain functions, so test_region.js can check them with Node.
(function (Region) {
    "use strict";

    // An image point from a point on the shown picture, rounded and kept inside the picture (0..width, 0..height)
    Region.toImage = (x, y, factor, size) => Region.clamp([Math.round(x * factor), Math.round(y * factor)], size);

    Region.clamp = ([x, y], [w, h]) => [Math.min(w, Math.max(0, Math.round(x))), Math.min(h, Math.max(0, Math.round(y)))];

    Region.bounds = (points) => {
        const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
        return {left: Math.min(...xs), top: Math.min(...ys), right: Math.max(...xs), bottom: Math.max(...ys)};
    };

    // The polygon's area centroid; the mean of its points when it has no area
    Region.centroid = (points) => {
        let area = 0, cx = 0, cy = 0;
        points.forEach(([x, y], i) => {
            const [nx, ny] = points[(i + 1) % points.length], cross = x * ny - nx * y;
            area += cross; cx += (x + nx) * cross; cy += (y + ny) * cross;
        });
        if (Math.abs(area) < 1e-9) return [points.reduce((s, p) => s + p[0], 0) / points.length, points.reduce((s, p) => s + p[1], 0) / points.length];
        return [cx / (3 * area), cy / (3 * area)];
    };

    Region.area = (points) => Math.abs(points.reduce((s, [x, y], i) => {
        const [nx, ny] = points[(i + 1) % points.length];
        return s + x * ny - nx * y;
    }, 0)) / 2;

    // Grown or shrunk about its centroid, every point kept inside the picture
    Region.scale = (points, factor, size, center = Region.centroid(points)) =>
        points.map(([x, y]) => Region.clamp([center[0] + (x - center[0]) * factor, center[1] + (y - center[1]) * factor], size));

    // Moved as a whole; the move stops at the picture's edges, so the shape never changes
    Region.translate = (points, dx, dy, [w, h]) => {
        const b = Region.bounds(points);
        const mx = Math.min(w - b.right, Math.max(-b.left, Math.round(dx)));
        const my = Math.min(h - b.bottom, Math.max(-b.top, Math.round(dy)));
        return points.map(([x, y]) => [x + mx, y + my]);
    };

    Region.inside = ([px, py], points) => {
        let hit = false;
        for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
            const [xi, yi] = points[i], [xj, yj] = points[j];
            if ((yi > py) !== (yj > py) && px < (xj - xi) * (py - yi) / (yj - yi) + xi) hit = !hit;
        }
        return hit;
    };

    function distanceToSegment([px, py], [ax, ay], [bx, by]) {
        const dx = bx - ax, dy = by - ay, length = dx * dx + dy * dy;
        const t = length ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length)) : 0;
        return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
    }

    // Ramer-Douglas-Peucker on an open line: drops points closer than tolerance to the line through their neighbours
    Region.simplify = (points, tolerance) => {
        if (points.length < 3) return points.slice();
        let worst = 0, at = 0;
        for (let i = 1; i < points.length - 1; i++) {
            const d = distanceToSegment(points[i], points[0], points[points.length - 1]);
            if (d > worst) { worst = d; at = i; }
        }
        if (worst <= tolerance) return [points[0], points[points.length - 1]];
        return Region.simplify(points.slice(0, at + 1), tolerance).slice(0, -1).concat(Region.simplify(points.slice(at), tolerance));
    };

    // A closed polygon with at most max points: simplified with a growing tolerance until it fits, never below 3 points
    Region.fit = (points, max) => {
        if (points.length <= max) return points;
        for (let tolerance = 0.5; ; tolerance *= 1.5) {
            const open = Region.simplify(points.concat([points[0]]), tolerance).slice(0, -1);
            if (open.length <= max && open.length >= 3) return open;
            if (open.length < 3) return points.slice(0, max);
        }
    };

    // ---- Shape correction: the outline as drawn, replaced by the nearest clean shape ----

    // Points every `step` pixels along the closed outline, so a fit is judged along the whole boundary
    function densify(points, step) {
        const out = [];
        points.forEach((a, i) => {
            const b = points[(i + 1) % points.length], n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / step));
            for (let k = 0; k < n; k++) out.push([a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n]);
        });
        return out;
    }

    // Mean distance from the drawn outline to the candidate's boundary, as a share of the shape's size (sqrt of its area)
    Region.fitError = (drawn, candidate) => {
        const size = Math.sqrt(Region.area(drawn)) || 1;
        const samples = densify(drawn, size / 60);
        const total = samples.reduce((sum, p) => sum + Math.min(...candidate.map((a, i) => distanceToSegment(p, a, candidate[(i + 1) % candidate.length]))), 0);
        return total / samples.length / size;
    };

    // Which k of the drawn points are the corners: repeatedly drops the point whose removal changes the area least
    // (Visvalingam-Whyatt). Returns their indices, in order
    function cornerIndices(points, k) {
        const kept = points.map((_, i) => i);
        while (kept.length > k) {
            let least = Infinity, at = 0;
            kept.forEach((bi, i) => {
                const a = points[kept[(i - 1 + kept.length) % kept.length]], b = points[bi], c = points[kept[(i + 1) % kept.length]];
                const triangle = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2;
                if (triangle < least) { least = triangle; at = i; }
            });
            kept.splice(at, 1);
        }
        return kept;
    }

    // The straight line through a side's drawn points (total least squares): a point on it and its direction
    function fitLine(side) {
        const cx = side.reduce((s, p) => s + p[0], 0) / side.length, cy = side.reduce((s, p) => s + p[1], 0) / side.length;
        let xx = 0, yy = 0, xy = 0;
        for (const [x, y] of side) { xx += (x - cx) ** 2; yy += (y - cy) ** 2; xy += (x - cx) * (y - cy); }
        const t = Math.atan2(2 * xy, xx - yy) / 2;
        return {point: [cx, cy], dir: [Math.cos(t), Math.sin(t)]};
    }

    function intersect(l1, l2) {
        const cross = l1.dir[0] * l2.dir[1] - l1.dir[1] * l2.dir[0];
        if (Math.abs(cross) < 1e-6) return null;  // parallel sides: no corner between them
        const dx = l2.point[0] - l1.point[0], dy = l2.point[1] - l1.point[1], t = (dx * l2.dir[1] - dy * l2.dir[0]) / cross;
        return [l1.point[0] + t * l1.dir[0], l1.point[1] + t * l1.dir[1]];
    }

    // Exactly k corners where the drawn sides really meet: each side is the best straight line through its own points
    // (leaving out the ends, which bend into the corners), and each corner is where two neighbouring lines cross
    Region.corners = (points, k) => {
        const at = cornerIndices(points, k);
        const lines = at.map((start, i) => {
            const end = at[(i + 1) % k], side = [];
            for (let j = start; j !== end; j = (j + 1) % points.length) side.push(points[j]);
            side.push(points[end]);
            const trim = side.length >= 8 ? Math.floor(side.length * 0.15) : 0;
            return fitLine(trim ? side.slice(trim, side.length - trim) : side);
        });
        return at.map((index, i) => intersect(lines[(i - 1 + k) % k], lines[i]) || points[index]);
    };

    // ---- Symmetry: the detected corners made into the regular shape they are close to ----

    const DEG = Math.PI / 180;
    const minus = (a, b) => [a[0] - b[0], a[1] - b[1]];
    const length = (v) => Math.hypot(v[0], v[1]);
    const unit = (v) => { const l = length(v) || 1; return [v[0] / l, v[1] / l]; };
    const turn = ([x, y], t) => [x * Math.cos(t) - y * Math.sin(t), x * Math.sin(t) + y * Math.cos(t)];
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
    const signedArea = (points) => points.reduce((s, [x, y], i) => { const [nx, ny] = points[(i + 1) % points.length]; return s + x * ny - nx * y; }, 0) / 2;
    const angleAt = (a, b, c) => Math.acos(Math.max(-1, Math.min(1, dot(unit(minus(a, b)), unit(minus(c, b)))))) / DEG;
    // Turned onto the picture's axes when within this much of them: a nearly level shape is meant level
    const LEVEL = 10 * DEG;
    const snap = (t, step, base = 0) => { const k = Math.round((t - base) / step), s = base + k * step; return Math.abs(t - s) <= LEVEL ? s : t; };
    const rotateAbout = (points, c, t) => points.map((p) => { const [x, y] = turn(minus(p, c), t); return [c[0] + x, c[1] + y]; });
    // The direction of a line, folded into 0..90 degrees (its angle times 4 averages sides that point either way)
    const quarterTurn = (dirs) => { let sx = 0, sy = 0; for (const t of dirs) { sx += Math.cos(4 * t); sy += Math.sin(4 * t); } return Math.atan2(sy, sx) / 4; };
    const sideAngles = (q) => q.map((a, i) => { const b = q[(i + 1) % q.length]; return Math.atan2(b[1] - a[1], b[0] - a[0]); });
    // How far apart two directions are, as lines (0..90 degrees)
    const lineGap = (s, t) => { const d = Math.abs(((s - t) % Math.PI + Math.PI) % Math.PI); return Math.min(d, Math.PI - d); };

    // A regular polygon (all sides and angles equal) with the corners' centre, mean radius, turning direction and
    // orientation, set level (a flat side at the bottom) when it nearly is
    function regular(corners) {
        const n = corners.length, c = Region.centroid(corners), dir = signedArea(corners) >= 0 ? 1 : -1;
        const r = corners.reduce((s, p) => s + length(minus(p, c)), 0) / n;
        let sx = 0, sy = 0;
        corners.forEach((p, i) => { const t = Math.atan2(p[1] - c[1], p[0] - c[0]) - dir * 2 * Math.PI * i / n; sx += Math.cos(t); sy += Math.sin(t); });
        const phase = snap(Math.atan2(sy, sx), 2 * Math.PI / n, Math.PI / 2 + Math.PI / n);
        return corners.map((_, i) => [c[0] + r * Math.cos(phase + dir * 2 * Math.PI * i / n), c[1] + r * Math.sin(phase + dir * 2 * Math.PI * i / n)]);
    }

    // A rectangle (a square when its sides are within 15% of each other) about the corners' centre, its sides the mean
    // of the opposite sides, level when nearly so
    function rectangle(quad) {
        const t = snap(quarterTurn(sideAngles(quad)), Math.PI / 2), ux = [Math.cos(t), Math.sin(t)], uy = [-Math.sin(t), Math.cos(t)];
        const c = Region.centroid(quad);
        let w = 2 * quad.reduce((s, p) => s + Math.abs(dot(minus(p, c), ux)), 0) / 4, h = 2 * quad.reduce((s, p) => s + Math.abs(dot(minus(p, c), uy)), 0) / 4;
        const square = Math.min(w, h) / Math.max(w, h) >= 0.85;
        if (square) w = h = Math.sqrt(w * h);
        // Each corner keeps its quadrant, so the outline keeps its order and turning direction
        const corners = quad.map((p) => {
            const sa = Math.sign(dot(minus(p, c), ux)) || 1, sb = Math.sign(dot(minus(p, c), uy)) || 1;
            return [c[0] + sa * w / 2 * ux[0] + sb * h / 2 * uy[0], c[1] + sa * w / 2 * ux[1] + sb * h / 2 * uy[1]];
        });
        return {kind: square ? "square" : "rectangle", points: corners};
    }

    // A four-sided shape that is not rectangular: an isosceles trapezoid when one pair of sides is parallel (within
    // 10 degrees), a rhombus or parallelogram when both are, otherwise the plain quadrilateral
    function quadrilateral(q) {
        const t = sideAngles(q), parallel = [lineGap(t[0], t[2]) <= LEVEL, lineGap(t[1], t[3]) <= LEVEL];
        const c = Region.centroid(q);
        if (parallel[0] && parallel[1]) {
            const sides = q.map((a, i) => length(minus(q[(i + 1) % 4], a)));
            if (Math.max(...sides) / Math.min(...sides) <= 1.15) {
                // Rhombus: equal sides, its diagonals at right angles through the centre
                const d1 = minus(q[2], q[0]), half1 = length(d1) / 2, half2 = length(minus(q[3], q[1])) / 2;
                const a = snap(Math.atan2(d1[1], d1[0]), Math.PI / 2), u = [Math.cos(a), Math.sin(a)];
                const v = signedArea(q) >= 0 ? [-u[1], u[0]] : [u[1], -u[0]];
                return {kind: "rhombus", points: [[c[0] - u[0] * half1, c[1] - u[1] * half1], [c[0] + v[0] * half2, c[1] + v[1] * half2],
                                                  [c[0] + u[0] * half1, c[1] + u[1] * half1], [c[0] - v[0] * half2, c[1] - v[1] * half2]]};
            }
            // Parallelogram: each pair of opposite sides made equal and parallel, about the centre
            const e1 = [(q[1][0] - q[0][0] + q[2][0] - q[3][0]) / 2, (q[1][1] - q[0][1] + q[2][1] - q[3][1]) / 2];
            const e2 = [(q[3][0] - q[0][0] + q[2][0] - q[1][0]) / 2, (q[3][1] - q[0][1] + q[2][1] - q[1][1]) / 2];
            return {kind: "parallelogram", points: [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => [c[0] + (a * e1[0] + b * e2[0]) / 2, c[1] + (a * e1[1] + b * e2[1]) / 2])};
        }
        if (parallel[0] || parallel[1]) {
            // Isosceles trapezoid: the two parallel sides centred on one axis at right angles to them
            const i = parallel[0] ? 0 : 1, j = i + 2;
            const a = snap(quarterTurn([t[i], t[j]]) + (lineGap(quarterTurn([t[i], t[j]]), t[i]) > Math.PI / 4 ? Math.PI / 2 : 0), Math.PI / 2);
            const u = [Math.cos(a), Math.sin(a)], n = [-u[1], u[0]];
            const mid = (k) => [(q[k][0] + q[(k + 1) % 4][0]) / 2, (q[k][1] + q[(k + 1) % 4][1]) / 2];
            const axis = (dot(mid(i), u) + dot(mid(j), u)) / 2;
            const out = q.map((p) => p.slice());
            for (const k of [i, j]) {
                const half = length(minus(q[(k + 1) % 4], q[k])) / 2, h = dot(mid(k), n), s = Math.sign(dot(minus(q[(k + 1) % 4], q[k]), u)) || 1;
                out[k] = [u[0] * (axis - s * half) + n[0] * h, u[1] * (axis - s * half) + n[1] * h];
                out[(k + 1) % 4] = [u[0] * (axis + s * half) + n[0] * h, u[1] * (axis + s * half) + n[1] * h];
            }
            return {kind: "isosceles trapezoid", points: out};
        }
        return {kind: "quadrilateral", points: q};
    }

    // A triangle: equilateral when its sides are within 15% of each other; right-angled when an angle is within 12
    // degrees of 90 (and isosceles too when its legs are within 15%); isosceles when two sides are within 12%
    function triangle(tri) {
        const sides = tri.map((_, i) => length(minus(tri[(i + 1) % 3], tri[(i + 2) % 3])));  // side opposite each corner
        if (Math.max(...sides) / Math.min(...sides) <= 1.15) return {kind: "equilateral triangle", points: regular(tri)};
        const angles = tri.map((p, i) => angleAt(tri[(i + 2) % 3], p, tri[(i + 1) % 3]));
        const r = angles.reduce((best, a, i) => (Math.abs(a - 90) < Math.abs(angles[best] - 90) ? i : best), 0);
        if (Math.abs(angles[r] - 90) <= 12) {
            const v = tri[r], p = tri[(r + 1) % 3], q = tri[(r + 2) % 3];
            let lp = length(minus(p, v)), lq = length(minus(q, v));
            const isosceles = Math.max(lp, lq) / Math.min(lp, lq) <= 1.15;
            if (isosceles) lp = lq = (lp + lq) / 2;
            // The legs at exactly 90 degrees about the angle's bisector, level when nearly so
            const bisector = unit([unit(minus(p, v))[0] + unit(minus(q, v))[0], unit(minus(p, v))[1] + unit(minus(q, v))[1]]);
            const side = Math.sign(minus(p, v)[0] * minus(q, v)[1] - minus(p, v)[1] * minus(q, v)[0]) || 1;
            let dp = turn(bisector, -side * Math.PI / 4);
            const level = snap(Math.atan2(dp[1], dp[0]), Math.PI / 2) - Math.atan2(dp[1], dp[0]);
            dp = turn(dp, level);
            const dq = turn(dp, side * Math.PI / 2), out = [];
            out[r] = v; out[(r + 1) % 3] = [v[0] + dp[0] * lp, v[1] + dp[1] * lp]; out[(r + 2) % 3] = [v[0] + dq[0] * lq, v[1] + dq[1] * lq];
            return {kind: isosceles ? "right isosceles triangle" : "right triangle", points: out};
        }
        // Isosceles: the corner between the two near-equal sides moved onto the base's perpendicular bisector
        for (let x = 0; x < 3; x++) {
            const y = (x + 1) % 3, z = (x + 2) % 3;
            if (Math.abs(sides[y] - sides[z]) / Math.max(sides[y], sides[z]) <= 0.12) {
                const m = [(tri[y][0] + tri[z][0]) / 2, (tri[y][1] + tri[z][1]) / 2], base = minus(tri[z], tri[y]);
                const t = Math.atan2(base[1], base[0]), level = snap(t, Math.PI / 2) - t;
                const [by, bz] = [rotateAbout([tri[y]], m, level)[0], rotateAbout([tri[z]], m, level)[0]];
                const n = unit([-(bz[1] - by[1]), bz[0] - by[0]]), h = dot(minus(rotateAbout([tri[x]], m, level)[0], m), n);
                const out = [];
                out[x] = [m[0] + n[0] * h, m[1] + n[1] * h]; out[y] = by; out[z] = bz;
                return {kind: "isosceles triangle", points: out};
            }
        }
        return {kind: "triangle", points: tri};
    }

    // The ellipse with the outline's own centre, orientation and spread (a boundary's variance along an axis is a²/2),
    // level when nearly so, and a true circle when its axes are within 10% of each other
    function ellipse(drawn, sides = 32) {
        const boundary = densify(drawn, Math.sqrt(Region.area(drawn)) / 80 || 1);
        const [cx, cy] = Region.centroid(drawn);
        let xx = 0, yy = 0, xy = 0;
        for (const [x, y] of boundary) { xx += (x - cx) ** 2; yy += (y - cy) ** 2; xy += (x - cx) * (y - cy); }
        xx /= boundary.length; yy /= boundary.length; xy /= boundary.length;
        const mid = (xx + yy) / 2, spread = Math.sqrt(((xx - yy) / 2) ** 2 + xy * xy), t = snap(Math.atan2(2 * xy, xx - yy) / 2, Math.PI / 2);
        let a = Math.sqrt(2 * (mid + spread)), b = Math.sqrt(2 * Math.max(0, mid - spread));
        const circle = b >= 0.9 * a;
        if (circle) a = b = Math.sqrt(a * b);
        return {kind: circle ? "circle" : "ellipse", points: Array.from({length: sides}, (_, i) => {
            const u = 2 * Math.PI * i / sides, x = a * Math.cos(u), y = b * Math.sin(u);
            return [cx + x * Math.cos(t) - y * Math.sin(t), cy + x * Math.sin(t) + y * Math.cos(t)];
        })};
    }

    // The corners made symmetric: a regular shape when the drawing is close to one
    function symmetric(corners) {
        if (corners.length === 3) return triangle(corners);
        if (corners.length === 4) {
            return corners.every((b, i) => Math.abs(angleAt(corners[(i + 3) % 4], b, corners[(i + 1) % 4]) - 90) <= 12) ? rectangle(corners) : quadrilateral(corners);
        }
        return {kind: corners.length === 5 ? "regular pentagon" : "regular hexagon", points: regular(corners)};
    }

    Region.symmetric = symmetric;

    // ponytail: fixed tolerances (a fit within 3% of the shape's size, an ellipse within 4.5%, 10 to 15% for "equal"
    // and 10 to 12 degrees for "square", "parallel" or "level"), tuned on hand-drawn test shapes; make them settings if
    // real drawings need it
    Region.straighten = (points, size, tolerance = 0.03) => {
        if (points.length < 3 || Region.area(points) < 1) return null;
        // The corner count comes from how well plain corners fit (raw); the shape returned is then made symmetric
        const fits = [3, 4, 5, 6].filter((k) => k <= points.length).map((k) => {
            const corners = Region.corners(points, k);
            return {corners, raw: Region.fitError(points, corners)};
        });
        // A drawn polygon fits sharply at its true corner count: the error at least halves from one corner fewer, and by
        // a third of the tolerance or more (a rectangle drops from about 5% to under 1% at 4). A round outline only
        // improves gradually, and 5 or 6 corners always fit it within 3%, so it is an ellipse unless some corner count
        // fits that sharply. Of the sharp ones the closest wins: a hexagon also halves at 5, then fits far better at 6
        const sharp = (f, i) => i === 0 ? f.raw <= tolerance / 2 : f.raw <= fits[i - 1].raw / 2 && fits[i - 1].raw - f.raw >= tolerance / 3;
        const polygon = fits.filter((f, i) => f.raw <= tolerance && sharp(f, i)).reduce((a, f) => (!a || f.raw < a.raw ? f : a), null);
        let best = polygon && symmetric(polygon.corners);
        if (!best) {
            const round = ellipse(points);
            best = Region.fitError(points, round.points) <= tolerance * 1.5 ? round : null;
        }
        return best ? {kind: best.kind, points: best.points.map((p) => Region.clamp(p, size))} : null;
    };

    // Stretched along one axis of the picture, away from a fixed line (an edge of its bounding box), kept in the picture
    Region.stretch = (points, axis, factor, anchor, size) =>
        points.map((p) => Region.clamp(axis === 0 ? [anchor + (p[0] - anchor) * factor, p[1]] : [p[0], anchor + (p[1] - anchor) * factor], size));
})(typeof module !== "undefined" ? module.exports : (window.Region = {}));
