import os
import sys
import numpy as np
import OpenImageIO as oiio

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.player_core import PlayerCore

def create_test_exr_with_metadata(path):
    try:
        td = oiio.BASETYPE.FLOAT
    except AttributeError:
        # Fallback for older versions if needed
        td = oiio.FLOAT
        
    spec = oiio.ImageSpec(100, 50, 3, td)
    spec.attribute("compression", "piz")
    spec.attribute("comment", "Testing metadata extraction")
    spec.attribute("test_int", 42)
    spec.attribute("test_float", 3.14)
    
    out = oiio.ImageOutput.create(path)
    if not out:
        return False
    out.open(path, spec)
    pixels = np.zeros((50, 100, 3), dtype=np.float32)
    out.write_image(pixels)
    out.close()
    return True

def test_metadata_extraction():
    test_dir = os.path.join(os.path.dirname(__file__), 'test_metadata_seq')
    os.makedirs(test_dir, exist_ok=True)
    
    exr_path = os.path.join(test_dir, 'metadata_test.0001.exr')
    if not create_test_exr_with_metadata(exr_path):
        print("Failed to create test EXR")
        return False

    print(f"Loading sequence: {exr_path}")
    core = PlayerCore()
    core.load(exr_path)
    
    media = core.media
    if not media:
        print("Error: MediaInfo not populated")
        return False
    
    print(f"Resolution: {media.size}")
    print(f"Format: {media.format}")
    print(f"Codec: {media.codec}")
    print(f"Metadata: {media.metadata}")

    success = True
    if media.size != (100, 50):
        print(f"Resolution mismatch: expected (100, 50), got {media.size}")
        success = False
    
    if media.codec != "piz":
        print(f"Codec mismatch: expected piz, got {media.codec}")
        success = False
        
    if media.metadata.get("comment") != "Testing metadata extraction":
        print(f"Metadata mismatch: 'comment' expected 'Testing metadata extraction', got {media.metadata.get('comment')}")
        success = False

    if media.metadata.get("test_int") != 42:
        print(f"Metadata mismatch: 'test_int' expected 42, got {media.metadata.get('test_int')}")
        success = False

    # Cleanup
    try:
        core.loader.stop()
        import shutil
        shutil.rmtree(test_dir)
    except:
        pass
        
    return success

if __name__ == "__main__":
    if test_metadata_extraction():
        print("\nVerification SUCCESS")
        sys.exit(0)
    else:
        print("\nVerification FAILED")
        sys.exit(1)
