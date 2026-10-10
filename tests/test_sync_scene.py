"""The sync illustration's shapes and motion, shared by the AppKit and Tk windows."""

import pytest

from blackboard_sync.menubar import sync_scene as scene


def inside(point, rect):
    x, y = point
    left, top, right, bottom = rect
    return left <= x <= right and top <= y <= bottom


def test_papers_leave_the_cloud_and_drop_into_the_folder():
    start, end = scene.paper_at(0.0), scene.paper_at(0.999)
    cloud = (scene.CLOUD_BASE[0], scene.CLOUD_PUFFS[1][1] - scene.CLOUD_PUFFS[1][2],
             scene.CLOUD_BASE[2], scene.CLOUD_BASE[3])
    assert inside((start.x, start.y), cloud) and start.alpha == 0  # fades in behind the cloud
    assert inside((end.x, end.y), scene.FOLDER_FRONT) and end.alpha == 1  # lands behind the folder's front
    top = min(scene.paper_at(u / 20).y for u in range(21))
    assert top < scene.CLOUD_BASE[1] and top < scene.FOLDER_FRONT[1]  # an arc over the gap
    assert start.angle < end.angle  # it tilts over on the way


def test_papers_move_and_follow_each_other_evenly():
    now = scene.papers(1.0)
    later = scene.papers(1.0 + scene.FRAME_SECONDS * 3)
    assert len(now) == scene.PAPERS and now != later
    phases = sorted(scene.phases(1.0))
    gaps = [b - a for a, b in zip(phases, phases[1:])]
    assert gaps == pytest.approx([1 / scene.PAPERS] * (scene.PAPERS - 1))
    # One period later everything is where it was: a seamless loop.
    again = scene.papers(1.0 + scene.PERIOD)
    for one, other in zip(now, again):
        assert (one.x, one.y, one.angle, one.alpha) == pytest.approx((other.x, other.y, other.angle, other.alpha))


def test_papers_are_drawn_closest_to_the_folder_last():
    xs = [paper.x for paper in scene.papers(0.7)]
    assert xs == sorted(xs)


def test_reduce_motion_draws_the_same_still_picture_at_any_time():
    assert scene.papers(0.0, still=True) == scene.papers(42.0, still=True)
    assert scene.trail(0.0, still=True) == scene.trail(42.0, still=True)
    assert scene.landing_glow(0.0, still=True) == scene.landing_glow(42.0, still=True)
    assert all(paper.alpha == 1 for paper in scene.papers(0.0, still=True))  # nothing half faded


def test_the_trail_pulses_and_the_folder_lights_up_as_a_paper_lands():
    assert scene.trail(0.0) != scene.trail(scene.PERIOD / 3)
    assert len(scene.trail(0.0)) == scene.TRAIL
    assert all(0 < alpha <= 1 for _x, _y, alpha in scene.trail(0.3))
    assert scene.landing_glow(0.0) == 1.0  # a paper lands at every 1/PAPERS of a period
    assert scene.landing_glow(scene.PERIOD / scene.PAPERS / 2) == 0.0


def test_fit_scales_the_design_box_into_the_view_and_centres_it():
    assert scene.fit(scene.WIDTH, scene.HEIGHT) == (1.0, 0.0, 0.0)
    scale, left, top = scene.fit(480, 140)  # wider than the design: centred horizontally
    assert (scale, left, top) == (1.0, 120.0, 0.0)
    scale, left, top = scene.fit(120, 140)
    assert scale == 0.5 and top == pytest.approx(35.0) and left == 0.0
    assert scene.fit(0, 0)[0] == 0.0


def test_paper_shapes_turn_around_their_centre():
    paper = scene.Paper(100.0, 50.0, angle=90.0, scale=1.0, alpha=1.0)
    outline = scene.paper_outline(paper)
    width, height = scene.PAPER_SIZE
    # Turned a quarter: the paper lies on its side.
    xs, ys = [x for x, _ in outline], [y for _, y in outline]
    assert max(xs) - min(xs) == pytest.approx(height) and max(ys) - min(ys) == pytest.approx(width)
    assert sum(xs) / 4 == pytest.approx(100.0) and sum(ys) / 4 == pytest.approx(50.0)
    assert len(scene.paper_lines(paper)) == len(scene.PAPER_LINES)


def test_blend_mixes_a_colour_with_the_background_for_tk():
    assert scene.blend("#ffffff", "#000000", 1.0) == "#ffffff"
    assert scene.blend("#ffffff", "#000000", 0.0) == "#000000"
    assert scene.blend(scene.CYAN, "#ffffff", 0.5) == "#a8eefa"


def test_the_palettes_use_the_app_colours():
    assert scene.LIGHT.folder == scene.NAVY and scene.LIGHT.accent == scene.DARK.accent == scene.CYAN
    assert scene.LIGHT.paper_line == scene.MUTED
