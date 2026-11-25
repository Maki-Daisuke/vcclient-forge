export type ApiErrorCode =
  | 'network'
  | 'http'
  | 'invalid_response'
  | 'timeout'
  | 'not_applied'
  | 'active'
  | 'starting'
  | 'rebuild_required'
  | 'model_in_use'
  | 'model_not_found'
  | 'invalid_compute_device'
  | 'invalid_audio_device'
  | 'invalid_filter'
  | 'etag_mismatch'
  | 'session_start_failed'
  | 'recording_unavailable'
  | 'client_audio';

export class ApiError extends Error {
  constructor(
    public code: ApiErrorCode,
    public status?: number,
    public detail?: string,
    public backendCode?: string,
    public details?: Record<string, unknown>,
  ) {
    super(code);
  }
}
