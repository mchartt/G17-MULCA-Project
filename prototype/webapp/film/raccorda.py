"""raccorda.py: fix the geometric jolt at each join of chained Higgsfield clips.

Higgsfield slightly rescales the uploaded start image (about +2 % vertically), so the first frame
of clip N+1 is a warped copy of the last frame of clip N. We estimate that affine warp W with ECC
and apply it to the tail of clip N progressively (identity -> W over RAMP frames), so the camera
'arrives' exactly at the geometry of the next clip. No dissolve: every output frame is a real frame,
only resampled.
"""
import sys, cv2, numpy as np, subprocess
RAMP = 24  # one second at 24 fps

def frames(path):
    cap = cv2.VideoCapture(path); out = []
    while True:
        ok, f = cap.read()
        if not ok: break
        out.append(f)
    return out

def estimate(last, first):
    a = cv2.GaussianBlur(cv2.cvtColor(last, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 2)
    b = cv2.GaussianBlur(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 2)
    W = np.eye(2, 3, dtype=np.float32)
    cc, W = cv2.findTransformECC(b, a, W, cv2.MOTION_AFFINE,
                                 (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-7), None, 5)
    return cc, W

def write(path, fr):
    h, w = fr[0].shape[:2]
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}',
                          '-r', '24', '-i', '-', '-c:v', 'libx264', '-crf', '12', '-preset', 'slow',
                          '-pix_fmt', 'yuv420p', path], stdin=subprocess.PIPE)
    for f in fr: p.stdin.write(f.tobytes())
    p.stdin.close(); p.wait()

clips = sys.argv[1:]
data = [frames(c) for c in clips]
ident = np.eye(2, 3, dtype=np.float32)
for i in range(len(data) - 1):
    cc, W = estimate(data[i][-1], data[i + 1][0])
    h, w = data[i][-1].shape[:2]
    def diff(x, y): return np.abs(x.astype(float) - y.astype(float)).mean()
    before = diff(data[i][-1], data[i + 1][0])
    n = min(RAMP, len(data[i]))
    for k in range(n):
        t = (k + 1) / n
        t = t * t * (3 - 2 * t)  # smoothstep
        M = (1 - t) * ident + t * W
        idx = len(data[i]) - n + k
        data[i][idx] = cv2.warpAffine(data[i][idx], M, (w, h), flags=cv2.INTER_CUBIC + cv2.WARP_INVERSE_MAP,
                                      borderMode=cv2.BORDER_REPLICATE)
    after = diff(data[i][-1], data[i + 1][0])
    print(f'join {i+1}->{i+2}: ECC {cc:.4f}, scale x {W[0,0]:.4f} y {W[1,1]:.4f}, shift {W[0,2]:.1f},{W[1,2]:.1f} px; '
          f'mean abs diff {before:.2f} -> {after:.2f}')
for c, fr in zip(clips, data):
    write(c.replace('.mp4', '-raccordata.mp4'), fr)
