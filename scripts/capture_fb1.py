#!/usr/bin/env python3
"""
Capture /dev/fb1 (RGB565) to PNG for Fluid Ardule.
Saves rotated 180° image into /tmp with timestamp.
"""
from pathlib import Path
from datetime import datetime
from PIL import Image

FB="/dev/fb1"
SYS=Path("/sys/class/graphics/fb1")

def main():
    w,h=map(int,(SYS/"virtual_size").read_text().strip().split(","))
    bpp=int((SYS/"bits_per_pixel").read_text().strip())
    if bpp!=16:
        raise RuntimeError(f"Expected 16bpp RGB565, got {bpp}")
    size=w*h*2
    raw=Path(FB).read_bytes()[:size]
    if len(raw)!=size:
        raise RuntimeError("Framebuffer size mismatch")
    img=Image.new("RGB",(w,h))
    pix=img.load()
    p=0
    for y in range(h):
        for x in range(w):
            v=raw[p]|(raw[p+1]<<8); p+=2
            r=((v>>11)&0x1F)*255//31
            g=((v>>5)&0x3F)*255//63
            b=(v&0x1F)*255//31
            pix[x,y]=(r,g,b)
    img=img.rotate(180)
    out=Path("/tmp")/("fluidardule-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".png")
    img.save(out)
    print(out)

if __name__=="__main__":
    main()
