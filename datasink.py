"""DataSinks"""
import re
from pathlib import Path
from json import dumps
import numpy as np
import nibabel as nb
from nipype.interfaces.io import add_traits
from nipype.interfaces.base import (
    BaseInterfaceInputSpec, DynamicTraitedSpec, SimpleInterface, TraitedSpec,
    traits, Str, File, InputMultiObject, OutputMultiObject, isdefined
)
from niworkflows.utils.misc import splitext as _splitext, _copy_any


BIDS_NAME = re.compile(
    r'^(.*\/)?'
    '(?P<subject_id>(sub|tpl)-[a-zA-Z0-9]+)'
    '(_(?P<session_id>ses-[a-zA-Z0-9]+))?'
    '(_(?P<task_id>task-[a-zA-Z0-9]+))?'
    '(_(?P<acq_id>acq-[a-zA-Z0-9]+))?'
    '(_(?P<rec_id>rec-[a-zA-Z0-9]+))?'
    '(_(?P<run_id>run-[a-zA-Z0-9]+))?')


class DerivativesDataSinkInputSpec(DynamicTraitedSpec, BaseInterfaceInputSpec):
    base_directory = traits.Directory(
        desc='Path to the base directory for storing data.')
    check_hdr = traits.Bool(True, usedefault=True, desc='fix headers of NIfTI outputs')
    compress = traits.Bool(desc="force compression (True) or uncompression (False)"
                                " of the output file (default: same as input)")
    desc = Str('', usedefault=True, desc='Label for description field')
    extra_values = traits.List(Str)
    in_file = InputMultiObject(File(exists=True), mandatory=True,
                               desc='the object to be saved')
    keep_dtype = traits.Bool(False, usedefault=True, desc='keep datatype suffix')
    meta_dict = traits.DictStrAny(desc='an input dictionary containing metadata')
    source_file = File(exists=False, mandatory=True, desc='the input func file')
    space = Str('', usedefault=True, desc='Label for space field')
    suffix = Str('', usedefault=True, desc='suffix appended to source_file')


class DerivativesDataSinkOutputSpec(TraitedSpec):
    out_file = OutputMultiObject(File(exists=True, desc='written file path'))
    out_meta = OutputMultiObject(File(exists=True, desc='written JSON sidecar path'))
    compression = OutputMultiObject(
        traits.Bool, desc='whether ``in_file`` was compressed/uncompressed '
                          'or `it was copied directly.')
    fixed_hdr = traits.List(traits.Bool, desc='whether derivative header was fixed')


class DerivativesDataSink(SimpleInterface):
    """
    Saves the `in_file` into a BIDS-Derivatives folder provided
    by `base_directory`, given the input reference `source_file`.
    >>> import tempfile
    >>> tmpdir = Path(tempfile.mkdtemp())
    >>> tmpfile = tmpdir / 'a_temp_file.nii.gz'
    >>> tmpfile.open('w').close()  # "touch" the file
    >>> dsink = DerivativesDataSink(base_directory=str(tmpdir), check_hdr=False)
    >>> dsink.inputs.in_file = str(tmpfile)
    >>> dsink.inputs.source_file = bids_collect_data(
    ...     str(datadir / 'ds114'), '01', bids_validate=False)[0]['t1w'][0]
    >>> dsink.inputs.keep_dtype = True
    >>> dsink.inputs.suffix = 'desc-denoised'
    >>> res = dsink.run()
    >>> res.outputs.out_file  # doctest: +ELLIPSIS
    '.../niworkflows/sub-01/ses-retest/anat/sub-01_ses-retest_desc-denoised_T1w.nii.gz'
    >>> dsink = DerivativesDataSink(base_directory=str(tmpdir), check_hdr=False,
    ...                             allowed_entities=['from', 'to'], **{'from': 'orig'})
    >>> dsink.inputs.in_file = str(tmpfile)
    >>> dsink.inputs.to = 'native'
    >>> dsink.inputs.source_file = bids_collect_data(
    ...     str(datadir / 'ds114'), '01', bids_validate=False)[0]['t1w'][0]
    >>> dsink.inputs.keep_dtype = True
    >>> res = dsink.run()
    >>> res.outputs.out_file  # doctest: +ELLIPSIS
    '.../sub-01_ses-retest_from-orig_to-native_T1w.nii.gz'
    >>> bids_dir = tmpdir / 'bidsroot' / 'sub-02' / 'ses-noanat' / 'func'
    >>> bids_dir.mkdir(parents=True, exist_ok=True)
    >>> tricky_source = bids_dir / 'sub-02_ses-noanat_task-rest_run-01_bold.nii.gz'
    >>> tricky_source.open('w').close()
    >>> dsink = DerivativesDataSink(base_directory=str(tmpdir), check_hdr=False)
    >>> dsink.inputs.in_file = str(tmpfile)
    >>> dsink.inputs.source_file = str(tricky_source)
    >>> dsink.inputs.keep_dtype = True
    >>> dsink.inputs.desc = 'preproc'
    >>> res = dsink.run()
    >>> res.outputs.out_file  # doctest: +ELLIPSIS
    '.../niworkflows/sub-02/ses-noanat/func/sub-02_ses-noanat_task-rest_run-01_\
desc-preproc_bold.nii.gz'
    >>> bids_dir = tmpdir / 'bidsroot' / 'sub-02' / 'ses-noanat' / 'func'
    >>> bids_dir.mkdir(parents=True, exist_ok=True)
    >>> tricky_source = bids_dir / 'sub-02_ses-noanat_task-rest_run-01_bold.nii.gz'
    >>> tricky_source.open('w').close()
    >>> dsink = DerivativesDataSink(base_directory=str(tmpdir), check_hdr=False)
    >>> dsink.inputs.in_file = str(tmpfile)
    >>> dsink.inputs.source_file = str(tricky_source)
    >>> dsink.inputs.keep_dtype = True
    >>> dsink.inputs.desc = 'preproc'
    >>> dsink.inputs.RepetitionTime = 0.75
    >>> res = dsink.run()
    >>> res.outputs.out_meta  # doctest: +ELLIPSIS
    '.../niworkflows/sub-02/ses-noanat/func/sub-02_ses-noanat_task-rest_run-01_\
desc-preproc_bold.json'
    >>> Path(res.outputs.out_meta).read_text().splitlines()[1]
    '  "RepetitionTime": 0.75'
    >>> bids_dir = tmpdir / 'bidsroot' / 'sub-02' / 'ses-noanat' / 'func'
    >>> bids_dir.mkdir(parents=True, exist_ok=True)
    >>> tricky_source = bids_dir / 'sub-02_ses-noanat_task-rest_run-01_bold.nii.gz'
    >>> tricky_source.open('w').close()
    >>> dsink = DerivativesDataSink(base_directory=str(tmpdir), check_hdr=False,
    ...                             SkullStripped=True)
    >>> dsink.inputs.in_file = str(tmpfile)
    >>> dsink.inputs.source_file = str(tricky_source)
    >>> dsink.inputs.keep_dtype = True
    >>> dsink.inputs.desc = 'preproc'
    >>> dsink.inputs.RepetitionTime = 0.75
    >>> res = dsink.run()
    >>> res.outputs.out_meta  # doctest: +ELLIPSIS
    '.../niworkflows/sub-02/ses-noanat/func/sub-02_ses-noanat_task-rest_run-01_\
desc-preproc_bold.json'
    >>> lines = Path(res.outputs.out_meta).read_text().splitlines()
    >>> lines[1]
    '  "RepetitionTime": 0.75,'
    >>> lines[2]
    '  "SkullStripped": true'
    >>> bids_dir = tmpdir / 'bidsroot' / 'sub-02' / 'ses-noanat' / 'func'
    >>> bids_dir.mkdir(parents=True, exist_ok=True)
    >>> tricky_source = bids_dir / 'sub-02_ses-noanat_task-rest_run-01_bold.nii.gz'
    >>> tricky_source.open('w').close()
    >>> dsink = DerivativesDataSink(base_directory=str(tmpdir), check_hdr=False,
    ...                             SkullStripped=True)
    >>> dsink.inputs.in_file = str(tmpfile)
    >>> dsink.inputs.source_file = str(tricky_source)
    >>> dsink.inputs.keep_dtype = True
    >>> dsink.inputs.desc = 'preproc'
    >>> dsink.inputs.RepetitionTime = 0.75
    >>> dsink.inputs.meta_dict = {'RepetitionTime': 1.75, 'SkullStripped': False, 'Z': 'val'}
    >>> res = dsink.run()
    >>> res.outputs.out_meta  # doctest: +ELLIPSIS
    '.../niworkflows/sub-02/ses-noanat/func/sub-02_ses-noanat_task-rest_run-01_\
desc-preproc_bold.json'
    >>> lines = Path(res.outputs.out_meta).read_text().splitlines()
    >>> lines[1]
    '  "RepetitionTime": 0.75,'
    >>> lines[2]
    '  "SkullStripped": true,'
    >>> lines[3]
    '  "Z": "val"'
    """
    input_spec = DerivativesDataSinkInputSpec
    output_spec = DerivativesDataSinkOutputSpec
    out_path_base = "templateflowreg"
    _always_run = True

    def __init__(self, allowed_entities=None, out_path_base=None, **inputs):
        self._allowed_entities = allowed_entities or []

        self._metadata = {}
        self._static_traits = self.input_spec.class_editable_traits() + self._allowed_entities
        for dynamic_input in set(inputs) - set(self._static_traits):
            self._metadata[dynamic_input] = inputs.pop(dynamic_input)

        super(DerivativesDataSink, self).__init__(**inputs)
        if self._allowed_entities:
            add_traits(self.inputs, self._allowed_entities)
            for k in set(self._allowed_entities).intersection(list(inputs.keys())):
                setattr(self.inputs, k, inputs[k])

        self._results['out_file'] = []
        if out_path_base:
            self.out_path_base = out_path_base

    def _run_interface(self, runtime):
        if isdefined(self.inputs.meta_dict):
            meta = self.inputs.meta_dict
            # inputs passed in construction take priority
            meta.update(self._metadata)
            self._metadata = meta

        src_fname, _ = _splitext(self.inputs.source_file)
        src_fname, dtype = src_fname.rsplit('_', 1)
        _, ext = _splitext(self.inputs.in_file[0])
        if self.inputs.compress is True and not ext.endswith('.gz'):
            ext += '.gz'
        elif self.inputs.compress is False and ext.endswith('.gz'):
            ext = ext[:-3]

        m = BIDS_NAME.search(src_fname)

        mod = Path(self.inputs.source_file).parent.name

        base_directory = runtime.cwd
        if isdefined(self.inputs.base_directory):
            base_directory = self.inputs.base_directory

        base_directory = Path(base_directory).resolve()
        out_path = base_directory / self.out_path_base / \
            '{subject_id}'.format(**m.groupdict())

        if m.groupdict().get('session_id') is not None:
            out_path = out_path / '{session_id}'.format(**m.groupdict())

        out_path = out_path / '{}'.format(mod)
        out_path.mkdir(exist_ok=True, parents=True)
        base_fname = str(out_path / src_fname)

        allowed_entities = {}
        for key in self._allowed_entities:
            value = getattr(self.inputs, key)
            if value is not None and isdefined(value):
                allowed_entities[key] = '_%s-%s' % (key, value)

        formatbase = '{bname}{space}{desc}' + ''.join(
            [allowed_entities.get(s, '') for s in self._allowed_entities])

        formatstr = formatbase + '{extra}{suffix}{dtype}{ext}'
        if len(self.inputs.in_file) > 1 and not isdefined(self.inputs.extra_values):
            formatstr = formatbase + '{suffix}{i:04d}{dtype}{ext}'

        space = '_space-{}'.format(self.inputs.space) if self.inputs.space else ''
        desc = '_desc-{}'.format(self.inputs.desc) if self.inputs.desc else ''
        suffix = '_{}'.format(self.inputs.suffix) if self.inputs.suffix else ''
        dtype = '' if not self.inputs.keep_dtype else ('_%s' % dtype)

        self._results['compression'] = []
        self._results['fixed_hdr'] = [False] * len(self.inputs.in_file)

        for i, fname in enumerate(self.inputs.in_file):
            extra = ''
            if isdefined(self.inputs.extra_values):
                extra = '_{}'.format(self.inputs.extra_values[i])
            out_file = formatstr.format(
                bname=base_fname,
                space=space,
                desc=desc,
                extra=extra,
                suffix=suffix,
                i=i,
                dtype=dtype,
                ext=ext,
            )
            self._results['out_file'].append(out_file)
            self._results['compression'].append(_copy_any(fname, out_file))

            is_nii = out_file.endswith('.nii') or out_file.endswith('.nii.gz')
            if self.inputs.check_hdr and is_nii:
                nii = nb.load(out_file)
                if not isinstance(nii, (nb.Nifti1Image, nb.Nifti2Image)):
                    # .dtseries.nii are CIfTI2, therefore skip check
                    return runtime
                hdr = nii.header.copy()
                curr_units = tuple([None if u == 'unknown' else u
                                    for u in hdr.get_xyzt_units()])
                curr_codes = (int(hdr['qform_code']), int(hdr['sform_code']))

                # Default to mm, use sec if data type is bold
                units = (curr_units[0] or 'mm', 'sec' if dtype == '_bold' else None)
                xcodes = (1, 1)  # Derivative in its original scanner space
                if self.inputs.space:
                    from templateflow.api import templates as _get_template_list
                    STANDARD_SPACES = _get_template_list()
                    xcodes = (4, 4) if self.inputs.space in STANDARD_SPACES \
                        else (2, 2)

                if curr_codes != xcodes or curr_units != units:
                    self._results['fixed_hdr'][i] = True
                    hdr.set_qform(nii.affine, xcodes[0])
                    hdr.set_sform(nii.affine, xcodes[1])
                    hdr.set_xyzt_units(*units)

                    # Rewrite file with new header
                    nii.__class__(np.array(nii.dataobj), nii.affine, hdr).to_filename(
                        out_file)

        if len(self._results['out_file']) == 1:
            meta_fields = self.inputs.copyable_trait_names()
            self._metadata.update({
                k: getattr(self.inputs, k)
                for k in meta_fields if k not in self._static_traits})
            if self._metadata:
                sidecar = (Path(self._results['out_file'][0]).parent /
                           ('%s.json' % _splitext(self._results['out_file'][0])[0]))
                sidecar.write_text(dumps(self._metadata, sort_keys=True, indent=2))
                self._results['out_meta'] = str(sidecar)
        return runtime
