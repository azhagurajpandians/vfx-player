
import sys
import os
import numpy as np

# Mocking some dependencies to test logic in isolation if needed, 
# but let's see if we can just import and test ColorManager since it has no GUI deps.

sys.path.append(os.getcwd())
from core.color_manager import ColorManager

def test_color_manager_processing():
    cm = ColorManager()
    # Create a simple 10x10 grey frame
    frame = np.full((10, 10, 3), 0.5, dtype=np.float32)
    
    # Test exposure
    exposed = cm.process(frame, exposure=1.0) # Should double to 1.0
    print(f"Exposure 1.0 test: {exposed[0,0,0]} (expected ~1.0)")
    assert np.allclose(exposed[0,0,0], 1.0)
    
    # Test gamma
    gamma_corrected = cm.process(frame, gamma=2.0) # Should be 0.5^(1/2) = 0.707
    print(f"Gamma 2.0 test: {gamma_corrected[0,0,0]:.3f} (expected ~0.707)")
    assert np.allclose(gamma_corrected[0,0,0], 0.707, atol=0.01)
    
    # Test channels
    red_only = cm.process(frame, channel='R')
    print(f"Channel R test shape: {red_only.shape}")
    assert red_only.shape == (10, 10, 3)
    
    print("ColorManager tests passed!")

if __name__ == "__main__":
    try:
        test_color_manager_processing()
    except Exception as e:
        print(f"Tests failed: {e}")
        sys.exit(1)
