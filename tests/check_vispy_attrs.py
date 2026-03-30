
import sys
from vispy.scene import visuals
import numpy as np

def check_image_filters():
    try:
        img = visuals.Image(data=np.zeros((10, 10, 3)))
        print(f"Image has filters: {hasattr(img, 'filters')}")
        if not hasattr(img, 'filters'):
            print("Attributes of Image:", dir(img))
            if hasattr(img, '_visual'):
                print(f"Internal _visual has filters: {hasattr(img._visual, 'filters')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_image_filters()
