import portraitUrl from '../../../web_front/ui/2.1.4/assets/icons/human.png';

// Display fixtures only. These are not backend settings or installed model slots.
export const preview = {
  portraitUrl,
  models: [
    { id: 'sample-1', slot: 1, name: 'RVC · Sample 01' },
    { id: 'sample-2', slot: 2, name: 'RVC · Sample 02' },
    { id: 'sample-3', slot: 3, name: 'RVC · Sample 03' },
  ],
  volume: [
    { key: 'input', label: 'common.controls.input_volume', value: 1 },
    { key: 'output', label: 'common.controls.output_volume', value: 1 },
    { key: 'monitor', label: 'common.controls.monitor_volume', value: 0 },
  ],
  voice: [
    { key: 'pitch', label: 'common.controls.pitch_adjust', value: 0, min: -24, max: 24, step: 1 },
    { key: 'formant', label: 'common.controls.formant_adjust', value: 0, min: -2, max: 2, step: 0.1 },
    { key: 'index', label: 'common.controls.index_adjust', value: 0, min: 0, max: 1, step: 0.01 },
  ],
} as const;
