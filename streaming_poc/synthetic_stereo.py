"""Synthetic stereo test frames for the Task 04B proof of concept.

No real camera images are used: the E1-E5 captures contain an identifiable
person, and E6-E9 have not been taken. Every frame is generated here, at the
validated OAK mono size (1280 x 800, 8-bit luma), using only the standard
library.

Each frame carries, burned into the pixels:

* a BARCODE strip at the top: a start pattern, then 32 bits of sequence
  number, 1 bit eye, 1 bit camera and 6 bits of check. A receiver can read it
  back after encoding and decoding, and compare it with the SEI metadata --
  the test that the metadata travelled with the right picture;
* an EYE MARKER: a solid block at the left edge in the left image, at the
  right edge in the right image (for the later Quest eye-mapping check: each
  eye should see its block on its own outer side);
* a textured background plus a central target and a near target shifted
  horizontally between the eyes by known disparities (+12 px and +36 px), so
  the pair fuses as a simple stereo scene;
* a MOVING BAR, so consecutive frames differ and the encoder does real work.
"""

from __future__ import annotations

WIDTH = 1280
HEIGHT = 800

CELL = 20                     # barcode cell size, px
BAR_X0 = 80                   # barcode left edge (clear of the eye marker)
BAR_Y0 = 16
START = (1, 0, 1, 1, 0, 1)    # start pattern
N_DATA = 40                   # 32 seq + eye + camera + 6 check
QUIET = 4                     # px of black around the strip

DISPARITY_MID = 12
DISPARITY_NEAR = 36


def _check6(value34: int) -> int:
    """6-bit check over the 34 payload bits (sum of 6-bit chunks, mod 64,
    XOR 0x2A so an all-black strip never validates)."""
    s = 0
    v = value34
    while v:
        s += v & 0x3F
        v >>= 6
    return (s & 0x3F) ^ 0x2A


def barcode_bits(seq: int, eye: int, camera: int) -> list[int]:
    seq &= 0xFFFFFFFF
    payload = seq | (eye & 1) << 32 | (camera & 1) << 33
    word = payload | _check6(payload) << 34
    return list(START) + [(word >> i) & 1 for i in range(N_DATA)]


def _fill(buf: bytearray, stride: int, x0: int, y0: int, w: int, h: int, value: int):
    row = bytes([value]) * w
    for y in range(y0, y0 + h):
        o = y * stride + x0
        buf[o:o + w] = row


def _background(eye: int) -> bytearray:
    """Textured background with two targets at known disparities."""
    buf = bytearray(WIDTH * HEIGHT)
    # diagonal gradient plus a 40 px checker, mid-grey overall
    for y in range(HEIGHT):
        base = 60 + (y * 80) // HEIGHT
        row = bytearray(WIDTH)
        for x in range(WIDTH):
            chk = 30 if ((x // 40) + (y // 40)) & 1 else 0
            row[x] = base + chk + (x * 40) // WIDTH
        buf[y * WIDTH:(y + 1) * WIDTH] = row
    # mid target (crossed squares) and near target, shifted for the right eye
    shift_mid = -DISPARITY_MID if eye else 0
    shift_near = -DISPARITY_NEAR if eye else 0
    cx, cy = WIDTH // 2, HEIGHT // 2
    _fill(buf, WIDTH, cx - 120 + shift_mid, cy - 120, 240, 240, 200)
    _fill(buf, WIDTH, cx - 60 + shift_mid, cy - 60, 120, 120, 40)
    _fill(buf, WIDTH, cx + 220 + shift_near, cy + 80, 120, 160, 230)
    _fill(buf, WIDTH, cx + 250 + shift_near, cy + 110, 60, 100, 20)
    # eye marker: outer edge of the eye it belongs to
    mx = 0 if eye == 0 else WIDTH - 48
    _fill(buf, WIDTH, mx, HEIGHT // 2 - 150, 48, 300, 255)
    return buf


_BG: dict[int, bytes] = {}


def make_luma(seq: int, eye: int, camera: int) -> bytes:
    """One 1280x800 luma plane (bytes, stride = WIDTH)."""
    if eye not in _BG:
        _BG[eye] = bytes(_background(eye))
    buf = bytearray(_BG[eye])
    # moving bar: sweeps the width once every 128 frames
    bx = 64 + (seq * 9) % (WIDTH - 192)
    _fill(buf, WIDTH, bx, 120, 24, HEIGHT - 240, 250 if camera == 0 else 10)
    # barcode strip with a quiet zone
    bits = barcode_bits(seq, eye, camera)
    _fill(buf, WIDTH, BAR_X0 - QUIET, BAR_Y0 - QUIET,
          len(bits) * CELL + 2 * QUIET, CELL + 2 * QUIET, 0)
    for i, bit in enumerate(bits):
        _fill(buf, WIDTH, BAR_X0 + i * CELL, BAR_Y0, CELL, CELL, 255 if bit else 0)
    return bytes(buf)


def read_barcode(luma, stride: int = WIDTH) -> tuple[int, int, int] | None:
    """(seq, eye, camera) from a decoded luma plane, or None if the strip is
    unreadable or fails its check. Samples a 4x4 patch at each cell centre."""
    mv = memoryview(luma)
    bits = []
    n = len(START) + N_DATA
    yc = BAR_Y0 + CELL // 2
    for i in range(n):
        xc = BAR_X0 + i * CELL + CELL // 2
        total = 0
        for dy in (-2, -1, 0, 1):
            o = (yc + dy) * stride + xc - 2
            total += sum(mv[o:o + 4])
        bits.append(1 if total >= 16 * 128 else 0)
    if tuple(bits[:len(START)]) != START:
        return None
    data = bits[len(START):]
    word = sum(b << i for i, b in enumerate(data))
    payload = word & ((1 << 34) - 1)
    if word >> 34 != _check6(payload):
        return None
    return payload & 0xFFFFFFFF, (payload >> 32) & 1, (payload >> 33) & 1
