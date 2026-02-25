import sys, os
from PIL import Image
import numpy as np

if len(sys.argv) < 2:
    print('Usage: debug_jpeg_pipeline.py <jpg_path> [exposure(g stops)>]')
    sys.exit(2)

jpg = sys.argv[1]
exp = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
gamma = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

im = Image.open(jpg).convert('RGB')
arr = np.asarray(im)
print('loaded', jpg, 'shape', arr.shape, 'dtype', arr.dtype)
print('min,max,mean', arr.min(), arr.max(), float(arr.mean()))

# simulate pipeline from gui.main_window

def srgb_to_linear(u):
    u = u.astype(np.float32) / 255.0
    out = np.empty_like(u, dtype=np.float32)
    mask = u <= 0.04045
    out[mask] = u[mask] / 12.92
    out[~mask] = ((np.clip(u[~mask], 0.0, 1.0) + 0.055) / 1.055) ** 2.4
    return out

lin = srgb_to_linear(arr)
print('lin min,max,mean', lin.min(), lin.max(), float(lin.mean()))
# apply exposure
gain = float(pow(2.0, exp))
lin2 = np.clip(lin * gain, 0.0, 1.0)
print('after gain min,max,mean', lin2.min(), lin2.max(), float(lin2.mean()))
# apply gamma display
if abs(gamma - 1.0) > 1e-6:
    disp = np.clip(lin2, 0.0, 1.0) ** (1.0 / gamma)
else:
    disp = lin2
print('after gamma min,max,mean', disp.min(), disp.max(), float(disp.mean()))

out = np.clip(disp * 255.0 + 0.5, 0, 255).astype(np.uint8)

out_path = os.path.join(os.path.dirname(jpg), 'debug_out.png')
Image.fromarray(out).save(out_path)
print('wrote', out_path)

# print a few pixel samples
h,w = out.shape[:2]
for y in (h//4, h//2, (3*h)//4):
    print('row', y, out[y, w//2, :])

