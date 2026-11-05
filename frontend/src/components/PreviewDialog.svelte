<script lang="ts">
  import { Dialog } from 'bits-ui';
  import { X } from '@lucide/svelte';
  import type { Snippet } from 'svelte';
  import { useUi } from '../lib/ui.svelte';

  let { title, trigger, children, wide = false }: {
    title: string; trigger: Snippet; children: Snippet; wide?: boolean;
  } = $props();
  const ui = useUi();
</script>

<Dialog.Root>
  <Dialog.Trigger class="button">{@render trigger()}</Dialog.Trigger>
  <Dialog.Portal>
    <Dialog.Overlay class="dialog-overlay" />
    <Dialog.Content class={`dialog-content ${wide ? 'dialog-wide' : ''}`}>
      <header class="dialog-header">
        <Dialog.Title class="dialog-title">{title}</Dialog.Title>
        <Dialog.Close class="icon-button" aria-label={ui.t('forge.close')}><X size={20} /></Dialog.Close>
      </header>
      <Dialog.Description class="preview-notice">{ui.t('forge.preview_dialog')}</Dialog.Description>
      <div class="dialog-body">{@render children()}</div>
      <footer class="dialog-footer"><Dialog.Close class="button">{ui.t('forge.close')}</Dialog.Close></footer>
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
