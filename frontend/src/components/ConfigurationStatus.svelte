<script lang="ts">
  import type { ApiError } from '../lib/api-error';
  import { useSession } from '../lib/session.svelte';
  import { useUi } from '../lib/ui.svelte';
  const session = useSession();
  const ui = useUi();

  function errorMessage(prefixKey: string, apiError: ApiError): string {
    const reason = ui.t(`forge.write_error_${apiError.code}`, { status: apiError.status });
    return apiError.detail ? `${ui.t(prefixKey)} ${reason} ${apiError.detail}` : `${ui.t(prefixKey)} ${reason}`;
  }
</script>

<div class="configuration-status" hidden={!session.error && !session.operationError && !session.recordingNotice} data-state={session.error || session.operationError ? 'error' : session.isSaving || session.dirty ? 'pending' : session.saved ? 'saved' : 'idle'}>
  {#if session.error}
    <p class="catalog-message" role="alert">{errorMessage('forge.save_failed', session.error)}</p>
    <div class="button-row">
      <button class="button small" disabled={!!session.operation} onclick={() => session.retry()}>{ui.t('forge.retry_save')}</button>
      <button class="button small" disabled={!!session.operation} onclick={() => session.discard()}>{ui.t('forge.discard_changes')}</button>
    </div>
  {/if}
  {#if session.operationError}
    <p class="catalog-message" role="alert">{errorMessage('forge.operation_failed', session.operationError)}</p>
    <button class="button small" onclick={() => session.operationError = null}>{ui.t('forge.close')}</button>
  {/if}
  {#if session.recordingNotice}
    <p class="catalog-message" role="status">{ui.t(`forge.recording_${session.recordingNotice}`)}</p>
    <button class="button small" onclick={() => session.recordingNotice = null}>{ui.t('forge.close')}</button>
  {/if}
</div>
