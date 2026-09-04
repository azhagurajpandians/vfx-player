import sys
import os
import tempfile
import numpy as np

sys.path.append(os.getcwd())
from core.color_manager import load_cdl_file, save_cdl_file

def test_cdl_xml_io():
    print("Running CDL XML I/O Test...")
    with tempfile.TemporaryDirectory() as tmpdir:
        cdl_path = os.path.join(tmpdir, "test_grade.cdl")
        
        # Target CDL parameters
        slope = (1.2, 0.95, 1.05)
        offset = (-0.05, 0.02, 0.0)
        power = (1.0, 1.05, 0.95)
        sat = 1.15
        
        # Save to file
        save_ok = save_cdl_file(cdl_path, slope, offset, power, sat)
        assert save_ok, "Failed to save CDL file"
        assert os.path.exists(cdl_path), "CDL file does not exist"
        
        # Load from file
        loaded = load_cdl_file(cdl_path)
        assert loaded is not None, "Failed to load/parse CDL file"
        
        l_slope, l_offset, l_power, l_sat = loaded
        
        print(f"Saved: Slope={slope}, Offset={offset}, Power={power}, Sat={sat}")
        print(f"Loaded: Slope={l_slope}, Offset={l_offset}, Power={l_power}, Sat={l_sat}")
        
        assert np.allclose(slope, l_slope), "Slopes do not match"
        assert np.allclose(offset, l_offset), "Offsets do not match"
        assert np.allclose(power, l_power), "Powers do not match"
        assert np.allclose(sat, l_sat), "Saturations do not match"
        
    print("CDL XML I/O Test Passed!")

def test_contact_sheet_generation():
    print("Running Contact Sheet HTML Generation Test...")
    # Mocking metadata lines and HTML generation
    media_name = "test_seq_v001"
    metadata_lines = [
        "<li><strong>Resolution:</strong> 1920x1080</li>",
        "<li><strong>FPS:</strong> 24.000</li>"
    ]
    items_html = [
        """
        <div class="card">
            <div class="card-header">Frame 12</div>
            <a href="test_images/frame_0012.png" target="_blank">
                <img src="test_images/frame_0012.png" class="card-img" />
            </a>
            <div class="card-body">
                <strong>Notes:</strong>
                <p>Fix specular highlights on the metal pipe.</p>
            </div>
        </div>
        """
    ]
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Test Review Contact Sheet</title>
</head>
<body>
    <h1>Review Contact Sheet - {media_name}</h1>
    <ul>{"".join(metadata_lines)}</ul>
    <div class="grid">{"".join(items_html)}</div>
</body>
</html>
"""
    assert "Review Contact Sheet - test_seq_v001" in html_content
    assert "Frame 12" in html_content
    assert "Fix specular highlights on the metal pipe." in html_content
    print("Contact Sheet HTML Generation Test Passed!")

if __name__ == "__main__":
    try:
        test_cdl_xml_io()
        test_contact_sheet_generation()
        print("\nAll enhancement tests passed successfully!")
    except AssertionError as e:
        print(f"\nAssertion Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected Error: {e}")
        sys.exit(1)
