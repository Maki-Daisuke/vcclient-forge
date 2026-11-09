<script lang="ts">
  import { Dialog } from 'bits-ui';
  import { X } from '@lucide/svelte';
  import type { Snippet } from 'svelte';
  import { useUi } from '../lib/ui.svelte';

  let { title, trigger, children, footer, wide = false, disabled = false, showCloseButton = true, preventClose = false, description, open = $bindable(false) }: {
    title: string; trigger: Snippet; children: Snippet; footer?: Snippet; wide?: boolean; disabled?: boolean; showCloseButton?: boolean; preventClose?: boolean; description?: string; open?: boolean;
  } = $props();
  const ui = useUi();
</script>

<Dialog.Root bind:open>
  <Dialog.Trigger class="button" {disabled}>{@render trigger()}</Dialog.Trigger>
  <Dialog.Portal>
    <Dialog.Overlay class="dialog-overlay" />
    <Dialog.Content class={`dialog-content ${wide ? 'dialog-wide' : ''}`}
      onEscapeKeydown={(event) => { if (preventClose) event.preventDefault(); }}
      onInteractOutside={(event) => { if (preventClose) event.preventDefault(); }}>
      <header class="dialog-header">
        <Dialog.Title class="dialog-title">{title}</Dialog.Title>
        {#if showCloseButton}<Dialog.Close class="icon-button" aria-label={ui.t('forge.close')}><X size={20} /></Dialog.Close>{/if}
      </header>
      {#if description}<Dialog.Description class="preview-notice">{description}</Dialog.Description>{/if}
      <div class="dialog-body">{@render children()}</div>
      <footer class="dialog-footer">
        {#if footer}{@render footer()}{:else}<Dialog.Close class="button">{ui.t('forge.close')}</Dialog.Close>{/if}
      </footer>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
