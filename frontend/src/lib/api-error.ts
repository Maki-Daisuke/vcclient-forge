export type ApiErrorCode = 'network' | 'http' | 'invalid_response' | 'timeout';

export class ApiError extends Error {
  constructor(public code: ApiErrorCode, public status?: number) {
    super(code);
  }
}
