import json, re, sys
import numpy as np
sys.path.insert(0, r'cloudsc_variants/autoconversion_snow')
import run_autoconversion_snow as mod
mod.HERE = r'cloudsc_variants/autoconversion_snow/vec_reports/fortran/autoconversion_snow/clang_apple_m_series_default'
import inspect as _inspect
_result = mod.make_inputs()
_nparams = len(_inspect.signature(mod.run_original_fortran).parameters)
if _nparams >= 2:
    _consts, _arrays = _result
    def _call(): mod.run_original_fortran(_consts, _arrays)
else:
    _arrays = _result
    def _call(): mod.run_original_fortran(_arrays)
warmup = 100
repeats = 200
for _ in range(warmup):
    _call()
for _ in range(repeats):
    _call()
# Sentinel so the parent knows the runs finished
print('__FORTRAN_DONE__')
