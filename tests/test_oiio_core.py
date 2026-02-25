import os
import sys
import time
import numpy as np
import OpenImageIO as oiio

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.player_core import PlayerCore

def create_test_exr(path):
    # Use TypeFloat directly if available, or TypeDesc(FLOAT)
    try:
        td = oiio.TypeFloat
    except AttributeError:
        td = oiio.TypeDesc(oiio.FLOAT)
        
    spec = oiio.ImageSpec(100, 50, 3, td)
    out = oiio.ImageOutput.create(path)
    if not out:
        print(f"Could not create output at {path}")
        return False
    out.open(path, spec)
    # Create a gradient
    pixels = np.zeros((50, 100, 3), dtype=np.float32)
    for y in range(50):
        for x in range(100):
            pixels[y, x, 0] = x / 100.0
            pixels[y, x, 1] = y / 50.0
            pixels[y, x, 2] = 0.5
    out.write_image(pixels)
    out.close()
    return True

def test_loading():
    print("Setting up test...")
    test_dir = os.path.join(os.path.dirname(__file__), 'test_seq')
    os.makedirs(test_dir, exist_ok=True)
    
    seq_path = os.path.join(test_dir, 'test.0001.exr')
    if not create_test_exr(seq_path):
        print("Failed to create test EXR")
        return

    print("Initializing PlayerCore...")
    core = PlayerCore(cache_capacity=10)
    print(f"Loading sequence: {seq_path}")
    core.load(seq_path)
    
    print(f"Frame count: {core.frame_count()}")
    if core.frame_count() == 0:
        print("Error: No frames loaded")
        return

    print("Requesting frame 0...")
    # It's async, so we loop wait
    for i in range(20):
        frame = core.get_frame(0)
        if frame is not None:
            print("Frame 0 loaded successfully!")
            print(f"Shape: {frame.shape}, Dtype: {frame.dtype}")
            print(f"Mean: {np.mean(frame)}")
            break
        print("Waiting for loader...")
        time.sleep(0.1)
    else:
        print("Timeout waiting for frame 0")

    # Cleanup
    try:
        core.loader.stop()
        import shutil
        shutil.rmtree(test_dir)
    except:
        pass

if __name__ == "__main__":
    test_loading()
