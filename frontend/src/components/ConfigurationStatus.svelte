<script lang="ts">
  import { useSession } from '../lib/session.svelte';
  import { useUi } from '../lib/ui.svelte';
  const session = useSession();
  const ui = useUi();
</script>

<div class="configuration-status" data-state={session.error ? 'error' : session.isSaving || session.dirty ? 'pending' : session.saved ? 'saved' : 'idle'}>
  {#if session.error}
    <p class="catalog-message" role="alert">
      {ui.t('forge.save_failed')} {ui.t(`forge.write_error_${session.error.code}`, { status: session.error.status })}
      {session.error.detail ?? ''}
    </p>
    <div class="button-row">
      <button class="button small" disabled={!!session.operation} onclick={() => session.retry()}>{ui.t('forge.retry_save')}</button>
      <button class="button small" disabled={!!session.operation} onclick={() => session.discard()}>{ui.t('forge.discard_changes')}</button>
    </div>
  {/if}
</div>
