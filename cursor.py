"""Navigate an irregular set of actionable intersections with a D-pad."""

from game import HEIGHT, WIDTH, coords


def focus(cursor, options, direction=None, flipped=False):
    points = [coords(index) for index in options]
    if not points:
        return cursor
    x, y = cursor
    if direction is None or cursor not in points or len(points) == 1:
        return min(points, key=lambda point: (abs(point[0] - x) + abs(point[1] - y),
                                              abs(point[0] - x), point))

    dx, dy = direction
    dx, dy = (-dx, -dy) if flipped else (dx, dy)

    def rank(point):
        px, py = point[0] - x, point[1] - y
        forward = px * dx + py * dy
        across = abs(px * dy - py * dx)
        # Follow the requested row or column first, then use nearby diagonals.
        if forward > 0:
            return (0, across * 2 + forward, across, forward, point)
        if forward == 0:
            return (2, across, 0, 0, point)
        wrapped = forward + (WIDTH if dx else HEIGHT)
        return (1, across * 2 + wrapped, across, wrapped, point)

    return min((point for point in points if point != cursor), key=rank)

