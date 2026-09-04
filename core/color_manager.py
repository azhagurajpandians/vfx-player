import os
import numpy as np
try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None

class ColorManager:
    """
    """
    def __init__(self, config_path: str = None):
        self.ocio_enabled = True
        self.config = None
        self.processor = None
        self.input_cs = None
        self.output_cs = None
        self.colorspaces = []
        self.input_choices = []
        self.output_choices = []
        self.view_choices = []
        # Prioritize passed path, then env
        self.config_path = config_path
        
        self._init_ocio()

    def _init_ocio(self):
        import sys
        cfg_path = self.config_path or os.environ.get('OCIO_CONFIG_PATH') or os.environ.get('OCIO')
        if not cfg_path or not os.path.isfile(cfg_path):
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = here

            candidates = [
                os.path.join(app_dir, 'configs', 'ocio', 'OpenColorIOConfigs', 'aces_1.2', 'config.ocio'),
                os.path.join(app_dir, 'configs', 'ocio', 'config.ocio'),
                os.path.join(app_dir, 'ocio', 'OpenColorIOConfigs', 'aces_1.2', 'config.ocio'),
                os.path.join(app_dir, 'ocio', 'config.ocio'),
                os.path.join(app_dir, '.knacktools', 'ocioconfig', 'OpenColorIOConfigs', 'aces_1.2', 'config.ocio'),
                os.path.join(here, 'configs', 'ocio', 'OpenColorIOConfigs', 'aces_1.2', 'config.ocio'),
                os.path.join(here, 'configs', 'ocio', 'config.ocio'),
            ]
            home = os.path.expanduser('~')
            for root in [home, 'C:\\', 'D:\\', 'E:\\']:
                candidates.append(os.path.join(root, '.knacktools', 'ocioconfig', 'OpenColorIOConfigs', 'aces_1.2', 'config.ocio'))

            for c in candidates:
                if os.path.isfile(c):
                    cfg_path = c
                    break
            else:
                return

        ocio_mod = None
        for name in ('PyOpenColorIO', 'OpenColorIO'):
            try:
                ocio_mod = __import__(name)
                break
            except ImportError:
                continue
        if ocio_mod is None:
            return
            
        try:
            self.config = ocio_mod.Config.CreateFromFile(cfg_path)
            self.config_path = cfg_path
            self.colorspaces = list(self.config.getColorSpaceNames())
            
            self.displays = {}
            try:
                if ocio_mod and hasattr(ocio_mod, 'Config'):
                     active_displays = self.config.getActiveDisplays()
                     if not active_displays:
                         active_displays = self.config.getDisplays()
                     for disp in active_displays:
                         views = self.config.getViews(disp)
                         self.displays[disp] = list(views)
            except Exception:
                pass
            
            for name in self.colorspaces:
                lname = name.lower()
                if any(k in lname for k in ('acescg','scene_linear','linear','lin_srgb', 'srgb', 'rec', '709', 'output', 'utility')):
                    self.input_choices.append(name)
            
            self.view_choices = []
            if self.displays:
                for disp in self.displays:
                    for view in self.displays[disp]:
                        label = f"{view} ({disp})"
                        self.view_choices.append(label)

            self.output_choices = []
            for name in self.colorspaces:
                lname = name.lower()
                if any(k in lname for k in ('output', 'utility', 'srgb','rec','709','display','video')):
                    self.output_choices.append(name)
            
            if not self.input_choices and self.colorspaces: self.input_choices = self.colorspaces[:]
            if not self.output_choices and self.colorspaces: self.output_choices = self.colorspaces[:]
            
            self.input_cs = self.input_choices[0] if self.input_choices else None
            self.output_cs = self.output_choices[0] if self.output_choices else None
            
            self.rebuild_processor()
        except Exception:
            pass

    def rebuild_processor(self):
        if not self.ocio_enabled or not (self.config and self.input_cs and self.output_cs):
            self.processor = None
            return
        try:
            self.processor = self.config.getProcessor(self.input_cs, self.output_cs)
        except Exception:
            self.processor = None

    def process(self, arr: np.ndarray, exposure: float = 0.0, gamma: float = 1.0, channel: str = 'RGB') -> np.ndarray:
        """
        Applies exposure, gamma, and channel selection.
        Input: float32 from cache (already OCIO processed).
        Output: float32 [0, 1] ready for display.
        """
        if arr is None:
            return None

        # 1. Work with float32 0-1
        if arr.dtype == np.uint8:
            disp = arr.astype(np.float32) * (1.0 / 255.0)
        elif arr.dtype != np.float32:
            disp = arr.astype(np.float32)
        else:
            # Only copy if we actually need to modify the data
            if exposure != 0.0 or gamma != 1.0 or channel != 'RGB':
                disp = arr.copy()
            else:
                disp = arr

        # 2. Channel Isolation
        if channel != 'RGB':
            if channel == 'R' and disp.shape[2] >= 1:
                disp = np.stack([disp[:,:,0]]*3, axis=-1)
            elif channel == 'G' and disp.shape[2] >= 2:
                disp = np.stack([disp[:,:,1]]*3, axis=-1)
            elif channel == 'B' and disp.shape[2] >= 3:
                disp = np.stack([disp[:,:,2]]*3, axis=-1)
            elif channel == 'A':
                if disp.shape[2] >= 4:
                    disp = np.stack([disp[:,:,3]]*3, axis=-1)
                else:
                    return np.ones((disp.shape[0], disp.shape[1], 3), dtype=np.float32)
        elif disp.shape[2] >= 4:
            # If we didn't copy above, we must copy now because slice modifies in-place later
            if disp.base is arr or disp is arr:
                disp = disp[:,:,:3].copy()
            else:
                disp = disp[:,:,:3]

        # 3. Apply Adjustments
        # Exposure (Gain = 2^stops)
        if exposure != 0.0:
            disp *= pow(2.0, exposure)

        # Gamma (pow(x, 1/gamma))
        if gamma != 1.0 and abs(gamma) > 0.01:
            # Clip to 0 to avoid NaNs in power
            np.clip(disp, 0.0, None, out=disp)
            np.power(disp, 1.0 / gamma, out=disp)

        # 4. Final Clamp for display
        return np.clip(disp, 0.0, 1.0)

    def get_colorspace_from_label(self, label: str) -> str:
        if not label or '(' not in label or ')' not in label:
            return label
        try:
            view = label.split(' (')[0]
            display = label.split(' (')[1].rstrip(')')
            if self.config:
                return self.config.getDisplayViewColorSpaceName(display, view)
        except Exception:
            pass
        return label

    def get_resolved_output_cs(self) -> str:
        """Get the resolved output colorspace name for background workers."""
        if self.output_cs:
            return self.get_colorspace_from_label(self.output_cs)
        return self.output_cs or ""

import xml.etree.ElementTree as ET

def load_cdl_file(path: str) -> tuple[tuple[float,float,float], tuple[float,float,float], tuple[float,float,float], float] | None:
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        ns = {}
        if '}' in root.tag:
            ns_url = root.tag.split('}')[0].strip('{')
            ns = {'cdl': ns_url}
            
        def find_element(name):
            if ns:
                elem = root.find(f".//cdl:{name}", ns)
                if elem is not None:
                    return elem
            return root.find(f".//{name}")
            
        slope_elem = find_element("Slope")
        offset_elem = find_element("Offset")
        power_elem = find_element("Power")
        sat_elem = find_element("Saturation")
        
        slope = (1.0, 1.0, 1.0)
        offset = (0.0, 0.0, 0.0)
        power = (1.0, 1.0, 1.0)
        sat = 1.0
        
        if slope_elem is not None and slope_elem.text:
            parts = [float(x) for x in slope_elem.text.strip().split()]
            if len(parts) == 3: slope = tuple(parts)
        if offset_elem is not None and offset_elem.text:
            parts = [float(x) for x in offset_elem.text.strip().split()]
            if len(parts) == 3: offset = tuple(parts)
        if power_elem is not None and power_elem.text:
            parts = [float(x) for x in power_elem.text.strip().split()]
            if len(parts) == 3: power = tuple(parts)
        if sat_elem is not None and sat_elem.text:
            sat = float(sat_elem.text.strip())
            
        return slope, offset, power, sat
    except Exception as e:
        print(f"Error reading CDL file {path}: {e}")
        return None

def save_cdl_file(path: str, slope: tuple, offset: tuple, power: tuple, sat: float) -> bool:
    try:
        root = ET.Element("ColorDecisionList", xmlns="urn:ASC:CDL:v1.01")
        cd = ET.SubElement(root, "ColorDecision")
        cc = ET.SubElement(cd, "ColorCorrection", id="vfx_player_grade")
        
        sop = ET.SubElement(cc, "SOPNode")
        s = ET.SubElement(sop, "Slope")
        s.text = f"{slope[0]:.6f} {slope[1]:.6f} {slope[2]:.6f}"
        o = ET.SubElement(sop, "Offset")
        o.text = f"{offset[0]:.6f} {offset[1]:.6f} {offset[2]:.6f}"
        p = ET.SubElement(sop, "Power")
        p.text = f"{power[0]:.6f} {power[1]:.6f} {power[2]:.6f}"
        
        sat_node = ET.SubElement(cc, "SatNode")
        sa = ET.SubElement(sat_node, "Saturation")
        sa.text = f"{sat:.6f}"
        
        tree = ET.ElementTree(root)
        try:
            ET.indent(tree, space="    ", level=0)
        except Exception:
            pass
        tree.write(path, encoding="utf-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error saving CDL file {path}: {e}")
        return False
