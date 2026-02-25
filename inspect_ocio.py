
import os
import OpenImageIO as oiio

# Detect config
cfg_path = os.environ.get('OCIO')
print(f"OCIO Path: {cfg_path}")

if not cfg_path or not os.path.exists(cfg_path):
    print("No OCIO config found in env.")
    # Try a common one or bundled if any
    pass

try:
    # OIIO doesn't explicitly expose OCIO Config object easily in python
    # But we can list colorspaces via ColorConfig
    config = oiio.ColorConfig(cfg_path)
    print(f"Config Name: {config.getConfigname()}")
    print("\n--- ColorSpaces ---")
    for i in range(config.getNumColorSpaces()):
        print(config.getColorSpaceNameByIndex(i))
        
    print("\n--- Displays/Views ---")
    # OIIO Python bindings for ColorConfig might be limited
    # Let's check what we have
    print(dir(config))
    
    # Try using PyOpenColorIO if available for more detail
    import PyOpenColorIO as ocio
    cfg = ocio.Config.CreateFromFile(cfg_path)
    print("\n--- OCIO Native Views ---")
    displays = cfg.getDisplays()
    for disp in displays:
        print(f"Display: {disp}")
        for view in cfg.getViews(disp):
            print(f"  - View: {view}")
            
except Exception as e:
    print(f"Error: {e}")
