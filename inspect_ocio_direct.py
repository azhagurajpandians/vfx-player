
import os
try:
    import PyOpenColorIO as ocio
except ImportError:
    print("PyOpenColorIO not found")
    exit()

cfg_path = os.environ.get('OCIO')
print(f"OCIO Path: {cfg_path}")

try:
    if cfg_path and os.path.exists(cfg_path):
        config = ocio.Config.CreateFromFile(cfg_path)
    else:
        print("Using default config")
        config = ocio.GetCurrentConfig()

    print(f"\nConfig: {config.getDescription()}")
    
    print("\n--- Displays ---")
    displays = config.getDisplays()
    for disp in displays:
        print(f"Display: {disp}")
        views = config.getViews(disp)
        for view in views:
            cs = config.getDisplayViewColorSpaceName(disp, view)
            print(f"  - View: {view} -> ColorSpace: {cs}")

except Exception as e:
    print(f"Error: {e}")
