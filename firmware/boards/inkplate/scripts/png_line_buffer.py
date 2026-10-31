"""Sets PNGdec's line buffer for the whole build, so a project need not know of it.

PNGdec holds two lines, each aligned to 16 bytes. Its default is too small for
the 1280 pixels of the Inkplate 5 V2, and then a page decodes wrong with no error.
The value changes the size of a PNGdec struct, so every library must see the same
one. PlatformIO creates the libraries in folder order, each with a copy of the
build's environment: so this sets the libraries created before this one, this
one, and the build's environment for those to come.
"""
Import("env")

from SCons.Script import DefaultEnvironment

# The widest Inkplate, at two lines and their alignment. A wider page draws the
# library's slower way: see pngLinesFit.
LINE_BUFFER_BYTES = 2640
NAME = "PNG_MAX_BUFFERED_PIXELS"


def is_set(environment):
    return any(d == NAME or (isinstance(d, (list, tuple)) and d[0] == NAME)
               for d in environment.get("CPPDEFINES", []))


build = DefaultEnvironment()
earlier = [builder.env for builder in build.get("__PIO_LIB_BUILDERS", [])]
for target in (build, env, *earlier):
    if not is_set(target):
        target.Append(CPPDEFINES=[(NAME, LINE_BUFFER_BYTES)])
