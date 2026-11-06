export type ApiErrorCode = 'network' | 'http' | 'invalid_response' | 'timeout' | 'not_applied' | 'active' | 'invalid_filter';

export class ApiError extends Error {
  constructor(public code: ApiErrorCode, public status?: number, public detail?: string) {
    super(code);
  }
}
