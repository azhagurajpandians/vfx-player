import OpenImageIO as oiio
print(f"oiio.FLOAT: {getattr(oiio, 'FLOAT', 'N/A')}")
print(f"oiio.STRING: {getattr(oiio, 'STRING', 'N/A')}")
print(f"oiio.INT: {getattr(oiio, 'INT', 'N/A')}")
print(f"oiio.TypeDesc attributes: {dir(oiio.TypeDesc)}")
