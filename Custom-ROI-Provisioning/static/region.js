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

    const angleAt = (a, b, c) => {
        const u = [a[0] - b[0], a[1] - b[1]], v = [c[0] - b[0], c[1] - b[1]];
        return Math.acos(Math.max(-1, Math.min(1, (u[0] * v[0] + u[1] * v[1]) / (Math.hypot(...u) * Math.hypot(...v) || 1)))) * 180 / Math.PI;
    };

    // A quadrilateral whose corners are all near right angles, squared into a rectangle at its own tilt, bounding the drawing
    function rectangle(quad, drawn) {
        let sx = 0, sy = 0;  // the mean edge direction, folded into 0..90 degrees by doubling the angle twice
        quad.forEach((a, i) => {
            const b = quad[(i + 1) % 4], t = Math.atan2(b[1] - a[1], b[0] - a[0]) * 4;
            sx += Math.cos(t); sy += Math.sin(t);
        });
        const t = Math.atan2(sy, sx) / 4, ux = [Math.cos(t), Math.sin(t)], uy = [-Math.sin(t), Math.cos(t)];
        const along = drawn.map((p) => p[0] * ux[0] + p[1] * ux[1]), across = drawn.map((p) => p[0] * uy[0] + p[1] * uy[1]);
        const [x0, x1, y0, y1] = [Math.min(...along), Math.max(...along), Math.min(...across), Math.max(...across)];
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([a, c]) => [a * ux[0] + c * uy[0], a * ux[1] + c * uy[1]]);
    }

    // The ellipse with the outline's own centre, orientation and spread: a boundary's variance along an axis is a²/2
    function ellipse(drawn, sides = 32) {
        const boundary = densify(drawn, Math.sqrt(Region.area(drawn)) / 80 || 1);
        const [cx, cy] = Region.centroid(drawn);
        let xx = 0, yy = 0, xy = 0;
        for (const [x, y] of boundary) { xx += (x - cx) ** 2; yy += (y - cy) ** 2; xy += (x - cx) * (y - cy); }
        xx /= boundary.length; yy /= boundary.length; xy /= boundary.length;
        const mid = (xx + yy) / 2, spread = Math.sqrt(((xx - yy) / 2) ** 2 + xy * xy), t = Math.atan2(2 * xy, xx - yy) / 2;
        const a = Math.sqrt(2 * (mid + spread)), b = Math.sqrt(2 * Math.max(0, mid - spread));
        return Array.from({length: sides}, (_, i) => {
            const u = 2 * Math.PI * i / sides, x = a * Math.cos(u), y = b * Math.sin(u);
            return [cx + x * Math.cos(t) - y * Math.sin(t), cy + x * Math.sin(t) + y * Math.cos(t)];
        });
    }

    const NAMES = {3: "triangle", 4: "quadrilateral", 5: "pentagon", 6: "hexagon"};
    // ponytail: fixed tolerances (3% of the shape's size for a fit, 12 degrees from square for a rectangle), tuned on
    // drawn test shapes; make them settings if real drawings need it
    Region.straighten = (points, size, tolerance = 0.03) => {
        if (points.length < 3 || Region.area(points) < 1) return null;
        const fits = [3, 4, 5, 6].filter((k) => k <= points.length).map((k) => {
            let shape = Region.corners(points, k), kind = NAMES[k];
            if (k === 4 && shape.every((b, i) => Math.abs(angleAt(shape[(i + 3) % 4], b, shape[(i + 1) % 4]) - 90) <= 12)) {
                shape = rectangle(shape, points); kind = "rectangle";
            }
            return {kind, points: shape, error: Region.fitError(points, shape)};
        });
        const round = {kind: "ellipse", points: ellipse(points), error: 0};
        round.error = Region.fitError(points, round.points);
        // The fewest corners that fit, unless an ellipse fits clearly better (a hexagon also fits a circle within 3%)
        const polygon = fits.find((f) => f.error <= tolerance);
        const best = round.error <= tolerance * 1.5 && (!polygon || round.error < polygon.error / 2) ? round : polygon;
        return best ? {kind: best.kind, error: best.error, points: best.points.map((p) => Region.clamp(p, size))} : null;
    };
})(typeof module !== "undefined" ? module.exports : (window.Region = {}));
