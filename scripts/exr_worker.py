import sys
import os
import numpy as np

def main():
    if len(sys.argv) < 3:
        print('Usage: exr_worker.py <in_path> <out_npy>')
        return 2
    in_path = sys.argv[1]
    out_npy = sys.argv[2]
    try:
        # Read EXR/image into numpy (prefer imageio.v3)
        arr = None
        try:
            import imageio.v3 as iio
            arr = iio.imread(in_path)
            arr = np.asarray(arr)
        except Exception:
            # Fallback to OpenEXR
            import OpenEXR, Imath
            exr = OpenEXR.InputFile(in_path)
            hdr = exr.header()
            dw = hdr['dataWindow']
            w = dw.max.x - dw.min.x + 1
            h = dw.max.y - dw.min.y + 1
            pt = Imath.PixelType(Imath.PixelType.FLOAT)
            ch_names = ['R','G','B']
            avail = list(hdr['channels'].keys())
            chs = [c for c in ch_names if c in avail]
            if not chs:
                chs = avail[:3]
            data = []
            for c in chs:
                raw = exr.channel(c, pt)
                try:
                    buf = bytes(raw)
                except Exception:
                    if isinstance(raw, str):
                        buf = raw.encode('latin1')
                    else:
                        buf = bytes(bytearray(raw))
                a = np.frombuffer(buf, dtype=np.float32).copy()
                data.append(a)
            img = np.stack(data, axis=-1).reshape(h, w, len(chs))
            arr = img

        # Ensure arr is uint8 RGB for PNG encoding
        if arr.dtype.kind == 'f':
            # assume linear float in [0,1]
            a8 = np.clip(arr, 0.0, 1.0)
            a8 = (a8 * 255.0 + 0.5).astype(np.uint8)
        else:
            a8 = arr.astype(np.uint8)

        # If grayscale, expand
        if a8.ndim == 2:
            a8 = np.repeat(a8[:, :, None], 3, axis=2)
        if a8.shape[2] > 3:
            a8 = a8[:, :, :3]

        # Write PNG bytes: prefer Pillow for robust PNG encoding
        try:
            from PIL import Image
            im = Image.fromarray(a8)
            if out_npy == '-':
                from io import BytesIO
                buf = BytesIO()
                im.save(buf, format='PNG')
                sys.stdout.buffer.write(buf.getvalue())
            else:
                im.save(out_npy, format='PNG')
        except Exception:
            try:
                import imageio.v3 as iio
                if out_npy == '-':
                    from io import BytesIO
                    buf = BytesIO()
                    iio.imwrite(buf, a8, format='PNG')
                    sys.stdout.buffer.write(buf.getvalue())
                else:
                    iio.imwrite(out_npy, a8)
            except Exception:
                # As last resort, write raw bytes (not ideal)
                if out_npy == '-':
                    sys.stdout.buffer.write(a8.tobytes())
                else:
                    with open(out_npy, 'wb') as f:
                        f.write(a8.tobytes())
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            with open(out_npy + '.err', 'w', encoding='utf-8') as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        return 1

if __name__ == '__main__':
    sys.exit(main())
