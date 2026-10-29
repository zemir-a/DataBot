"""XP formula. Change the numbers here to tune the game."""

BASE_POINTS = 10     # for any correct answer in time
SPEED_BONUS = 10     # extra points, scaled by how fast the answer was
GRACE_SECONDS = 2     # allowance for network delay


def points_for(correct, seconds_used, time_limit):
    if not correct:
        return 0
    if seconds_used > time_limit + GRACE_SECONDS:
        return 0
    fraction_left = max(0.0, 1 - seconds_used / time_limit)
    return round(BASE_POINTS + SPEED_BONUS * fraction_left)