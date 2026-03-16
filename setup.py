import glob
import os
import platform
import struct

import numpy as np
try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup
    from distutils.core import Extension


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_sys = platform.system()
_machine = platform.machine()

if _sys == 'Linux':
    _lib_subdir = 'linux'
    _intel_fortran_libs = ['ifcore', 'imf', 'iomp5', 'irc', 'svml']
elif _sys == 'Darwin':
    # PHaRLAP 4.7.4 ships two macOS variants:
    #   maca — Apple Silicon (arm64)
    #   maci — Intel (x86_64)
    # The maca/maci static libs were compiled with GCC/gfortran and require
    # the gfortran runtime (__gfortran_* symbols).  No Intel Fortran needed.
    _lib_subdir = 'maca' if _machine == 'arm64' else 'maci'
    _intel_fortran_libs = []  # not needed
    # Locate Homebrew gfortran runtime (required for __gfortran_* symbols).
    import subprocess, shutil
    _gfc = shutil.which('gfortran')
    if _gfc:
        _gfc_libdir = subprocess.check_output(
            [_gfc, '-print-file-name=libgfortran.dylib'],
            text=True
        ).strip()
        _gfc_libdir = os.path.dirname(_gfc_libdir)
    else:
        _gfc_libdir = '/opt/homebrew/lib/gcc/current'
    _extra_darwin_lib_dirs = [_gfc_libdir]
    _extra_darwin_libs = ['gfortran', 'gomp']
else:
    raise OSError(f'Unsupported operating system: {_sys}')

_extra_lib_dirs  = _extra_darwin_lib_dirs if _sys == 'Darwin' else []
_extra_libs      = _extra_darwin_libs     if _sys == 'Darwin' else []

# ---------------------------------------------------------------------------
# Locate PHaRLAP
# ---------------------------------------------------------------------------
if 'PHARLAP_HOME' not in os.environ:
    raise OSError('Set PHARLAP_HOME to the PHaRLAP install directory before building.')

pharlap_path = os.environ['PHARLAP_HOME']
if not os.path.isdir(pharlap_path):
    raise OSError(f'PHARLAP_HOME does not exist: {pharlap_path}')

pharlap_include_path = os.path.join(pharlap_path, 'src', 'C')
pharlap_lib_path = os.path.join(pharlap_path, 'lib', _lib_subdir)

if not os.path.isdir(pharlap_lib_path):
    raise OSError(f'PHaRLAP library path not found: {pharlap_lib_path}')

# On Linux the Intel Fortran redistributable path is still required.
intel_lib_dirs = []
if _sys == 'Linux':
    if 'LD_LIBRARY' not in os.environ:
        raise OSError('Set LD_LIBRARY to the Intel Fortran redistributable lib dir on Linux.')
    intel_path = os.environ['LD_LIBRARY']
    if not os.path.isdir(intel_path):
        raise OSError(f'LD_LIBRARY does not exist: {intel_path}')
    intel_lib_dirs = [intel_path]

# PHaRLAP 4.7.4 ships libiri2020 (consolidated; replaces iri2007/2012/2016).
# Modules that needed legacy IRI versions are skipped when those libs are absent.
_available_libs = {
    os.path.splitext(f)[0].replace('lib', '')
    for f in os.listdir(pharlap_lib_path)
    if f.startswith('lib')
}

# ---------------------------------------------------------------------------
# Module definitions
# ---------------------------------------------------------------------------
native_modules = []
COMMON_GLOB = glob.glob('modules/source/common/*.c')


def _libs(*base):
    """Append Intel Fortran runtime libs on Linux; omit on macOS."""
    return list(base) + _intel_fortran_libs


def create_module(name, libraries):
    """Register a C-extension module if all required native libs are present."""
    missing = [lib for lib in libraries if lib not in _available_libs
               and lib not in _intel_fortran_libs
               and lib not in ('m',)]
    if missing:
        print(f'  SKIP  pylap.{name}  (missing PHaRLAP libs: {missing})')
        return
    src = os.path.join('modules', 'source', name + '.c')
    if not os.path.exists(src):
        print(f'  SKIP  pylap.{name}  (source not found: {src})')
        return
    native_modules.append(Extension(
        'pylap.' + name,
        sources=[src] + COMMON_GLOB,
        include_dirs=[np.get_include(), pharlap_include_path,
                      os.path.join('modules', 'include')],
        library_dirs=[pharlap_lib_path] + intel_lib_dirs + _extra_lib_dirs,
        libraries=libraries + _extra_libs,
    ))
    print(f'  BUILD pylap.{name}')


# PHaRLAP 4.7.4: IRI consolidated into iri2020.  Modules that required
# the legacy iri2007/iri2012/iri2016 archives are updated accordingly;
# those that only existed as thin wrappers for the legacy models are skipped.
print(f'\nConfiguring pyLAP for PHaRLAP on {_sys}/{_machine} (lib/{_lib_subdir})\n')

create_module('abso_bg',       _libs('propagation', 'maths', 'iri2020'))
create_module('dop_spread_eq', _libs('propagation', 'iri2020'))
create_module('ground_bs_loss',_libs('propagation'))
create_module('ground_fs_loss',_libs('propagation'))
# igrf2007/igrf2011 need legacy iri2007/iri2012 — skipped on PHaRLAP 4.7.4
create_module('igrf2007',      _libs('maths', 'iri2007'))
create_module('igrf2011',      _libs('maths', 'iri2012'))
create_module('igrf2016',      _libs('maths', 'iri2020'))
# Standalone IRI wrappers — skipped for legacy versions not in 4.7.4
create_module('iri2007',       _libs('iri2007'))
create_module('iri2012',       _libs('iri2012'))
create_module('iri2016',       _libs('iri2020'))
create_module('irreg_strength',_libs('propagation', 'iri2020'))
create_module('nrlmsise00',    _libs('maths', 'iri2020'))
create_module('raytrace_2d',   _libs('propagation', 'maths'))
create_module('raytrace_2d_sp',_libs('propagation', 'maths'))
create_module('raytrace_3d',   _libs('propagation', 'maths'))
create_module('raytrace_3d_sp',_libs('propagation', 'maths'))

print()

setup(
    name='pylap',
    version='0.1.0-alpha',
    description='A numpy-compatible Python 3 wrapper for the PHaRLAP ionospheric raytracer',
    packages=['pylap'],
    package_dir={'pylap': 'modules/pylap'},
    ext_modules=native_modules,
)
