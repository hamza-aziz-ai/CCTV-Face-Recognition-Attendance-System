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
})(typeof module !== "undefined" ? module.exports : (window.Region = {}));
