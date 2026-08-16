# West End Sentinel — the mark

Source for the third demonstration publisher's identity. SVG rather than PNG so
it can be regenerated at any size; the site itself carries rendered PNGs.

| File | Where it is used |
|---|---|
| `wesmc-logo.svg` | The mark on a light ground. Not currently on the site. |
| `wesmc-logo-light.svg` | Reversed, for the site's dark header. **This is the one in use.** |
| `wesmc-icon.svg` | The lantern alone, square, as the browser-tab icon. |

## Why a lantern

A sentinel is a watchman, and this one stands in Boston. The mark is geometric
rather than illustrative so it survives at 24 pixels in a browser tab, and the
flame is the only warm colour in it — on either ground, it is the thing the eye
lands on first.

## Why there are two versions

The first was drawn in ink navy and installed on a dark Divi header, where it
was very nearly invisible. A mark needs to be designed against the ground it
will actually sit on, which is worth remembering before drawing the next one.

## Regenerating the PNGs

There is no SVG rasteriser assumed on the machine, so the renders were taken
with headless Chrome against a transparent background, at 2x, then reduced:

```
chrome --headless --default-background-color=00000000 \
       --window-size=1960,480 --screenshot=out.png file://render.html
sips -Z 980 out.png --out logo.png
```
