export interface AudioDevice {
  id: number;
  name: string;
  host: string;
}

export interface AudioDevices {
  input: AudioDevice[];
  output: AudioDevice[];
}
