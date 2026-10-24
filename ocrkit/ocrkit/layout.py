"""Page layout helpers: find the gutter of a two-page spread and split it."""

try:
    import numpy as np
except ImportError:   # gutter detection degrades to the middle of the image
    np = None

WORK_WIDTH = 800      # spreads are downscaled to this width for analysis
SEARCH = (0.35, 0.65) # the gutter is looked for in this band of the width


def find_gutter(img):
    """
    x position (in img pixels) between the two pages of an upright spread,
    and a note when no clear gutter was found.

    Text columns have many light/dark transitions top to bottom; a white
    margin and a dark gutter shadow both have few. The gutter is the centre
    of the quietest run of columns in the middle band.
    """
    w, h = img.size
    if np is None:
        return w // 2, "numpy not installed - split at the middle"
    scale = WORK_WIDTH / w
    small = img.convert("L").resize((WORK_WIDTH, max(1, int(h * scale))))
    a = np.asarray(small, dtype=float)
    dark = a < (np.median(a) * 0.7)
    trans = np.abs(np.diff(dark.astype(np.int8), axis=0)).sum(axis=0).astype(float)
    k = max(3, WORK_WIDTH // 100)
    smooth = np.convolve(trans, np.ones(k) / k, mode="same")

    lo, hi = int(WORK_WIDTH * SEARCH[0]), int(WORK_WIDTH * SEARCH[1])
    band = smooth[lo:hi]
    text_level = np.percentile(smooth, 75)
    if text_level <= 0:
        return w // 2, "no text found - split at the middle"
    floor = band.min()
    if floor > 0.35 * text_level:
        return w // 2, "no clear gutter - split at the middle"

    quiet = band <= floor + 0.10 * text_level
    i = int(band.argmin())
    left, right = i, i
    while left > 0 and quiet[left - 1]:
        left -= 1
    while right < len(band) - 1 and quiet[right + 1]:
        right += 1
    x_small = lo + (left + right) / 2
    return int(round(x_small / scale)), None


def split_spread(img, rtl=False):
    """
    [earlier page, later page], split_x, note.
    A portrait image is not a spread: it is returned whole.
    """
    w, h = img.size
    if w < h:
        return [img], None, "portrait image in a two-page scan - kept as one page"
    x, note = find_gutter(img)
    halves = [img.crop((0, 0, x, h)), img.crop((x, 0, w, h))]
    return (halves[::-1] if rtl else halves), x, note
